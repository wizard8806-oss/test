#!/usr/bin/env python3
"""Exercise the Windows bootstrap against mocks and a real existing Linux Python.

No downloaded EXE is executed. Signature/network/installer/Windows platform
boundaries are mocked explicitly; runtime probes use a real x64 interpreter.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _runtime import PWSH, ROOT

HARNESS=r'''
param([string]$Setup,[string]$FixtureDirectory,[string]$ActualPython,[string]$ActualVersion,[string]$Mode)
$ErrorActionPreference='Stop'
. $Setup
$official=Get-ProjectPythonPackage
if($official.version -ne '3.13.17' -or $official.sha256 -ne '5da012101ba2e17113a9a1cd901e9ce1441086f2b7ecb5de06ec94163899a190'){throw 'Unexpected official package pin'}
$realRuntime=Read-ProjectPythonRuntime $ActualPython
Assert-ProjectPythonRuntime $realRuntime $ActualPython

$script:root=Join-Path $FixtureDirectory 'Local AppData'
$script:target=Join-Path $script:root 'Programs/Python/Python313'
$script:cache=Join-Path $script:root 'CodexDownloads/ProjectPython'
$null=[IO.Directory]::CreateDirectory($script:root)
$script:fixtureBytes=[Text.Encoding]::UTF8.GetBytes('SYNTHETIC installer fixture; never executed')
$h=[Security.Cryptography.SHA256]::Create()
try{$script:fixtureSHA=([BitConverter]::ToString($h.ComputeHash($script:fixtureBytes))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}
$script:starts=0;$script:downloads=0;$script:mode=$Mode;$script:pythonSource=$ActualPython
$script:version=$ActualVersion
function Get-ProjectPythonLocalRoot{return $script:root}
function Get-ProjectPythonPackage{
 return [pscustomobject]@{schemaVersion=1;version=$script:version;architecture='amd64';scope='current-user';targetFolder='Python313';fileName='python-fixture-amd64.exe';url='https://www.python.org/fixture-never-requested';publisher='Python Software Foundation';sha256=$script:fixtureSHA}
}
if($Mode -ne 'platform_refused'){function Assert-ProjectPythonPlatform{}}
function Get-AuthenticodeSignature{
 param([string]$LiteralPath)
 $status='Valid';$publisher='Python Software Foundation'
 if($script:mode -eq 'invalid_signature'){$status='HashMismatch'}
 if($script:mode -eq 'wrong_publisher'){$publisher='Another Publisher'}
 return [pscustomobject]@{Status=$status;SignerCertificate=[pscustomobject]@{Subject=('CN='+$publisher+', O='+$publisher+', C=US')}}
}
function Invoke-WebRequest{
 param([switch]$UseBasicParsing,[string]$Uri,[string]$OutFile)
 $script:downloads++
 if($Uri -ne 'https://www.python.org/fixture-never-requested'){throw 'Unexpected download URL'}
 if($script:mode -eq 'download_failure'){throw 'Synthetic network failure'}
 $b=$script:fixtureBytes
 if($script:mode -eq 'wrong_hash'){$b=[Text.Encoding]::UTF8.GetBytes('CORRUPTED fixture')}
 [IO.File]::WriteAllBytes($OutFile,$b)
}
function Start-Process{
 param([string]$FilePath,[string[]]$ArgumentList,[string]$WindowStyle,[switch]$Wait,[switch]$PassThru)
 $script:starts++
 if($script:starts -ne 1){throw 'Automatic installer retry detected'}
 if($FilePath -ne (Join-Path $script:cache 'python-fixture-amd64.exe') -or $WindowStyle -ne 'Hidden' -or -not $Wait -or -not $PassThru){throw 'Unexpected process invocation'}
 foreach($required in @('/quiet','InstallAllUsers=0','PrependPath=0','AssociateFiles=0','Include_launcher=0','InstallLauncherAllUsers=0','Include_pip=0','Include_test=0')){
  if($ArgumentList -notcontains $required){throw ('Missing scope flag '+$required)}
 }
 if($ArgumentList -notcontains ('TargetDir="'+$script:target+'"')){throw 'Target path with spaces was not quoted'}
 if($script:mode -eq 'installer_failure'){return [pscustomobject]@{ExitCode=1603}}
 $null=[IO.Directory]::CreateDirectory($script:target)
 if($script:mode -ne 'runtime_missing'){
  $null=New-Item -ItemType SymbolicLink -Path (Join-Path $script:target 'python.exe') -Target $script:pythonSource
 }
 $exit=0;if($script:mode -eq 'restart_code'){$exit=3010}
 return [pscustomobject]@{ExitCode=$exit}
}
if($Mode -in @('runtime_wrong_version','runtime_wrong_arch','runtime_wrong_path','runtime_prerelease','existing_incompatible')){
 function Read-ProjectPythonRuntime{
  param([string]$PythonPath)
  $v=@(3,13,17);$bits=64;$release='final';$exe=$PythonPath
  if($script:mode -eq 'runtime_wrong_version'){$v=@(3,11,0)}
  if($script:mode -in @('runtime_wrong_arch','existing_incompatible')){$bits=32}
  if($script:mode -eq 'runtime_wrong_path'){$exe=$script:pythonSource}
  if($script:mode -eq 'runtime_prerelease'){$release='candidate'}
  return [pscustomobject]@{version=$v;bits=$bits;release=$release;executable=$exe}
 }
}
if($Mode -in @('reuse','existing_incompatible')){
 $null=[IO.Directory]::CreateDirectory($script:target)
 $null=New-Item -ItemType SymbolicLink -Path (Join-Path $script:target 'python.exe') -Target $ActualPython
}
if($Mode -eq 'existing_directory'){
 $null=[IO.Directory]::CreateDirectory($script:target);[IO.File]::WriteAllText((Join-Path $script:target 'keep'),'preserve')
}
if($Mode -in @('cached','bad_cache')){
 $null=[IO.Directory]::CreateDirectory($script:cache)
 $b=$script:fixtureBytes;if($Mode -eq 'bad_cache'){$b=[Text.Encoding]::UTF8.GetBytes('PRESERVE bad cached fixture')}
 [IO.File]::WriteAllBytes((Join-Path $script:cache 'python-fixture-amd64.exe'),$b)
}
$targetArg=$script:target;$cacheArg=$script:cache
if($Mode -eq 'outside_user_root'){$targetArg=Join-Path $FixtureDirectory 'outside'}
if($Mode -eq 'nested_cache'){$cacheArg=Join-Path $script:target 'cache'}
$protocol=[Net.ServicePointManager]::SecurityProtocol
$success=$Mode -in @('normal','cached','reuse','restart_code')
try{
 $result=Install-ProjectPython -TargetDirectory $targetArg -CacheDirectory $cacheArg
 if(-not $success){throw 'UNEXPECTED_SUCCESS'}
 if($result.version -ne $ActualVersion -or $result.pathChangeRequested -ne $false){throw 'Bad runtime result'}
 if($Mode -eq 'reuse'){
  if(-not $result.reused -or $script:starts -ne 0 -or $script:downloads -ne 0){throw 'Existing compatible runtime was modified'}
 }else{
  if(-not $result.installed -or $script:starts -ne 1){throw 'Expected exactly one install'}
  if($Mode -eq 'cached' -and $script:downloads -ne 0){throw 'Verified cache downloaded again'}
 }
 if($Mode -eq 'restart_code' -and -not $result.restartSuggested){throw 'Restart code lost'}
}catch{
 if($success -or $_.Exception.Message -eq 'UNEXPECTED_SUCCESS'){throw}
 $afterStart=$Mode -in @('installer_failure','runtime_missing','runtime_wrong_version','runtime_wrong_arch','runtime_wrong_path','runtime_prerelease')
 if($script:starts -ne [int]$afterStart){throw ('Unexpected install count: '+$Mode+' '+$script:starts)}
}
if([Net.ServicePointManager]::SecurityProtocol -ne $protocol){throw 'TLS preference was not restored'}
if(@(Get-ChildItem -LiteralPath $script:root -File -Recurse -Filter '*.part-*').Count -ne 0){throw 'Partial download not cleaned'}
if($Mode -eq 'existing_directory' -and [IO.File]::ReadAllText((Join-Path $script:target 'keep')) -ne 'preserve'){throw 'Existing directory changed'}
Write-Host ('PASS '+$Mode)
'''


def main():
    modes=['normal','cached','reuse','restart_code','platform_refused','outside_user_root',
           'nested_cache','existing_directory','existing_incompatible','bad_cache',
           'wrong_hash','invalid_signature','wrong_publisher','download_failure','installer_failure',
           'runtime_missing','runtime_wrong_version','runtime_wrong_arch','runtime_wrong_path','runtime_prerelease']
    script=ROOT/'tools/Install-ProjectPython.ps1'
    assert script.read_bytes().isascii(), 'Keep PS5.1 source ASCII; labels/package are UTF8 resources'
    spec=json.loads((ROOT/'tools/python-windows-package.json').read_text())
    assert spec['sha256']=='5da012101ba2e17113a9a1cd901e9ce1441086f2b7ecb5de06ec94163899a190'
    actual='.'.join(map(str,sys.version_info[:3]));results=[]
    with tempfile.TemporaryDirectory(prefix='project-python-bootstrap-') as tmp:
        folder=Path(tmp);harness=folder/'verify.ps1';harness.write_text(HARNESS)
        for mode in modes:
            case=folder/mode;case.mkdir()
            env=dict(os.environ,XDG_CACHE_HOME=str(folder/'pscache'),XDG_CONFIG_HOME=str(folder/'psconfig'),XDG_DATA_HOME=str(folder/'psdata'))
            command=[PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(harness),'-Setup',str(script),'-FixtureDirectory',str(case),'-ActualPython',sys.executable,'-ActualVersion',actual,'-Mode',mode]
            p=subprocess.run(command,env=env,text=True,capture_output=True,timeout=30)
            assert p.returncode==0 and not p.stderr,(mode,p.stdout,p.stderr)
            assert 'PASS '+mode in p.stdout,p.stdout
            results.append(dict(case=mode,passed=True))
    print(json.dumps(dict(passed=True,cases=results,realRuntimeProbe=actual,
        windowsInstallerExecuted=False,networkAndSignatureBoundariesMocked=True),indent=2))


if __name__=='__main__':main()
