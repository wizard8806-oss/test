"""Build the Oshsky four-drive native poll and fault publication from saved r3f.

The original nine tables and their read/write workers stay in the project. Only
the normal read-only worker uses a working copy of the existing row descriptors.
"""
import hashlib
import struct
from pathlib import Path

from build_cascade_r10 import add, bit, cmp, d, mov, r, w
from build_manual_no_sensor_pdw import u16
from build_oshsky_cascade_r3 import assemble, network_inventory

SOURCE = 'f867e7ac2492b8359b48792d7e7b9d7330dd784d20abf6200302181186d118a8'
CORE = (0, 3, 16, 17, 8, 12, 13, 14)  # Four complete snapshots, four pressure readings.
AUX = (1, 2, 4, 5, 6, 7, 9, 10, 11, 15)
TABLE = 3650
MAGIC = 27428
ALWAYS = w(0x4fe8)


def build(source):
    raw = Path(source).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE:
        raise ValueError('Expected saved four-pump r3f')
    part, rows, codes, bounds = network_inventory(raw)
    regs = set(range(3610, 3636)) | set(range(TABLE, TABLE + 128))
    end = u16(part['image'], 270)
    words = list(struct.unpack('>' + 'H' * ((end-512)//2), part['image'][512:end]))
    if any(r(n) in words or ('R'+str(n)).encode() in raw for n in regs):
        raise ValueError('Occupied fault/table register')
    for off, op in enumerate(words[:-3]):
        if op == 0xf4ce:
            src, dst, count = words[off+1:off+4]
            if any(start <= r(n) < start+2*count for start in (src,dst) for n in regs):
                raise ValueError('Block transfer overlaps new registers')
    anchors = {key.split(' | ')[0]:key for key in codes}
    before, edited = {}, {}
    index = 0

    def net(anchor, name, body):
        nonlocal index
        index += 1
        before.setdefault(anchors[anchor], []).append((f'65.CNF{index:03} | {name}', body))

    def replace(anchor, old, new):
        key = anchors[anchor]
        if codes[key].count(old) != 1:
            raise ValueError('Unexpected native instruction in '+anchor)
        edited[key] = codes[key].replace(old, new)

    def copy_row(original, slot):
        return w(0xf4ce, 0x2800 + 2*(2+7*original), r(TABLE+2+7*slot), 7)

    if sorted(CORE+AUX) != list(range(18)):
        raise ValueError('A source transaction is missing or duplicated')
    boot = bit('ORG', 1924)
    net('65.00','NORMAL_HEADER',boot+mov(r(TABLE),0xa550))
    net('65.00','SHORT_COUNT_AT_BOOT',boot+mov(r(TABLE+1),0x070a))
    for slot, row in enumerate(CORE+AUX):
        net('65.00',f'ROW_{row}_TO_SLOT_{slot}',boot+copy_row(row,slot))
    for reg, value in ((3630,0),(3631,65535)):
        net('65.00',f'SCHED_INIT_{reg}',boot+mov(r(reg),value))
    replace('65.00',w(0xf31b,0x2800,d(300)),w(0xf31b,r(TABLE),d(300)))

    # Change only future auxiliary descriptors, while slot 1 is active.
    # All eight core descriptors are immutable throughout a CPU run.
    entry = cmp('ORG','=',r(3080),1)+cmp('AND','<>',r(3631),1)
    net('65.T001','PAIR_ADVANCE',entry+add(r(3630),r(3630),r(2893)))
    net('65.T001','PAIR_WRAP',cmp('ORG','>',r(3630),4)+mov(r(3630),0))
    net('65.T001','DEGRADED_SCHEDULE',entry+mov(r(TABLE+1),0x070a))
    good=entry+b''.join(bit('AND',1748+i) for i in range(4))
    net('65.T001','ALL_PRESENT',good+mov(r(TABLE+1),0x0712))
    net('65.T001','FULL_AUX_ORDER',good+mov(r(3630),0))
    for pair in range(5):
        gate=entry+cmp('AND','=',r(3630),pair)
        for side in range(2):
            net('65.T001',f'AUX_{pair}_{side}',gate+copy_row(AUX[2*pair+side],8+side))
    net('65.T001','PREVIOUS_SLOT',ALWAYS+mov(r(3631),r(3080),False))
    for i, old in enumerate(CORE[:4]):
        if i != old:
            for suffix, reg in ((1,d(300)),(5,r(3080))):
                replace(f'65.T{9*i+suffix:03}',cmp('AND','=',reg,old),cmp('AND','=',reg,i))

    # Code, own validity, last-receive heartbeat and sample sequence are
    # independent of READY, pressure, drive state, frequency value and source of RUN.
    # Retained code only clears on a positively received zero.
    missing = cmp('ORG','<>',r(3610),MAGIC)+cmp('OR','<>',r(3629),65535-MAGIC)
    for n in (*range(3612,3616),*range(3624,3628)):
        net('10.01',f'FIRST_INSTALL_{n}',missing+mov(r(n),0))
    net('10.01','INITIAL_SIGNATURE_INVERSE',missing+mov(r(3629),65535-MAGIC))
    net('10.01','FEATURE_MARKER',ALWAYS+mov(r(3610),MAGIC))
    net('96.L077','FEATURE_HEARTBEAT',ALWAYS+mov(r(3611),r(2840),False))
    # Preflight leaves exactly one writer of the shared mute word unchanged.
    net('96.L077','NEW_NATIVE_EVENT_DEFAULT',ALWAYS+mov(r(3628),0))
    for i in range(4):
        code, quality, last, seq = 3612+i,3616+i,3620+i,3624+i
        received = r(2801+8*i)
        sample = bit('ORG',1744+i)+bit('ANDN',1924)
        net('96.L077',f'P{i+1}_CHANGED_NONZERO',sample+cmp('AND','<>',received,0)
            +cmp('AND','<>',received,r(code),False)+mov(r(3628),1))
        for dst,src in ((code,received),(last,r(2840))):
            net('96.L077',f'P{i+1}_SNAP_{dst}',sample+mov(r(dst),src,False))
        net('96.L077',f'P{i+1}_SEQUENCE',sample+add(r(seq),r(seq),r(2893)))
        net('96.L077',f'P{i+1}_WRAP',sample+cmp('AND','=',r(seq),0)+mov(r(seq),1))
        net('96.L077',f'P{i+1}_UNKNOWN',ALWAYS+mov(r(quality),0))
        net('96.L077',f'P{i+1}_FRESH',bit('ORG',1748+i)+bit('ANDN',1924)+mov(r(quality),1))
    k=anchors['96.L077']
    if not codes[k].endswith(bit('OUT',1800)):
        raise ValueError('Unexpected sound owner')
    # A confirmed fault persists for the event/sound protocol across unknown
    # intervals. Live UI also requires own quality before showing it as current.
    edited[k]=codes[k][:-2]+b''.join(cmp('OR','<>',r(3612+i),0) for i in range(4))+bit('OUT',1800)
    net('96.L079','NEW_NATIVE_GENERATION',cmp('ORG','=',r(3628),1)+bit('SET',1801))
    result, added, delta, free = assemble(raw,part,rows,codes,bounds,edited,before)
    return result, dict(newNetworks=len(added),editedNetworks=len(edited),extraBytes=delta,freeWords=free//2)


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    data,stats=build(args.source)
    with args.output.open('xb') as f:
        f.write(data)
    print(stats)
