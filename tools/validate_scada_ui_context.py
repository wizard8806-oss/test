#!/usr/bin/env python3
"""Parse/compile the read-only context probe; never call Win32 on Linux."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from _runtime import ROOT, PWSH


def main():
    path=ROOT/'tools/Get-ScadaUiContext.ps1'
    text=path.read_text(encoding='utf8')
    blocks=re.findall(r"\$interopSource=@'\n(.*?)\n'@",text,re.S)
    assert len(blocks)==1
    imports=set(re.findall(r'extern\s+[\w?]+\s+(\w+)\(',blocks[0]))
    expected={'EnumWindows','GetWindowThreadProcessId','IsWindowVisible','GetWindowText',
              'GetClassName','GetClientRect','GetDpiForWindow','GetForegroundWindow',
              'GetProcessWindowStation','GetThreadDesktop','GetCurrentThreadId',
              'WTSGetActiveConsoleSessionId','GetUserObjectInformation','OpenProcess',
              'OpenProcessToken','GetTokenInformation','CloseHandle'}
    assert imports==expected,imports
    assert not re.search(r'\b(?:SetForegroundWindow|SendInput|SendMessage|ShowWindow|CreateProcess|WriteProcessMemory|ActivateInstance|CreateInstance)\b',text)
    with tempfile.TemporaryDirectory(prefix='scada-ui-context-') as temporary:
        folder=Path(temporary)
        (folder/'interop.cs').write_text(blocks[0],encoding='utf8')
        (folder/'check.ps1').write_text('''$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
[void][System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'PowerShell syntax failed'}
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'interop.cs')))
if(-not ('CodexScadaUiContextV1' -as [type])){throw 'Interop did not compile'}
Write-Host 'PASS PowerShell syntax and CSharp interop compile only'
''',encoding='utf8')
        env=dict(os.environ,XDG_CACHE_HOME=str(folder/'cache'),XDG_CONFIG_HOME=str(folder/'config'),XDG_DATA_HOME=str(folder/'data'))
        compiled=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(folder/'check.ps1'),str(path)],
                                env=env,text=True,capture_output=True,timeout=60)
        assert compiled.returncode==0,compiled.stdout+compiled.stderr
        print(compiled.stdout.strip())
        if os.name!='nt':
            out=folder/'context.json'
            args=[PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(path),'-OutPath',str(out)]
            ran=subprocess.run(args,env=env,text=True,capture_output=True,timeout=30)
            assert ran.returncode==0,ran.stderr
            result=json.loads(out.read_text())
            assert result['status']=='unsupported-platform' and result['platformSupported'] is False
            assert result['windows']==[] and result['opcObjectsCreated']==result['windowActionsInvoked']==result['equipmentCommands']==0
            assert result['fullWindowTitlesExported'] is False
            before=hashlib.sha256(out.read_bytes()).hexdigest()
            retry=subprocess.run(args,env=env,text=True,capture_output=True,timeout=30)
            assert retry.returncode!=0 and hashlib.sha256(out.read_bytes()).hexdigest()==before
            print('PASS unsupported-platform result and existing-report preservation')
    print('PASS getter/enumeration Win32 allowlist='+str(len(imports))+'; Windows session/window/token/registry calls NOT executed')


if __name__=='__main__':main()
