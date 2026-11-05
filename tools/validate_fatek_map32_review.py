#!/usr/bin/env python3
"""Version mismatch, corruption and input-preservation checks; no vendor GUI."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from _runtime import PLC, ROOT
from build_setpoint_feedback_pdw_01 import build
from prepare_setpoint_feedback_01 import ANCHOR, networks
import review_fatek_map32 as reader
from review_fatek_process_map_01 import review as legacy_review


def refused(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('Invalid input/output was accepted')


def main():
    before = (PLC / 'station_MC_CM55_900G_04.pdw').read_bytes()
    generated, _, _ = build(before, networks(), ANCHOR)
    with tempfile.TemporaryDirectory(prefix='fatek-map32-review-') as folder:
        root = Path(folder)
        copies = []
        for revision, raw, count in [('04', before, 1834), ('05', generated, 1841)]:
            source = root / ('baseline' + revision + '.pdw')
            source.write_bytes(raw)
            copies.append(source)
            report = reader.inspect(source)
            assert report['mapVersion'] == 32 and report['networks'] == count
            assert report['baselineRevision'] == revision and report['sourceUnchanged']
            assert [d['frequencySource'] for d in report['drives']] == [
                'R2803', 'R2811', 'R2819', 'R2827']
            assert [d['frequencyExport'] for d in report['drives']] == [
                'R2500', 'R2501', 'R2502', 'R2503']
            assert [d['normalPollRowOneBased'] for d in report['drives']] == [1, 4, 17, 18]
            assert sum(t['register'] == 'R5000' and t['rows'] == 18
                       for t in report['tables']) == 1
            refused(lambda: legacy_review(source))
            refused(lambda: reader.write_report(source, source))
            assert source.read_bytes() == raw
        # The old reader is still valid for its original map31 baseline.
        old = PLC / 'station_MC_CM55_CL50S_02.pdw'
        assert legacy_review(old)['mov_anchors_checked'] == 20
        refused(lambda: reader.inspect(old))
        damaged = root / 'modified.pdw'
        changed = bytearray(generated)
        changed[-1] ^= 1
        damaged.write_bytes(changed)
        refused(lambda: reader.inspect(damaged))
        damaged.write_bytes(generated + b'extra')
        refused(lambda: reader.inspect(damaged))
        # Exercise the standalone command as used by Windows Codex.
        output = root / 'report.json'
        run = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'tools/review_fatek_map32.py'),
                              str(copies[1]), '--out', str(output)],
                             capture_output=True, text=True, timeout=20)
        assert run.returncode == 0, run.stderr
        assert json.loads(output.read_text(encoding='utf8'))['sourceSHA256'] == hashlib.sha256(generated).hexdigest()
        alias_checks = []
        for kind in ('hardlink', 'symlink'):
            alias = root / (kind + '.json')
            try:
                if kind == 'hardlink':
                    os.link(copies[1], alias)
                else:
                    alias.symlink_to(copies[1])
            except (OSError, NotImplementedError):
                alias_checks.append(kind + ': unavailable')
                continue
            refused(lambda: reader.write_report(copies[1], alias))
            assert copies[1].read_bytes() == generated
            alias_checks.append(kind + ': refused')
    assert (PLC / 'station_MC_CM55_900G_04.pdw').read_bytes() == before
    print('PASS map32 baseline review: source04/generated05, old map31 reader, '
          'wrong-version/corruption refusals, standalone CLI and input preservation; '
          + ', '.join(alias_checks) + '. No native compilation.')


if __name__ == '__main__':
    main()
