#!/usr/bin/env python3
"""Add read-only native-fault exports to an exact three-pump r10 PDW copy.

Reuse the existing seven-WORD success/cache indications. No new serial jobs,
drive reset, RUN command, protection or scheduling changes. Unknown data keeps
the last confirmed fault; only a fresh zero clears a fault event.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_manual_no_sensor_pdw import frame, pack_record, word_sum, u16

SOURCE_SHA = 'b5de31e3fddd45041c8f11b97be94eb55cf13f7aad7b63f3467707227c192a8b'
SOURCE_BYTES = 187549
REGISTERS = list(range(3040, 3080))
RETAINED = list(range(2832, 2838))+list(range(2844, 2849))
MARKER = 27120
ANCHOR = '95.W032 | WORD_STATUS_VERSION'
sha = lambda b: hashlib.sha256(b).hexdigest()
w = lambda *v: struct.pack('>'+'H'*len(v), *v)
r = lambda n: 0xa00 + 2*n


def bit(mode, n):
    return w({'ORG': 0x4000, 'ORGN': 0x5000, 'AND': 0x8000,
              'ANDN': 0x9000, 'OR': 0xa000, 'ORN': 0xb000}[mode] + 0x810+n)


def cmp(mode, rel, left, right, immediate=True):
    return w(0xf67f if immediate else 0xf47f,
             {'ORG': 0x15, 'AND': 0x21, 'OR': 0x27}[mode]
             + {'=': 0, '>': 1, '<': 2, '<>': 3}[rel], left, right & 65535)


def mov(destination, source, immediate=True):
    return w(0xf5ac if immediate else 0xf4ac, source & 65535, destination)


def add(destination, left, right):
    return w(0xc400, 0x8fe7, 0x6400, 0x9fe7, 0xf462, left, right, destination)


def inventory(raw):
    f = frame(raw)
    rows = [(u16(body, 0), body[4:].decode('cp1251').strip())
            for kind, body, _ in f['records']
            if kind == 0x1002 and len(body) >= 4 and body[4:6].isdigit()]
    if rows != sorted(rows) or len({p for p, _ in rows}) != len(rows):
        raise ValueError('Network metadata order/uniqueness differs')
    return f, rows


def networks():
    rows = []
    def emit(name, code):
        rows.append({'label': '95.NF%03d | %s' % (len(rows)+1, name), 'codeHex': code.hex()})
    # Volatile validity resets at boot. Retained confirmed codes survive a
    # PLC restart so a lost connection/restart cannot falsely restore an alarm.
    for n in REGISTERS:
        emit('BOOT_CLEAR_R'+str(n), bit('ORG', 1924)+mov(r(n), 0))
    emit('CONSTANT_ONE', w(0x4fe8)+mov(r(3074), 1))
    emit('RETAINED_INIT_DEFAULT', w(0x4fe8)+mov(r(3079), 0))
    for register, value in ((2847, MARKER), (2848, MARKER ^ 65535)):
        emit('RETAINED_INIT_GUARD_'+str(register), bit('ORG', 1924)
             +cmp('AND', '<>', r(register), value)+mov(r(3079), 1))
    for n in RETAINED:
        emit('RETAINED_FIRST_USE_CLEAR_'+str(n), cmp('ORG', '=', r(3079), 1)+mov(r(n), 0))
    emit('RETAINED_SIGNATURE', cmp('ORG', '=', r(3079), 1)+mov(r(2847), MARKER))
    emit('RETAINED_INVERSE', cmp('ORG', '=', r(3079), 1)+mov(r(2848), MARKER ^ 65535))
    for i in range(3):
        raw, quality, sequence, state, last = 3040+i, 3043+i, 3046+i, 3050+i, 3053+i
        flags, unknown, receive = 3056+5*i, 3071+i, 2801+8*i
        retained_raw, retained_seq, retained_last = 2832+i, 2835+i, 2844+i
        sample = bit('ORG', 1744+i)+bit('ANDN', 1924)
        emit('P%d_UPDATE_FLAGS_DEFAULT' % (i+1), w(0x4fe8)+mov(r(3079), 0))
        emit('P%d_UPDATE_FLAGS_BOOT' % (i+1), bit('ORG', 1924)+mov(r(3079), 1))
        emit('P%d_UPDATE_FLAGS_CHANGED' % (i+1), sample
             +cmp('AND', '<>', r(receive), r(retained_raw), False)+mov(r(3079), 1))
        emit('P%d_NEW_FAULT_EVENT' % (i+1), sample+cmp('AND', '<>', r(receive), 0)
             +cmp('AND', '<>', r(receive), r(retained_raw), False)+add(r(3076), r(3076), r(3074)))
        emit('P%d_RETAINED_RAW' % (i+1), sample+mov(r(retained_raw), r(receive), False))
        emit('P%d_RETAINED_LAST' % (i+1), sample+cmp('AND', '<>', r(retained_raw), 0)
             +mov(r(retained_last), r(retained_raw), False))
        emit('P%d_RETAINED_SEQUENCE' % (i+1), sample+add(r(retained_seq), r(retained_seq), r(3074)))
        emit('P%d_RETAINED_SEQUENCE_WRAP' % (i+1), sample+cmp('AND', '=', r(retained_seq), 0)+mov(r(retained_seq), 1))
        for destination, source in ((raw, retained_raw), (sequence, retained_seq), (last, retained_last)):
            emit('P%d_PUBLISH_R%d' % (i+1, destination), w(0x4fe8)+mov(r(destination), r(source), False))
        update = cmp('ORG', '=', r(3079), 1)
        for j in range(5):
            emit('P%d_FLAGS_CLEAR_%d' % (i+1, j), update+mov(r(flags+j), 0))
        emit('P%d_UNKNOWN_CLEAR' % (i+1), update+mov(r(unknown), 0))
        emit('P%d_UNKNOWN_NONZERO' % (i+1), update+cmp('AND', '<>', r(raw), 0)+mov(r(unknown), 1))
        emit('P%d_KNOWN_RANGE' % (i+1), update+cmp('AND', '>', r(raw), 0)
             +cmp('AND', '<', r(raw), 81)+mov(r(unknown), 0))
        for code in range(1, 81):
            emit('P%d_CODE_%02d' % (i+1, code), update+cmp('AND', '=', r(raw), code)
                 +mov(r(flags+(code-1)//16), 1 << ((code-1) % 16)))
        emit('P%d_QUALITY_UNKNOWN' % (i+1), w(0x4fe8)+mov(r(quality), 0))
        emit('P%d_QUALITY_FRESH' % (i+1), bit('ORG', 1748+i)+bit('ANDN', 1924)+mov(r(quality), 1))
        emit('P%d_STATE_NEVER_SEEN' % (i+1), w(0x4fe8)+mov(r(state), 0))
        emit('P%d_STATE_STALE' % (i+1), cmp('ORG', '=', r(quality), 0)
             +cmp('AND', '<>', r(sequence), 0)+mov(r(state), 3))
        emit('P%d_STATE_CLEAR' % (i+1), cmp('ORG', '=', r(quality), 1)
             +cmp('AND', '=', r(raw), 0)+mov(r(state), 1))
        emit('P%d_STATE_FAULT' % (i+1), cmp('ORG', '=', r(quality), 1)
             +cmp('AND', '<>', r(raw), 0)+mov(r(state), 2))
    emit('SUMMARY_CLEAR', w(0x4fe8)+mov(r(3075), 0))
    emit('DISPLAY_COUNT_BASE', w(0x4fe8)+mov(r(3077), r(2363), False))
    for i in range(3):
        # Fault validity can be unknown without confirming recovery. The
        # remembered summary/event flags clear only on a fresh zero/boot.
        present = cmp('ORG', '<>', r(3040+i), 0)
        # Disjoint masks are summed, no bitwise instruction/extra bits needed.
        emit('SUMMARY_P%d_PREPARE' % (i+1), w(0x4fe8)+mov(r(3078), 1 << i))
        emit('SUMMARY_P%d' % (i+1), present+add(r(3075), r(3075), r(3078)))
        emit('DISPLAY_COUNT_P%d' % (i+1), present+add(r(3077), r(3077), r(3074)))
    emit('FEATURE_CONTRACT', w(0x4fe8)+mov(r(3049), MARKER))
    return rows


def prepare(source):
    source = Path(source); raw = source.read_bytes()
    if len(raw) != SOURCE_BYTES or sha(raw) != SOURCE_SHA:
        raise ValueError('Use exact r10; preserve changed/native saves for review')
    f, old_rows = inventory(raw); image = f['image']; end = u16(image, 270)
    if len(old_rows) != 2070:
        raise ValueError('Unexpected source network inventory')
    points = [p for p, name in old_rows if name == ANCHOR]
    if len(points) != 1:
        raise ValueError('Fault export insertion anchor differs')
    at = points[0]
    for n in REGISTERS+RETAINED:
        if any(image[p:p+2] == w(r(n)) for p in range(512, end, 2)):
            raise ValueError('Possible existing reference: R'+str(n))
        if ('R'+str(n)).encode() in raw:
            raise ValueError('Existing metadata reference: R'+str(n))
    added = networks(); code = b''.join(bytes.fromhex(v['codeHex']) for v in added); delta = len(code)
    if delta % 2 or image[-delta:] != b'\xff'*delta or u16(image, 264) < delta//2:
        raise ValueError('Insufficient program capacity')
    result = bytearray(image[:at]+code+image[at:-delta])
    struct.pack_into('<HH', result, 262, u16(image, 262)+delta//2, u16(image, 264)-delta//2)
    for p in (268, 270):
        struct.pack_into('<H', result, p, u16(image, p)+delta)
    struct.pack_into('<H', result, 200, (u16(image, 200)+word_sum(result[256:512])-word_sum(image[256:512])) & 65535)
    struct.pack_into('<H', result, 202, word_sum(result[512:u16(result, 270)]))
    encoded = bytes(v ^ f['key'][i % 1280] for i, v in enumerate(result))
    final = bytearray(raw[:f['first']+4]); final.extend(encoded)
    final.extend(raw[f['second']:f['checksum']])
    final.extend(struct.pack('<H', (sum(encoded)+sum(f['payload'])) & 65535))
    for kind, body, record in f['records']:
        if kind in (0x1001, 0x1002) and len(body) >= 4:
            pc = u16(body, 0)
            if pack_record(kind, body) != record:
                raise ValueError('Metadata checksum differs')
            if kind == 0x1002 and pc == at:
                cursor = at
                for v in added:
                    label = (v['label']+'\r\n').encode('cp1251')
                    final.extend(pack_record(kind, struct.pack('<HH', cursor, len(label))+label))
                    v['pc'] = cursor; cursor += len(bytes.fromhex(v['codeHex']))
            if pc >= at:
                record = pack_record(kind, struct.pack('<H', pc+delta)+body[2:])
        final.extend(record)
    final = bytes(final); checked = frame(final)
    if checked['image'] != bytes(result) or checked['payload'] != f['payload'] or source.read_bytes() != raw:
        raise ValueError('Round trip/source preservation failed')
    return final, {'revision': 14, 'sourceSHA256': sha(raw), 'sourceBytes': len(raw),
                   'candidateSHA256': sha(final), 'candidateBytes': len(final), 'addedProgramBytes': delta,
                   'insertionPC': at, 'addedNetworks': added, 'registers': REGISTERS,
                   'retainedRegisters': RETAINED, 'retainedSignature': [2847, 2848],
                   'markerAddress': 'R3049', 'marker': MARKER,
                   'faultSources': ['R2801', 'R2809', 'R2817'], 'eventCodes': [1, 80],
                   'reuseExistingFiveSecondSampleCaches': True,
                   'freshFaultReadWorksWithoutREADY': True, 'zeroOnTimeoutUsed': False,
                   'existingControlCountR2363Preserved': True, 'newDisplayCount': 'R3077',
                   'dataFramesAndPollTablesChanged': False, 'driveResetCommandsAdded': False,
                   'allOriginalNetworkBytesPreserved': True, 'nativeF8Observed': False,
                   'memoryLimits': 'New volatile/retained words have no direct operands/symbols in exact r10; native indirection/HMI/retain review remains',
                   'equipmentActions': 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'out', 'report'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    if len({v.resolve() for v in (a.source, a.out, a.report)}) != 3 or any(v.exists() or v.is_symlink() for v in (a.out, a.report)):
        raise ValueError('Distinct source and NEW output/report required')
    final, report = prepare(a.source)
    with a.out.open('xb') as f:
        f.write(final)
    with a.report.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2); f.write('\n')
    print('Created PLC native-fault candidate:', len(final), 'bytes;', sha(final))
    print('No equipment access. Native memory review/F8 and bench validation remain.')


if __name__ == '__main__':
    main()
