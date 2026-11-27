"""Build the Oshsky r3 first-event recorder in a separate PDW. No controller I/O."""
import argparse
import hashlib
import struct
from pathlib import Path

from build_cascade_r10 import add, bit, cmp, d, mov, r, w
from build_manual_no_sensor_pdw import u16
from build_oshsky_cascade_r3 import assemble, network_inventory
from check_native_drive_edit_02 import unpack

SOURCE = '683753c3388b0e404cd12bf2325c7c9f967fe3978e0b1b2529278f4a9df8a402'
MAGIC = 27426
SLOTS = {'poll4': 3240, 'drop4': 3320, 'mode4': 3400, 'other_mode': 3480}
# The slot number is committed last. A zero number means the entire slot is empty.
FIELDS = ('sequence cause target scan queue_gen accepted_gen write_gen read_gen stop_gen '
          'D300 D301 M601 M602 D250 D251 D230 D231 D232 M667 D320 D321 D340 D341 '
          'D360 D361 D240 D241 D242 D243 R2402 R2405 R2406 M1601 M1602 X4 Y4 '
          'M613 M713 D263 M1617 M1623 M1627 R2393 M1633 M363 R2503 R2513 R2840 '
          'M1533 M1637 R2183 R2193 M1563 M1624 M1625 M1626 R2390 R2391 R2392 '
          'M1600 M707 M321 stop4_in stop_all_in T90 M1680 M694 M1613 M691 M681 M671 '
          'M1629 prev_run session_lost permit_lost M1564').split()
assert len(FIELDS) <= 80
REGS = set(range(3200, 3226)) | {base+i for base in SLOTS.values() for i in range(len(FIELDS))}
ALWAYS = w(0x4fe8)


def flag(op, name):
    kind, n = name[0], int(name[1:])
    if kind == 'T':
        return w({'ORG':0x4000, 'AND':0x8000}[op] + 0x200 + n)
    return bit(op, n, kind)


def ensure_space(source, raw, image, registers=REGS):
    end = u16(image, 270)
    words = set(struct.unpack('>' + 'H' * ((end-512)//2), image[512:end]))
    if any(r(n) in words or ('R'+str(n)).encode() in raw for n in registers):
        raise ValueError('Existing register in recorder range')
    for pc in range(512, end-7, 2):
        if image[pc:pc+2] != w(0xf4ce):
            continue
        src, dst, last = struct.unpack_from('>3H', image, pc+2)
        for operand in (src, dst):
            if 0xa00 <= operand < 0x2800 and not operand % 2:
                first = (operand-0xa00)//2
                if any(first <= n <= first+last for n in registers):
                    raise ValueError('Existing block transfer touches recorder range')
    for address, table in unpack(source)['tables'].items():
        base = int(address[1:])
        if any(base <= n < base+1+7*len(table['rows']) for n in registers):
            raise ValueError('Existing table storage')
        for row in table['rows']:
            if row[3] == 12 and any(row[4] <= n < row[4]+row[2] for n in registers):
                raise ValueError('Existing RTU local buffer')


def plan(codes):
    before = {}
    serial = 0
    anchors = {}
    for key in codes:
        anchors.setdefault(key.split(' | ')[0], []).append(key)

    def insert(ref, label, body):
        nonlocal serial
        if ref in codes:
            key = ref
        else:
            matches = anchors[ref]
            if len(matches) != 1:
                raise ValueError('Ambiguous source '+ref)
            key = matches[0]
        serial += 1
        before.setdefault(key, []).append((f'95.SD{serial:04} | {label}', body))

    def setword(ref, label, gate, number, value, literal=True):
        insert(ref, label, gate + mov(r(number), value, literal))

    def copybit(ref, name, gate, dst):
        setword(ref, 'ZERO_'+name, gate, dst, 0)
        setword(ref, 'TRUE_'+name, gate + flag('AND', name), dst, 1)

    def incr(ref, label, gate, number):
        insert(ref, label, gate + add(r(number), r(number), r(3204)))

    first = '10.01'
    # R3200/01 are signature and complement. Commit signature after all valid words.
    invalid = cmp('ORG', '<>', r(3200), MAGIC) + cmp('OR', '<>', r(3201), 65535-MAGIC)
    for n in (3202, 3203, 3205, 3206, 3207, 3208, 3209, 3210, 3211, *SLOTS.values()):
        setword(first, 'INIT_'+str(n), invalid, n, 0)
    setword(first, 'INIT_COMPLEMENT', invalid, 3201, 65535-MAGIC)
    setword(first, 'INIT_SIGNATURE', cmp('ORG','<>',r(3200),MAGIC), 3200, MAGIC)
    # No edge from a previously powered session. Valid slots survive a CPU restart
    # if the controller retains these registers. No operator writes are required.
    for n in (3206, 3207, 3208, 3209, 3210, 3211, 3212):
        setword(first, 'BOOT_'+str(n), bit('ORG',1924), n, 0)
    setword(first, 'CONSTANT_ONE', ALWAYS, 3204, 1)
    incr(first, 'SCAN_16', ALWAYS, 3203)
    for name, n in [('M387',3214), ('M311',3215)]:
        copybit(first, name, ALWAYS, n)
    for n in (3217,3218):
        setword(first, 'SCAN_EDGE_CLEAR_'+str(n), ALWAYS, n, 0)
    setword('65.M071', 'FIRST_SESSION_LOST',
            cmp('ORG','=',r(3206),1)+bit('ANDN',1623), 3217, 1)
    setword('65.M183', 'FIRST_PERMIT_LOST',
            cmp('ORG','=',r(3206),1)+bit('ANDN',1633), 3218, 1)

    # Mode/frequency owner and queue phase remain original. Generation 0 means
    # no completion observed for this manual mode selection. Reset tags on pick.
    pick = bit('ORG',1607)
    for n in (3208,3209,3210,3211,3212):
        setword('65.M078', 'NEW_JOB_CLEAR_'+str(n), pick, n, 0)
    incr('65.M078', 'MAN_QUEUE_GENERATION', pick, 3207)
    setword('65.M078', 'GEN_ZERO_RESERVED', pick+cmp('AND','=',r(3207),0), 3207, 1)
    accept = bit('ORG',694)+bit('AND',1601)+cmp('AND','=',d(251),r(2402),False)
    setword('65.36A', 'ACCEPT_MATCHING_TARGET', accept, 3208, r(3207), False)
    for ref, pulse, dest, wr, fc in [('65.40',668,3209,321,6),('65.44',683,3210,341,3),
                                      ('65.50',693,3211,361,3)]:
        for t in range(1,5):
            gate = (bit('ORG',pulse)+bit('AND',1601)+cmp('AND','=',d(251),t)
                    +cmp('AND','=',r(2402),t)+cmp('AND','=',d(wr),256*t+fc))
            setword(ref, f'DONE_P{t}_GENERATION_{dest}', gate, dest, r(3208), False)
    # Observe the actual set of M667 around each native worker decision.
    for start, after, why in [('65.40','65.41',10),('65.44','65.45',11),
                              ('65.47','65.48',13),('65.50','65.51',14)]:
        copybit(start, 'M667', ALWAYS, 3213)
        edge = (bit('ORG',667)+bit('AND',1601)+cmp('AND','=',r(3213),0)
                +cmp('AND','=',r(3212),0))
        if why == 11:
            setword(after, 'READ_VALUE_MISMATCH', edge+bit('ANDN',681), 3212, 12)
        setword(after, 'FIRST_WORKER_CAUSE_'+str(why), edge, 3212, why)

    scratch = dict(scan=3203, queue_gen=3207, accepted_gen=3208, write_gen=3209,
                   read_gen=3210, stop_gen=3211, stop4_in=3214, stop_all_in=3215,
                   prev_run=3206, session_lost=3217, permit_lost=3218)

    def freeze(ref, slot, trigger, reason, target):
        base = SLOTS[slot]
        setword(ref, slot+'_IDLE', ALWAYS, 3205, 0)
        setword(ref, slot+'_TRIGGER', trigger+cmp('AND','=',r(base),0), 3205, 1)
        gate = cmp('ORG','=',r(3205),1)
        for off, name in enumerate(FIELDS[1:],1):
            if name == 'cause':
                src, literal = reason
            elif name == 'target':
                src, literal = target
            elif name in scratch:
                src, literal = r(scratch[name]), False
            elif name[0] in 'RD':
                src = (r if name[0]=='R' else d)(int(name[1:]))
                literal = False
            else:
                copybit(ref, name, gate, base+off)
                continue
            setword(ref, slot+'_'+name, gate, base+off, src, literal)
        incr(ref, slot+'_SEQUENCE', gate, 3202)
        setword(ref, slot+'_COMMIT', gate, base, r(3202), False)

    running = cmp('ORG','=',r(3206),1)
    # Capture before the original RST M613 and retain the normal WR at that scan.
    freeze('65.08 | VFD2_COMM_OK_RESET#2','poll4',
           running+bit('AND',602)+bit('AND',601)+cmp('AND','=',d(301),0x0403),
           (1,True),(4,True))
    # Both selected-target and other-target faults are retained separately.
    failure = bit('ORG',1629)+bit('AND',1601)
    setword('65.M116', 'QUEUE_CAUSE_FALLBACK', failure+cmp('AND','=',r(3212),0), 3212, 15)
    for slot,rel in [('mode4','='),('other_mode','<>')]:
        freeze('65.M116',slot,failure+cmp('AND',rel,r(2402),4),(r(3212),False),(r(2402),False))
    # Observe the output and both exported start permits after their own producers.
    ref = '95.M043'
    setword(ref,'DROP_PENDING', ALWAYS, 3216, 0)
    for name, n, kind in [('OUT',4,'Y'),('LATCH',363,'M'),('PERMIT',1633,'M')]:
        setword(ref,'DROP_'+name,running+bit('ANDN',n,kind),3216,1)
    freeze(ref,'drop4',cmp('ORG','=',r(3216),1),(3,True),(4,True))
    setword(ref,'PREVIOUS_IDLE',ALWAYS,3206,0)
    setword(ref,'PREVIOUS_MANUAL_RUN',bit('ORG',321)+bit('AND',363)+bit('AND',4,'Y'),3206,1)
    return before


def build(source):
    raw = source.read_bytes()
    if len(raw)!=181384 or hashlib.sha256(raw).hexdigest()!=SOURCE:
        raise ValueError('Use exact field four-pump r3')
    part, rows, codes, bounds = network_inventory(raw)
    ensure_space(source, raw, part['image'])
    before = plan(codes)
    data, added, delta, space = assemble(raw,part,rows,codes,bounds,{},before)
    if source.read_bytes()!=raw:
        raise ValueError('Source changed during build')
    return data, dict(original=len(rows), added=len(added), extraBytes=delta, freeBytes=space)


if __name__ == '__main__':
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('source',type=Path)
    args.add_argument('output',type=Path)
    selected = args.parse_args()
    data, stats = build(selected.source)
    with selected.output.open('xb') as stream:
        stream.write(data)
    print(stats)
