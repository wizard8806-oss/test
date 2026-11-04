#!/usr/bin/env python3
"""Exercise current panel probes and copy guards with synthetic data only."""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import prepare_native_panel_probe as panel
from _runtime import ROOT, fpc, fpc_units
from build_native_operator_console_01 import native_navigation_grid_pages, repair_visual_page_style
from validate_native_operator_console_01 import STUB
from validate_native_ui_event_probe import fixture
from validate_process_display_01 import serialize_scripts
from validate_radio_install_01 import parse_scripts

PROBE = 'UIPANEL11-TEST0001'


def saved_card(root):
    tabs = root/'codex_diag_11_review_tabs_test0001'
    fixture(tabs)
    page_file = tabs/'Pages.spg'
    page_file.write_bytes(native_navigation_grid_pages(repair_visual_page_style(page_file.read_bytes(), True)))
    script_file = tabs/'Scripts/Scripts.ssc'
    script_file.write_bytes(panel.copy.pressure_display_scripts(script_file.read_bytes()))
    pins = panel.copy.inventory(tabs)
    overview = root/'codex_diag_11_review_overview_test0001'
    panel.copy.prepare_overview_panel(tabs, overview, pins['Pages.spg'], pins['Scripts/Scripts.ssc'])
    pins = panel.copy.inventory(overview)
    card = root/'codex_diag_11_review_station_card_test0001'
    panel.copy.prepare_station_card(overview, card, pins['Pages.spg'], pins['Scripts/Scripts.ssc'])
    return card


def rewrite(raw, target, change):
    rows = parse_scripts(raw)
    return serialize_scripts([(*row[:3], change(row[3])) if row[1] == target else row for row in rows])


def runtime(folder, records):
    module = records[7]['body']
    names = sorted(set(re.findall(r'\b(Ui\w+|ProcessTitle)\.Text', module)))
    stub = STUB.replace('__CONTROLS__', ','.join(names)).replace(
        'LastClient,LastName,Notice:string;Calls,GroupID:Integer;',
        'LastClient,LastName,Notice,Logs,ProbeClient:string;Calls,GroupID,GetterCalls:Integer;'
        'FailApi,FailLog:Boolean;FromTime,ToTime:Double;')
    stub = stub.replace('function GetClientName:string;',
        'procedure Log_Add(const Text:string;Timings:Boolean=True);\nfunction GetClientName:string;', 1)
    stub = stub.replace("function GetClientName:string;begin Result:='ClientA';end;", '''
procedure Log_Add(const Text:string;Timings:Boolean);
begin if FailLog then raise Exception.Create('synthetic logging error');Logs:=Logs+Text+LineEnding;end;
function GetClientName:string;begin Inc(GetterCalls);Result:=ProbeClient;end;''')
    for old, new in [
        ('procedure GoToMessagesGroupClient(Client:string;ID:Integer);begin LastClient:=Client;GroupID:=ID;Inc(Calls);end;',
         "procedure GoToMessagesGroupClient(Client:string;ID:Integer);begin if FailApi then raise Exception.Create('synthetic panel error');LastClient:=Client;GroupID:=ID;Inc(Calls);end;"),
        ('procedure GoToTrendsClient(Client:string;From_,To_:Double);begin LastClient:=Client;Inc(Calls);end;',
         "procedure GoToTrendsClient(Client:string;From_,To_:Double);begin if FailApi then raise Exception.Create('synthetic panel error');LastClient:=Client;FromTime:=From_;ToTime:=To_;Inc(Calls);end;")]:
        assert old in stub
        stub = stub.replace(old, new)
    (folder/'UiApi.pas').write_text(stub, encoding='utf8')
    (folder/'UiConsole.pas').write_text('unit UiConsole;\n{$mode objfpc}{$H+}{$codepage utf8}\n'+
        module.replace('interface', 'interface\nuses SysUtils,UiApi;', 1), encoding='utf8')
    callbacks = '\n'.join('procedure Click'+str(i)+';\n'+records[id_]['body'].rsplit('end.', 1)[0]+'end;'
                          for i, id_ in enumerate([32, 39]))
    harness = r'''program VerifyPanelProbe;
{$mode objfpc}{$H+}{$codepage utf8}
uses cwstring,SysUtils,UiApi,UiConsole;
var I,J,N,Mode,BeforeCalls:Integer;Raised:Boolean;EventName:string;
procedure Check(B:Boolean;const Why:string);
begin Inc(N);if not B then raise Exception.Create(Why);end;
__CALLBACKS__
procedure Click;
begin if Mode=0 then Click0 else Click1;end;
begin
 DefaultSystemCodePage:=65001;
 __INIT__
 for I:=0 to 1 do for J:=0 to 6 do V[I,J]:=TM_Variable.Create;
 V[0,5].OriginalAsInt:=400;Clock:=7200;
 OperatorUiUpdate;OperatorUiUpdate;
 Check(Logs='[UIPANEL11-TEST0001] BOOT'+LineEnding,'one module BOOT');
 for Mode:=0 to 1 do begin
  if Mode=0 then EventName:='UiMessages2_OnClick' else EventName:='UiTrendsAll1_OnClick';
  ProbeClient:='SYNTHETIC_PRIVATE_CLIENT';Logs:='';GetterCalls:=0;BeforeCalls:=Calls;Click;
  Check(GetterCalls=1,'caller resolved once');
  Check(Calls=BeforeCalls+1,'one native API invocation');
  Check(LastClient=ProbeClient,'only invoking client targeted');
  Check(Pos('ENTER '+EventName,Logs)>0,'specific entry marker');
  Check(Pos('CLIENT_PRESENT '+EventName,Logs)>0,'caller present');
  Check(Pos('AFTER_API '+EventName,Logs)>Pos('BEFORE_API '+EventName,Logs),'ordered API return');
  Check(Pos(ProbeClient,Logs)=0,'client name excluded from diagnostic log');
  if Mode=0 then Check(GroupID=-1,'documented all-messages group')
  else Check((Abs(FromTime-1/24.0)<0.00000001) and (Abs(ToTime-2/24.0)<0.00000001),'one-hour range preserved');
  ProbeClient:='';Logs:='';GetterCalls:=0;BeforeCalls:=Calls;Click;
  Check(GetterCalls=1,'empty caller resolved once');
  Check(Calls=BeforeCalls,'no request without caller');
  Check(Pos('CLIENT_EMPTY '+EventName,Logs)>0,'empty caller distinguishable');
  Check(Pos('BEFORE_API',Logs)=0,'empty caller exits before API');
  ProbeClient:='SYNTHETIC_PRIVATE_CLIENT';Logs:='';FailApi:=True;Raised:=False;
  try Click;except Raised:=True;end;
  Check(Raised,'native error remains observable by host');
  Check(Pos('BEFORE_API '+EventName,Logs)>0,'error localized before API return');
  Check(Pos('AFTER_API',Logs)=0,'exception is not a successful return');
  FailApi:=False;FailLog:=True;BeforeCalls:=Calls;Click;FailLog:=False;
  Check(Calls=BeforeCalls+1,'failed logging cannot break native navigation');
 end;
 Check(V[0,5].OriginalAsInt=400,'no setpoint write');
 WriteLn('PASS panel probe Pascal assertions=',N,'; synthetic APIs, not native dispatch');
end.
'''.replace('__CALLBACKS__', callbacks).replace('__INIT__', '\n'.join(n+':=TControl.Create;' for n in names))
    (folder/'VerifyPanelProbe.pas').write_text(harness, encoding='utf8')
    compiler = fpc()
    args = [str(compiler), '-gl', '-Cr', '-Co', '-Fu'+str(folder), '-FE'+str(folder), '-FU'+str(folder)]
    args += ['-Fu'+str(p) for p in fpc_units(compiler)]+[str(folder/'VerifyPanelProbe.pas')]
    result = subprocess.run(args, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout+result.stderr
    result = subprocess.run([str(folder/'VerifyPanelProbe')], text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout+result.stderr
    return result.stdout.strip()


def main():
    entry = subprocess.run([sys.executable, '-I', '-B', str(ROOT/'tools/prepare_native_panel_probe.py'), '--help'],
                           capture_output=True, text=True, timeout=20)
    assert entry.returncode == 0 and '--expected-scripts-sha' in entry.stdout, entry.stderr
    with tempfile.TemporaryDirectory(prefix='native-panel-probe-') as tmp:
        root = Path(tmp)
        source = saved_card(root)
        before = panel.copy.inventory(source)
        out = root/'codex_diag_11_panel_probe_test0001'
        args = [source, out, PROBE, before['Pages.spg'], before['Scripts/Scripts.ssc']]
        report = panel.prepare(*args)
        assert set(report['changedScripts']) == {'OperatorConsole', *panel.TARGETS}
        assert report['pagesUnchanged'] and report['sourceUnchanged']
        assert report['requiresBootBeforeInterpretingMissingEntry']
        assert report['hardwareCommands'] == 0 and not report['WindowsCompileObserved']
        assert panel.copy.inventory(source) == before
        for name, digest in before.items():
            if name in ('Scripts/Scripts.ssc', 'CodexProbeManifest.json') or name.startswith('Scripts/Compiled/'):
                continue
            assert panel.copy.SHA((out/name).read_bytes()) == digest, name
        assert not list((out/'Scripts/Compiled').iterdir())
        if os.name != 'nt':
            assert out.stat().st_mode & 0o077 == 0
        native = panel.copy.scripts((source/'Scripts/Scripts.ssc').read_bytes())
        patched = panel.copy.scripts((out/'Scripts/Scripts.ssc').read_bytes())
        for id_, row in native.items():
            assert row['meta'] == patched[id_]['meta'] and row['name'] == patched[id_]['name']
            if row['name'] not in report['changedScripts']:
                assert row == patched[id_]
        raw = (source/'Scripts/Scripts.ssc').read_bytes()
        for bad in [raw[:-1], raw+b'X', (out/'Scripts/Scripts.ssc').read_bytes(),
                    rewrite(raw, 'UiMessages2_OnClick', lambda lines: ['begin end.']),
                    rewrite(raw, 'OperatorConsole', lambda lines: [l.replace('KnownCount: Integer;', 'Other: Integer;') for l in lines])]:
            try: panel.patch_scripts(bad, PROBE)
            except ValueError: pass
            else: raise AssertionError('unknown or already instrumented scripts accepted')
        for change in [dict(out=out), dict(out=source/'codex_diag_11_panel_probe_nested0001'),
                       dict(out=root/'wrong_name'), dict(probe_id="unsafe'"), dict(pages_sha='0'*64),
                       dict(scripts_sha='0'*64), dict(project=root/'not_current_card')]:
            values = dict(project=source, out=root/'codex_diag_11_panel_probe_refusal0001',
                          probe_id=PROBE, pages_sha=before['Pages.spg'], scripts_sha=before['Scripts/Scripts.ssc'])
            values.update(change)
            try: panel.prepare(**values)
            except (ValueError, FileNotFoundError): pass
            else: raise AssertionError('invalid copy accepted: '+str(change))
        assert panel.copy.inventory(source) == before
        pascal = root/'pascal';pascal.mkdir()
        print(runtime(pascal, patched))
        print('PASS current R2 panel probe: three script bodies only, unchanged pages/resources/metadata, source pins, refusal cases and isolated CLI')


if __name__ == '__main__':
    main()
