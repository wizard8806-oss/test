#!/usr/bin/env python3
"""Unattended package tests; no real credentials, scheduler or network calls."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from _runtime import PWSH,ROOT
from build_radio_autostart_03 import build,SOURCE,SOURCE_SHA

CANARY='SYNTHETIC_RADIO_SECRET'
Q=lambda s:"'"+str(s).replace("'","''")+"'"


def ps(root,code,case=''):
    script=root/('run-'+str(len(list(root.glob('run-*.ps1'))))+'.ps1');script.write_text(code)
    env=dict(os.environ,XDG_CACHE_HOME=str(root/'cache'),XDG_CONFIG_HOME=str(root/'config'),
        XDG_DATA_HOME=str(root/'store'),RADIOAUTO_TEST_CASE=case)
    return subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(script)],
        text=True,capture_output=True,env=env,timeout=25)


def config(directory):
    result=json.loads((ROOT/'artifacts/teleofis-radio-service-01/stations.json').read_text())
    result['Groups'][0].update(Id='teleofis-service-9336',Login=9336)
    result['Stations'][0].update(GroupId='teleofis-service-9336',RadioDataDirectory=str(directory))
    return result


FAKE=r'''Add-Type -TypeDefinition @'
using System;
using System.IO;
public sealed class RadioServiceFailure01:Exception {
 public readonly int State;public readonly bool Fatal;
 public RadioServiceFailure01(string code,int state,bool fatal):base(code){State=state;Fatal=fatal;}
}
public sealed class TeleofisRadioService01:IDisposable {
 public TeleofisRadioService01(string imei){}
 public void Connect(string host,int port){}
 public void Login(long group,string secret){}
 public void Authenticate(byte[] secret){}
 public long[] ReadRadio(){
  if(Environment.GetEnvironmentVariable("RADIOAUTO_TEST_CASE")=="session_conflict")throw new RadioServiceFailure01("CLOUD_GROUP_ACCESS_REJECTED",4,false);
  File.WriteAllText(Environment.GetEnvironmentVariable("RADIOAUTO_TEST_STOP"),"");
  return new long[]{19,2,11761};
 }
 public void Dispose(){}
}
'@
'''


def main():
    before=hashlib.sha256(SOURCE.read_bytes()).hexdigest();assert before==SOURCE_SHA
    with tempfile.TemporaryDirectory(prefix='radio-autostart-') as temporary:
        root=Path(temporary);out=root/'package';result=build(out)
        source=SOURCE.read_text();runtime=(out/'Run-Radio-Service-Collector-03.ps1').read_text()
        transport=lambda t:re.search(r"-TypeDefinition @'\n(.*?)\n'@",t,re.S)[1]
        assert transport(source)==transport(runtime),'C# transport changed'
        assert 'Read-Host' not in runtime and '$svcLock=' in runtime
        assert 'exit $script:radioAutoExit' in runtime
        assert not result['windowsInstallObserved'] and not result['publicationFailureResolved']
        digest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
        build(out);assert digest=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
        paths=','.join(Q(out/name) for name in ('Run-Radio-Service-Collector-03.ps1','Radio-Autostart.Common.ps1','Manage-Radio-Autostart03.ps1'))
        parsed=ps(root,"$ErrorActionPreference='Stop'\nforeach($path in @("+paths+")){$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$t,[ref]$e);if($e.Count){throw ($e|Out-String)}}\nWrite-Host 'PASS package syntax'")
        assert parsed.returncode==0,parsed.stdout+parsed.stderr
        common=out/'Radio-Autostart.Common.ps1';valid=root/'valid.json';valid.write_text(json.dumps(config(root/'data')))
        xml_path=root/'task.xml'
        helpers=ps(root,"$ErrorActionPreference='Stop'\n. "+Q(common)+"\n$config=Get-RadioAutoConfig "+Q(valid)+" 'station-001'\n$xml=Get-RadioAutoTaskXml '/private folder/a&b' '/system/powershell.exe' 'station-001'\n[IO.File]::WriteAllText("+Q(xml_path)+",$xml)\nWrite-Host 'PASS config/XML'")
        assert helpers.returncode==0,helpers.stdout+helpers.stderr
        xml=ET.parse(xml_path);ns={'t':'http://schemas.microsoft.com/windows/2004/02/mit/task'}
        value=lambda p:xml.find('.//t:'+p.replace('/','/t:'),ns).text
        assert value('Settings/Enabled')=='false' and value('Settings/MultipleInstancesPolicy')=='IgnoreNew'
        assert value('Triggers/BootTrigger/Enabled')=='true' and value('Settings/ExecutionTimeLimit')=='PT0S'
        assert value('Principals/Principal/UserId')=='S-1-5-18'
        assert xml.find('.//t:LogonType',ns) is None, 'SYSTEM task must not use the unsupported XML value ServiceAccount'
        assert value('Settings/RestartOnFailure/Count')=='3'
        args=value('Actions/Exec/Arguments');assert '-NonInteractive' in args and '-WindowStyle Hidden' in args
        assert 'credentials.json' in args and CANARY not in args and '/private folder/a&b' in args
        refusal_count=0
        for case in ('wrong_group','second_station','unknown_secret','wrong_station'):
            data=config(root/'data')
            if case=='wrong_group':data['Groups'][0]['Login']=7058
            if case=='second_station':data['Stations'].append(dict(data['Stations'][0]))
            if case=='unknown_secret':data['Groups'][0]['Password']=CANARY
            path=root/(case+'.json');path.write_text(json.dumps(data))
            check=ps(root,"$ErrorActionPreference='Stop'\n. "+Q(common)+"\ntry{$null=Get-RadioAutoConfig "+Q(path)+" '"+('wrong' if case=='wrong_station' else 'station-001')+"';exit 4}catch{Write-Host 'REFUSED'}")
            assert check.returncode==0 and 'REFUSED' in check.stdout and CANARY not in check.stdout+check.stderr
            refusal_count+=1
        if os.name!='nt':
            guard=ps(root,'& '+Q(out/'Manage-Radio-Autostart03.ps1')+' -Mode Enable -PublicationVerified')
            assert guard.returncode!=0 and 'RADIOAUTO_WINDOWS_REQUIRED' in guard.stderr
            # A tampered helper must not be executed even to define functions.
            helper_original=common.read_bytes();common.write_text("throw 'UNTRUSTED_HELPER_EXECUTED'")
            corrupt=ps(root,'& '+Q(out/'Manage-Radio-Autostart03.ps1'))
            assert corrupt.returncode!=0 and 'RADIOAUTO_PACKAGE_HASH_MISMATCH' in corrupt.stderr
            assert 'UNTRUSTED_HELPER_EXECUTED' not in corrupt.stdout+corrupt.stderr
            common.write_bytes(helper_original)
            crypto=ps(root,'. '+Q(common)+"\ntry{$v=ConvertTo-SecureString 'synthetic' -AsPlainText -Force;$null=Protect-RadioAutoSecret $v;exit 4}catch{Write-Host 'REFUSED_WINDOWS_ONLY'}")
            assert crypto.returncode==0 and 'REFUSED_WINDOWS_ONLY' in crypto.stdout
        # Run the actual unattended script against a fake API type and a fake
        # credential boundary. The original C# transport is compared above.
        runtime_cases=[]
        for case in ('success_stop','publication_failure','lock_held','credential_failure','session_conflict','config_failure'):
            area=root/case;area.mkdir();directory=area/'data';directory.mkdir()
            path=area/'stations.json';path.write_text(json.dumps(config(directory)))
            if case=='config_failure':path.write_text('{invalid '+CANARY)
            (area/'collector.ps1').write_text(runtime)
            (area/'Radio-Autostart.Common.ps1').write_text(
                (ROOT/'tools/radio_autostart_common.ps1').read_text()+
                "\nfunction Read-RadioAutoSecret {param($Path,$Name) if($env:RADIOAUTO_TEST_CASE -eq 'credential_failure'){throw '"+CANARY+"'};ConvertTo-SecureString '"+CANARY+"' -AsPlainText -Force}\n")
            if case=='publication_failure':(directory/'radio.txt').mkdir()
            prefix=FAKE+"\n$env:RADIOAUTO_TEST_STOP="+Q(directory/'radio.stop')+'\n'
            if case=='lock_held':prefix+="$held=[IO.File]::Open("+Q(directory/'collector.lock')+",[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)\n"
            failure=area/'error.json'
            run=ps(area,prefix+'& '+Q(area/'collector.ps1')+' -ConfigPath '+Q(path)+' -CredentialPath '+Q(area/'fake-credentials')+' -DiagnosticPath '+Q(failure)+'\nexit $LASTEXITCODE\n',case)
            assert CANARY not in run.stdout+run.stderr,(case,'secret in output')
            if case=='success_stop':
                assert run.returncode==0,run.stdout+run.stderr
                rows=(directory/'radio.txt').read_text().splitlines()
                assert rows[:2]==['ARADIO1','SERVICE'] and rows[3]=='2' and rows[6:] == ['5','-1','-1','-1']
            elif case=='session_conflict':
                assert run.returncode==0,'Task Scheduler must not restart a protocol fatal'
                rows=(directory/'radio.txt').read_text().splitlines();assert rows[6]=='4'
                assert 'CLOUD_SESSION_REPLACED' in run.stdout and json.loads(failure.read_text())['Code']=='CLOUD_SESSION_REPLACED'
            else:
                assert run.returncode==1,(case,run.returncode,run.stdout,run.stderr)
                recorded=json.loads(failure.read_text());assert recorded['HResult'].startswith('0x')
                assert CANARY not in failure.read_text() and CANARY not in json.dumps(recorded)
                if case=='lock_held':assert recorded['Code']=='COLLECTOR_LOCKED_OR_DIRECTORY_UNAVAILABLE'
            assert not list(directory.glob('*.tmp')),case
            runtime_cases.append(case)
        assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==before
        print('PASS autostart03: deterministic build; syntax/XML; config refusals='+str(refusal_count)+
              '; fake runtime cases='+','.join(runtime_cases)+'; C# transport/radio02 unchanged')
        print('NOT TESTED: Windows ACL/DPAPI/SYSTEM/Task Scheduler/boot; actual radio publication failure remains unclassified')


if __name__=='__main__':main()
