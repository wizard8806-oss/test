#!/usr/bin/env python3
"""Offline four-pump regression and strict saved-candidate review; no PLC I/O."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from _runtime import PLC
from build_oshsky_telemetry_r2 import prepare, sha
from build_setpoint_feedback_pdw_01 import build
from build_vfd_fault_export_r14 import inventory
from check_native_drive_edit_02 import unpack
from prepare_setpoint_feedback_01 import ANCHOR, networks
from validate_telemetry_continuity import check


def compare(source, candidate):
    source, candidate = Path(source), Path(candidate)
    before, actual = source.read_bytes(), candidate.read_bytes()
    expected, report = prepare(source)
    wanted, wanted_rows = inventory(expected)
    saved, saved_rows = inventory(actual)
    if saved['image'] != wanted['image'] or saved_rows != wanted_rows:
        raise ValueError('Saved native program differs: retain both copies for explicit review')
    if saved['payload'] != wanted['payload']:
        raise ValueError('Saved native data/settings differ')
    for key in ('records',):
        # PC records may be reserialised; all other settings/tables stay exact.
        keep = lambda f: [rec for kind, _, rec in f[key] if kind not in (0x1001, 0x1002)]
        if keep(saved) != keep(wanted):
            raise ValueError('Saved native non-PC metadata differs')
    assert unpack(source)['tables'] == unpack(candidate)['tables']
    count = check(candidate, pumps=4)
    if source.read_bytes() != before or candidate.read_bytes() != actual:
        raise ValueError('Input changed during review')
    return dict(sourceSHA256=sha(before), candidateSHA256=sha(actual),
                candidateBytes=len(actual), expectedCandidateSHA256=sha(expected),
                actualBytecodeCasesPassed=count, networkCount=len(saved_rows),
                protectedSourceNetworks=len(wanted_rows) - len(report['newNetworks'])
                    - len(report['modifiedNetworks']),
                allOtherNetworksAndNineTablesPreserved=True,
                mapVersion=32, newSerialRequests=0, sourceAndCandidateUnchanged=True,
                nativeF8Observed=False, hardwareObserved=False)


def refused(call, kind=ValueError):
    try:
        call()
    except kind:
        return
    raise AssertionError('Expected rejection')


def regression():
    original = PLC / 'station_MC_CM55_900G_04.pdw'
    before = original.read_bytes()
    seed, _, _ = build(before, networks(), ANCHOR)
    with tempfile.TemporaryDirectory(prefix='oshsky-r2-check-') as folder:
        root = Path(folder)
        source, candidate = root / 'source05.pdw', root / 'candidate.pdw'
        source.write_bytes(seed)
        # Reproduce absent current exports and cross-request invalidation first.
        refused(lambda: check(source, pumps=4), AssertionError)
        data, report = prepare(source)
        assert report['addedProgramBytes'] == 98 and report['freeProgramBytes'] == 13680
        assert len(report['modifiedNetworks']) == 16 and len(report['newNetworks']) == 3
        candidate.write_bytes(data)
        audit = compare(source, candidate)
        assert audit['actualBytecodeCasesPassed'] == 222
        assert audit['networkCount'] == 1844 and audit['protectedSourceNetworks'] == 1825
        refused(lambda: prepare(candidate))
        refused(lambda: prepare(original))
        refused(lambda: compare(source, source))
        damaged = root / 'damaged.pdw'
        changed = bytearray(data); changed[600] ^= 1
        damaged.write_bytes(changed)
        refused(lambda: compare(source, damaged))
        script = Path(__file__).with_name('build_oshsky_telemetry_r2.py')
        output, evidence = root / 'cli.pdw', root / 'build.json'
        args = [sys.executable, '-B', str(script), '--source', str(source),
                '--out', str(output), '--report', str(evidence)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
        assert output.read_bytes() == data
        assert json.loads(evidence.read_text())['candidateSHA256'] == sha(data)
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        assert result.returncode != 0 and output.read_bytes() == data
        args[args.index('--out') + 1] = str(source)
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        assert result.returncode != 0 and source.read_bytes() == seed
    assert original.read_bytes() == before
    print('PASS Oshsky r2: 222 bytecode cases,1844 networks/1825 protected, '
          'nine tables, baseline regression, corruption/version/overwrite refusals; '
          'no native F8 or hardware test')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Exact reviewed05')
    parser.add_argument('--candidate', type=Path, help='Candidate or native-saved copy')
    parser.add_argument('--out', type=Path, help='NEW JSON report; never an input alias')
    args = parser.parse_args()
    if args.source is None and args.candidate is None and args.out is None:
        regression()
        return
    if not args.source or not args.candidate:
        parser.error('--source and --candidate are required together')
    if args.out and (args.out.exists() or args.out.is_symlink() or
                    args.out.resolve() in {args.source.resolve(), args.candidate.resolve()}):
        parser.error('Report must be a NEW file distinct from both inputs')
    report = compare(args.source, args.candidate)
    if args.out:
        with args.out.open('x', encoding='utf8') as output:
            json.dump(report, output, ensure_ascii=False, indent=2); output.write('\n')
    print('PASS saved Oshsky candidate:', report['actualBytecodeCasesPassed'],
          'bytecode cases; native F8/hardware remain separate evidence')


if __name__ == '__main__':
    main()
