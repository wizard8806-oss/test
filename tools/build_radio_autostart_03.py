#!/usr/bin/env python3
"""Build a disabled-by-default Windows startup package from unchanged radio02."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/radio-autostart-03'
SOURCE=ROOT/'artifacts/teleofis-radio-service-02/Run-Radio-Service-Collector-02.ps1'
SOURCE_SHA='89c5762599b6b43044d0688f98f5df4e0d80ac603a70d446ee131351607b0e82'
SHA=lambda b:hashlib.sha256(b).hexdigest()


def collector():
    raw=SOURCE.read_bytes()
    if SHA(raw)!=SOURCE_SHA:raise ValueError('Reviewed radio02 changed')
    text=raw.decode()
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Unexpected radio02 source anchor')
        text=text.replace(old,new,1)
    replace(text.splitlines()[0],'''param([string]$StationId='station-001',
 [Parameter(Mandatory=$true)][string]$ConfigPath,
 [Parameter(Mandatory=$true)][string]$CredentialPath,
 [string]$DiagnosticPath=(Join-Path $PSScriptRoot 'last-error.json'))
. (Join-Path $PSScriptRoot 'Radio-Autostart.Common.ps1')
$script:radioAutoExit=0''')
    replace("$svcCloudSecret=Read-Host ('M2M24 Service GROUP '+$svcGroup+' password (same as Service server Login settings)') -AsSecureString",
            "$svcCloudSecret=Read-RadioAutoSecret $CredentialPath 'Cloud'")
    replace("$svcModemSecret=Read-Host 'TELEOFIS MODEM settings password (same as successful USB test)' -AsSecureString",
            "$svcModemSecret=Read-RadioAutoSecret $CredentialPath 'Modem'")
    replace(" Write-Host ('Output: '+$svcFile+'. Keep this window open. Stop: Ctrl+C. Main50008 and USB are not used.')",
            " Write-Host ('RADIO AUTOSTART: '+$svcFile+'. Control through the Automatika-Radio-Service03 task; Main50008 and USB are not used.')")
    replace("}catch{Write-Host ('ERROR: Station configuration: '+$_.Exception.Message) -ForegroundColor Red;return}",
            "}catch{$script:radioAutoExit=1;Write-RadioAutoFailure $DiagnosticPath 'RADIOAUTO_CONFIG_FAILED' $_.Exception;return}")
    replace('  if($svcFatal){', '''  if($svcFatal){
   Write-RadioAutoFailure $DiagnosticPath $code $null''')
    replace(" Write-Host 'ERROR: Collector could not start or publish its local file. Check whether another collector is running and the data directory is writable.' -ForegroundColor Red", ''' $script:radioAutoExit=1
 $radioCode='RADIOAUTO_LOCAL_FAILURE'
 if($_.Exception.Message -match '^(COLLECTOR_LOCKED_OR_DIRECTORY_UNAVAILABLE|RADIOAUTO_[A-Z_]+)$'){$radioCode=$_.Exception.Message}
 Write-RadioAutoFailure $DiagnosticPath $radioCode $_.Exception''')
    # Protocol fatal exits remain zero, so Task Scheduler cannot restart a
    # session conflict. Ordinary network faults retain radio02's own backoff.
    return text+'\nexit $script:radioAutoExit\n'


def build(out=OUT):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    payload={'Run-Radio-Service-Collector-03.ps1':collector().encode(),
             'Radio-Autostart.Common.ps1':(ROOT/'tools/radio_autostart_common.ps1').read_bytes()}
    pins={name:SHA(data) for name,data in payload.items()}
    pin_literal='@{'+ ';'.join("'"+name+"'='"+digest+"'" for name,digest in sorted(pins.items()))+'}'
    manage=(ROOT/'tools/radio_autostart_manage_template.ps1').read_text().replace('__RADIOAUTOPINS__',pin_literal)
    payload['Manage-Radio-Autostart03.ps1']=manage.encode()
    for name,data in payload.items():(out/name).write_bytes(data)
    result=dict(schemaVersion=1,date='2026-11-03',sourceCollectorSHA256=SOURCE_SHA,
        files={name:SHA(data) for name,data in payload.items()},
        taskName='Automatika-Radio-Service03',taskRegisteredEnabled=False,
        installationRoot=r'%ProgramFiles%\AutomatikaRadioAutostart03',
        credentialScope='Windows DPAPI LocalMachine; SYSTEM/Admin ACL',
        stationCount=1,serviceGroup=9336,hardwareCommandsSent=0,
        windowsInstallObserved=False,bootObserved=False,publicationFailureResolved=False)
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PREPARED radio-autostart03; no installation or cloud connection performed')
    return result


if __name__=='__main__':build()
