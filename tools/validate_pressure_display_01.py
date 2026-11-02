#!/usr/bin/env python3
"""One decimal in pressure UI; raw values, commands and archives stay exact."""
import subprocess
import sys
import tempfile
from pathlib import Path

import prepare_native_ui_event_probe as candidate
from _runtime import ROOT
from audit_native_ui_navigation import scripts
from build_native_operator_console_01 import pressure_display_changes, pressure_display_module
from validate_native_ui_event_probe import fixture
from validate_setpoint_control_01 import HARNESS, run_logic


def main():
    entry=subprocess.run([sys.executable,'-I','-B',str(ROOT/'tools/prepare_native_ui_event_probe.py'),
                          '--mode','pressure-display','--help'],capture_output=True,text=True,timeout=20)
    assert entry.returncode==0 and 'pressure-display' in entry.stdout,entry.stderr
    saved_pins=candidate.PINS
    with tempfile.TemporaryDirectory(prefix='pressure-display-') as temporary:
        root=Path(temporary);source=root/'source';fixture(source)
        raw=(source/'Scripts/Scripts.ssc').read_bytes()
        # The real pinned11 still has two-decimal masks in OperatorConsole.
        # Rebuild only the fixture's two module lines, including string lengths.
        from validate_radio_install_01 import parse_scripts
        from validate_process_display_01 import serialize_scripts
        rows=parse_scripts(raw)
        for i,row in enumerate(rows):
            if row[1]=='OperatorConsole':
                body='\n'.join(row[3])
                for edit in pressure_display_changes(row[1]):body=body.replace(edit['new'],edit['old'])
                rows[i]=(*row[:3],body.split('\n'))
        raw=serialize_scripts(rows);(source/'Scripts/Scripts.ssc').write_bytes(raw)
        before=scripts(raw);patched=candidate.pressure_display_scripts(raw);after=scripts(patched)
        assert candidate.pressure_display_scripts(patched)==patched,'format transform must be idempotent'
        for id_,row in before.items():
            updated=after[id_]
            assert (row['name'],row['meta'])==(updated['name'],updated['meta'])
            if row['name'] not in ['StationDiagnostics','OperatorConsole']:assert row==updated
            else:
                restored=updated['body']
                for edit in pressure_display_changes(row['name']):restored=restored.replace(edit['new'],edit['old'])
                assert restored==row['body'],'only the ten presentation masks may change'
        module=after[0]['body']
        journal="SpControlJournal('Запрос ' + FormatFloat('0.00', SpControlTarget / 100.0)"
        assert journal in module,'command journal retains hundredths and raw target'
        assert module.count('Command.Value := Integer(SpControlTarget);')==1
        try:
            candidate.PINS={name:candidate.SHA((source/name).read_bytes()) for name in saved_pins}
            before_hash=candidate.inventory(source)
            out=root/'codex_diag_11_display_test0001'
            result=candidate.prepare_pressure_display(source,out)
            assert set(result['changedScripts'])=={'StationDiagnostics','OperatorConsole'}
            assert result['pressureDecimals']==1 and result['rawPressureDivisor']==100
            assert result['commandPrecisionUnchanged'] and 'probeId' not in result
            assert not result['WindowsCompileObserved'] and result['hardwareCommands']==0
            assert candidate.inventory(source)==before_hash
            for name,digest in before_hash.items():
                if name=='Scripts/Scripts.ssc' or name.startswith('Scripts/Compiled/'):continue
                assert candidate.SHA((out/name).read_bytes())==digest,name
            for kind in ['existing','wrong_output_kind','diagnostic_source','unexpected_expression']:
                target=out if kind=='existing' else root/('codex_diag_11_display_'+kind)
                data=raw
                if kind=='wrong_output_kind':target=root/'codex_diag_11_probe_test0001'
                if kind=='diagnostic_source':data=candidate.patch_scripts(raw,'UINAV11-TEST0002')
                if kind=='unexpected_expression':
                    data=data.replace("FormatFloat('0.00', PV / 100.0)".encode('utf-16le'),
                                      "FormatFloat('9.99', PV / 100.0)".encode('utf-16le'))
                    candidate.PINS['Scripts/Scripts.ssc']=candidate.SHA(data)
                (source/'Scripts/Scripts.ssc').write_bytes(data)
                existing=candidate.inventory(target) if target.exists() else None
                try:candidate.prepare_pressure_display(source,target)
                except ValueError:pass
                else:raise AssertionError(kind+' should fail')
                assert (source/'Scripts/Scripts.ssc').read_bytes()==data
                if existing is not None:assert candidate.inventory(target)==existing
                else:assert not target.exists()
                (source/'Scripts/Scripts.ssc').write_bytes(raw)
                candidate.PINS['Scripts/Scripts.ssc']=candidate.SHA(raw)
            assert not list(root.glob('.event-probe-*'))
        finally:candidate.PINS=saved_pins
    extra='''
 Prime;V[1].Raw:=290;V[3].Raw:=410;V[20].Raw:=410;Tick(3,3);
 Check(ProcessPressure.Text='2.9 бар','calibrator reference displays one decimal');
 Check(ProcessSetpoint.Text='4.1 бар','PLC readback displays one decimal');
 V[1].Raw:=294;Tick(4,4);Check(ProcessPressure.Text='2.9 бар','hundredths are rounded on screen');
 Check((V[1].Raw=294)and(V[3].Raw=410)and(WriteCount=0),'formatting cannot round raw values or write');
 V[1].Raw:=299;Tick(5,5);Check(ProcessPressure.Text='3.0 бар','rounding carries into integer');
 V[1].Good:=False;Tick(6,6);Check(Pos('бар',ProcessPressure.Text)=0,'BAD remains unavailable');
 V[1].Good:=True;V[2].Raw:=0;Tick(7,7);Check(Pos('бар',ProcessPressure.Text)=0,'missing source never substitutes calibrator value');
 V[2].Raw:=1;V[1].Raw:=290;DefaultFormatSettings.DecimalSeparator:=',';Tick(8,8);
 Check(ProcessPressure.Text='2,9 бар','regional comma is respected');
 DefaultFormatSettings.DecimalSeparator:='.';
'''
    harness=HARNESS.replace('3.60 бар','3.6 бар').replace(
        " WriteLn('PASS operator control assertions=',N);",extra+"\n WriteLn('PASS one-decimal pressure/control assertions=',N);")
    print(run_logic(harness,module_source=module))
    print('PASS pressure formatting copy/refusal cases=5; masks only, command journal/IDs/metadata/archive preserved; isolated CLI works')


if __name__=='__main__':main()
