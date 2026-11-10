#!/usr/bin/env python3
"""Reorder reviewed native macro metadata: all reads, then BootAck write.

The live probe showed correct PLC P3 values in macro P1. This candidate
tests an R/W packing hypothesis; only a native Compile and a live repeat
can confirm the cause/fix. C source, addresses and every UI byte stay intact.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from repair_skm_section_index import read_directory

SOURCE_BYTES = 1273731
SOURCE_SHA = '1ea6cece228acbb1dd5d99750a44399bfc9a3a36fa261403649b0297d251bfc2'
VARIABLES = (
    ('AlarmWords', 'Batch 16-Bit Unsigned Int', '10', 'R', '2550'),
    ('MapVersion', '16-Bit Unsigned Int', '', 'R', '2554'),
    ('BootAck', '16-Bit Unsigned Int', '', 'W', '2553'),
    ('PumpAnimTelemetry', 'Batch 16-Bit Unsigned Int', '26', 'R', '2500'),
    ('PumpAnimRoles', 'Batch 16-Bit Unsigned Int', '14', 'R', '2320'),
    ('PumpAnimManual', 'Batch 16-Bit Unsigned Int', '6', 'R', '2380'),
    ('PumpAnimLeader', '16-Bit Unsigned Int', '', 'R', '2304'),
)
ORDER = (0, 1, 3, 4, 5, 6, 2)
sha = lambda value: hashlib.sha256(value).hexdigest()


def qs(value):
    data = value.encode('utf-16-be')
    return struct.pack('>I', len(data)) + data


def entry(row):
    name, kind, size, mode, address = row
    return (qs(name)+qs(kind)+qs(size)+qs(mode)+qs('R'+address)
            +b'\x01\x06\x01'+qs(address)+qs('R')+b'\x01\0\0\0\0')


def packed(rows):
    return qs(''.join('%s#%s#%s#%s#R#%s#0:Fatek FB Series:6#1#' % row for row in rows))


def prepare(source):
    source = Path(source); raw = source.read_bytes()
    if len(raw) != SOURCE_BYTES or sha(raw) != SOURCE_SHA:
        raise ValueError('Use exact latest USER r13; preserve any newer native/HMI edits for reviewed adaptation')
    directory = read_directory(raw)
    rows = [VARIABLES[i] for i in ORDER]
    pairs = [(packed(VARIABLES), packed(rows), 'packed variable table'),
             (struct.pack('>I', 7)+b''.join(map(entry, VARIABLES)),
              struct.pack('>I', 7)+b''.join(map(entry, rows)), 'native variable records')]
    edits = []
    for old, new, label in pairs:
        if raw.count(old) != 1 or len(old) != len(new):
            raise ValueError('Exact native schema/count differs: '+label)
        edits.append((raw.index(old), old, new, label))
    edits.sort(); out = bytearray(raw)
    for i, (at, old, new, label) in enumerate(edits):
        if i and edits[i-1][0]+len(edits[i-1][1]) > at:
            raise ValueError('Overlapping variable metadata')
        if at < 1220488:
            raise ValueError('Metadata edit would affect reviewed screen area')
        out[at:at+len(old)] = new
    result = bytes(out)
    if read_directory(result) != directory or len(result) != len(raw):
        raise ValueError('Unchanged directory/size check failed')
    inverse = bytearray(result)
    for at, old, new, label in edits:
        if result[at:at+len(new)] != new:
            raise ValueError('Reordered metadata differs: '+label)
        inverse[at:at+len(new)] = old
    if bytes(inverse) != raw or result[:1220488] != raw[:1220488]:
        raise ValueError('Source/UI preservation failed')
    if any(result.count(new) != 1 for _, _, new, _ in edits):
        raise ValueError('New table uniqueness failed')
    if source.read_bytes() != raw:
        raise ValueError('Source changed during build')
    return result, {
        'sourceSHA256': sha(raw), 'sourceBytes': len(raw),
        'candidateSHA256': sha(result), 'candidateBytes': len(result),
        'oldOrder': [r[0] for r in VARIABLES], 'newOrder': [r[0] for r in rows],
        'edits': [{'offset': at, 'bytes': len(old), 'label': label} for at, old, _, label in edits],
        'bothSerializedVariableTablesReordered': True,
        'allOtherBytesPreservedByFullInversion': True,
        'allUIBytesPreserved': True, 'macroCSourcePreserved': True,
        'addressesTypesSizesAndModesPreserved': True, 'variableCount': 7,
        'PLCChanged': False, 'newPLCWrites': 0, 'BootAckAddressAndMode': 'W R2553',
        'probeSignatureUnchanged': 27119,
        'nativeCompileObserved': False, 'nativeABIFixConfirmed': False,
        'liveRetestRequired': 'Only P3 at25Hz: macro LW922=250/LW925=2, P1 macro frequency0; compare direct inputs',
        'notClaimed': 'This is a minimal metadata hypothesis test, not proven native ABI repair or completed HMI fault r14',
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path)
    p.add_argument('--check', type=Path, help='Validate an existing exact candidate instead of building')
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    if (a.out is None) == (a.check is None):
        p.error('Choose exactly one of --out or --check')
    target = a.out or a.check
    paths = [a.source, target, a.report]
    if len({v.resolve() for v in paths}) != 3 or any(v.is_symlink() for v in paths):
        raise ValueError('Distinct regular paths required; symlinks refused')
    if a.report.exists() or (a.out is not None and a.out.exists()):
        raise ValueError('NEW output/report required; existing files are preserved')
    data, report = prepare(a.source)
    if a.check is not None:
        if target.read_bytes() != data:
            raise ValueError('Candidate differs from exact read-before-write reorder')
        report['exactCandidateValidated'] = True
    else:
        with target.open('xb') as f:
            f.write(data)
    with a.report.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2); f.write('\n')
    print(('PASS' if a.check is not None else 'Created')+' read-before-write HMI candidate:', len(data), sha(data))
    print('Screens, user labels, HAD, C source and PLC bindings preserved. Native Compile/live repeat remain.')


if __name__ == '__main__':
    main()
