#!/usr/bin/env python3
"""Read-only inspection of the two reviewed map32 pump-station baselines.

Accepts exact source04/generated05 hashes. Verifies saved-file checksums,
the map-version MOV, telemetry tables and four frequency exports. This is
baseline evidence, not a memory allocator, native compiler or PLC test.
The legacy review_fatek_process_map_01.py intentionally expects map31.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_setpoint_feedback_pdw_01 import layout
from check_native_drive_edit_02 import unpack


BASELINES = {
    'a25f9b5d2fe006bcb039896bae3989569b08e1b1adc4b503a755bfd5e3b22993':
        ('04', 1834),
    '6aba2a67d07596e4a479c462412859565186de86b410a3cd44476a81f20ffe81':
        ('05', 1841),
}
LABELS = (
    '65.T006 | P1_FREQ_VALUE', '65.T015 | P2_FREQ_VALUE',
    '65.T024 | P3_FREQ_VALUE', '65.T033 | P4_FREQ_VALUE',
)


def inspect(source):
    source = Path(source)
    original = source.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if digest not in BASELINES:
        raise ValueError('Unreviewed baseline: expected exact source04 or generated05; '
                         'review changed projects separately')
    revision, expected_networks = BASELINES[digest]
    framed = layout(original)
    obj = unpack(source)
    if obj['bytes'] != original or obj['image'] != framed['image']:
        raise ValueError('Source changed or image decoders disagree')
    rungs = obj['rungs']
    if len(rungs) != expected_networks or len({pc for pc, _ in rungs}) != len(rungs):
        raise ValueError('Unexpected network inventory')
    required_labels = (*LABELS, '95.W032 | WORD_STATUS_VERSION')
    if any(sum(label == required for _, label in rungs) != 1 for required in required_labels):
        raise ValueError('Required evidence label missing or ambiguous')
    end = int.from_bytes(obj['image'][270:272], 'little')
    spans = {
        label: obj['image'][pc:rungs[i + 1][0] if i + 1 < len(rungs) else end - 2]
        for i, (pc, label) in enumerate(rungs)
        if label in required_labels
    }
    version_code = spans['95.W032 | WORD_STATUS_VERSION']
    version_mov = struct.pack('>3H', 0xf5ac, 32, 0x0a00 + 2 * 2554)
    if sum(version_code[i:i + 6] == version_mov
           for i in range(0, len(version_code) - 5, 2)) != 1:
        raise ValueError('Expected map32 MOV missing or ambiguous')
    tables = obj['tables']
    if len(tables) != 9 or len(tables['R5000']['rows']) != 18:
        raise ValueError('Unexpected baseline table inventory')
    normal = tables['R5000']['rows']
    drives = []
    for index, label in enumerate(LABELS):
        drive = index + 1
        start = 2800 + 8 * index
        code = spans[label]
        mov = struct.pack('>3H', 0xf4ac, 0x0a00 + 2 * (start + 3),
                          0x0a00 + 2 * (2500 + index))
        if len(code) != 8 or code[2:] != mov:
            raise ValueError('Map32 frequency MOV mismatch: ' + label)
        row = [drive, 1, 7, 12, start, 4, 4097]
        if normal.count(row) != 1:
            raise ValueError('Map32 seven-word telemetry read mismatch: drive ' + str(drive))
        drives.append(dict(drive=drive, telemetryBuffer='R' + str(start),
                           telemetryWords=7, nativeStartPDU=0x1000,
                           normalPollRowOneBased=normal.index(row) + 1,
                           frequencySource='R' + str(start + 3),
                           frequencyExport='R' + str(2500 + index),
                           currentBuffer='R' + str(start + 6),
                           evidenceNetwork=label))
    if source.read_bytes() != original:
        raise ValueError('Source changed during inspection')
    return dict(sourceName=source.name, sourceSHA256=digest, baselineRevision=revision,
                bytes=len(original), mapVersion=32, mapVersionRegister='R2554',
                networks=expected_networks,
                combinedFrameChecksumVerified=True, programWordChecksumVerified=True,
                tableCopiesVerified=True,
                tables=[dict(register=reg, name=table['name'], rows=len(table['rows']))
                        for reg, table in sorted(tables.items())],
                drives=drives, sourceUnchanged=True,
                limits=['Exact reviewed baseline only; edited candidates require a new review',
                        'No complete instruction decoding or free-register allocation',
                        'No native F8, hardware test or live tag-quality observation',
                        'No implementation or acceptance of configurable pump count'])


def write_report(source, output):
    source, output = Path(source), Path(output)
    if (source.resolve() == output.resolve() or
            (output.exists() and source.samefile(output))):
        raise ValueError('Report must not overwrite the input, including an alias')
    report = inspect(source)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = write_report(args.source, args.out)
    print('Map32 baseline' + report['baselineRevision'] + ':', report['networks'],
          'networks, 9 tables, four seven-word telemetry reads/frequency exports verified; '
          'source unchanged. No native compilation or hardware action.')


if __name__ == '__main__':
    main()
