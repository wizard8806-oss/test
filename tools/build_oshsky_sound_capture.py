"""Append a passive, retained first sound-rearm record to the saved Oshsky r3e.

No serial requests, alarm outputs, service tokens or control registers are written.
R3562=2 commits both halves of the same PLC scan. Addresses are field-readable.
"""
import argparse
import hashlib
from pathlib import Path

from build_cascade_r10 import add, bit, cmp, d, mov, r
from build_oshsky_cascade_r3 import assemble, network_inventory
from build_oshsky_stop4_capture import ALWAYS, ensure_space

SOURCE_SHA = 'fa73a14cebefd7562ace571402a233b2ae4a36809ed589e908548b7e62004fa5'
MAGIC = 27427
REGISTERS = set(range(3560, 3610))
# Values prefixed by pre/post are read before SAVE_ALARM and after CL50 decisions.
FIELDS = {
    3560:'schema',3561:'complement',3562:'status',3563:'cpu_start_count',
    3564:'event_cpu_start',3565:'heartbeat',3566:'scan',3567:'pre_generation',
    3568:'post_generation',3569:'received_token',3570:'pre_expected_token',
    3571:'post_expected_token',3572:'current_low',3573:'current_high_and_boot',
    3574:'published_high',3575:'previous_low',3576:'previous_high',
    3577:'rising_low',3578:'rising_high',3579:'first_bit_plus_one',
    3580:'new_alarm',3581:'pre_muted',3582:'post_muted',3583:'pre_desired',
    3584:'post_desired',3585:'last_mode',3586:'pending_mode',3587:'phase',
    3588:'phase_snapshot',3589:'retry',3590:'result0',3591:'result1',
    3592:'result_state',3593:'tx_count',3594:'last_request',3595:'port2_D1320',
    3596:'port2_D1321',3597:'port2_busy',3598:'port2_error',3599:'port2_done',
    3600:'transfer_OK',3601:'transfer_failure',3602:'mute_accepted',
    3603:'captured_at_boot',3604:'armed',3605:'last_mute_gen',
    3606:'last_mute_boot',3607:'last_mute_heartbeat',3608:'previously_muted',
}


def plan(codes):
    anchors = {key.split(' | ')[0]: key for key in codes}
    groups = {}
    serial = 0

    def emit(ref, name, code):
        nonlocal serial
        serial += 1
        groups.setdefault(anchors[ref], []).append((f'96.AR{serial:03} | {name}', code))

    def word(ref, number, gate, value, literal=True):
        emit(ref, FIELDS.get(number, 'WEIGHT'), gate + mov(r(number), value, literal))

    def boolean(ref, number, gate, relay):
        word(ref, number, gate, 0)
        word(ref, number, gate + bit('AND', relay), 1)

    begin, pre, post = '10.01', '96.L103', '96.L159'
    invalid = cmp('ORG','<>',r(3560),MAGIC) + cmp('OR','<>',r(3561),65535-MAGIC)
    for n in (3562, 3563, 3604, 3605, 3606, 3607, 3608):
        word(begin, n, invalid, 0)
    word(begin,3561,invalid,65535-MAGIC)
    word(begin,3560,cmp('ORG','<>',r(3560),MAGIC),MAGIC)
    # Do not present an incomplete capture if power failed between pre and post.
    word(begin,3562,bit('ORG',1924)+cmp('AND','=',r(3562),1),0)
    word(begin,3609,bit('ORG',1924),1)
    emit(begin,'CPU_START',bit('ORG',1924)+add(r(3563),r(3563),r(3609)))
    gate = bit('ORG',1801) + cmp('AND','=',r(3604),1) + cmp('AND','=',r(3562),0)
    word(pre,3562,gate,1)
    pending = cmp('ORG','=',r(3562),1)
    for dst,src in {3564:3563,3565:2840,3566:3203,3567:2678,3569:2676,
                    3570:2679,3572:2550,3573:2551,3583:2660}.items():
        word(pre,dst,pending,r(src),False)
    for dst,relay in [(3580,1801),(3581,1802),(3603,1924)]:
        boolean(pre,dst,pending,relay)
    for n in range(3575,3580):
        word(pre,n,pending,0)
    for index in range(24):
        hi = int(index >= 16)
        word(pre,3609,pending,1 << (index % 16))
        prev = pending + bit('AND',1840+index)
        rise = pending + bit('AND',1550+index) + bit('ANDN',1840+index)
        for gate,dst in [(prev,3575+hi),(rise,3577+hi)]:
            emit(pre,'PACK_'+str(index),gate+add(r(dst),r(dst),r(3609)))
        word(pre,3579,rise+cmp('AND','=',r(3579),0),index+1)
    for dst,src in {3568:2678,3571:2679,3574:2551,3584:2660,3585:2661,3586:2662,
                    3587:2663,3588:2664,3589:2665,3590:2666,3591:2667,
                    3592:2668,3593:2669,3594:2671}.items():
        word(post,dst,pending,r(src),False)
    for dst,src in [(3595,1320),(3596,1321)]:
        word(post,dst,pending,d(src),False)
    for dst,relay in [(3582,1802),(3597,1810),(3598,1811),(3599,1812),
                      (3600,1807),(3601,1808),(3602,1803)]:
        boolean(post,dst,pending,relay)
    word(post,3562,pending,2)
    mute_edge=bit('ORG',1802)+cmp('AND','=',r(3608),0)+cmp('AND','=',r(3562),0)
    for n,src in [(3605,2678),(3606,3563),(3607,2840)]:
        word(post,n,mute_edge,r(src),False)
    word(post,3604,mute_edge,1)
    boolean(post,3608,ALWAYS,1802)
    return groups


def build(source):
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('Expected saved Oshsky four-pump r3e')
    part, rows, codes, bounds = network_inventory(raw)
    ensure_space(source,raw,part['image'],REGISTERS)
    result, added, delta, free = assemble(raw,part,rows,codes,bounds,{},plan(codes))
    return result, dict(original=len(rows), added=len(added), extraBytes=delta, freeBytes=free)


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source',type=Path);ap.add_argument('output',type=Path)
    args=ap.parse_args()
    data, stats=build(args.source)
    with args.output.open('xb') as file:
        file.write(data)
    print(stats)
