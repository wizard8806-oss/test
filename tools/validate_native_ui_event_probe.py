#!/usr/bin/env python3
"""Probe-copy preservation/refusal cases and isolated diagnostic Pascal branches."""
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import prepare_native_ui_event_probe as probe
from _runtime import ROOT, PWSH, fpc, fpc_units
from audit_native_ui_navigation import scripts
from build_native_operator_console_01 import Builder, catalog
from validate_native_operator_console_01 import STUB
from validate_process_display_01 import serialize_scripts
from validate_radio_install_01 import parse_scripts

PROBE_ID = 'UINAV11-TEST0001'


def fixture(path):
    b = Builder(catalog(ROOT/'ui/native-console/catalog.json')).build()
    rows = parse_scripts((ROOT/'source/scada-native-08/Scripts.ssc').read_bytes())
    by_name = {r[1]: r for r in rows}
    rows.append((7, 'OperatorConsole', by_name['StationDiagnostics'][2],
                 ('unit OperatorConsole;\n'+b.module).splitlines()))
    for event in b.events:
        rows.append((event['id'], event['name'], by_name['ProcessSpPlus_OnClick'][2],
                     ('unit '+event['name']+';\n'+event['body']).splitlines()))
    (path/'Scripts/Compiled').mkdir(parents=True)
    (path/'Pages.spg').write_bytes(b.pages)
    (path/'Scripts/Scripts.ssc').write_bytes(serialize_scripts(rows))
    (path/'Scripts/Compiled/program.exs').write_bytes(b'old cache must not execute')
    (path/'Project.spr').write_bytes(bytes(8)+struct.pack('<4H',2,6,15,0))
    for name in ['Windows.swn', 'Trends.str', 'Variables.svr', 'Servers.ssr']:
        (path/name).write_bytes(b'SYNTHETIC_PRIVATE_RESOURCE_KEEP_IDENTICAL_'+name.encode())
    return b


def runtime(folder, module, event):
    names = sorted(set(re.findall(r'\b(Ui\w+|ProcessTitle)\.Text',module)) | {'UiOverview0Heading'})
    stub = STUB.replace('__CONTROLS__', ','.join(names))
    stub = stub.replace('LastClient,LastName,Notice:string;', 'LastClient,LastName,Notice,ProbeClient,Logs:string;RaiseNavigation:Boolean;')
    stub = stub.replace('function GetClientName:string;',
                        'procedure Log_Add(const Text:string;ATimings:Boolean=True);\nfunction GetClientName:string;',1)
    stub = stub.replace("function GetClientName:string;begin Result:='ClientA';end;",
                        "procedure Log_Add(const Text:string;ATimings:Boolean);begin Logs:=Logs+Text+LineEnding;end;\n"
                        "function GetClientName:string;begin Result:=ProbeClient;end;")
    stub = stub.replace('begin LastClient:=Client;Inc(Calls);end;',
                        "begin if RaiseNavigation then raise Exception.Create('synthetic');LastClient:=Client;Inc(Calls);end;",1)
    (folder/'UiApi.pas').write_text(stub,encoding='utf8')
    (folder/'UiConsole.pas').write_text('unit UiConsole;\n{$mode objfpc}{$H+}{$codepage utf8}\n'+
        module.replace('interface','interface\nuses SysUtils,UiApi;',1),encoding='utf8')
    body = '''program VerifyProbe;
{$mode objfpc}{$H+}{$codepage utf8}
uses cwstring,SysUtils,UiApi,UiConsole;
var I,J,C,N:Integer;
procedure Check(B:Boolean;const Why:string);
begin Inc(N);if not B then raise Exception.Create(Why);end;
procedure Click;
__EVENT__
begin
 DefaultSystemCodePage:=65001;
 __INIT__
 for I:=0 to 1 do for J:=0 to 6 do V[I,J]:=TM_Variable.Create;
 ProbeClient:='SYNTHETIC_PRIVATE_CLIENT';P:=TM_Page.Create;
 OperatorUiUpdate;OperatorUiUpdate;
 Check(Logs='[UINAV11-TEST0001] BOOT'+LineEnding,'one BOOT per module instance');
 Logs:='';C:=Calls;Click;
 Check(Pos('ENTER UiOverview0Nav1',Logs)>0,'entry logged');
 Check(Pos('CLIENT_PRESENT',Logs)>0,'caller availability logged');
 Check(Pos('AFTER_HELPER',Logs)>0,'successful return logged');
 Check(Calls=C+1,'one navigation request');
 Check(Pos(ProbeClient,Logs)=0,'client name never logged');
 Check(UiOverview0Heading.Text='UI probe: handler entered','dedicated UI label');
 ProbeClient:='';Logs:='';C:=Calls;Click;
 Check(Pos('CLIENT_EMPTY',Logs)>0,'missing caller is distinguishable');
 Check(Calls=C,'missing caller cannot navigate');
 ProbeClient:='SYNTHETIC_PRIVATE_CLIENT';P:=nil;Logs:='';Click;
 Check(Pos('TARGET_MISSING',Logs)>0,'missing target is distinguishable');
 Check(Pos('BEFORE_HELPER',Logs)=0,'missing target stops before helper');
 P:=TM_Page.Create;RaiseNavigation:=True;Logs:='';Click;
 Check(Pos('EXCEPTION',Logs)>0,'untyped except records navigation error');
 Check(Pos('AFTER_HELPER',Logs)=0,'error is not success');
 WriteLn('PASS probe Pascal assertions=',N,'; API stubs, not Windows dispatch');
end.
'''.replace('__EVENT__',event.rsplit('end.',1)[0]+'end;').replace(
        '__INIT__','\n'.join(name+':=TControl.Create;' for name in names))
    (folder/'VerifyProbe.pas').write_text(body,encoding='utf8')
    compiler = fpc()
    args = [str(compiler),'-gl','-Cr','-Co','-Fu'+str(folder),'-FE'+str(folder),'-FU'+str(folder)]
    args += ['-Fu'+str(p) for p in fpc_units(compiler)]+[str(folder/'VerifyProbe.pas')]
    compiled = subprocess.run(args,capture_output=True,text=True,timeout=60)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    ran = subprocess.run([str(folder/'VerifyProbe')],capture_output=True,text=True,timeout=20)
    assert ran.returncode==0,ran.stdout+ran.stderr
    return ran.stdout.strip()


def main():
    entry = subprocess.run([sys.executable, '-I', '-B', str(ROOT/'tools/prepare_native_ui_event_probe.py'), '--help'],
                           text=True, capture_output=True, timeout=20)
    assert entry.returncode==0 and '--probe-id' in entry.stdout,entry.stderr
    cases = ['normal','existing','nested','git_destination','edited_pages','edited_scripts',
             'wrong_version','invalid_id','unexpected_event','unexpected_module','privacy_failure','source_changed']
    if os.name != 'nt': cases.append('symlink')
    with tempfile.TemporaryDirectory(prefix='native-event-probe-') as temporary:
        root=Path(temporary)
        module=event=None
        original_pins,original_privacy,original_inventory=probe.PINS,probe._private_directory,probe.inventory
        try:
            for case in cases:
                area=root/case;source=area/'source';fixture(source)
                out=area/'codex_diag_11_probe_test0001'
                probe.PINS={name:probe.SHA((source/name).read_bytes()) for name in original_pins}
                if case=='existing':out.mkdir();(out/'keep').write_text('preserve')
                if case=='nested':out=source/'codex_diag_11_probe_test0001'
                if case=='git_destination':
                    (area/'.git').mkdir();(area/'.git/HEAD').write_text('ref: refs/heads/synthetic\n')
                if case in ['edited_pages','edited_scripts']:
                    path=source/('Pages.spg' if case=='edited_pages' else 'Scripts/Scripts.ssc')
                    path.write_bytes(path.read_bytes()+b'changed')
                if case=='wrong_version':(source/'Project.spr').write_bytes(bytes(16))
                if case in ['unexpected_event','unexpected_module']:
                    path=source/'Scripts/Scripts.ssc';records=parse_scripts(path.read_bytes())
                    name='UiOverview0Nav1_OnClick' if case=='unexpected_event' else 'OperatorConsole'
                    i=next(i for i,r in enumerate(records) if r[1]==name);row=records[i]
                    if case=='unexpected_event':lines=['begin end.']
                    else:lines=[line.replace('var Index: Integer;', 'var Other: Integer;') for line in row[3]]
                    records[i]=(*row[:3],lines);path.write_bytes(serialize_scripts(records))
                    probe.PINS['Scripts/Scripts.ssc']=probe.SHA(path.read_bytes())
                if case=='symlink':(source/'alias').symlink_to(source/'Variables.svr')
                before=original_inventory(source) if case!='symlink' else None
                existing=original_inventory(out) if out.exists() else None
                if case=='privacy_failure':
                    def fail_private(path):raise ValueError('synthetic ACL failure')
                    probe._private_directory=fail_private
                if case=='source_changed':
                    calls=0
                    def changed_inventory(path):
                        nonlocal calls
                        value=original_inventory(path)
                        if path==source:
                            calls+=1
                            if calls>1:value['Variables.svr']='synthetic changed hash'
                        return value
                    probe.inventory=changed_inventory
                try:
                    result=probe.prepare(source,out,'unsafe\' id' if case=='invalid_id' else PROBE_ID)
                except ValueError:
                    assert case!='normal',case
                    if existing is not None:assert original_inventory(out)==existing
                    else:assert not out.exists(),case
                else:
                    assert case=='normal',case
                    updated=scripts((out/'Scripts/Scripts.ssc').read_bytes())
                    original=scripts((source/'Scripts/Scripts.ssc').read_bytes())
                    changed=[r['name'] for i,r in updated.items() if r!=original[i]]
                    assert set(changed)==set(result['changedScripts'])
                    assert not list((out/'Scripts/Compiled').iterdir())
                    assert result['sourceUnchanged'] and not result['unsavedEditorModelIncluded']
                    assert not result['runtimeBootObserved'] and not result['WindowsCompileObserved']
                    for name,value in before.items():
                        if name not in ['Scripts/Scripts.ssc','Scripts/Compiled/program.exs']:
                            assert probe.SHA((out/name).read_bytes())==value
                    module=updated[7]['body'];event=updated[19]['body']
                    if os.name!='nt':assert stat_mode(out)==0o700
                finally:
                    probe._private_directory=original_privacy;probe.inventory=original_inventory
                if before is not None:assert original_inventory(source)==before,case
                assert not list(area.glob('.event-probe-*')),case
            runtime_dir=root/'pascal';runtime_dir.mkdir()
            print(runtime(runtime_dir,module,event))
            (root/'acl-source.ps1').write_text(probe.ACL_SCRIPT,encoding='utf8')
            (root/'parse-acl.ps1').write_text("$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'acl-source.ps1'),[ref]$t,[ref]$e);if($e.Count){throw 'ACL syntax'};Write-Host 'PASS ACL PowerShell syntax only'",encoding='utf8')
            env=dict(os.environ,XDG_CACHE_HOME=str(root/'cache'),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'))
            parsed=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(root/'parse-acl.ps1')],env=env,text=True,capture_output=True,timeout=30)
            assert parsed.returncode==0,parsed.stdout+parsed.stderr
            print(parsed.stdout.strip())
        finally:
            probe.PINS=original_pins;probe._private_directory=original_privacy;probe.inventory=original_inventory
    print('PASS private event-probe copy cases='+str(len(cases))+' '+','.join(cases)+'; native GUI/Windows ACL not executed')
    print('PASS isolated Python -I -B entry point')


def stat_mode(path):return path.stat().st_mode & 0o777


if __name__=='__main__':main()
