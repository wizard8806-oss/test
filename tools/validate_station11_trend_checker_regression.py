#!/usr/bin/env python3
"""Reject comment/string-only quality evidence; exercise reference boundaries.

These are checker regressions with synthetic saved scripts. They do not prove
that the private native producer implements the reference contract.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import validate_station11_trend_quality_01 as quality
from _runtime import ROOT
from validate_process_display_01 import serialize_scripts

BODY = '''var MapOk, PlcFresh, PvOk, SpOk, FreqOk: Boolean;
PvRaw, SpRaw, FreqRaw, FreqState: Integer; Age: Double;
begin
  MapOk := codex_Device1_MapVersion.IsGoodQuality and (codex_Device1_MapVersion.OriginalAsInt = 32);
  Age := (Now - codex_Device1_PlcAliveCounter.Timestamp) * 86400.0;
  PlcFresh := codex_Device1_PlcAliveCounter.IsGoodQuality and (Age >= 0) and (Age <= 15.0);
  PvRaw := codex_Device1_PressurePV_x100.OriginalAsInt;
  SpRaw := codex_Device1_PressureSP_x100.OriginalAsInt;
  FreqRaw := codex_Device1_Vfd1FreqRaw.OriginalAsInt;
  FreqState := codex_Device1_Vfd1FreqState.OriginalAsInt;
  PvOk := MapOk and PlcFresh and codex_Device1_PressurePV_x100.IsGoodQuality
    and codex_Device1_PressureSourceOK.IsGoodQuality
    and (codex_Device1_PressureSourceOK.OriginalAsInt = 1) and (PvRaw >= 0) and (PvRaw <= 1600);
  SpOk := MapOk and PlcFresh and codex_Device1_PressureSP_x100.IsGoodQuality
    and (SpRaw >= 10) and (SpRaw <= 1190) and (SpRaw mod 10 = 0);
  FreqOk := MapOk and PlcFresh and codex_Device1_Vfd1FreqRaw.IsGoodQuality
    and codex_Device1_Vfd1FreqState.IsGoodQuality
    and (((FreqState = 1) and (FreqRaw = 0)) or ((FreqState = 2) and (FreqRaw >= 1) and (FreqRaw <= 500)));
  if PvOk then TrendPressurePVBar.Value := PvRaw / 100.0 else TrendPressurePVBar.Archiving := False;
  if SpOk then TrendPressureSPBar.Value := SpRaw / 100.0 else TrendPressureSPBar.Archiving := False;
  if FreqOk then TrendVfd1FreqHz.Value := FreqRaw / 10.0 else TrendVfd1FreqHz.Archiving := False;
end.'''


def cli(folder, body):
    (folder/'Scripts').mkdir(exist_ok=True)
    (folder/'Scripts/Scripts.ssc').write_bytes(
        serialize_scripts([(50,'Script_49',bytes(17),body.splitlines())]))
    return subprocess.run([sys.executable,'-I','-B',str(ROOT/'tools/validate_station11_trend_quality_01.py'),
                           '--project-directory',str(folder)],capture_output=True,text=True,timeout=20)


def main():
    assert all(quality.static_clues(BODY).values())
    assert all(quality.static_clues(BODY.lower().replace('.value :=','. value\n :=' )).values())
    bad_bodies = ['begin\n{'+BODY+'}\nend.', 'begin\n(*'+BODY+'*)\nend.',
                  'begin\n'+'\n'.join('//'+line for line in BODY.splitlines())+'\nend.',
                  "begin MessageText := '"+BODY.replace('\n',' ').replace("'","''")+"'; end."]
    for body in bad_bodies:
        clues=quality.static_clues(body)
        assert not clues['map-clues-present'] and not clues['named-target-assignments-present']
    masked=quality.executable_text("begin s := 'it''s fake'; { outer (* nested *) } x := 1; end.")
    assert 'fake' not in masked and 'nested' not in masked and 'x := 1' in masked
    for body in ["begin s := 'unterminated",'begin { unterminated','begin (* unterminated']:
        try:quality.executable_text(body)
        except ValueError:pass
        else:raise AssertionError('malformed lexical evidence accepted')
    for assignment in ['PressurePV_x100.Value:=1;', 'codex_Device1_PressureSP_Command . Value\n:=400;',
                       'PRESSURESP_X100{comment}.VALUE := 1;', 'Vfd1FreqRaw.Value := 1;', 'WriteValue(x);']:
        assert not quality.static_clues(BODY+'\n'+assignment)['no-recognized-direct-source-assignment']
    valid=quality.gate(quality.sample())
    assert [valid[k] for k in ['pv','sp','freq']] == [3.9,4.1,12.0]
    for overrides in [dict(age=16),dict(age=-1),dict(counter_good=False),dict(counter_progress_seen=False)]:
        state=quality.gate(quality.sample(**overrides))
        assert not any(state[k+'_valid'] for k in ['pv','sp','freq'])
    state=quality.gate(quality.sample(age=16,freq_independent_fresh=True))
    assert state['freq_valid'] and not state['pv_valid'] and not state['sp_valid']
    state=quality.gate(quality.sample(source_ok=0,previous=valid))
    assert not state['pv_valid'] and not state['pv_archive'] and state['pv']==valid['pv']
    assert state['sp_valid'] and state['freq_valid']
    assert quality.gate(quality.sample(source_ok=1,pv_raw=0))['pv_valid']
    assert quality.gate(quality.sample(pv_raw=400,previous=state))['pv']==4.0
    with tempfile.TemporaryDirectory(prefix='trend-checker-regression-') as tmp:
        folder=Path(tmp)
        for body in bad_bodies:
            result=cli(folder,body)
            assert result.returncode != 0,'Comment/literal-only event received PASS'
        result=cli(folder,BODY)
        assert result.returncode == 0,result.stdout+result.stderr
        assert 'native-quality-gap-acceptance: UNVERIFIED' in result.stdout
        assert 'model is independent of the supplied Pascal body' in result.stdout
    print('PASS trend checker regressions: comments/strings rejected, casing/spacing handled, known direct writes detected; reference requires freshness and explicit availability; native Pascal/archive remain unverified')


if __name__ == '__main__':main()
