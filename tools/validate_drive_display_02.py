#!/usr/bin/env python3
"""Behavior and copy-preservation tests; never claim native F9 or PLC testing."""
from _runtime import fpc as runtime_fpc, fpc_units as runtime_units
from _runtime import PWSH as PWSH_RUNTIME
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from build_drive_display_02 import BASE, OUT, ROOT, sha
from build_radio_display_01 import bootstrap
from validate_process_display_01 import HARNESS, STUB, fixture_source, serialize_scripts
from validate_radio_install_01 import hashes, parse_scripts

PWSH = PWSH_RUNTIME

EXTRA = r'''
 Fresh;StationProcessUpdate;
 for I:=8 to 10 do Check(V[I].Reads=0,'map31 never reads new drive payload');
 Fresh;V[0].Raw:=32;StationProcessUpdate;
 Check(ProcessCurrent.Text='0.0 А','map32 zero current is a valid value');
 Check(ProcessFault.Text='Код 0','zero is displayed as native code, not blanket station health');
 Check(Pos('32',ProcessMap.Text)>0,'map32 displayed');
 Check(Pos('состояния 3',ProcessFrequencyNote.Text)>0,'native stop state');
 Check(Pos('из 3',ProcessOPC.Text)>0,'three new item diagnostic');
 Fresh;V[0].Raw:=32;V[4].Raw:=437;V[5].Raw:=2;V[8].Raw:=1;V[9].Raw:=47;V[10].Raw:=20;
 StationProcessUpdate;
 Check(ProcessCurrent.Text='4.7 А','native current scale is0.1A');
 Check(ProcessFault.Text='Код 20','actual raw code retained');
 Check(Pos('Обрыв',ProcessFaultNote.Text)+Pos('обрыв',ProcessFaultNote.Text)>0,'900G fault20 text');
 Check(ProcessStatus.Color=RGB(165,50,50),'native fault takes precedence over pressure warning');
 V[10].Raw:=52;StationProcessUpdate;Check(Pos('нехватка воды',ProcessFaultNote.Text)>0,'native fault52');
 V[10].Raw:=53;StationProcessUpdate;Check(Pos('избыточное давление',ProcessFaultNote.Text)>0,'native fault53');
 V[10].Raw:=65535;StationProcessUpdate;
 Check(ProcessFault.Text='Код 65535','unknown raw code is not silently normalized');
 Check(Pos('неизвестна',ProcessFaultNote.Text)>0,'unknown model-specific code remains unknown');
 V[10].Good:=False;StationProcessUpdate;
 Check(ProcessFault.Text='Нет данных','BAD code quality hides last nonzero code');
 Check(ProcessFault.Color=RGB(105,105,105),'stale red color is cleared');
 Check(ProcessCurrent.Text='4.7 А','bad fault item does not erase independent valid current');
 for I:=8 to 10 do begin
  Fresh;V[0].Raw:=32;V[I].Good:=False;StationProcessUpdate;
  Check(V[I].Reads=0,'BAD new item is never read');
  if (I=8)or(I=9) then Check(ProcessCurrent.Text='Нет данных','missing state/current hides amperes');
  if (I=8)or(I=10) then Check(ProcessFault.Text='Нет данных','missing state/code hides fault number');
 end;
 for I:=8 to 10 do begin
  Fresh;V[0].Raw:=32;Present[I]:=False;StationProcessUpdate;
  if (I=8)or(I=9) then Check(ProcessCurrent.Text='Нет данных','absent state/current is not zero');
  if (I=8)or(I=10) then Check(ProcessFault.Text='Нет данных','absent state/code is not code0');
 end;
 for I:=8 to 10 do begin
  Fresh;V[0].Raw:=32;V[I].ComputerName:='OtherStationHost';StationProcessUpdate;
  Check(V[I].Reads=0,'wrong host does not provide a drive payload');
 end;
 for J:=0 to 2 do begin
  Fresh;V[0].Raw:=32;
  case J of 0:V[8].Raw:=0;1:V[8].Raw:=4;2:V[8].Raw:=99;end;
  StationProcessUpdate;
  Check(ProcessCurrent.Text='Нет данных','unknown native state hides amperes');
  Check(ProcessFault.Text='Нет данных','unknown native state hides fault number');
 end;
 for J:=0 to 3 do begin
  Fresh;V[0].Raw:=32;
  case J of
   0:V[5].Raw:=0;
   1:begin V[5].Raw:=1;V[4].Raw:=1;end;
   2:begin V[5].Raw:=2;V[4].Raw:=0;end;
   3:begin V[5].Raw:=2;V[4].Raw:=6000;end;
  end;
  StationProcessUpdate;
  Check(ProcessCurrent.Text='Нет данных','invalid frequency state hides new current');
  Check(ProcessFault.Text='Нет данных','invalid frequency state hides new fault');
 end;
 Fresh;V[0].Raw:=32;V[9].Raw:=65536;StationProcessUpdate;
 Check(ProcessCurrent.Text='Нет данных','out-of-word-range current rejected');
 Fresh;V[0].Raw:=32;V[10].Raw:=-1;StationProcessUpdate;
 Check(ProcessFault.Text='Нет данных','negative native code rejected');
 Fresh;V[0].Raw:=33;StationProcessUpdate;
 for I:=1 to 10 do Check(V[I].Reads=0,'unknown interface version blocks all payloads');
 Fresh;V[0].Raw:=32;StationProcessUpdate;
 for I:=1 to 100 do StationProcessUpdate;
 Check(ProcessCurrent.Text='0.0 А','constant zero current is not a freeze alarm');
 Check(Pos('не подтверждается',ProcessFreshness.Text)>0,'full-route freshness remains explicitly unconfirmed');
'''


def pascal():
    source = (OUT / 'scripts/StationDiagnostics.txt').read_text()
    assert 'CL50S' not in source and 'AddMessage' not in source
    assert not re.search(r'\bV\.(?:Value|As\w+|Active)\s*:=', source)
    stub = STUB.replace('array[0..7]', 'array[0..10]').replace('for I:=0 to 7', 'for I:=0 to 10')
    harness = HARNESS.replace('Items:array[0..7]', 'Items:array[0..10]')
    harness = harness.replace("'Vfd1FreqRaw','Vfd1FreqState','AlarmLo','AlarmHi');", "'Vfd1FreqRaw','Vfd1FreqState','AlarmLo','AlarmHi','Vfd1NativeState','Vfd1CurrentRaw','Vfd1FaultCode');")
    harness = harness.replace('Values:array[0..7]', 'Values:array[0..10]').replace('(31,0,0,350,0,1,7624,8960);', '(31,0,0,350,0,1,7624,8960,3,0,0);')
    harness = harness.replace('for K:=0 to 7', 'for K:=0 to 10').replace('for I:=0 to 7 do V[I]:=', 'for I:=0 to 10 do V[I]:=')
    harness = harness.replace('Fresh;V[0].Raw:=32;StationProcessUpdate;UnknownPressure;', 'Fresh;V[0].Raw:=33;StationProcessUpdate;UnknownPressure;')
    harness = harness.replace(" WriteLn('PASS process-card assertions=',N);", EXTRA + "\n WriteLn('PASS process-card assertions=',N);")
    controls = sorted(set(re.findall(r'\b(Process\w+)\.(?:Text|Color)\s*:=', source)))
    harness = harness.replace('__CONTROLS__', '\n'.join(n + ':=TControl.Create;' for n in controls))
    with tempfile.TemporaryDirectory(prefix='drive-logic-') as t:
        p = Path(t)
        (p / 'ProcessStubs.pas').write_text(stub)
        module = 'unit ProcessCard;\n{$mode objfpc}{$H+}{$codepage utf8}\n' + source.replace('interface\n', 'interface\nuses SysUtils,ProcessStubs;\n', 1)
        (p / 'ProcessCard.pas').write_text(module)
        (p / 'check.pas').write_text(harness)
        compiler = runtime_fpc()
        args = [str(compiler), '-gl', '-Cr', '-Co', '-Fu' + str(p), '-FU' + str(p), '-FE' + str(p)]
        args += ['-Fu' + str(d) for d in runtime_units(compiler) if d.is_dir()]
        result = subprocess.run(args + [str(p / 'check.pas')], capture_output=True, text=True, timeout=25)
        assert result.returncode == 0, result.stdout + result.stderr
        result = subprocess.run([str(p / 'check')], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout.strip()


def fixture(folder):
    records = fixture_source(folder)
    records[0] = (*records[0][:3], BASE.read_text().splitlines())
    records[2] = (*records[2][:3], ['begin', '  StationProcessUpdate;', '  StationRadioUpdate;', 'end.'])
    (folder / 'Scripts/Scripts.ssc').write_bytes(serialize_scripts(records))
    (folder / 'Pages.spg').write_bytes((ROOT / 'artifacts/station-process-display-01/Pages.spg').read_bytes())
    return records


def powershell(output=OUT, installer_name='Install-Drive-Display-02.ps1',
               target_name='codex_diag_04', fixture_factory=fixture):
    installer = (output / installer_name).read_text()
    cases = []
    for case in ['normal', 'unit_header_carets', 'changed_radio', 'changed_core', 'wrong_timer', 'destination_exists', 'wrong_version', 'corrupt_module']:
        with tempfile.TemporaryDirectory(prefix='drive-copy-') as t:
            p = Path(t)
            src = p / 'Current source'; dst = p / ('Desktop/' + target_name); dst.parent.mkdir()
            records = fixture_factory(src)
            if case == 'unit_header_carets':
                records = [(uid, name, meta[:9] + bytes.fromhex('070000000c000000'), ['unit '+name+';'] + lines if name != 'StationDiagnosticsTimer' else lines)
                           for uid, name, meta, lines in records]
            if case == 'changed_radio':
                row = records[1]
                records[1] = (*row[:3], [s.replace('RadioPublishedUnix', 'RadioPublishedSeconds') for s in row[3]])
            if case == 'changed_core':
                row = records[0]; records[0] = (*row[:3], row[3] + ['// user custom source'])
            if case == 'wrong_timer':
                row = records[2]; records[2] = (*row[:3], ['begin', '  DifferentUpdate;', 'end.'])
            (src / 'Scripts/Scripts.ssc').write_bytes(serialize_scripts(records))
            if case == 'destination_exists':
                dst.mkdir(); (dst / 'Keep.txt').write_text('preserve existing destination')
            if case == 'wrong_version':
                data = bytearray((src / 'Project.spr').read_bytes()); data[12:14] = b'\x10\x00'; (src / 'Project.spr').write_bytes(data)
            before = hashes(src); prior = hashes(dst) if dst.exists() else None
            code = re.sub(r'^\$processTarget=.*$', lambda _: "$processTarget='"+str(dst)+"'", installer, count=1, flags=re.M)
            code = re.sub(r'\$candidates=@\(.*?\n    \)', lambda _: "$candidates=@('"+str(src)+"')", code, count=1, flags=re.S)
            if case == 'corrupt_module':
                packed = re.search(r"\$driveModuleGzip='([^']+)'", code)[1]
                code = code.replace(packed, 'AAAA' + packed[4:], 1)
            runner = p / 'run.ps1'; runner.write_text(bootstrap(code))
            env = os.environ | {k: str(p / v) for k, v in [('XDG_CACHE_HOME', 'cache'), ('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data')]}
            result = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(runner)], env=env, capture_output=True, text=True, timeout=25)
            assert result.returncode == 0 and not result.stderr, (case, result.stdout, result.stderr)
            assert hashes(src) == before, (case, 'source altered')
            assert not list(dst.parent.glob('*.stage-*')), (case, 'stage left behind')
            if case in ('normal', 'unit_header_carets', 'changed_radio'):
                assert 'SAVED:' in result.stdout and 'ERROR:' not in result.stdout, (case, result.stdout)
                parsed = parse_scripts((dst / 'Scripts/Scripts.ssc').read_bytes())
                assert parsed[0][3] == (output / 'scripts/StationDiagnostics.txt').read_text().splitlines()
                assert parsed[1:] == records[1:]
                for record in records[1:]:
                    one_record = serialize_scripts([record])[8+4+3+4+4:]
                    assert (src / 'Scripts/Scripts.ssc').read_bytes().count(one_record) == 1
                    assert (dst / 'Scripts/Scripts.ssc').read_bytes().count(one_record) == 1
                for relative, digest in before.items():
                    if relative == 'Scripts/Scripts.ssc' or relative.startswith('Scripts/Compiled/'):
                        continue
                    assert sha((dst / relative).read_bytes()) == digest, (case, relative)
                assert not list((dst / 'Scripts/Compiled').iterdir())
            else:
                assert 'ERROR:' in result.stdout and 'SAVED:' not in result.stdout, (case, result.stdout)
                assert hashes(dst) == prior if prior is not None else not dst.exists()
            cases.append(dict(case=case, passed=True))
            print('PASS copy', case, flush=True)
    return cases


def bindings():
    from _runtime import page_bindings
    source = (OUT / 'scripts/StationDiagnostics.txt').read_text()
    used = set(re.findall(r'\b(Process\w+)\.(?:Text|Color)\s*:=', source))
    return page_bindings(ROOT, used)



def main():
    logic = pascal(); print(logic, flush=True)
    report = dict(date='2026-10-30', logic=logic, copyCases=powershell(), bindings=bindings(),
                  nativeWindowsF9Observed=False, liveCurrentOrFaultReadObserved=False,
                  sourceAndRadioPreserved=True)
    (OUT / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Drive display verification passed; native Windows/F9 and PLC tests remain separate.')


if __name__ == '__main__':
    main()
