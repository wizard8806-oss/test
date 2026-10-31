#!/usr/bin/env python3
"""Verify mode selection decoding, stale-data guards and reversible copy06."""
from _runtime import fpc as runtime_fpc, fpc_units as runtime_units
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from build_station_mode_display_01 import BASE, OUT, ROOT
from validate_drive_display_02 import fixture, powershell
from validate_process_display_01 import STUB, HARNESS, serialize_scripts
from validate_station_freshness_03 import FRESH_HARNESS
from validate_drive_display_02 import PWSH
from validate_radio_install_01 import hashes

MODE_CASES = r'''
 Fresh;V[12].Raw:=0;Tick(0,0);
 Check(Pos('РЕЖИМ: НЕТ ДАННЫХ',ProcessTitle.Text)>0,'first sample cannot announce STOP');
 Check(V[12].Reads=0,'no mode read before first counter change');
 Tick(1,1);
 Check(Pos('РЕЖИМ: СТОП',ProcessTitle.Text)>0,'confirmed live zero is STOP selector');
 Check(Pos('Режим: СТОП',ProcessMap.Text)>0,'mode shown on Diagnostics');
 Check(Pos('Состояние ПЧ показано отдельно',ProcessDetail.Text)>0,'selector STOP is not drive stop feedback');
 for I:=10 to 12 do begin
  V[12].Raw:=I;Tick(I-8,I);
  Check(Pos('РЕЖИМ: АВТО',ProcessTitle.Text)>0,'AUTO group');
 end;
 Check(Pos('Автоматическое управление разрешено',ProcessDetail.Text)>0,'AUTO12 is permit, not actual motor RUN');
 for I:=20 to 22 do begin
  V[12].Raw:=I;Tick(I-15,I);
  Check(Pos('РЕЖИМ: РУЧНОЙ',ProcessTitle.Text)>0,'MANUAL group');
 end;
 Check(Pos('выдана команда работы',ProcessDetail.Text)>0,'MANUAL22 is a command indication');
 V[12].Raw:=90;Tick(8,23);
 Check(Pos('ОШИБКА СЕЛЕКТОРА',ProcessTitle.Text)>0,'both selector signals are invalid, not STOP');
 V[12].Raw:=5;Tick(9,24);
 Check(Pos('НЕИЗВЕСТЕН (код 5)',ProcessTitle.Text)>0,'unrecognized code retained');
 V[12].Raw:=65535;Tick(10,25);
 Check(Pos('код 65535',ProcessTitle.Text)>0,'unsigned unknown word retained');
 Fresh;Tick(0,0);Tick(1,1);V[12].Good:=False;V[12].Reads:=0;Tick(2,2);
 Check(Pos('РЕЖИМ: НЕТ ДАННЫХ',ProcessTitle.Text)>0,'BAD quality cannot show last AUTO');
 Check(V[12].Reads=0,'BAD mode is not converted');
 V[12].Good:=True;Tick(3,3);
 Check(Pos('РЕЖИМ: АВТО',ProcessTitle.Text)>0,'mode quality recovery');
 Fresh;Present[12]:=False;Tick(0,0);Tick(1,1);
 Check(Pos('РЕЖИМ: НЕТ ДАННЫХ',ProcessTitle.Text)>0,'missing tag is not STOP');
 Check(ProcessPressure.Text='3.45 бар','missing mode does not erase independent process fields');
 for I:=0 to 4 do begin
  Fresh;
  case I of
   0:V[12].ComputerName:='OtherStation';
   1:V[12].OPCServerName:='OtherServer';
   2:V[12].Outer:=False;
   3:V[12].FailRead:=True;
   4:V[12].Address:='codex.OtherDevice.StationMode';
  end;
  Tick(0,0);Tick(1,1);
  Check(Pos('РЕЖИМ: НЕТ ДАННЫХ',ProcessTitle.Text)>0,'binding/read failure cannot announce a mode');
  if I<>3 then Check(V[12].Reads=0,'wrong binding is never converted');
 end;
 Fresh;V[12].Raw:=-1;Tick(0,0);Tick(1,1);
 Check(Pos('РЕЖИМ: НЕТ ДАННЫХ',ProcessTitle.Text)>0,'negative raw rejected');
 V[12].Raw:=65536;Tick(2,2);
 Check(Pos('РЕЖИМ: НЕТ ДАННЫХ',ProcessTitle.Text)>0,'over-word raw rejected');
 Fresh;Tick(0,0);Tick(1,1);
 for I:=2 to 16 do Tick(I,1);
 Check(Pos('РЕЖИМ: НЕТ ДАННЫХ',ProcessTitle.Text)>0,'frozenGOOD counter hides mode at15s');
 Check(Pos('Режим: НЕТ ДАННЫХ',ProcessMap.Text)>0,'Diagnostics also hides stale mode');
 Tick(17,2);Check(Pos('РЕЖИМ: АВТО',ProcessTitle.Text)>0,'mode restores after counter progress');
 Tick(40,3);Check(Pos('РЕЖИМ: НЕТ ДАННЫХ',ProcessTitle.Text)>0,'long timer pause hides mode');
 Tick(41,4);Check(Pos('РЕЖИМ: АВТО',ProcessTitle.Text)>0,'resume requires another counter sample');
 Fresh;V[0].Raw:=31;Tick(0,0);Tick(1,1);
 Check(V[12].Reads=0,'legacy map has no confirmed new-mode route');
 Fresh;V[0].Raw:=33;Tick(0,0);Tick(1,1);
 Check(V[12].Reads=0,'wrong map cannot provide mode');
 Fresh;V[2].Raw:=0;Tick(0,0);Tick(1,1);
 Check(Pos('РЕЖИМ: АВТО',ProcessTitle.Text)>0,'pressure validity does not redefine selected mode');
 Check(Pos('нет достоверного',ProcessStatus.Text)>0,'pressure warning retained');
 V[10].Raw:=20;Tick(2,2);
 Check(ProcessStatus.Color=RGB(165,50,50),'mode display preserves existing VFD fault priority');
 V[12].Raw:=0;V[8].Raw:=1;V[4].Raw:=437;V[5].Raw:=2;Tick(3,3);
 Check(Pos('РЕЖИМ: СТОП',ProcessTitle.Text)>0,'STOP is selected mode while drive can still rotate');
 Check(ProcessFrequency.Text='43.7 Гц','selected STOP does not fake zero drive frequency');
'''


def run(harness, clock=True):
    source = (OUT / 'scripts/StationDiagnostics.txt').read_text()
    assert not re.search(r'\bV\.(?:Value|As\w+|Active)\s*:=', source)
    assert 'AddMessage' not in source
    stub = STUB.replace('array[0..7]', 'array[0..12]').replace('for I:=0 to 7', 'for I:=0 to 12')
    stub = stub.replace('ProcessMap:TControl;', 'ProcessMap,ProcessTitle:TControl;')
    stub = stub.replace(' LookupFailure:Boolean;', ' TestSeconds:Double;\n LookupFailure:Boolean;')
    if clock:
        assert source.count('Now * 86400.0') == 1
        source = source.replace('Now * 86400.0', 'TestSeconds')
    controls = sorted(set(re.findall(r'\b(Process\w+)\.(?:Text|Color)\s*:=', source)))
    harness = harness.replace('__CONTROLS__', '\n'.join(n + ':=TControl.Create;' for n in controls))
    with tempfile.TemporaryDirectory(prefix='station-mode-') as t:
        folder = Path(t)
        (folder / 'ProcessStubs.pas').write_text(stub)
        (folder / 'ProcessCard.pas').write_text('unit ProcessCard;\n{$mode objfpc}{$H+}{$codepage utf8}\n' + source.replace('interface\n', 'interface\nuses SysUtils,ProcessStubs;\n', 1))
        (folder / 'check.pas').write_text(harness)
        compiler = runtime_fpc()
        args = [str(compiler), '-gl', '-Cr', '-Co', '-Fu' + str(folder), '-FU' + str(folder), '-FE' + str(folder)]
        args += ['-Fu' + str(d) for d in runtime_units(compiler) if d.is_dir()]
        p = subprocess.run(args + [str(folder / 'check.pas')], capture_output=True, text=True, timeout=25)
        assert p.returncode == 0, p.stdout + p.stderr
        p = subprocess.run([str(folder / 'check')], capture_output=True, text=True, timeout=10)
        assert p.returncode == 0, p.stdout + p.stderr
        return p.stdout.strip()


def fixture05(folder):
    records = fixture(folder)
    records[0] = (*records[0][:3], BASE.read_text().splitlines())
    (folder / 'Scripts/Scripts.ssc').write_bytes(serialize_scripts(records))
    return records


def parent_folder_cases():
    cases = []
    for case in ['project_parent_folder', 'folder_without_project']:
        with tempfile.TemporaryDirectory(prefix='mode-source-folder-') as temp:
            root = Path(temp)
            parent = root / 'Projects'
            source = parent / 'codex_diag_05'
            target = root / 'Desktop/codex_diag_06'
            target.parent.mkdir()
            fixture05(source)
            before = hashes(source)
            selected = parent if case == 'project_parent_folder' else root / 'No project here'
            selected.mkdir(exist_ok=True)
            quote = lambda s: "'" + str(s).replace("'", "''") + "'"
            code = (OUT / 'Install-Station-Mode-01.ps1').read_text()
            code = re.sub(r'^\$processTarget=.*$', lambda _: '$processTarget=' + quote(target), code, count=1, flags=re.M)
            code = re.sub(r'\$candidates=@\(.*?\n    \)', lambda _: '$candidates=@()', code, count=1, flags=re.S)
            code = 'function Read-Host {param([string]$Prompt) return ' + quote(selected) + '}\n' + code
            runner = root / 'run.ps1'
            runner.write_text(code)
            env = os.environ | {k: str(root / v) for k, v in [('XDG_CACHE_HOME', 'cache'), ('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data')]}
            p = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(runner)], env=env, capture_output=True, text=True, timeout=25)
            assert p.returncode == 0 and not p.stderr, (case, p.stdout, p.stderr)
            assert hashes(source) == before
            if case == 'project_parent_folder':
                assert 'SAVED:' in p.stdout and 'ERROR:' not in p.stdout, p.stdout
                assert (target / 'Project.spr').is_file()
            else:
                assert 'Choose the codex_diag_05 project folder' in p.stdout and not target.exists(), p.stdout
            cases.append(dict(case=case, passed=True))
            print('PASS copy', case, flush=True)
    return cases


def main():
    legacy = HARNESS.replace('Fresh;V[0].Raw:=32;StationProcessUpdate;UnknownPressure;', 'Fresh;V[0].Raw:=33;StationProcessUpdate;UnknownPressure;')
    reports = [run(legacy, False)]
    harness = FRESH_HARNESS.replace('array[0..11]', 'array[0..12]').replace("'PlcAliveCounter');", "'PlcAliveCounter','StationMode');")
    harness = harness.replace('7624,1792,3,0,0,0);', '7624,1792,3,0,0,0,10);')
    harness = harness.replace('for K:=0 to 11', 'for K:=0 to 12').replace('for I:=0 to 11', 'for I:=0 to 12')
    harness = harness.replace(" WriteLn('PASS freshness assertions=',N);", MODE_CASES + "\n WriteLn('PASS freshness and mode assertions=',N);")
    reports.append(run(harness))
    for report in reports:
        print(report, flush=True)
    copies = powershell(output=OUT, installer_name='Install-Station-Mode-01.ps1', target_name='codex_diag_06', fixture_factory=fixture05)
    copies += parent_folder_cases()
    used = set(re.findall(r'\b(Process\w+)\.(?:Text|Color)\s*:=', (OUT / 'scripts/StationDiagnostics.txt').read_text()))
    from _runtime import page_bindings
    bindings = page_bindings(ROOT, used)
    result = dict(date='2026-10-30', logicReports=reports, copyCases=copies, bindings=bindings,
                  referencedControls=len(used), nativeF9Observed=False, nativeModeDisplayObserved=False,
                  method='Actual generated Pascal under FPC with only clock/API seams; real PowerShell/Linux preservation cases; optional page-loader result recorded separately in bindings')
    (OUT / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('Mode display/copy checks passed; native Windows F9 and selector comparison remain pending.')


if __name__ == '__main__':
    main()
