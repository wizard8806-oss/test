#!/usr/bin/env python3
"""Read-only evidence for telemetry buffers; never declares memory allocated.

MOV operands and table ranges provide positive conflict evidence. Absence of
an encoded word is only a conservative candidate filter, not a complete
indirect-address or external-HMI memory audit.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from review_fatek_process_map_01 import plain_records, register, review, u16

EXPECTED = '41e0788134b7cbd4fa6e0f8ab1b6515a9a396c5fdcef0b40b871d460e38f3dff'


def inspect(source):
    original = source.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if digest != EXPECTED:
        raise ValueError('Different source project; repeat the memory review')
    checked = review(source)
    first = 0x106 + u16(original, 0x102)
    length = u16(original, first + 2)
    encrypted = original[first + 4:first + 4 + length]
    key = bytes(value ^ 255 for value in encrypted[-1280:])
    image = bytes(value ^ key[index % 1280]
                  for index, value in enumerate(encrypted))
    second = first + 4 + length
    text_start = second + 4 + u16(original, second + 2)
    rungs = []
    for offset, body in plain_records(original, text_start, 0x1002):
        if len(body) < 8:
            continue
        pc, size = struct.unpack_from('<HH', body)
        if size + 4 == len(body) and body[4:6].isdigit() and body[6:7] == b'.':
            rungs.append({'pc': pc, 'label': body[4:].decode('cp1251').strip()})
    refs = {}
    for index, rung in enumerate(rungs):
        end = rungs[index + 1]['pc'] if index + 1 < len(rungs) else rung['pc'] + 16
        for offset in range(rung['pc'], end - 5, 2):
            opcode, src, dst = struct.unpack_from('>HHH', image, offset)
            if opcode not in (0xf4ac, 0xf5ac):
                continue
            operands = [(register(dst), 'destination')]
            if opcode == 0xf4ac:
                operands.append((register(src), 'source'))
            for address, role in operands:
                refs.setdefault(address, []).append(dict(
                    pc=rung['pc'], label=rung['label'], role=role))
    normal = next(t for t in checked['master_tables'] if t['register'] == 'R5000')
    collisions = []
    for drive in checked['drive_frequency_exports']:
        row_number = drive['normal_poll_row']
        start = normal['rows'][row_number - 1][4]
        overlaps = []
        for index, row in enumerate(normal['rows'], 1):
            if index == row_number or row[3] != 13:
                continue
            if max(start, row[4]) < min(start + 7, row[4] + row[2]):
                overlaps.append(dict(tableRow=index, slave=row[0],
                                     first='D' + str(row[4]), count=row[2]))
        if not overlaps:
            raise ValueError('Existing buffer overlap expectation changed')
        collisions.append(dict(drive=drive['drive'], existingBuffer='D' + str(start),
                               attemptedCount=7, conflictingRows=overlaps))
    words = {struct.unpack_from('>H', image, index)[0]
             for index in range(0, len(image) - 1, 2)}
    candidates = []
    for kind, base, begin, end in [('D', 0x4000, 432, 463),
                                   ('R', 0x0a00, 2800, 2831)]:
        hits = [kind + str(number) for number in range(begin, end + 1)
                if base + number * 2 in words]
        table_hits = []
        if kind == 'D':
            for table in checked['master_tables']:
                for index, row in enumerate(table['rows'], 1):
                    if row[3] == 13 and max(begin, row[4]) < min(end + 1, row[4] + row[2]):
                        table_hits.append(dict(table=table['register'], row=index))
        candidates.append(dict(first=kind + str(begin), last=kind + str(end),
                               encodedWordMatches=hits, tableDRangeOverlaps=table_hits,
                               allocated=False,
                               status='Candidate for native memory/indirection/HMI review only'))
    recovery = {address: refs.get(address, []) for address in
                ['R2520', 'R2521', 'R2524', 'R2540', 'R2542']}
    if any(not evidence for evidence in recovery.values()):
        raise ValueError('Recovery-interface conflict anchors changed')
    if source.read_bytes() != original:
        raise ValueError('Source file changed during review')
    return dict(source=source.name, sourceSHA256=digest,
                status='Read-only evidence; no allocations or PLC patch',
                sourceRungsChecked=checked['rung_comments_checked'],
                sourceMOVAnchorsChecked=checked['mov_anchors_checked'],
                imageBytes=len(image), tablesChecked=len(checked['master_tables']),
                oldBufferExpansionConflicts=collisions,
                recoveryRegistersNotFree=recovery,
                proposedRangesForReview=candidates,
                unresolved=['Decode indirect and multiword access extents',
                            'Check external HMI/OPC use before allocation',
                            'Bind each accepted slave/row result to its full snapshot',
                            'Implement shared freshness/invalidation and preserve old frequency consumers',
                            'Native WinProladder project validation before any bench download'],
                deployable=False, PLCModified=False, originalSourceUnchanged=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.source)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Reviewed4 old-buffer conflicts,5 occupied recovery registers,2 candidate ranges; source unchanged; no allocation.')


if __name__ == '__main__':
    main()
