#!/usr/bin/env python3
"""Create a NEW offline four-pump PLC candidate from the exact reviewed05.

Publish existing seven-word currents and scope display freshness to each poll.
No new serial requests or SCADA/control changes. Native F8/bench remain required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_manual_no_sensor_pdw import pack_record, u16, word_sum
from build_telemetry_quality_r16 import bit, parallel_actions
from build_vfd_fault_export_r14 import inventory, r, w
from review_fatek_map32 import inspect

SOURCE_SHA = '6aba2a67d07596e4a479c462412859565186de86b410a3cd44476a81f20ffe81'
MARKER = 27401
PREP = '65.T000 | TELEMETRY_RESULT_ROW'
FEATURE = '65.I001 | CURRENT_FEATURE'
HEARTBEAT = '65.I002 | CURRENT_HEARTBEAT'
RESERVED = (*range(2504, 2510), 3080)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(source):
    source = Path(source)
    raw = source.read_bytes()
    if len(raw) != 178479 or sha(raw) != SOURCE_SHA:
        raise ValueError('Use exact reviewed four-pump05; preserve changed/native files')
    baseline = inspect(source)
    f, rows = inventory(raw)
    image, end = f['image'], u16(f['image'], 270)
    spans = {label: (pc, image[pc:rows[i + 1][0] if i + 1 < len(rows) else end - 2])
             for i, (pc, label) in enumerate(rows)}
    words = struct.unpack('>' + 'H' * ((end - 512) // 2), image[512:end])
    for register in RESERVED:
        if r(register) in words or ('R' + str(register)).encode() in raw:
            raise ValueError('Possible occupied operand/metadata: R' + str(register))
    blocks = 0
    for at in range(512, end - 7, 2):
        if image[at:at + 2] != w(0xf4ce):
            continue
        a, b, count = struct.unpack_from('>3H', image, at + 2)
        for address in (a, b):
            if 0xa00 <= address < 0x2800 and address % 2 == 0:
                first = (address - 0xa00) // 2
                if any(first <= n <= first + count for n in RESERVED):
                    raise ValueError('Block move overlaps a reserved register')
        blocks += 1
    for address, table in baseline_table_rows(source).items():
        first = int(address[1:])
        if any(first <= n < first + 1 + 7 * len(table) for n in RESERVED):
            raise ValueError('Table storage overlaps a reserved register')
        for row in table:
            if row[3] == 12 and any(row[4] <= n < row[4] + row[2] for n in RESERVED):
                raise ValueError('Serial receive buffer overlaps a reserved register')

    patches = {}
    for pump, own in enumerate((0, 3, 16, 17)):
        label = f'65.T{5 + 9 * pump:03d} | P{pump + 1}_FREQ_INVALIDATE'
        pc, old = spans[label]
        tag = w(0xf67f, 0x21, 0x4000 + 2 * 301, ((pump + 1) << 8) | 3)
        if old.count(tag) != 1 or old.count(w(0xe444)) != 1:
            raise ValueError('Unexpected error-branch shape: ' + label)
        # Accepted own snapshots take precedence over a latched error indication.
        own_error = tag + w(0xf67f, 0x21, r(3080), own) + bit('ANDN', 1744 + pump)
        patches[label] = (pc, old, old.replace(tag, own_error))
        for number, suffix in ((8, 'DISPLAY_STOP'), (9, 'DISPLAY_RUNNING')):
            label = f'65.T{number + 9 * pump:03d} | P{pump + 1}_{suffix}'
            at, old = spans[label]
            prefix = bit('ORG', 1748 + pump) + bit('AND', 610 + pump)
            if not old.startswith(prefix):
                raise ValueError('Unexpected display-quality guard: ' + label)
            patches[label] = (at, old, bit('ORG', 1748 + pump) + old[len(prefix):])
        label = f'65.T{6 + 9 * pump:03d} | P{pump + 1}_FREQ_VALUE'
        at, old = spans[label]
        if old != bit('ORG', 1744 + pump) + w(0xf4ac, r(2803 + 8 * pump), r(2500 + pump)):
            raise ValueError('Unexpected snapshot publisher: ' + label)
        patches[label] = (at, old, bit('ORG', 1744 + pump) + parallel_actions(
            w(0xf4ac, r(2803 + 8 * pump), r(2500 + pump)),
            w(0xf4ac, r(2806 + 8 * pump), r(2504 + pump))))

    inserted = [
        (PREP, w(0x4fe8, 0xf6c6, 0x4000 + 2 * 300, 255, r(3080))),
        (FEATURE, w(0x4fe8, 0xf5ac, MARKER, r(2509))),
        # A retained capability marker alone is unsafe after rollback to05.
        # HMI must observe this NEW mirror advancing before admitting currents.
        (HEARTBEAT, w(0x4fe8, 0xf4ac, r(2840), r(2508))),
    ]
    point = spans['65.T001 | P1_FREQ_ROW_DONE'][0]
    edits = sorted([(point, b'', b''.join(code for _, code in inserted)),
                    *patches.values()], key=lambda v: (v[0], len(v[1])))
    delta = sum(len(new) - len(old) for _, old, new in edits)
    if delta <= 0 or delta % 2 or delta > u16(image, 264) * 2 or image[-delta:] != b'\xff' * delta:
        raise ValueError('Insufficient native program capacity')

    def shifted(pc, after_insert=True):
        return pc + sum(len(new) - len(old) for at, old, new in edits
                        if at < pc or (at == pc and not old and after_insert))

    out, cursor = bytearray(), 0
    for at, old, new in edits:
        if at < cursor or image[at:at + len(old)] != old:
            raise ValueError('Overlapping or changed edit')
        out.extend(image[cursor:at]); out.extend(new); cursor = at + len(old)
    out.extend(image[cursor:])
    result = out[:-delta]
    struct.pack_into('<HH', result, 262, u16(image, 262) + delta // 2, u16(image, 264) - delta // 2)
    for at in (268, 270):
        struct.pack_into('<H', result, at, shifted(u16(image, at)))
    struct.pack_into('<H', result, 200,
                     (u16(image, 200) + word_sum(result[256:512]) - word_sum(image[256:512])) & 65535)
    struct.pack_into('<H', result, 202, word_sum(result[512:u16(result, 270)]))
    encoded = bytes(v ^ f['key'][i % 1280] for i, v in enumerate(result))
    final = bytearray(raw[:f['first'] + 4]); final.extend(encoded)
    final.extend(raw[f['second']:f['checksum']])
    final.extend(struct.pack('<H', (sum(encoded) + sum(f['payload'])) & 65535))
    for kind, body, record in f['records']:
        if kind in (0x1001, 0x1002) and len(body) >= 4:
            pc = u16(body, 0)
            if kind == 0x1002 and pc == point:
                address = point
                for label, code in inserted:
                    text = (label + '\r\n').encode('cp1251')
                    final.extend(pack_record(kind, struct.pack('<HH', address, len(text)) + text))
                    address += len(code)
            if shifted(pc) != pc:
                if pack_record(kind, body) != record:
                    raise ValueError('Native metadata checksum differs')
                record = pack_record(kind, struct.pack('<H', shifted(pc)) + body[2:])
        final.extend(record)
    final = bytes(final)
    checked, after = inventory(final)
    after_spans = {label: checked['image'][pc:after[i + 1][0] if i + 1 < len(after)
                                          else u16(checked['image'], 270) - 2]
                   for i, (pc, label) in enumerate(after)}
    if checked['image'] != bytes(result) or checked['payload'] != f['payload']:
        raise ValueError('Native frame reconstruction differs')
    if len(after) != len(rows) + len(inserted):
        raise ValueError('Network count differs')
    for label, code in inserted:
        if after_spans.get(label) != code:
            raise ValueError('Inserted network differs: ' + label)
    for label, (_, old) in spans.items():
        if after_spans[label] != (patches[label][2] if label in patches else old):
            raise ValueError('Unreviewed network change: ' + label)
    if [rec for kind, _, rec in checked['records'] if kind not in (0x1001, 0x1002)] != [
            rec for kind, _, rec in f['records'] if kind not in (0x1001, 0x1002)]:
        raise ValueError('Non-PC metadata, serial tables or settings changed')
    if source.read_bytes() != raw:
        raise ValueError('Source changed')
    return final, dict(sourceSHA256=sha(raw), candidateSHA256=sha(final), candidateBytes=len(final),
        mapVersion=32, featureMarker=MARKER, markerRegister='R2509',
        featureHeartbeat='R2508 mirrors R2840; require observed progression, not marker alone',
        currentExports=['R2504', 'R2505', 'R2506', 'R2507'], currentScale=0.1,
        currentSource=['R2806', 'R2814', 'R2822', 'R2830'], quality=['R2510', 'R2511', 'R2512', 'R2513'],
        ownRowsZeroBased=[0, 3, 16, 17], rowDecoder='R3080', addedProgramBytes=delta,
        freeProgramBytes=u16(result, 264) * 2, modifiedNetworks=list(patches),
        newNetworks=[label for label, _ in inserted], allOtherNetworksByteIdentical=True,
        serialTablesAndDataPreserved=True, originalNetworkCount=baseline['networks'],
        blockMoveCandidatesChecked=blocks, newSerialRequests=0, watchdogSeconds=5,
        nativeF8Observed=False, hardwareTestObserved=False,
        externalActualHmiOpcAllocationReviewed=False)


def baseline_table_rows(source):
    from check_native_drive_edit_02 import unpack
    return {k: v['rows'] for k, v in unpack(source)['tables'].items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'out', 'report'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    paths = (args.source, args.out, args.report)
    if len({p.resolve() for p in paths}) != 3 or any(p.is_symlink() for p in paths) or any(
            p.exists() for p in (args.out, args.report)):
        parser.error('Distinct source and NEW regular output/report required')
    data, report = prepare(args.source)
    with args.out.open('xb') as output:
        output.write(data)
    with args.report.open('x', encoding='utf8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2); output.write('\n')
    print('Offline Oshsky candidate:', len(data), sha(data), '; native F8/bench still required')


if __name__ == '__main__':
    main()
