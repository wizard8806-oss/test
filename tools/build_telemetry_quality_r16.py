#!/usr/bin/env python3
"""Scope display freshness to each seven-WORD poll; keep serial/control code.

Input is the exact accepted r15 native PDW. Outputs are NEW offline files;
WinProLadder Syntax Check and a bench test remain separate requirements.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_manual_no_sensor_pdw import pack_record, u16, word_sum
from build_vfd_fault_export_r14 import inventory, r, w

SOURCE_SHA = 'd45ada8b0781175cf5c4a91e14a2f4bf23d9c037957ce830da44c1daca2e58ae'
MARKER = 27133
ROW_REGISTER = 3080
PREP = '65.T000 | TELEMETRY_RESULT_ROW'
sha = lambda data: hashlib.sha256(data).hexdigest()


def bit(mode, relay):
    return w({'ORG': 0x4000, 'AND': 0x8000, 'ANDN': 0x9000}[mode] + 0x810 + relay)


def parallel_actions(first, second):
    # Same native fan-out used by the accepted reset r15 actions(). Two
    # sequential output functions are executable by the host model but
    # rejected by WinProLadder's network-to-node converter.
    return w(0xc400, 0x8fea) + first + w(0x6400) + second


def prepare(source):
    source = Path(source)
    raw = source.read_bytes()
    if len(raw) != 206320 or sha(raw) != SOURCE_SHA:
        raise ValueError('Use the preserved accepted r15 native, not a new field readback')
    f, rows = inventory(raw)
    image, end = f['image'], u16(f['image'], 270)
    spans = {label: (pc, image[pc:rows[i + 1][0] if i + 1 < len(rows) else end - 2])
             for i, (pc, label) in enumerate(rows)}
    # These spare slots are inside the EXISTING 26-byte HMI Batch16 input.
    # R3080 is a volatile row decoder, not a command or retained setting.
    reserved = [2504, 2505, 2506, 2509, ROW_REGISTER]
    words = struct.unpack('>' + 'H' * ((end - 512) // 2), image[512:end])
    for register in reserved:
        if r(register) in words or ('R' + str(register)).encode() in raw:
            raise ValueError('Reserved register already referenced: R' + str(register))
    # Existing block moves must not span a newly reserved register.
    for at in range(512, end - 7, 2):
        if image[at:at + 2] != w(0xf4ce):
            continue
        a, b, count = struct.unpack_from('>3H', image, at + 2)
        for address in (a, b):
            if 0xa00 <= address < 0x2800 and address % 2 == 0:
                first = (address - 0xa00) // 2
                if any(first <= n <= first + count for n in reserved):
                    raise ValueError('Block move overlaps a reserved register')

    patches, edits = {}, []
    for pump, own_row in enumerate((0, 3, 13)):
        label = f'65.T{5 + 9 * pump:03d} | P{pump + 1}_FREQ_INVALIDATE'
        pc, old = spans[label]
        tag = w(0xf67f, 0x21, 0x4000 + 2 * 301, ((pump + 1) << 8) | 3)
        if old.count(tag) != 1 or old.count(w(0xe444)) != 1:
            raise ValueError('Native invalidate branch differs: ' + label)
        new = old.replace(tag, tag + w(0xf67f, 0x21, r(ROW_REGISTER), own_row))
        patches[label] = (pc, old, new)
        for number, suffix in ((8, 'DISPLAY_STOP'), (9, 'DISPLAY_RUNNING')):
            name = f'65.T{number + 9 * pump:03d} | P{pump + 1}_{suffix}'
            at, before = spans[name]
            prefix = bit('ORG', 1748 + pump) + bit('AND', 610 + pump)
            if not before.startswith(prefix):
                raise ValueError('Native display-quality guard differs: ' + name)
            patches[name] = (at, before, bit('ORG', 1748 + pump) + before[len(prefix):])
        name = f'65.T{6 + 9 * pump:03d} | P{pump + 1}_FREQ_VALUE'
        at, before = spans[name]
        expected = bit('ORG', 1744 + pump) + w(0xf4ac, r(2803 + 8 * pump), r(2500 + pump))
        if before != expected:
            raise ValueError('Native seven-WORD sample publisher differs')
        patches[name] = (at, before, bit('ORG', 1744 + pump) + parallel_actions(
            w(0xf4ac, r(2803 + 8 * pump), r(2500 + pump)),
            w(0xf4ac, r(2806 + 8 * pump), r(2504 + pump))))

    name = '10.N3002 | BUILD_MARKER'
    at, before = spans[name]
    if before != w(0x4fe8, 0xf5ac, 27114, r(2861)):
        raise ValueError('Build marker differs')
    patches[name] = (at, before, w(0x4fe8, 0xf5ac, MARKER, r(2861)))
    point = spans['65.T001 | P1_FREQ_ROW_DONE'][0]
    prep = w(0x4fe8) + parallel_actions(
        w(0xf6c6, 0x4000 + 2 * 300, 255, r(ROW_REGISTER)),
        w(0xf5ac, MARKER, r(2509)))
    edits = [(point, b'', prep)] + list(patches.values())
    edits.sort(key=lambda v: (v[0], len(v[1])))
    delta = sum(len(new) - len(old) for _, old, new in edits)
    if delta <= 0 or delta % 2 or delta > u16(image, 264) * 2 or image[-delta:] != b'\xff' * delta:
        raise ValueError('Insufficient native program capacity')

    def shifted(pc, after_insert=True):
        return pc + sum(len(new) - len(old) for at, old, new in edits
                        if at < pc or (at == pc and not old and after_insert))

    out, cursor = bytearray(), 0
    for at, old, new in edits:
        if at < cursor or image[at:at + len(old)] != old:
            raise ValueError('Overlapping or changed native edit')
        out.extend(image[cursor:at]); out.extend(new); cursor = at + len(old)
    out.extend(image[cursor:])
    result = out[:-delta]
    struct.pack_into('<HH', result, 262, u16(image, 262) + delta // 2,
                     u16(image, 264) - delta // 2)
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
                label = (PREP + '\r\n').encode('cp1251')
                final.extend(pack_record(kind, struct.pack('<HH', shifted(point, False), len(label)) + label))
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
    if len(after) != len(rows) + 1 or after_spans[PREP] != prep:
        raise ValueError('New row decoder missing')
    for label, (_, old) in spans.items():
        if after_spans[label] != (patches[label][2] if label in patches else old):
            raise ValueError('Unreviewed program-network change: ' + label)
    if [rec for kind, _, rec in checked['records'] if kind not in (0x1001, 0x1002)] != [
            rec for kind, _, rec in f['records'] if kind not in (0x1001, 0x1002)]:
        raise ValueError('Non-PC metadata or serial tables changed')
    if source.read_bytes() != raw:
        raise ValueError('Source changed')
    return final, dict(sourceSHA256=sha(raw), candidateSHA256=sha(final),
        candidateBytes=len(final), featureMarker=MARKER, markerRegisters=['R2509', 'R2861'],
        currentExports=['R2504', 'R2505', 'R2506'], currentScale=0.1,
        currentSource=['R2806', 'R2814', 'R2822'], rowDecoder='R3080',
        addedProgramBytes=delta, freeProgramBytes=u16(result, 264) * 2,
        modifiedNetworks=list(patches), newNetwork=PREP, allOtherNetworksByteIdentical=True,
        serialTablesAndDataPreserved=True, watchdogUnchangedSeconds=5,
        genericCommAndControlNetworksPreserved=True, noNewSerialQueries=True,
        nativeSyntaxCheckObserved=False, fieldFixConfirmed=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'out', 'report'):
        p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args()
    if len({v.resolve() for v in (a.source, a.out, a.report)}) != 3 or any(
            v.is_symlink() for v in (a.source, a.out, a.report)) or a.out.exists() or a.report.exists():
        p.error('Distinct source and NEW regular output/report required')
    data, report = prepare(a.source)
    with a.out.open('xb') as f:
        f.write(data)
    with a.report.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2); f.write('\n')
    print('Created offline telemetry candidate:', len(data), sha(data),
          'free bytes:', report['freeProgramBytes'], '; native/bench checks remain')


if __name__ == '__main__':
    main()
