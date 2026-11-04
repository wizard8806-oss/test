#!/usr/bin/env python3
"""Native event-import preservation/refusal checks; synthetic files only."""
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import import_native_empty_timer as timer
from _runtime import ROOT
from validate_process_display_01 import serialize_scripts


def fixture(source):
    (source/'Scripts/Compiled').mkdir(parents=True)
    # Pages deliberately cannot be parsed as Text-only: the importer must keep
    # arbitrary native classes opaque instead of silently dropping them.
    (source/'Pages.spg').write_bytes(b'SYNTHETIC_OPAQUE_NATIVE_TREND_COMPONENT')
    (source/'Project.spr').write_bytes(bytes(8)+struct.pack('<4H',2,6,15,0))
    rows = [(0,'ExistingModule',bytes(range(17)),['unit ExistingModule;','interface','implementation','end.']),
            (48,'Script_48',bytes(range(17)),['unit Script_48;','interface','procedure PlotUpdate;','implementation','procedure PlotUpdate;','begin end;','end.']),
            (49,'Script_49',bytes(range(16,-1,-1)),['unit Script_49;','begin','','end.'])]
    (source/'Scripts/Scripts.ssc').write_bytes(serialize_scripts(rows))
    (source/'Scripts/Compiled/program.exs').write_bytes(b'SYNTHETIC_STALE_BYTECODE')
    for name in ['Variables.svr','Trends.str','Windows.swn','Servers.ssr','UserProfile.dat']:
        (source/name).write_bytes(b'SYNTHETIC_PRIVATE_RESOURCE_'+name.encode())


def main():
    help_ = subprocess.run([sys.executable,'-I','-B',str(ROOT/'tools/import_native_empty_timer.py'),'--help'],
                           capture_output=True,text=True,timeout=20)
    assert help_.returncode == 0 and '--expected-payload-sha' in help_.stdout, help_.stderr
    with tempfile.TemporaryDirectory(prefix='empty-native-timer-') as tmp:
        root = Path(tmp);source=root/'saved-native-model';fixture(source)
        payload=root/'reviewed-timer.txt';payload.write_text('begin\n  PlotUpdate;\nend.\n',encoding='utf8')
        before=timer.copy.inventory(source)
        args=dict(project=source,out=root/'codex_diag_11_trend_timer_test0001',payload_file=payload,
                  script_id=49,script_name='Script_49',pages_sha=before['Pages.spg'],
                  scripts_sha=before['Scripts/Scripts.ssc'],payload_sha=timer.copy.SHA(payload.read_bytes()))
        result=timer.prepare(**args)
        assert result['sourceUnchanged'] and result['pagesOpaqueAndUnchanged']
        assert not result['WindowsCompileObserved'] and not result['timerExecutionObserved']
        assert result['hardwareCommands'] == 0 and result['unsavedEditorModelIncluded'] is False
        assert timer.copy.inventory(source) == before
        for name,digest in before.items():
            if name == 'Scripts/Scripts.ssc' or name.startswith('Scripts/Compiled/'):
                continue
            assert timer.copy.SHA((args['out']/name).read_bytes()) == digest,name
        assert not list((args['out']/'Scripts/Compiled').iterdir())
        if os.name != 'nt':assert args['out'].stat().st_mode & 0o077 == 0
        old=timer.copy.scripts((source/'Scripts/Scripts.ssc').read_bytes())
        new=timer.copy.scripts((args['out']/'Scripts/Scripts.ssc').read_bytes())
        assert len(old) == len(new) == 3
        for id_,row in old.items():
            assert row['meta'] == new[id_]['meta'] and row['name'] == new[id_]['name']
            if id_ != 49:assert row == new[id_]
        assert new[49]['body'] == 'begin\n  PlotUpdate;\nend.'
        raw=(source/'Scripts/Scripts.ssc').read_bytes()
        cases=[dict(out=args['out']),dict(out=source/'codex_diag_11_trend_timer_nested001'),
               dict(out=root/'wrong-name'),dict(script_id=48,script_name='Script_48'),
               dict(script_id=50),dict(script_name='DifferentName'),dict(pages_sha='0'*64),
               dict(scripts_sha='0'*64),dict(payload_sha='0'*64)]
        for change in cases:
            values=dict(args,out=root/'codex_diag_11_trend_timer_refusal001');values.update(change)
            try:timer.prepare(**values)
            except ValueError:pass
            else:raise AssertionError('invalid import accepted: '+str(change))
        for bad in [raw[:-1],raw+b'X',(args['out']/'Scripts/Scripts.ssc').read_bytes()]:
            try:timer.patch(bad,49,'Script_49',payload.read_text())
            except ValueError:pass
            else:raise AssertionError('corrupt or nonempty script accepted')
        for bad in ['begin end.','procedure Wrong; begin PlotUpdate; end.','unit Wrong; begin PlotUpdate; end.',
                    'begin\x00 PlotUpdate; end.','begin PlotUpdate;', 'begin '+('X'*65536)+' end.']:
            try:timer.patch(raw,49,'Script_49',bad)
            except ValueError:pass
            else:raise AssertionError('invalid payload accepted')
        original_privacy=timer.copy._private_directory
        def deny(path):raise ValueError('synthetic private-directory failure')
        timer.copy._private_directory=deny
        try:
            try:timer.prepare(**dict(args,out=root/'codex_diag_11_trend_timer_acltest01'))
            except ValueError:pass
            else:raise AssertionError('private-copy failure ignored')
        finally:timer.copy._private_directory=original_privacy
        assert timer.copy.inventory(source) == before
        assert not list(root.glob('.trend-timer-*'))
    print('PASS empty native timer import: exact ID/name/body pins, unchanged metadata/opaque pages/private resources, source preservation, stale-cache exclusion, refusal/cleanup cases, isolated CLI; no Pascal execution')


if __name__ == '__main__':main()
