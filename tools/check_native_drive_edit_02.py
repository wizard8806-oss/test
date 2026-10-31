#!/usr/bin/env python3
"""Read-only comparison of a user-saved native PDW against proposal02.

Passing the comparison is not memory allocation, native compilation or PLC
acceptance. The local R-table type requires independent native confirmation.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

from prepare_native_drive_edit_02 import EXPECTED, OUT, SOURCE
from review_fatek_process_map_01 import plain_records, u16


def unpack(path):
    data = path.read_bytes()
    if not data.startswith(b'Fatek WinProladder, File Format 1'):
        raise ValueError('Unsupported file format')
    n = u16(data, 0x102)
    if u16(data, 0x100) != 0x1006 or sum(data[0x104:0x104+n]) & 65535 != u16(data, 0x104+n):
        raise ValueError('Invalid project record')
    start = 0x106 + n
    if u16(data, start) != 0x180a:
        raise ValueError('Missing program image')
    count = u16(data, start + 2)
    cipher = data[start+4:start+4+count]
    if len(cipher) < 3840 or len(cipher) % 1280 or not cipher[-1280:] == cipher[-2560:-1280] == cipher[-3840:-2560]:
        raise ValueError('Unsupported image padding')
    key = bytes(x ^ 255 for x in cipher[-1280:])
    image = bytes(x ^ key[i % 1280] for i, x in enumerate(cipher))
    if image[:8] != b'FBS40003':
        raise ValueError('Unexpected CPU image header')
    second = start + 4 + count
    if u16(data, second) != 0x180b:
        raise ValueError('Missing second image')
    tail = second + 4 + u16(data, second + 2)
    rungs = []
    for _, body in plain_records(data, tail, 0x1002):
        if len(body) < 8:
            continue
        pc, size = struct.unpack_from('<HH', body)
        if size + 4 == len(body) and re.match(rb'[0-9]{2}\.', body[4:]):
            rungs.append((pc, body[4:].decode('cp1251').strip()))
    if len(rungs) < 1000 or rungs != sorted(rungs):
        raise ValueError('Invalid rung comments/order')
    tables = {}
    for _, body in plain_records(data, tail, 0x1015):
        n = u16(body, 0)
        if not 2 <= n <= 128:
            continue
        reg = re.search(rb'R[0-9]+\x00', body[2+n:2+n+40])
        if not reg:
            continue
        copies = []
        for pos in range(len(body) - 4):
            if body[pos:pos+2] != b'\x50\xa5':
                continue
            rows, cols = body[pos+2:pos+4]
            if cols != 7 or not rows or pos + 4 + rows * 14 > len(body):
                continue
            values = struct.unpack_from('<' + 'H' * rows * cols, body, pos + 4)
            copies.append([list(values[j*7:(j+1)*7]) for j in range(rows)])
        if copies:
            if len(copies) != 2 or copies[0] != copies[1]:
                raise ValueError('Table copies disagree')
            address = reg[0].rstrip(b'\0').decode()
            if address in tables:
                raise ValueError('Duplicate table address')
            tables[address] = dict(name=body[2:2+n].rstrip(b'\0').decode('ascii'), rows=copies[0])
    return dict(bytes=data, image=image, rungs=rungs, tables=tables)


def check(path, r_type=None):
    old = unpack(SOURCE)
    if hashlib.sha256(old['bytes']).hexdigest() != EXPECTED:
        raise ValueError('Baseline source changed')
    new = unpack(path)
    if new['rungs'] != old['rungs'] or len(new['image']) != len(old['image']):
        raise ValueError('Rung positions/comments or image size changed; manual review required')
    spec = json.loads((OUT / 'native-edit-proposal.json').read_text())
    expected = bytearray(old['image'])
    anchors = {label: pc for pc, label in old['rungs']}
    edits = []
    for row in spec['changes']:
        mov = row['frequencyMOV']
        pc = anchors[mov['label']]
        old_source = int(mov['oldSource'][1:]) * 2 + 0x4000
        destination = int(mov['unchangedDestination'][1:]) * 2 + 0x0a00
        instruction = struct.pack('>HHH', 0xf4ac, old_source, destination)
        if expected[pc+2:pc+8] != instruction:
            raise ValueError('Baseline MOV instruction changed')
        source = int(mov['proposedSource'][1:]) * 2 + 0x0a00
        struct.pack_into('>H', expected, pc + 4, source)
        edits.append(dict(label=mov['label'], source=mov['proposedSource'], destination=mov['unchangedDestination']))
    version = spec['proposedMapVersion']
    pc = anchors[version['label']]
    pattern = struct.pack('>HHH', 0xf5ac, version['old'], 0x0a00 + version['register'] * 2)
    rung_end = next((p for p, _ in old['rungs'] if p > pc), pc + 16)
    position = bytes(expected).find(pattern, pc, rung_end)
    if position < 0:
        raise ValueError('Baseline map-version MOV changed')
    struct.pack_into('>H', expected, position + 2, version['new'])
    unexpected = [i for i in range(512, len(expected)) if expected[i] != new['image'][i]]
    if unexpected:
        raise ValueError('Program differs from the four MOV sources and map32 at offsets ' + str(unexpected[:20]))
    if new['tables'].keys() != old['tables'].keys():
        raise ValueError('Table set changed')
    expected_tables = json.loads(json.dumps(old['tables']))
    kinds = set()
    for row in spec['changes']:
        index = row['nativeSeqZeroBased']
        actual = new['tables']['R5000']['rows'][index]
        kind = actual[3]
        if kind == 13 or (r_type is not None and kind != r_type):
            raise ValueError('Local destination register type does not match proposed R memory')
        kinds.add(kind)
        target = row['proposedUI']
        expected_tables['R5000']['rows'][index] = [row['drive'], 1, 7, kind, int(target['masterData'][1:]), 4, 4097]
    if len(kinds) != 1 or expected_tables != new['tables']:
        raise ValueError('Unexpected table change or inconsistent local memory type')
    return dict(candidate=path.name, sha256=hashlib.sha256(new['bytes']).hexdigest(),
                programMatchesFiveProposedOperandChanges=True,
                unchangedRungLabelsAndPCs=len(new['rungs']),
                tableRows=18, changedFrequencyRows=[0, 3, 16, 17],
                otherTablesUnchanged=True, tableCopiesAgree=True,
                observedLocalMemoryType=list(kinds)[0],
                localRTypeIndependentlyConfirmed=r_type is not None,
                changedProgramHeaderOffsets=[i for i in range(512) if old['image'][i] != new['image'][i]],
                editedMOVs=edits, nativeEditorCompileObserved=False,
                candidateMemoryAllocated=False, PLCModifiedByThisChecker=False,
                deployable=False,
                remaining='Independent R memory type/header/indirect-HMI review, compatible SCADA and native bench validation')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--confirmed-r-type', type=int)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = check(args.candidate, args.confirmed_r_type)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Candidate matches proposed code/table edits; independent native/memory checks still required.')


if __name__ == '__main__':
    main()
