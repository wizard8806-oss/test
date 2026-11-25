#!/usr/bin/env python3
"""New offline four-pump PLC copy: independent add delays and PLC countdown.

Only exact reviewed r2 inputs. Never connects to a PLC or overwrites a source.
Existing remove delay, physical safety, SCADA and telemetry are preserved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_cascade_r10 import add, bit, cmp, d, mov, r, w
from build_manual_no_sensor_pdw import pack_record, u16, word_sum
from build_vfd_fault_export_r14 import inventory
from check_native_drive_edit_02 import unpack

SOURCES = {
    'aec1a1c053681ea98f0ee26f5064e6a7bd808cc0835759461d1d7b4acdaabbda': 178597,
    'ecdc1abc4ea0cf3162a1757c86d0a9b1aa1ca9769f6093d92f874cb38bf9ca4a': 178518,
}
MARKER = 27402
REGISTERS = (*range(2884, 2904), *range(3120, 3126))
sha = lambda data: hashlib.sha256(data).hexdigest()


def network_inventory(raw):
    part, rows = inventory(raw)
    codes, bounds, counts = {}, {}, {}
    for i, (pc, label) in enumerate(rows):
        counts[label] = counts.get(label, 0) + 1
        key = label.split(' | ')[0] if label.startswith(('65.C', '95.S')) else f'{label}#{counts[label]}'
        stop = rows[i + 1][0] if i + 1 < len(rows) else u16(part['image'], 270) - 2
        if key in codes:
            raise ValueError('Duplicate cascade/settings identity')
        codes[key], bounds[key] = part['image'][pc:stop], (pc, stop)
    return part, rows, codes, bounds


def changes(codes):
    edits, before = {}, {}

    def insert(anchor, name, code):
        label = f'{anchor}N{len(before.get(anchor, [])) + 1:03d} | {name}'
        before.setdefault(anchor, []).append((label, code))

    def append(anchor, code):
        old = codes[anchor]
        if len(old) < 2 or old[-2:] not in (bit('OUT', 1282), bit('OUT', 1280), bit('OUT', 1471)):
            raise ValueError('Unexpected source acceptance coil: ' + anchor)
        edits[anchor] = old[:-2] + code + old[-2:]

    boot = bit('ORG', 1924) + cmp('AND', '<>', r(2886), MARKER)
    for setting in (2884, 2885):
        insert('65.C001', f'ADD_DEFAULT_R{setting}', boot + mov(r(setting), 10))
        insert('65.C001', f'ADD_INHERIT_R{setting}', boot + cmp('AND', '>', r(2123), 0)
               + cmp('AND', '<', r(2123), 601) + mov(r(setting), r(2123), False))
    insert('65.C001', 'ADD_EXTENSION_INITIALIZED', boot + mov(r(2886), MARKER))
    insert('65.C001', 'COUNTER_ONE', w(0x4fe8) + mov(r(2893), 1))

    def valid(a, b):
        return (cmp('ORG', '>', r(a), 0) + cmp('AND', '<', r(a), 3601)
                + cmp('AND', '>', r(b), 0) + cmp('AND', '<', r(b), 3601))

    for anchor, a, b, flag in (('65.C007', 2884, 2885, 2891), ('95.S034', 2887, 2888, 2892)):
        insert(anchor, 'NEW_DELAYS_INVALID', w(0x4fe8) + mov(r(flag), 0))
        insert(anchor, 'NEW_DELAYS_VALID', valid(a, b) + mov(r(flag), 1))
        append(anchor, cmp('AND', '=', r(flag), 1))
    append('65.C016', cmp('OR', '<>', r(2884), r(2889), False)
           + cmp('OR', '<>', r(2885), r(2890), False))
    for active, shadow, previous in ((2884, 2887, 2889), (2885, 2888, 2890)):
        insert('65.C023', f'SNAPSHOT_R{active}', w(0x4fe8) + mov(r(previous), r(active), False))
        insert('95.S021', f'EDIT_R{active}', bit('ORG', 1467) + mov(r(shadow), r(active), False))
        insert('95.S050', f'APPLY_R{active}', bit('ORG', 1469) + mov(r(active), r(shadow), False))
        insert('95.S066', f'IDLE_R{active}', bit('ORGN', 1463) + mov(r(shadow), r(active), False))

    # A changed candidate or stage must not inherit the old wait.
    changed = (cmp('ORG', '<>', d(906), r(2894), False)
               + cmp('OR', '<>', d(904), r(2895), False))
    for reg in (d(910), r(2896), r(2897)):
        insert('65.C075', 'ADD_TARGET_RESET_' + str(reg), changed + mov(reg, 0))
    insert('65.C075', 'ADD_TARGET_CLOCK_RESET', changed + bit('RST', 1246))
    stop_changed = cmp('ORG', '<>', d(909), r(2900), False)
    insert('65.C075', 'REMOVE_TARGET_RESET', stop_changed + mov(d(911), 0))
    insert('65.C075', 'REMOVE_TARGET_CLOCK_RESET', stop_changed + bit('RST', 1247))
    for source, target in ((d(906), 2894), (d(904), 2895), (d(909), 2900)):
        insert('65.C075', 'PENDING_SNAPSHOT_' + str(target), w(0x4fe8) + mov(r(target), source, False))
    for stage, elapsed in ((0, d(910)), (1, r(2896)), (2, r(2897))):
        insert('65.C075', f'ADD_STAGE{stage}_RESET', bit('ORGN', 1244)
               + cmp('OR', '<>', d(906), stage) + mov(elapsed, 0))

    def snapshot(anchor):
        insert(anchor, 'SELECT_ORIGINAL_PRESET', w(0x4fe8) + mov(r(2898), r(2123), False))
        insert(anchor, 'SELECT_ORIGINAL_ELAPSED', w(0x4fe8) + mov(r(2899), d(910), False))
        for stage, preset, elapsed in ((1, 2884, 2896), (2, 2885, 2897)):
            insert(anchor, f'SELECT_STAGE{stage}_PRESET', cmp('ORG', '=', d(906), stage)
                   + mov(r(2898), r(preset), False))
            insert(anchor, f'SELECT_STAGE{stage}_ELAPSED', cmp('ORG', '=', d(906), stage)
                   + mov(r(2899), r(elapsed), False))

    for anchor, count in (('65.C079', 1), ('65.C087', 2)):
        snapshot(anchor)
        old = codes[anchor]
        if old.count(w(d(910), r(2123))) != count:
            raise ValueError('Unexpected add comparator: ' + anchor)
        edits[anchor] = old.replace(w(d(910), r(2123)), w(r(2899), r(2898)))
    old = codes['65.C082']
    if old != bit('ORG', 1248) + w(0x7fe8, 0xf664, d(910), 65535, d(910)):
        raise ValueError('Unexpected original elapsed increment')
    # Explicit native carry branch is needed after the new stage comparator.
    edits['65.C082'] = bit('ORG', 1248) + cmp('AND', '=', d(906), 0) + add(d(910), d(910), r(2893))
    for stage, elapsed in ((1, 2896), (2, 2897)):
        insert('65.C083', f'ADD_STAGE{stage}_SECOND', bit('ORG', 1248)
               + cmp('AND', '=', d(906), stage) + add(r(elapsed), r(elapsed), r(2893)))
    old = codes['65.C116']
    if old != w(0x4fe8) + mov(r(2132), d(910), False):
        raise ValueError('Unexpected legacy elapsed export')
    edits['65.C116'] = w(0x4fe8) + mov(r(2132), r(2899), False)

    # Publish only real, unfinished PLC waits, after increment/commit networks.
    for address, value in ((3120, MARKER), (3121, 0), (3122, 0), (3123, 0), (3124, 0)):
        insert('65.C117', f'COUNTDOWN_DEFAULT_R{address}', w(0x4fe8) + mov(r(address), value))
    insert('65.C117', 'COUNTDOWN_HEARTBEAT', w(0x4fe8) + mov(r(3125), r(2840), False))
    for flag in (2901, 2902, 2903):
        insert('65.C117', f'COUNTDOWN_FLAG_CLEAR_{flag}', w(0x4fe8) + mov(r(flag), 0))
    insert('65.C117', 'COUNTDOWN_ADD_TARGET_VALID', cmp('ORG', '>', d(904), 0)
           + cmp('AND', '<', d(904), 5) + cmp('AND', '>', d(906), -1)
           + cmp('AND', '<', d(906), 3) + mov(r(2903), 1))
    for action, enable, target, preset, elapsed in ((1, 1244, d(904), r(2898), r(2899)),
                                                    (2, 1245, d(909), r(2124), d(911))):
        guard = (bit('ORG', enable) + bit('ANDN', 1260) + bit('ANDN', 1261)
                 + bit('ANDN', 1265) + bit('ANDN', 1924))
        if action == 1:
            guard += cmp('AND', '=', r(2903), 1)
        else:
            guard += cmp('AND', '>', target, 0) + cmp('AND', '<', target, 5)
        guard += cmp('AND', '<', elapsed, preset, False)
        insert('65.C117', f'COUNTDOWN_{action}_ACTIVE', guard + mov(r(2900 + action), 1))
        guard = cmp('ORG', '=', r(2900 + action), 1)
        for address, value, immediate in ((3121, action, True), (3122, target, False), (3124, preset, False)):
            insert('65.C117', f'COUNTDOWN_{action}_R{address}', guard + mov(r(address), value, immediate))
        subtract = add(r(3123), preset, elapsed).replace(w(0xf462), w(0xf464))
        insert('65.C117', f'COUNTDOWN_{action}_SECONDS', guard + subtract)
    return edits, before


def prepare(source):
    source = Path(source)
    raw = source.read_bytes()
    if SOURCES.get(sha(raw)) != len(raw):
        raise ValueError('Use exact reviewed four-pump r2; preserve changed/native saves')
    part, rows, codes, bounds = network_inventory(raw)
    image, end = part['image'], u16(part['image'], 270)
    if len(rows) != 1844:
        raise ValueError('Unexpected r2 network inventory')
    operands = struct.unpack('>' + 'H' * ((end - 512) // 2), image[512:end])
    for n in REGISTERS:
        if r(n) in operands or ('R' + str(n)).encode() in raw:
            raise ValueError('Possible occupied operand/metadata R' + str(n))
    blocks = 0
    for at in range(512, end - 7, 2):
        if image[at:at + 2] != w(0xf4ce):
            continue
        for address in struct.unpack_from('>2H', image, at + 2):
            count = struct.unpack_from('>H', image, at + 6)[0]
            if 0xa00 <= address < 0x2800 and address % 2 == 0:
                first = (address - 0xa00) // 2
                if any(first <= n <= first + count for n in REGISTERS):
                    raise ValueError('Block move overlaps new registers')
        blocks += 1
    tables = unpack(source)['tables']
    for address, table in tables.items():
        first = int(address[1:])
        if any(first <= n < first + 1 + 7 * len(table['rows']) for n in REGISTERS):
            raise ValueError('Table storage overlaps new registers')
        for row in table['rows']:
            if row[3] == 12 and any(row[4] <= n < row[4] + row[2] for n in REGISTERS):
                raise ValueError('Serial receive buffer overlaps new registers')

    edited, before = changes(codes)
    operations, added = [], []
    for anchor, group in before.items():
        pc, body = bounds[anchor][0], b''
        for label, code in group:
            added.append(dict(sourcePC=pc, relativePC=len(body), label=label, codeHex=code.hex()))
            body += code
        operations.append((pc, pc, body))
    for anchor, body in edited.items():
        operations.append((*bounds[anchor], body))
    operations.sort(key=lambda op: (op[0], op[1]))
    delta = sum(len(b) - (z - a) for a, z, b in operations)
    if delta <= 0 or delta % 2 or image[-delta:] != b'\xff' * delta or u16(image, 264) < delta // 2:
        raise ValueError('Insufficient native program capacity')

    def shifted(pc):
        return pc + sum(len(b) - (z - a) for a, z, b in operations if z <= pc)

    result, cursor = bytearray(), 0
    for a, z, b in operations:
        if a < cursor:
            raise ValueError('Overlapping network edits')
        result.extend(image[cursor:a]); result.extend(b); cursor = z
    result.extend(image[cursor:len(image) - delta])
    struct.pack_into('<HH', result, 262, u16(image, 262) + delta // 2, u16(image, 264) - delta // 2)
    for at in (268, 270):
        struct.pack_into('<H', result, at, shifted(u16(image, at)))
    struct.pack_into('<H', result, 200, (u16(image, 200) + word_sum(result[256:512]) - word_sum(image[256:512])) & 65535)
    struct.pack_into('<H', result, 202, word_sum(result[512:u16(result, 270)]))
    encoded = bytes(v ^ part['key'][i % 1280] for i, v in enumerate(result))
    final = bytearray(raw[:part['first'] + 4]); final.extend(encoded)
    final.extend(raw[part['second']:part['checksum']])
    final.extend(struct.pack('<H', (sum(encoded) + sum(part['payload'])) & 65535))
    for kind, body, record in part['records']:
        if kind in (0x1001, 0x1002) and len(body) >= 4:
            pc = u16(body, 0)
            if kind == 0x1002:
                start = pc + sum(len(b) - (z - a) for a, z, b in operations if z < pc or (z == pc and a < pc))
                for item in (v for v in added if v['sourcePC'] == pc):
                    item['pc'] = start + item['relativePC']
                    text = (item['label'] + '\r\n').encode('cp1251')
                    final.extend(pack_record(kind, struct.pack('<HH', item['pc'], len(text)) + text))
            if shifted(pc) != pc:
                if pack_record(kind, body) != record:
                    raise ValueError('Source metadata checksum differs')
                record = pack_record(kind, struct.pack('<H', shifted(pc)) + body[2:])
        final.extend(record)
    final = bytes(final)
    actual, after_rows, after, _ = network_inventory(final)
    if actual['image'] != bytes(result) or actual['payload'] != part['payload']:
        raise ValueError('Native frame reconstruction differs')
    if len(after_rows) != len(rows) + len(added):
        raise ValueError('Network count differs')
    for key, body in codes.items():
        if after[key] != edited.get(key, body):
            raise ValueError('Unreviewed source network change: ' + key)
    for item in added:
        if after[item['label'].split(' | ')[0]] != bytes.fromhex(item['codeHex']):
            raise ValueError('Inserted network differs')
    keep = lambda f: [record for kind, _, record in f['records'] if kind not in (0x1001, 0x1002)]
    if keep(actual) != keep(part) or source.read_bytes() != raw:
        raise ValueError('Metadata/settings/source preservation differs')
    return final, dict(revision=3, sourceSHA256=sha(raw), candidateSHA256=sha(final), candidateBytes=len(final),
        addedProgramBytes=delta, freeProgramBytes=u16(result, 264) * 2, marker=MARKER,
        registers=REGISTERS, newNetworks=added,
        changedNetworks=[dict(label=k, beforeHex=codes[k].hex(), codeHex=v.hex()) for k, v in edited.items()],
        unchangedNetworks=len(rows) - len(edited), serialTablesPreserved=len(tables),
        blockMoveCandidatesChecked=blocks, newSerialRequests=0, removeDelayPreserved=True,
        defaults='inherit valid R2123 on first use; otherwise existing 10s default',
        sourceNativeInputTestedInCloud=sha(raw) != 'ecdc1abc4ea0cf3162a1757c86d0a9b1aa1ca9769f6093d92f874cb38bf9ca4a',
        actualExternalAllocationReviewed=False, nativeF8Observed=False, hardwareObserved=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'out', 'report'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    if len({p.resolve() for p in (args.source, args.out, args.report)}) != 3 or any(
            p.is_symlink() for p in (args.source, args.out, args.report)) or any(p.exists() for p in (args.out, args.report)):
        parser.error('Distinct source and NEW regular output/report required')
    data, report = prepare(args.source)
    with args.out.open('xb') as output:
        output.write(data)
    with args.report.open('x', encoding='utf8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2); output.write('\n')
    print('Offline candidate', len(data), sha(data), '; native F8/bench remain')


if __name__ == '__main__':
    main()
