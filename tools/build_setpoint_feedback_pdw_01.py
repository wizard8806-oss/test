#!/usr/bin/env python3
"""Build a source-hash-locked offline PDW copy and a compact transfer patch.

Format1/FBS40003 only. Program/data masking and the combined byte checksum
follow the original WinPro writer. The source's random mask is retained.
No PLC connection, live write or replacement of the source file is performed.
"""
import argparse
import base64
import gzip
import hashlib
import json
import struct
from pathlib import Path

from check_native_drive_edit_02 import unpack
from check_setpoint_feedback_01 import compare
from prepare_setpoint_feedback_01 import SOURCE, EXPECTED, OUT, ANCHOR, networks
from review_fatek_process_map_01 import u16


def sha(data):
    return hashlib.sha256(data).hexdigest()


def word_sum(data):
    if len(data) % 2:
        raise ValueError('Odd checksum range')
    return sum(struct.unpack('<' + 'H' * (len(data) // 2), data)) & 65535


def layout(data):
    n = u16(data, 0x102)
    first = 0x106 + n
    if data[:33] != b'Fatek WinProladder, File Format 1\r\n'[:33]:
        raise ValueError('Different native file format')
    if u16(data, first) != 0x180a or u16(data, first + 2) != 0xa000:
        raise ValueError('Unsupported program frame')
    second = first + 4 + 0xa000
    if u16(data, second) != 0x180b or u16(data, second + 2) != 0x6100:
        raise ValueError('Unsupported data frame')
    checksum = second + 4 + 0x6100
    program = data[first + 4:second]
    payload = data[second + 4:checksum]
    if (sum(program) + sum(payload)) & 65535 != u16(data, checksum):
        raise ValueError('Program/data frame checksum differs')
    seed = payload[-256:]
    key = bytes(seed[i % 256] ^ b'FATEK'[i % 5] for i in range(1280))
    image = bytes(value ^ key[i % 1280] for i, value in enumerate(program))
    if image[:8] != b'FBS40003' or word_sum(image[512:u16(image, 270)]) != u16(image, 202):
        raise ValueError('Program signature or word checksum differs')
    records = []
    position = checksum + 2
    while position < len(data):
        if position + 6 > len(data):
            raise ValueError('Truncated record')
        kind, size = struct.unpack_from('<HH', data, position)
        end = position + size + 6
        if end > len(data):
            raise ValueError('Record exceeds file')
        records.append(dict(offset=position, kind=kind, body=data[position + 4:end - 2],
                            raw=data[position:end]))
        position = end
    if records[-1]['kind'] != 0xffff:
        raise ValueError('End marker missing')
    return dict(first=first, second=second, checksum=checksum, program=program, payload=payload,
                image=image, key=key, records=records)


def record(kind, body):
    if kind == 0x1001:
        checksum = sum(body) & 65535
    elif kind == 0x1002:
        checksum = (sum(body[:4]) + sum(v if v < 128 else v - 256 for v in body[4:])) & 65535
    else:
        raise ValueError('Only unit and network-comment records may be rebuilt')
    return struct.pack('<HH', kind, len(body)) + body + struct.pack('<H', checksum)


def changed_spans(before, after, absolute):
    if len(before) != len(after):
        raise ValueError('Expected equal-sized frame')
    positions = [i for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    spans = []
    if not positions:
        return spans
    start = previous = positions[0]
    for index in positions[1:]:
        if index - previous > 9:
            spans.append((absolute + start, previous + 1 - start, after[start:previous + 1]))
            start = index
        previous = index
    spans.append((absolute + start, previous + 1 - start, after[start:previous + 1]))
    return spans


def build(data, plan, anchor, schema_byte=None):
    part = layout(data)
    image = bytearray(part['image'])
    matches = [r for r in part['records'] if r['kind'] == 0x1002 and r['body'][4:].decode('cp1251').strip() == anchor]
    if len(matches) != 1:
        raise ValueError('Anchor not unique')
    anchor_record = matches[0]
    pc = u16(anchor_record['body'], 0)
    code = b''.join(bytes.fromhex(r['expectedCodeHex']) for r in plan)
    delta = len(code)
    if not delta or delta % 2 or image[-delta:] != b'\xff' * delta:
        raise ValueError('Image capacity or instruction length mismatch')
    image = image[:pc] + code + image[pc:-delta]
    if schema_byte is not None:
        image[257] = schema_byte
    used, free = u16(image, 262), u16(image, 264)
    if free < delta // 2:
        raise ValueError('Insufficient PLC program space')
    struct.pack_into('<HH', image, 262, used + delta // 2, free - delta // 2)
    for offset in (268, 270):
        end = u16(image, offset)
        if end < pc or end + delta >= 0xa000:
            raise ValueError('Unsupported main/subprogram layout')
        struct.pack_into('<H', image, offset, end + delta)
    # A changed-word delta preserves the known source's additive header sum.
    header_delta = word_sum(image[256:512]) - word_sum(part['image'][256:512])
    struct.pack_into('<H', image, 200, (u16(part['image'], 200) + header_delta) & 65535)
    struct.pack_into('<H', image, 202, word_sum(image[512:u16(image, 270)]))
    encoded = bytes(value ^ part['key'][i % 1280] for i, value in enumerate(image))
    edits = changed_spans(part['program'], encoded, part['first'] + 4)
    new_checksum = (sum(encoded) + sum(part['payload'])) & 65535
    edits.append((part['checksum'], 2, struct.pack('<H', new_checksum)))
    extra = []
    address = pc
    for row in plan:
        label = (row['label'] + '\r\n').encode('cp1251')
        extra.append(record(0x1002, struct.pack('<HH', address, len(label)) + label))
        address += len(bytes.fromhex(row['expectedCodeHex']))
    edits.append((anchor_record['offset'], 0, b''.join(extra)))
    shifted_units = []
    shifted_comments = 0
    for row in part['records']:
        if row['kind'] not in (0x1001, 0x1002):
            continue
        body = row['body']
        if len(body) < 4 or u16(body, 0) < pc:
            continue
        if record(row['kind'], body) != row['raw']:
            raise ValueError('Unexpected existing record checksum')
        rewritten = record(row['kind'], struct.pack('<H', u16(body, 0) + delta) + body[2:])
        edits.append((row['offset'], len(row['raw']), rewritten))
        if row['kind'] == 0x1001:
            shifted_units.append(body[6:].decode('cp1251').strip())
        else:
            shifted_comments += 1
    result = apply(data, edits)
    check = layout(result)
    if check['image'] != bytes(image) or check['payload'] != part['payload']:
        raise ValueError('Encoded-frame round trip failed')
    return result, sorted(edits, key=lambda x: (x[0], x[1])), dict(
        insertedAtPC=pc, addedProgramBytes=delta, shiftedUnits=shifted_units,
        shiftedComments=shifted_comments, addedNetworkComments=len(plan),
        headerOffsetsChanged=[i for i in range(512) if image[i] != part['image'][i]],
        sourceRandomMaskRetained=True, dataFramePreserved=True,
        combinedEncodedChecksumVerified=True, programWordChecksumVerified=True)


def apply(data, edits):
    parts = []
    cursor = 0
    for offset, count, replacement in sorted(edits, key=lambda x: (x[0], x[1])):
        if offset < cursor or offset + count > len(data):
            raise ValueError('Overlapping or out-of-range patch')
        parts.extend((data[cursor:offset], replacement))
        cursor = offset + count
    parts.append(data[cursor:])
    return b''.join(parts)


def patch_bytes(source, target, edits):
    result = bytearray(b'FSPPATCH1' + struct.pack('<III', len(source), len(target), len(edits)))
    for offset, count, replacement in edits:
        result += struct.pack('<III', offset, count, len(replacement)) + replacement
    return bytes(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=OUT / 'station_MC_CM55_900G_05.pdw')
    args = parser.parse_args()
    before = SOURCE.read_bytes()
    if sha(before) != EXPECTED:
        raise ValueError('Source differs; refused to build')
    result, edits, evidence = build(before, networks(), ANCHOR)
    if args.out.exists() and args.out.read_bytes() != result:
        raise ValueError('Different destination exists; preserved')
    args.out.write_bytes(result)
    report = compare(unpack(SOURCE), unpack(args.out))
    patch = patch_bytes(before, result, edits)
    (OUT / 'native-file.patch.gz').write_bytes(gzip.compress(patch, mtime=0))
    report.update(evidence, date='2026-10-31', sourceSHA256=EXPECTED, targetSHA256=sha(result),
                  targetBytes=len(result), patchSHA256=sha(patch), patchBytes=len(patch),
                  patchEdits=len(edits), generatedPDW=True, actualPLCUpdateObserved=False,
                  nativeWindowsF8Observed=False)
    (OUT / 'offline-file-generation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    from build_radio_display_01 import bootstrap
    template = (Path(__file__).resolve().parent / 'setpoint_feedback_copy_template.ps1').read_text()
    values = dict(SOURCE_SHA=EXPECTED, TARGET_SHA=sha(result), TARGET_SIZE=str(len(result)),
                  PATCH_GZIP=base64.b64encode(gzip.compress(patch, mtime=0)).decode(),
                  PATCH_SHA=sha(patch), PATCH_COUNT=str(len(edits)))
    for key, value in values.items():
        template = template.replace('__' + key + '__', value)
    (OUT / 'Create-Setpoint-Feedback-Copy-01.ps1').write_text(template)
    paste = bootstrap(template).replace('$radio', '$spCopy')
    (OUT / 'Paste-Setpoint-Feedback-Copy-01.ps1').write_text(paste)
    report.update(installerSHA256=sha(template.encode()), inlineCharacters=len(paste))
    (OUT / 'offline-file-generation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    assert SOURCE.read_bytes() == before
    print('Built offline copy:', len(result), 'bytes;', len(edits), 'edits;', len(gzip.compress(patch)), 'compressed patch bytes')
    print('Target SHA256:', sha(result))


if __name__ == '__main__':
    main()
