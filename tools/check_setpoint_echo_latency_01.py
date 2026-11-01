#!/usr/bin/env python3
"""Replay confirmation timing with mock values; never connect to equipment."""
import argparse
import hashlib
import json
from pathlib import Path

from build_setpoint_click_fix_01 import OUT, EVENTS
from validate_setpoint_control_01 import HARNESS, run_logic


def check():
    module = (OUT / 'scripts/StationDiagnostics.txt').read_text()
    events = {n: (OUT / 'scripts' / (n + '_OnClick.txt')).read_text() for n, _ in EVENTS}
    prefix = HARNESS.split('begin\n DefaultSystemCodePage', 1)[0]
    body = r'''begin
 DefaultSystemCodePage:=65001;DefaultFormatSettings.DecimalSeparator:='.';N:=0;
 for I:=0 to 20 do V[I]:=TM_Variable.Create;
 __CREATE_CONTROLS__
 Prime;ActorID:=0;for J:=1 to 5 do StationSpAdjust(10);StationSpApply;
 Check((WriteCount=1)and(LastWrite=400),'mock operator submits raw400 once');
 V[3].Raw:=400;V[20].Raw:=400;Tick(3,3);Tick(4,4);
 Check(Pos('ПЛК принял',ProcessMainScope.Text)>0,'two prompt counter changes accept echo');
 Check(WriteCount=1,'prompt echo does not repeat setter');
 WriteLn('FAST: ',ProcessMainScope.Text);
 Prime;ActorID:=0;for J:=1 to 5 do StationSpAdjust(10);StationSpApply;
 Check((WriteCount=1)and(LastWrite=400),'slow scenario submits raw400 once');
 V[3].Raw:=400;V[20].Raw:=400;
 for I:=3 to 22 do Tick(I,2+((I-2)div 14)*14);
 Check(Pos('20 с не подтверждён',ProcessMainScope.Text)>0,'one new counter in20s times out despite matching values');
 Check((V[3].Raw=400)and(V[20].Raw=400),'timeout does not undo mock register values');
 WriteLn('SLOW20: ',ProcessMainScope.Text);
 for I:=23 to 35 do Tick(I,2+((I-2)div 14)*14);
 Check(Pos('20 с не подтверждён',ProcessMainScope.Text)>0,'late second change preserves historical timeout');
 Check((WriteCount=1)and(LogCount=2),'no retry: exactly request and timeout logs');
 WriteLn('LATE: ',ProcessMainScope.Text);
 WriteLn('PASS echo latency assertions=',N);
end.
'''
    result = run_logic(prefix + body, module_source=module, event_sources=events)
    paths = [OUT / 'scripts/StationDiagnostics.txt'] + [OUT / 'scripts' / (n + '_OnClick.txt') for n, _ in EVENTS]
    return dict(method='FreePascal source replay with mock TM_Variable and actual caller-aware event sources',
                sourceSHA256={str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                assumptions=['Both readbacks set to400 immediately in mock, not observed on hardware',
                             'After submission, counter visible changes every14 seconds; hypothetical schedule, not measured SCADA timer trace',
                             'Timer runs each second with GOOD quality; actual OPC delivery is not simulated'],
                output=result.splitlines(), hardwareConnections=False, liveWriteTested=False,
                runtimeSourceModified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = check()
    if args.out:
        # No arbitrary output paths: use an unused JSON result, never a native input.
        if args.out.suffix.lower() != '.json' or args.out.exists():
            raise ValueError('Use a new .json report path')
        with args.out.open('x') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
    print('\n'.join(result['output']))


if __name__ == '__main__':
    main()
