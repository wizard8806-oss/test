#!/usr/bin/env python3
"""Check interleaved polling and guarded workpack creation; no PLC execution."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from build_setpoint_feedback_pdw_01 import build
from prepare_setpoint_feedback_01 import SOURCE, EXPECTED, ANCHOR, networks
from prepare_pump_count_workpack import SOURCE_SHA, inspect, prepare, schedules, sha


def refuses(call):
    try:
        call()
    except (ValueError, FileExistsError):
        return
    raise AssertionError('Unexpected acceptance')


def main():
    old = SOURCE.read_bytes()
    assert sha(old) == EXPECTED
    baseline, _, _ = build(old, networks(), ANCHOR)
    assert sha(baseline) == SOURCE_SHA
    cases = 0
    with tempfile.TemporaryDirectory(prefix='pump-count-workpack-') as folder:
        root = Path(folder)
        src = root / 'baseline05.pdw'
        src.write_bytes(baseline)
        report = inspect(src)
        assert report['physicalAddressesAllocated'] is False
        assert report['nativePumpCountImplemented'] is False
        assert report['sourceUnchanged'] is True
        assert not any(report['rawEvenWordPossibleReferences'].values())
        cases += 1
        normal = [entry['fields'] for entry in report['normalPollSchedules']['4']]
        for count, expected_length in ((2, 11), (3, 14), (4, 18)):
            plan = report['normalPollSchedules'][str(count)]
            assert len(plan) == expected_length
            assert {entry['fields'][0] for entry in plan} == set(range(1, count + 1))
            assert [entry['sourceRowOneBased'] for entry in plan] == sorted(entry['sourceRowOneBased'] for entry in plan)
            assert all(normal[entry['sourceRowOneBased'] - 1] == entry['fields'] for entry in plan)
            # Every installed drive must retain its pressure and 7-word telemetry read.
            for drive in range(1, count + 1):
                rows = [entry['fields'] for entry in plan if entry['fields'][0] == drive]
                assert any(row[2] == 7 and row[3] == 12 and row[4] == 2800 + 8 * (drive - 1) for row in rows)
                assert any(row[2] == 1 and row[3] == 13 and row[6] == 4111 for row in rows)
            cases += 1
        assert any(row[0] > 3 for row in normal[:14])
        assert any(row[0] > 2 for row in normal[:11])
        assert len(report['oneShotTables']) == 8
        cases += 1
        before = copy.deepcopy(normal)
        schedules(normal)
        assert normal == before
        cases += 1
        for bad in ([], [[5, 1, 7, 12, 2800, 4, 4097]], [[1, 1]], [[True, 1, 7, 12, 2800, 4, 4097]]):
            refuses(lambda: schedules(bad))
            cases += 1
        output = root / 'report.json'
        prepare(src, output)
        assert json.loads(output.read_text()) == report and src.read_bytes() == baseline
        cases += 1
        refuses(lambda: prepare(src, output))
        refuses(lambda: prepare(src, src))
        cases += 2
        changed = root / 'changed.pdw'
        raw = bytearray(baseline)
        raw[-1] ^= 1
        changed.write_bytes(raw)
        refuses(lambda: inspect(changed))
        cases += 1
        alias = root / 'alias.json'
        os.link(src, alias)
        refuses(lambda: prepare(src, alias))
        assert src.read_bytes() == baseline
        cases += 1
        standalone = subprocess.run([
            sys.executable, '-I', '-B', str(Path(__file__).with_name('prepare_pump_count_workpack.py')),
            '--plc', str(src), '--out', str(root / 'standalone.json')],
            capture_output=True, text=True, timeout=30)
        assert standalone.returncode == 0, standalone.stderr
        assert json.loads((root / 'standalone.json').read_text()) == report
        cases += 1
    assert SOURCE.read_bytes() == old
    print('PASS', cases, 'pump-count workpack checks; correct 11/14/18 row selections, aliases/stale inputs refused; no PLC/HMI execution.')


if __name__ == '__main__':
    main()
