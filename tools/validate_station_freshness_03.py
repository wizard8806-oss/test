#!/usr/bin/env python3
"""General PLC freshness state-machine/UI tests and copy preservation."""
from _runtime import fpc as runtime_fpc, fpc_units as runtime_units
import json
import re
import subprocess
import tempfile
from pathlib import Path

from build_station_freshness_03 import BASE, OUT, ROOT
from validate_drive_display_02 import fixture, powershell
from validate_process_display_01 import HARNESS, STUB, serialize_scripts


FRESH_HARNESS = r'''program CheckFreshness;
{$mode objfpc}{$H+}{$codepage utf8}
uses cwstring,SysUtils,ProcessStubs,ProcessCard;
const Items:array[0..11]of string=('MapVersion','PressurePV_x100','PressureSourceOK',
 'PressureSP_x100','Vfd1FreqRaw','Vfd1FreqState','AlarmLo','AlarmHi',
 'Vfd1NativeState','Vfd1CurrentRaw','Vfd1FaultCode','PlcAliveCounter');
 Values:array[0..11]of Int64=(32,345,1,350,0,1,7624,1792,3,0,0,0);
var I,N,S,A:Integer;
procedure Check(B:Boolean;const Why:string);
begin Inc(N);if not B then raise Exception.Create(IntToStr(N)+' '+Why);end;
procedure Fresh;
var K:Integer;
begin
 RouteFreshReset;LookupFailure:=False;TestSeconds:=0;
 for K:=0 to 11 do begin
  Present[K]:=True;V[K].Good:=True;V[K].Outer:=True;V[K].FailRead:=False;
  V[K].Address:='codex.Device1.'+Items[K];V[K].OPCServerName:='InSAT.ModbusOPCServer.DA';
  V[K].ComputerName:='localhost';V[K].Raw:=Values[K];V[K].Reads:=0;
 end;
end;
procedure Tick(T:Double;C:Int64);
begin TestSeconds:=T;V[11].Raw:=C;StationProcessUpdate;end;
procedure Hidden;
begin
 Check(ProcessPressure.Text='Нет достоверных данных','no stale pressure');
 Check(ProcessSetpoint.Text='Нет данных','no stale setpoint echo');
 Check(ProcessFrequency.Text='Нет данных','no stale frequency');
 Check(ProcessCurrent.Text='Нет данных','no stale zero amperes');
 Check(ProcessFault.Text='Нет данных','no stale code0 or fault code');
 Check(ProcessFault.Color=RGB(105,105,105),'no stale fault color');
end;
procedure Live;
begin
 Check(ProcessFreshness.Color=RGB(40,140,90),'counter progress confirms route');
 Check(ProcessPressure.Text='3.45 бар','live pressure retained');
 Check(ProcessFrequency.Text='0.0 Гц','constant stopped frequency is valid');
 Check(ProcessCurrent.Text='0.0 А','live zero current retained');
 Check(ProcessFault.Text='Код 0','live zero code retained');
end;
begin
 DefaultSystemCodePage:=65001;DefaultFormatSettings.DecimalSeparator:='.';N:=0;
 for I:=0 to 11 do V[I]:=TM_Variable.Create;
 __CONTROLS__
 Fresh;Tick(0,0);Hidden;
 Check(Pos('первого изменения',ProcessFreshness.Text)>0,'first sample is not progress');
 Tick(1,0);Hidden;
 Tick(2,1);Live;
 for I:=3 to 16 do begin Tick(I,1);Live;end;
 Tick(17,1);Hidden;
 Check(ProcessFreshness.Color=RGB(165,50,50),'15s frozenGOOD is expired');
 Check(Pos('15 с',ProcessFreshness.Text)>0,'timeout reason visible');
 Tick(18,2);Live;
 V[11].Good:=False;V[11].Reads:=0;Tick(19,3);Hidden;
 Check(V[11].Reads=0,'BAD heartbeat never converted');
 V[11].Good:=True;Tick(20,3);Hidden;
 Tick(21,4);Live;
 Tick(5,5);Hidden;
 Check(Pos('паузы',ProcessFreshness.Text)>0,'clock rollback resets confirmation');
 Tick(6,6);Live;
 Tick(30,7);Hidden;
 Tick(31,8);Live;
 Fresh;Tick(0,65534);Hidden;Tick(1,65535);Live;Tick(2,0);Live;Tick(3,1);Live;
 Fresh;Tick(0,32767);Tick(1,32768);Live;
 Fresh;Tick(0,1000);Tick(1,1001);Live;Tick(2,0);Hidden;
 Check(Pos('скачком',ProcessFreshness.Text)>0,'counter reset requires a new increment');
 Tick(3,1);Live;
 Fresh;Tick(0,0);Tick(1,500);Hidden;Tick(2,501);Live;
 Fresh;Present[11]:=False;Tick(0,0);Hidden;
 Fresh;V[11].ComputerName:='OtherHost';Tick(0,0);Hidden;
 Check(V[11].Reads=0,'wrong station cannot supply heartbeat');
 Fresh;Tick(0,0);Tick(1,1);Live;
 V[10].Raw:=20;Tick(2,2);Check(ProcessFault.Text='Код 20','live native fault retained');
 Check(ProcessStatus.Color=RGB(165,50,50),'native fault has its own red status');
 for I:=3 to 17 do Tick(I,2);
 Hidden;
 V[10].Raw:=0;Tick(18,3);Live;
 V[2].Raw:=0;Tick(19,4);
 Check(ProcessPressure.Text='Нет достоверных данных','route progress does not validate the pressure sensor');
 Check(ProcessCurrent.Text='0.0 А','pressure flag does not erase independent fresh drive fields');
 Check(ProcessFreshness.Color=RGB(40,140,90),'route still progresses without a valid pressure source');
 Fresh;Tick(0,0);Tick(1,1);V[5].Raw:=0;Tick(2,2);
 Check(ProcessCurrent.Text='Нет данных','PLC heartbeat does not replace per-drive validity');
 Check(ProcessFault.Text='Нет данных','PLC heartbeat does not invent a drive fault result');
 RouteFreshReset;RouteFreshStep(True,-1,0,S,A);Check(S=3,'negative counter rejected');
 RouteFreshStep(True,65536,1,S,A);Check(S=3,'counter over65535 rejected');
 RouteFreshStep(False,0,2,S,A);Check((S=2)and(A=-1),'missing quality resets core');
 RouteFreshStep(True,0,3,S,A);Check(S=5,'recovery begins with a baseline');
 RouteFreshStep(True,1,4,S,A);Check(S=1,'recovery requires a later increment');
 WriteLn('PASS freshness assertions=',N);
end.
'''


def run_harness(harness, inject_clock):
    source = (OUT / 'scripts/StationDiagnostics.txt').read_text()
    assert not re.search(r'\bV\.(?:Value|As\w+|Active)\s*:=', source)
    assert 'CL50S' not in source and 'AddMessage' not in source
    stub = STUB.replace('array[0..7]', 'array[0..11]').replace('for I:=0 to 7', 'for I:=0 to 11')
    stub = stub.replace(' LookupFailure:Boolean;', ' TestSeconds:Double;\n LookupFailure:Boolean;')
    if inject_clock:
        assert source.count('Now * 86400.0') == 1
        source = source.replace('Now * 86400.0', 'TestSeconds')
    controls = sorted(set(re.findall(r'\b(Process\w+)\.(?:Text|Color)\s*:=', source)))
    harness = harness.replace('__CONTROLS__', '\n'.join(n + ':=TControl.Create;' for n in controls))
    with tempfile.TemporaryDirectory(prefix='station-freshness-') as t:
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


def fixture04(folder):
    records = fixture(folder)
    records[0] = (*records[0][:3], BASE.read_text().splitlines())
    (folder / 'Scripts/Scripts.ssc').write_bytes(serialize_scripts(records))
    return records


def main():
    legacy = HARNESS.replace('Fresh;V[0].Raw:=32;StationProcessUpdate;UnknownPressure;', 'Fresh;V[0].Raw:=33;StationProcessUpdate;UnknownPressure;')
    reports = [run_harness(legacy, False), run_harness(FRESH_HARNESS, True)]
    for line in reports:
        print(line, flush=True)
    copies = powershell(output=OUT, installer_name='Install-Station-Freshness-03.ps1',
                        target_name='codex_diag_05', fixture_factory=fixture04)
    used = set(re.findall(r'\b(Process\w+)\.(?:Text|Color)\s*:=', (OUT / 'scripts/StationDiagnostics.txt').read_text()))
    from _runtime import page_bindings
    bindings = page_bindings(ROOT, used)
    result = dict(date='2026-10-30', logicReports=reports, copyCases=copies,
                  bindings=bindings,
                  nativeWindowsF9Observed=False, nativeCounterTestObserved=False,
                  clockInjectionScope='Only Now*86400.0 replaced with a deterministic test clock in the UI harness')
    (OUT / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('Freshness logic and copy preservation passed; native PLC/Windows tests pending.')


if __name__ == '__main__':
    main()
