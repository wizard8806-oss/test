#!/usr/bin/env python3
"""Verify actual Pascal feedback display and preservation of the Windows copy."""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from _runtime import fpc, fpc_units
from build_setpoint_display_01 import ROOT, BASE, OUT
from validate_process_display_01 import STUB, HARNESS, serialize_scripts
from validate_station_freshness_03 import FRESH_HARNESS
from validate_station_mode_display_01 import MODE_CASES
from validate_drive_display_02 import fixture, powershell, PWSH
from validate_radio_install_01 import hashes

FEEDBACK_CASES = r'''
 Fresh;V[19].Raw:=2;Tick(0,0);
 for I:=13 to 19 do Check(V[I].Reads=0,'no feedback conversion before live PLC route');
 Tick(1,1);
 Check(ProcessSetpointNote.Color<>RGB(40,140,90),'first tuple cannot confirm');
 Tick(1.5,1);
 Check(ProcessSetpointNote.Color<>RGB(40,140,90),'repeated OPC tuple needs another PLC counter');
 Tick(2,2);
 Check(ProcessSetpointNote.Text='Подтверждено ПЛК: ПЧ 1, 3.50 бар','coherent live feedback');
 Check(ProcessSetpoint.Text='3.50 бар','PLC mirror remains separate');
 Check(ProcessSetpointNote.Color=RGB(40,140,90),'verified status color');
 Check(Pos('не результат новой команды',ProcessScope.Text)>0,'not a request-ID acknowledgment');
 Check(Pos('уставка: прочитано 7 из 7',ProcessOPC.Text)>0,'seven feedback tags counted');
 V[3].Raw:=360;Tick(3,3);
 Check(ProcessSetpoint.Text='3.60 бар','new PLC input displayed');
 Check(ProcessSetpointNote.Color<>RGB(40,140,90),'old verified cache cannot confirm a changed target');
 Check(Pos('3.50',ProcessSetpointNote.Text)=0,'old cached value hidden');
 V[15].Raw:=360;Tick(4,4);
 Check(ProcessSetpointNote.Color<>RGB(40,140,90),'new matching cache starts a new sample');
 Tick(5,5);Check(Pos('3.60 бар',ProcessSetpointNote.Text)>0,'new matching setpoint confirmed');
 V[19].Raw:=0;Tick(6,6);
 Check(ProcessSetpointNote.Color<>RGB(40,140,90),'cleared M969 immediately removes old confirmation');
 Tick(7,7);Check(Pos('не получено',ProcessSetpointNote.Text)>0,'no flag is not success');
 Check(Pos('3.60',ProcessSetpointNote.Text)=0,'inactive cache does not look verified');

 for I:=13 to 19 do begin
  Fresh;V[19].Raw:=2;Tick(0,0);Tick(1,1);Tick(2,2);
  V[I].Good:=False;V[I].Reads:=0;Tick(3,3);
  Check(V[I].Reads=0,'BAD feedback is not converted');
  Check(ProcessSetpointNote.Color=RGB(105,105,105),'BAD feedback clears green');
  Check(Pos('3.50',ProcessSetpointNote.Text)=0,'BAD feedback clears cached numeric result');
  Check(ProcessPressure.Text='3.45 бар','missing feedback does not erase pressure');
  V[I].Good:=True;Tick(4,4);
  Check(ProcessSetpointNote.Color<>RGB(40,140,90),'quality recovery requires a new tuple pair');
  Tick(5,5);Check(ProcessSetpointNote.Color=RGB(40,140,90),'quality recovery confirmed');
  Present[I]:=False;Tick(6,6);
  Check(ProcessSetpointNote.Color=RGB(105,105,105),'missing tag hides feedback');
  Check(ProcessSetpoint.Text='3.50 бар','independent PLC setpoint mirror retained');
 end;
 for I:=13 to 19 do for J:=0 to 4 do begin
  Fresh;V[19].Raw:=2;
  case J of
   0:V[I].ComputerName:='OtherStation';
   1:V[I].OPCServerName:='OtherServer';
   2:V[I].Outer:=False;
   3:V[I].Address:='codex.OtherDevice.'+Items[I];
   4:V[I].FailRead:=True;
  end;
  Tick(0,0);Tick(1,1);Tick(2,2);
  Check(ProcessSetpointNote.Color<>RGB(40,140,90),'wrong binding/read failure cannot confirm');
  if J<>4 then Check(V[I].Reads=0,'foreign feedback is never converted');
 end;
 for I:=13 to 19 do for J:=0 to 1 do begin
  Fresh;V[19].Raw:=2;
  if J=0 then V[I].Raw:=-1 else V[I].Raw:=65536;
  Tick(0,0);Tick(1,1);Tick(2,2);
  Check(ProcessSetpointNote.Color<>RGB(40,140,90),'out-of-word feedback rejected');
 end;
 for I:=0 to 2 do begin
  Fresh;V[19].Raw:=2;
  case I of 0:V[13].Raw:=0;1:V[13].Raw:=2;2:V[13].Raw:=65535;end;
  Tick(0,0);Tick(1,1);Tick(2,2);
  Check(Pos('версия',ProcessSetpointNote.Text)>0,'unsupported version retained');
  for J:=14 to 19 do Check(V[J].Reads=0,'unknown contract stops payload conversion');
 end;
 for I:=0 to 1 do begin
  Fresh;V[19].Raw:=2;if I=0 then V[0].Raw:=31 else V[0].Raw:=33;
  Tick(0,0);Tick(1,1);Tick(2,2);
  for J:=13 to 19 do Check(V[J].Reads=0,'wrong PLC map does not consume feedback');
 end;
 Fresh;V[19].Raw:=2;V[3].Good:=False;Tick(0,0);Tick(1,1);Tick(2,2);
 Check(ProcessSetpointNote.Color<>RGB(40,140,90),'no working input cannot confirm');
 Fresh;V[19].Raw:=3;Tick(0,0);Tick(1,1);Tick(2,2);
 Check(Pos('Несогласованные',ProcessSetpointNote.Text)>0,'both M968 and M969 rejected');
 Check(ProcessSetpointNote.Color<>RGB(40,140,90),'contradictory flags never green');
 Fresh;V[19].Raw:=65534;Tick(0,0);Tick(1,1);Tick(2,2);
 Check(ProcessSetpointNote.Color=RGB(40,140,90),'uncontracted high flag bits not interpreted as errors');
 Fresh;V[19].Raw:=4;Tick(0,0);Tick(1,1);Tick(2,2);
 Check(Pos('не получено',ProcessSetpointNote.Text)>0,'high bit cannot replace M969');

 for I:=0 to 6 do begin
  Fresh;V[19].Raw:=2;
  case I of
   0:V[14].Raw:=0;
   1:V[14].Raw:=5;
   2:begin V[3].Raw:=0;V[15].Raw:=0;end;
   3:begin V[3].Raw:=9;V[15].Raw:=9;end;
   4:begin V[3].Raw:=1200;V[15].Raw:=1200;end;
   5:begin V[3].Raw:=351;V[15].Raw:=351;end;
   6:V[15].Raw:=0;
  end;
  Tick(0,0);Tick(1,1);Tick(2,2);
  Check(ProcessSetpointNote.Color<>RGB(40,140,90),'invalid drive or pressure cannot confirm');
 end;
 for I:=0 to 1 do begin
  Fresh;V[19].Raw:=2;
  if I=0 then V[3].Raw:=10 else V[3].Raw:=1190;
  V[15].Raw:=V[3].Raw;Tick(0,0);Tick(1,1);Tick(2,2);
  Check(ProcessSetpointNote.Color=RGB(40,140,90),'profile boundary accepted');
 end;
 for I:=1 to 4 do begin
  Fresh;V[19].Raw:=2;V[14].Raw:=I;Tick(0,0);Tick(1,1);Tick(2,2);
  Check(Pos('ПЧ '+IntToStr(I),ProcessSetpointNote.Text)>0,'all four leading-drive addresses supported');
 end;
 for I:=0 to 4 do begin
  Fresh;V[19].Raw:=2;
  case I of 0:V[16].Raw:=20;1:V[16].Raw:=30;2:V[16].Raw:=40;3:V[16].Raw:=90;4:V[16].Raw:=65535;end;
  Tick(0,0);Tick(1,1);Tick(2,2);
  Check(ProcessSetpointNote.Color<>RGB(40,140,90),'nonidle phase cannot finish confirmation');
  Check(Pos(IntToStr(V[16].Raw),ProcessSetpointNote.Text)>0,'raw phase remains visible');
 end;
 Fresh;V[19].Raw:=1;V[17].Raw:=27;V[18].Raw:=9;Tick(0,0);Tick(1,1);Tick(2,2);
 Check(Pos('ошибка применения',ProcessSetpointNote.Text)>0,'M968 identifies coordinator error');
 Check(Pos('27',ProcessSetpointNote.Text)>0,'raw coordinator code retained');
 Check(Pos('Подробность: 9',ProcessScope.Text)>0,'raw detail retained');
 Check(ProcessStatus.Color=RGB(165,50,50),'apply error prevents normal banner');
 Check(ProcessFault.Text='Код 0','apply error is not native VFD fault');
 V[10].Raw:=20;Tick(3,3);
 Check(ProcessFault.Text='Код 20','native VFD fault remains visible');
 Check(ProcessStatus.Text<>'ПЛК: ошибка применения уставки','native VFD fault keeps banner priority');
 V[19].Raw:=2;V[10].Raw:=0;Tick(4,4);Tick(5,5);
 Check(ProcessSetpointNote.Color=RGB(40,140,90),'stale error fields ignored without M968');
 Check(Pos('27',ProcessSetpointNote.Text)=0,'old error code does not appear as an active error');
 Fresh;V[19].Raw:=0;V[17].Raw:=65535;V[18].Raw:=65535;Tick(0,0);Tick(1,1);Tick(2,2);
 Check(ProcessSetpointNote.Color<>RGB(165,50,50),'nonzero diagnostic words alone are not active errors');

 Fresh;V[19].Raw:=2;V[2].Raw:=0;Tick(0,0);Tick(1,1);Tick(2,2);
 Check(ProcessSetpointNote.Color=RGB(40,140,90),'PLC-reported applied pressure distinct from sensor validity');
 Check(Pos('нет достоверного',ProcessStatus.Text)>0,'pressure warning remains');
 Fresh;V[19].Raw:=2;Tick(0,0);Tick(1,1);Tick(2,2);
 for I:=3 to 17 do Tick(I,2);
 Check(ProcessSetpointNote.Color<>RGB(40,140,90),'frozenGOOD hides confirmed feedback at15s');
 Check(Pos('3.50',ProcessSetpointNote.Text)=0,'freeze clears last verified cache');
 Tick(18,3);Check(ProcessSetpointNote.Color<>RGB(40,140,90),'counter recovery starts another pair');
 Tick(19,4);Check(ProcessSetpointNote.Color=RGB(40,140,90),'counter recovery pair confirmed');
 Tick(40,5);Check(ProcessSetpointNote.Color<>RGB(40,140,90),'timer pause hides feedback');
 Tick(41,6);Check(ProcessSetpointNote.Color<>RGB(40,140,90),'resumed route requires first tuple');
 Tick(42,7);Check(ProcessSetpointNote.Color=RGB(40,140,90),'resumed tuple pair confirmed');
 Fresh;V[19].Raw:=2;Tick(0,65534);Tick(1,65535);Tick(2,0);
 Check(ProcessSetpointNote.Color=RGB(40,140,90),'16bit heartbeat wrap accepted');
 Tick(3,300);Check(ProcessSetpointNote.Color<>RGB(40,140,90),'counter reset/jump invalidates tuple');
'''

EXTRA_ITEMS = "'StationMode','SpFeedbackVersion','SpConfirmedDrive','SpConfirmed_x100','SpApplyPhase','SpApplyError','SpApplyDetail','SpApplyFlags'"


def run(harness, clock=True):
    source = (OUT / 'scripts/StationDiagnostics.txt').read_text()
    assert not re.search(r'\bV\.(?:Value|As\w+|Active|OriginalAsInt)\s*:=', source)
    assert 'AddMessage' not in source and 'CL50S' not in source
    stub = STUB.replace('array[0..7]', 'array[0..19]').replace('for I:=0 to 7', 'for I:=0 to 19')
    stub = stub.replace('ProcessMap:TControl;', 'ProcessMap,ProcessTitle,ProcessSetpointLabel,ProcessSetpointNote,ProcessScope,ProcessMainScope:TControl;')
    stub = stub.replace(' LookupFailure:Boolean;', ' TestSeconds:Double;\n LookupFailure:Boolean;')
    if clock:
        assert source.count('Now * 86400.0') == 1
        source = source.replace('Now * 86400.0', 'TestSeconds')
    controls = sorted(set(re.findall(r'\b(Process\w+)\.(?:Text|Color)\s*:=', source)))
    known = {row['name'] for row in json.loads((ROOT / 'artifacts/station-process-display-01/manifest.json').read_text())['objects']}
    assert set(controls) <= known, set(controls) - known
    harness = harness.replace('__CONTROLS__', '\n'.join(n + ':=TControl.Create;' for n in controls))
    with tempfile.TemporaryDirectory(prefix='setpoint-display-') as name:
        p = Path(name)
        (p / 'ProcessStubs.pas').write_text(stub)
        (p / 'ProcessCard.pas').write_text('unit ProcessCard;\n{$mode objfpc}{$H+}{$codepage utf8}\n' + source.replace('interface\n', 'interface\nuses SysUtils,ProcessStubs;\n', 1))
        (p / 'check.pas').write_text(harness)
        compiler = fpc()
        command = [str(compiler), '-gl', '-Cr', '-Co', '-Fu' + str(p), '-FU' + str(p), '-FE' + str(p)]
        command += ['-Fu' + str(d) for d in fpc_units(compiler)]
        r = subprocess.run(command + [str(p / 'check.pas')], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stdout + r.stderr
        r = subprocess.run([str(p / 'check')], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout.strip()


def fixture06(folder):
    records = fixture(folder)
    # Git placeholders stand for empty Windows directories, not project content.
    for placeholder in folder.rglob('.gitkeep'):
        placeholder.unlink()
    records[0] = (*records[0][:3], BASE.read_text().splitlines())
    (folder / 'Scripts/Scripts.ssc').write_bytes(serialize_scripts(records))
    return records


def folder_cases():
    results = []
    for case in ['project_parent_folder', 'folder_without_project']:
        with tempfile.TemporaryDirectory(prefix='sp-copy-folder-') as name:
            p = Path(name)
            source = p / 'Projects/codex_diag_06'
            fixture06(source)
            before = hashes(source)
            selected = source.parent if case == 'project_parent_folder' else p / 'Empty folder'
            selected.mkdir(exist_ok=True)
            target = p / 'Desktop/codex_diag_07'
            target.parent.mkdir()
            quote = lambda value: "'" + str(value).replace("'", "''") + "'"
            code = (OUT / 'Install-Setpoint-Display-01.ps1').read_text()
            code = re.sub(r'^\$processTarget=.*$', lambda _: '$processTarget=' + quote(target), code, count=1, flags=re.M)
            code = re.sub(r'\$candidates=@\(.*?\n    \)', lambda _: '$candidates=@()', code, count=1, flags=re.S)
            code = 'function Read-Host {param([string]$Prompt) return ' + quote(selected) + '}\n' + code
            runner = p / 'run.ps1'; runner.write_text(code)
            env = dict(os.environ, XDG_CACHE_HOME=str(p/'cache'), XDG_CONFIG_HOME=str(p/'config'), XDG_DATA_HOME=str(p/'data'))
            r = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(runner)], env=env, capture_output=True, text=True, timeout=25)
            assert r.returncode == 0 and not r.stderr, (case, r.stdout, r.stderr)
            assert hashes(source) == before
            if case == 'project_parent_folder':
                assert 'SAVED:' in r.stdout and 'ERROR:' not in r.stdout and (target/'Project.spr').is_file()
            else:
                assert 'Choose the codex_diag_06' in r.stdout and not target.exists()
            results.append(dict(case=case, passed=True))
    return results


def main():
    legacy = HARNESS.replace('Fresh;V[0].Raw:=32;StationProcessUpdate;UnknownPressure;', 'Fresh;V[0].Raw:=33;StationProcessUpdate;UnknownPressure;')
    legacy = legacy.replace('array[0..7]', 'array[0..19]').replace('for K:=0 to 7', 'for K:=0 to 19').replace('for I:=0 to 7 do V[I]:=', 'for I:=0 to 19 do V[I]:=')
    legacy = legacy.replace("'AlarmLo','AlarmHi');", "'AlarmLo','AlarmHi','Vfd1NativeState','Vfd1CurrentRaw','Vfd1FaultCode','PlcAliveCounter'," + EXTRA_ITEMS + ');')
    legacy = legacy.replace('0,1,7624,8960);', '0,1,7624,8960,3,0,0,0,10,1,1,350,0,0,0,0);')
    reports = [run(legacy, False)]
    harness = FRESH_HARNESS.replace('array[0..11]', 'array[0..19]').replace('for K:=0 to 11', 'for K:=0 to 19').replace('for I:=0 to 11', 'for I:=0 to 19')
    harness = harness.replace("'PlcAliveCounter');", "'PlcAliveCounter'," + EXTRA_ITEMS + ');')
    harness = harness.replace('7624,1792,3,0,0,0);', '7624,1792,3,0,0,0,10,1,1,350,0,0,0,0);')
    harness = harness.replace('var I,N,S,A:Integer;', 'var I,J,N,S,A:Integer;')
    harness = harness.replace(" WriteLn('PASS freshness assertions=',N);", MODE_CASES + FEEDBACK_CASES + "\n WriteLn('PASS freshness/mode/setpoint assertions=',N);")
    reports.append(run(harness))
    for report in reports:
        print(report, flush=True)
    copies = powershell(output=OUT, installer_name='Install-Setpoint-Display-01.ps1', target_name='codex_diag_07', fixture_factory=fixture06)
    copies += folder_cases()
    result = dict(date='2026-10-31', logicReports=reports, copyCases=copies,
                  nativeWindowsF9Observed=False, nativeNewFeedbackDisplayObserved=False,
                  method='Actual generated Pascal under strict FPC stubs; deterministic clock; PowerShell copy/preservation on Linux; all referenced existing control names checked',
                  liveWritesPerformed=False, PLCOrHMIChanged=False)
    (OUT / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('Setpoint feedback logic and ten copy/preservation cases passed.')


if __name__ == '__main__':
    main()
