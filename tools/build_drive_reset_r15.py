#!/usr/bin/env python3
"""Prepare a source-locked, STOP-only Port3 VFD reset service.

One operator sequence starts one FC06 request (PDU2000=7), then FC03
verification. Session/window guards prevent queued old HMI requests from
becoming new operations. Existing Port3 workers yield while this service
owns the bus; Port2/CL50 and run/protection logic are not rewritten.
Native F7/F8 and real-device acceptance are still required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_manual_no_sensor_pdw import frame, pack_record, word_sum, u16
from build_vfd_fault_export_r14 import inventory, w, r, cmp, mov, add

SOURCE_SHA = '35d22baa604527bd0b29fd99ed27bd8a2154ddf3768d6ade32d6137ce750d182'
SOURCE_BYTES = 201327
PROFILE = 27131
RETAINED = (2857, 2858, 2859)
WORDS = list(range(3200, 3289))
BITS = list(range(1815, 1840)) + list(range(1871, 1880))
PRE_ANCHOR = '65.G01 | AUTO_FREQ_INIT'
CALL_ANCHOR = '65.T001 | P1_FREQ_ROW_DONE'
sha = lambda b: hashlib.sha256(b).hexdigest()
d = lambda n: 0x4000+2*n


def bit(mode, n, kind='M'):
    base = {'M': 0x810, 'X': 0, 'Y': 0x100, 'T': 0x200}[kind]
    op = {'ORG': 0x4000, 'ORGN': 0x5000, 'AND': 0x8000, 'ANDN': 0x9000,
          'OR': 0xa000, 'ORN': 0xb000, 'LD': 0x6000, 'LDN': 0x7000,
          'OUT': 0xc000, 'SET': 0x1000, 'RST': 0}[mode]
    return w(op+base+n)


def variable(mode, rel, left, right):
    return cmp(mode, rel, r(left), r(right), False)


def constant(mode, rel, left, right):
    return cmp(mode, rel, r(left), right)


def movement(dst, src, immediate=True):
    return mov(r(dst), src if immediate else r(src), immediate)


def timer(index, ticks):
    return w(0xfd81, ticks, 0x390+2*index)


def make_plan():
    pre, calls = [], []
    def emit(label, code, destination=pre):
        destination.append({'label': '65.VR%03d | %s' % (len(pre)+len(calls)+1, label),
                            'codeHex': code.hex()})
    def actions(label, condition, values):
        # Native fan-out scaffold, checked with the vendor node converter.
        for off in range(0, len(values), 8):
            chunk = values[off:off+8]
            body = chunk[0] if len(chunk) == 1 else (
                w(0xc400, 0x8fea)+chunk[0]+b''.join(w(0x6400)+v for v in chunk[1:]))
            emit(label+('_'+str(off//8) if len(values)>8 else ''), condition+body)
    boot = bit('ORG', 1924)
    # BT_M length is encoded as count-1. Use a private eight-WORD zero
    # template; no overlap propagation or assumptions about old RAM values.
    actions('BOOT_ZERO_TEMPLATE', boot, [movement(n, 0) for n in range(3280, 3288)])
    for dst in list(range(3200, 3240, 8))+[3260, 3270]:
        emit('BOOT_CLEAR_'+str(dst), boot+w(0xf4ce, r(3280), r(dst), 7))
    actions('BOOT_WINDOW', boot, [movement(3225, 1), movement(3278, 1)])
    emit('CONSTANT_ONE', w(0x4fe8)+movement(3278, 1))
    emit('RETAIN_GUARD_DEFAULT', boot+movement(3279, 0))
    for number, value in ((2858, PROFILE), (2859, PROFILE ^ 65535)):
        emit('RETAIN_GUARD_'+str(number), boot+constant('AND', '<>', number, value)+movement(3279, 1))
    actions('RETAIN_FIRST_USE', boot+constant('AND', '=', 3279, 1),
            [movement(2857, 0), movement(2858, PROFILE), movement(2859, PROFILE ^ 65535)])
    emit('BOOT_SESSION_ADVANCE', boot+add(r(2857), r(2857), r(3278)))
    emit('BOOT_SESSION_WRAP', boot+constant('AND', '=', 2857, 0)+movement(2857, 1))
    actions('PUBLISH_CONTRACT', w(0x4fe8), [movement(3200, PROFILE), movement(3215, 2857, False)])
    write_table = [0xa550, 0x0701, 1, 3, 1, 12, 3288, 4, 8193, 0]
    read_table = [0xa550, 0x0701, 1, 1, 7, 12, 2800, 4, 4097, 0]
    actions('BOOT_TABLES', boot, [movement(3240+i, v) for i, v in enumerate(write_table)]
            +[movement(3250+i, v) for i, v in enumerate(read_table)]+[movement(3288, 7)])
    # Reject continuous Port3 execution rather than changing system settings.
    emit('COPY_SYSTEM_EXECUTION_MODE', w(0x4fe8)+mov(r(3238), d(4044), False))
    # Native FUN18 AND, Sb immediate. Only high-byte 56h plus Port3 bit3
    # selects continuous execution; all other settings retain one-edge mode.
    emit('READ_SYSTEM_EXECUTION_MODE', w(0x4fe8, 0xf6c6, r(3238), 0xff08, r(3238)))
    emit('SINGLE_TRANSACTION_MODE', constant('ORG', '<>', 3238, 0x5608)+bit('OUT', 1835))
    emit('STOP_PERMIT', bit('ORG', 305)+bit('ANDN', 306)+bit('AND', 51, 'T')
         +bit('ANDN', 8, 'X')+bit('ANDN', 9, 'X')
         +b''.join(bit('ANDN', i, 'Y') for i in range(1, 5))+bit('OUT', 1833))
    for i in range(3):
        emit('TARGET_ELIGIBLE_'+str(i+1), bit('ORG', 1748+i)
             +constant('AND', '=', 3043+i, 1)+constant('AND', '=', 2500+i, 0)
             +constant('AND', '<>', 3040+i, 0)+bit('OUT', 1817+i))
    # Snapshot before actions: each state transition occurs at most once/scan.
    emit('PHASE_SNAPSHOT', w(0x4fe8)+movement(3230, 3201, False))
    emit('FRAME_SNAPSHOT', w(0x4fe8, 0xf4ce, r(3216), r(3232), 5))
    emit('SESSION_INVERSE_SUM', w(0x4fe8)+add(r(3268), r(3234), r(3235)))
    emit('WINDOW_INVERSE_SUM', w(0x4fe8)+add(r(3269), r(3236), r(3237)))
    emit('WINDOW_ADVANCE_PREVIOUS', bit('ORG', 125, 'T')+movement(3226, 3225, False))
    emit('WINDOW_ADVANCE', bit('ORG', 125, 'T')+add(r(3225), r(3225), r(3278)))
    emit('WINDOW_WRAP', constant('ORG', '=', 3225, 0)+movement(3225, 1))
    emit('WINDOW_CLOCK', bit('ORGN', 125, 'T')+timer(125, 20))
    emit('FRAME_HEADER_NEW', bit('ORGN', 1924)+constant('AND', '<>', 3232, 0)
         +constant('AND', '<>', 3233, 0)+variable('AND', '<>', 3233, 3222)
         +variable('AND', '=', 3234, 3215)+constant('AND', '=', 3268, 65535)+bit('OUT', 1838))
    emit('FRAME_WINDOW_VALID', variable('ORG', '=', 3236, 3225)
         +variable('OR', '=', 3236, 3226)+constant('AND', '=', 3269, 65535)+bit('OUT', 1816))
    emit('FRAME_IDLE_WINDOW', constant('ORG', '=', 3230, 0)+bit('AND', 1816)+bit('OUT', 1873))
    for i, mask in enumerate((1,2,4)):
        emit('FRAME_TARGET_P'+str(i+1), bit('ORG', 1838)+constant('AND', '=', 3232, mask)+bit('OUT', 1874+i))
        emit('FRAME_ACCEPT_P'+str(i+1), bit('ORG', 1874+i)+bit('AND', 1873)
             +bit('AND', 1833)+bit('AND', 1835)+bit('AND', 1817+i)+bit('OUT', 1877+i))
    emit('ACTIVE_ELIGIBLE_DEFAULT', w(0x4fe8)+movement(3279, 0))
    for i in range(3):
        emit('ACTIVE_ELIGIBLE_'+str(i+1), constant('ORG', '=', 3202, i+1)
             +bit('AND', 1817+i)+movement(3279, 1))
    emit('ACTIVE_ELIGIBLE', constant('ORG', '=', 3279, 1)+bit('OUT', 1815))
    emit('PORT_IDLE', bit('ORG', 1936)+bit('ANDN', 600)+bit('AND', 827)
         +bit('AND', 947)+bit('AND', 1033)
         +b''.join(bit('ANDN', n) for n in (665, 664, 669, 694, 670, 680, 690))+bit('OUT', 1839))
    emit('ABORT', bit('ORGN', 1833)+bit('ORN', 1835)+bit('OR', 124, 'T')
         +constant('AND', '<>', 3230, 0)+constant('AND', '<', 3230, 40)+bit('OUT', 1823))
    emit('WRITE_GOOD', constant('ORG', '=', 3230, 20)+bit('AND', 1826)+bit('ANDN', 1825)
         +bit('ANDN', 1823)+constant('AND', '=', 3260, 0)
         +variable('AND', '=', 3261, 3228)+bit('OUT', 1836))
    emit('READ_GOOD', constant('ORG', '=', 3230, 30)+bit('AND', 1829)+bit('ANDN', 1828)
         +bit('ANDN', 1823)+constant('AND', '=', 3270, 0)
         +variable('AND', '=', 3271, 3229)+bit('OUT', 1837))
    emit('WRITE_RESULT_SNAPSHOT', constant('ORG', '=', 3230, 20)+bit('AND', 1826)
         +movement(3211, 3260, False))
    emit('READ_RESULT_SNAPSHOT', constant('ORG', '=', 3230, 30)+bit('AND', 1829)
         +movement(3212, 3270, False))
    emit('WRITE_START', constant('ORG', '=', 3230, 10)+bit('AND', 1839)
         +bit('AND', 1833)+bit('AND', 1835)+bit('AND', 1815)+bit('ANDN', 1823)+bit('OUT', 1821))
    emit('READ_START', constant('ORG', '=', 3230, 25)+bit('AND', 1936)
         +bit('ANDN', 1824)+bit('ANDN', 1823)+bit('OUT', 1822))
    for i in range(3):
        emit('QUALIFIED_SAMPLE_'+str(i+1), bit('ORG', 1837)
             +constant('AND', '=', 3202, i+1)+bit('OUT', 1830+i))
    actions('CLEANUP', constant('ORG', '=', 3230, 40)+bit('ANDN', 1824)+bit('ANDN', 1827),
            [movement(3201, 0), movement(3231, 0)])
    actions('DISPATCH', bit('ORG', 1821), [movement(3201, 20), movement(3231, 1)])
    emit('COUNT_DISPATCH', bit('ORG', 1821)+add(r(3205), r(3205), r(3278)))
    emit('WAIT_VERIFY', bit('ORG', 1836)+movement(3201, 25))
    emit('DISPATCH_VERIFY', bit('ORG', 1822)+movement(3201, 30))
    # Errors never create another start edge. Only a new operator frame can retry.
    fail_write = constant('ORG', '=', 3230, 20)+bit('AND', 1826)+bit('ANDN', 1836)+bit('ANDN', 1823)
    fail_read = constant('ORG', '=', 3230, 30)+bit('AND', 1829)+bit('ANDN', 1837)+bit('ANDN', 1823)
    for label, condition, detail in (('WRITE_FAILED', fail_write, 11), ('READ_FAILED', fail_read, 10),
                                      ('ABORTED', bit('ORG', 1823), 12)):
        actions(label, condition, [movement(3201, 40), movement(3204, detail)])
        for i in range(3):
            emit(label+'_P'+str(i+1), condition+constant('AND', '=', 3202, i+1)+movement(3206+i, 4))
    for i in range(3):
        emit('ABORT_NEEDS_STOP_P'+str(i+1), bit('ORG', 1823)+bit('ANDN', 1833)
             +constant('AND', '=', 3202, i+1)+movement(3206+i, 3))
    emit('ABORT_STOP_REASON', bit('ORG', 1823)+bit('ANDN', 1833)+movement(3204, 9))
    emit('ABORT_MODE_REASON', bit('ORG', 1823)+bit('ANDN', 1835)+movement(3204, 13))
    # A queued target may lose its cache/fault before dispatch. Do not reset it.
    qbad = constant('ORG', '=', 3230, 10)+bit('ANDN', 1815)+bit('ANDN', 1823)
    actions('QUEUED_DATA_LOST', qbad, [movement(3201, 40), movement(3204, 8)])
    for i in range(3):
        emit('QUEUED_DATA_LOST_P'+str(i+1), qbad+constant('AND', '=', 3202, i+1)+movement(3206+i, 4))
    for i in range(3):
        cond = bit('ORG', 1830+i)
        actions('VERIFIED_CODE_P'+str(i+1), cond,
                [movement(3214, 2801+8*i, False), movement(3201, 40)])
        actions('VERIFIED_CLEAR_P'+str(i+1), cond+constant('AND', '=', 2801+8*i, 0),
                [movement(3206+i, 2), movement(3204, 2)])
        actions('FAULT_REMAINS_P'+str(i+1), cond+constant('AND', '<>', 2801+8*i, 0),
                [movement(3206+i, 4), movement(3204, 16)])
    actions('FRAME_ACK', bit('ORG', 1838), [movement(3222, 3233, False), movement(3223, 3232, False),
            movement(3224, 15), movement(3216, 0)])
    for i, mask in enumerate((1, 2, 4)):
        base = bit('ORG', 1874+i)
        rejects = [
            ('BUSY', constant('AND', '<>', 3230, 0), 4, 5),
            ('EXPIRED', constant('AND', '=', 3230, 0)+bit('ANDN', 1816), 4, 14),
            ('STOP', bit('AND', 1873)+bit('ANDN', 1833), 3, 3),
            ('MODE', bit('AND', 1873)+bit('AND', 1833)+bit('ANDN', 1835), 4, 13),
            ('DATA', bit('AND', 1873)+bit('AND', 1833)
             +bit('AND', 1835)+bit('ANDN', 1817+i), 4, 8),
        ]
        for name, extra, result, detail in rejects:
            actions('REJECT_'+name+'_P'+str(i+1), base+extra,
                    [movement(3206+i, result), movement(3224, detail)])
        accept = bit('ORG', 1877+i)
        actions('ACCEPT_P'+str(i+1), accept, [movement(3201, 10), movement(3202, i+1),
                movement(3206+i, 1), movement(3204, 1), movement(3224, 1),
                movement(3213, 3040+i, False), movement(3214, 65535), movement(3231, 0),
                movement(3242, i+1), movement(3252, i+1), movement(3256, 2800+8*i),
                movement(3228, ((i+1)<<8)|6), movement(3229, ((i+1)<<8)|3)])
    emit('PENDING', constant('ORG', '<>', 3201, 0)+bit('OUT', 1834))
    emit('BUS_OWNER', constant('ORG', '=', 3231, 1)+bit('OUT', 1820))
    actions('PUBLIC_DEFAULTS', w(0x4fe8), [movement(3209, 0), movement(3227, 0),
            movement(3210, 3231, False), mov(r(3203), 0x390+2*124, False)])
    emit('PUBLIC_STOP', bit('ORG', 1833)+movement(3227, 1))
    for i in range(3):
        emit('PERMIT_WEIGHT_'+str(i+1), w(0x4fe8)+movement(3279, 1<<i))
        emit('PUBLIC_PERMIT_'+str(i+1), bit('ORG', 1833)+bit('AND', 1835)
             +bit('AND', 1817+i)+constant('AND', '=', 3201, 0)+add(r(3209), r(3209), r(3279)))
    emit('REQUEST_TIMEOUT', bit('ORG', 1834)+timer(124, 50))
    emit('WRITE_ABORT', constant('ORG', '<>', 3201, 20)+bit('OR', 1823)
         +bit('AND', 1824)+bit('OUT', 1871))
    emit('READ_ABORT', constant('ORG', '<>', 3201, 30)+bit('OR', 1823)
         +bit('AND', 1827)+bit('OUT', 1872))
    for name, start, phase, sr, wr, abort, outputs in (
        ('RESET_FC06_PORT3', 1821, 20, 3240, 3260, 1871, (1824, 1825, 1826)),
        ('VERIFY_FC03_PORT3', 1822, 30, 3250, 3270, 1872, (1827, 1828, 1829))):
        code = bit('ORG', start)+bit('AND', 1820)+bit('AND', 1936)+bit('AND', 1833)
        code += bit('AND', 1835)+constant('AND', '=', 3201, phase)+w(0x7fe8)+bit('LD', abort)
        code += w(0xf31b, r(sr), r(wr))
        for flag, relay in zip((0x6ffc, 0x6ffd, 0x6ffe), outputs):
            code += w(flag)+bit('OUT', relay)
        emit(name, code, calls)
    return pre, calls


def prepare(source):
    source = Path(source); raw = source.read_bytes()
    if len(raw) != SOURCE_BYTES or sha(raw) != SOURCE_SHA:
        raise ValueError('Use the exact user-accepted PLC; preserve other native saves')
    f, rows = inventory(raw); image = f['image']; end = u16(image, 270)
    for n in WORDS+list(RETAINED):
        if any(image[p:p+2] == w(r(n)) for p in range(512, end, 2)) or ('R'+str(n)).encode() in raw:
            raise ValueError('Existing register reference: R'+str(n))
    for n in BITS:
        token = 0x810+n
        if any((v & 4095) == token and v>>12 in (0,1,4,5,6,7,8,9,10,11,12)
               for v in struct.unpack('>'+'H'*((end-512)//2), image[512:end])):
            raise ValueError('Possible existing bit reference: M'+str(n))
    pre, calls = make_plan(); anchors = {name: pc for pc, name in rows}
    if PRE_ANCHOR not in anchors or CALL_ANCHOR not in anchors:
        raise ValueError('Reset insertion anchors differ')
    insertion = {anchors[PRE_ANCHOR]: pre, anchors[CALL_ANCHOR]: calls}
    patches = {}; modified = []
    simple = {'65.F02 | VFD_FREQ_POLL_CREDIT': 1834,
              '65.F34 | VFD_FREQ_PORT_IDLE': 1820,
              '65.35 | VFD_MODE_WRITE_START_PULSE': 1834,
              '65.S29 | STATUS_READ_START': 1834}
    fresh = {'65.T002 | P1_FREQ_NEW_SAMPLE': 1830, '65.T011 | P2_FREQ_NEW_SAMPLE': 1831,
             '65.T020 | P3_FREQ_NEW_SAMPLE': 1832}
    invalid = {'65.T005 | P1_FREQ_INVALIDATE': 1830, '65.T014 | P2_FREQ_INVALIDATE': 1831,
               '65.T023 | P3_FREQ_INVALIDATE': 1832}
    for i, (pc, label) in enumerate(rows):
        stop = rows[i+1][0] if i+1<len(rows) else end-2
        old = image[pc:stop]; new = old
        if label in simple:
            if label == '65.35 | VFD_MODE_WRITE_START_PULSE':
                if new[-4:-2] != w(0x8fe4):raise ValueError('Mode start spare contact differs')
                new = new[:-4]+bit('ANDN', simple[label])+new[-2:]
            else:
                new = new[:-2]+bit('ANDN', simple[label])+new[-2:]
        if label in fresh:
            new = new[:-2]+bit('OR', fresh[label])+new[-2:]
        if label in invalid:
            new = new[:-2]+bit('ANDN', invalid[label])+new[-2:]
        if w(0xf31b) in new and label != '65.00 | MODBUS_MASTER_POLL':
            p = new.index(w(0xf31b)); where = new.rfind(w(0x7fe8), 0, p)
            if where < 0:
                raise ValueError('Port3 input shape differs: '+label)
            new = new[:where]+bit('ANDN', 1820)+new[where:]
        if new != old:
            patches[pc] = (old, new)
            modified.append({'label': label, 'pc': pc, 'oldHex': old.hex(), 'newHex': new.hex()})
    if not (set(simple)|set(fresh)|set(invalid)) <= set(anchors):
        raise ValueError('Expected worker/cache networks missing')
    edits = [(pc, b'', b''.join(bytes.fromhex(v['codeHex']) for v in group)) for pc, group in insertion.items()]
    edits += [(pc, old, new) for pc, (old, new) in patches.items()]
    edits.sort(key=lambda v: (v[0], len(v[1])))
    delta = sum(len(new)-len(old) for _, old, new in edits)
    if delta % 2 or delta > u16(image, 264)*2 or image[-delta:] != b'\xff'*delta:
        raise ValueError('Reset code exceeds remaining CPU capacity: '+str(delta))
    def shifted(pc, include_insert=True):
        return pc+sum(len(new)-len(old) for at, old, new in edits
                      if at < pc or (at == pc and not old and include_insert))
    out = bytearray(); cursor = 0
    for at, old, new in edits:
        if at < cursor or image[at:at+len(old)] != old:
            raise ValueError('Overlapping reset edit')
        out.extend(image[cursor:at]); out.extend(new); cursor = at+len(old)
    out.extend(image[cursor:]); result = out[:-delta]
    struct.pack_into('<HH', result, 262, u16(image,262)+delta//2, u16(image,264)-delta//2)
    for at in (268,270):struct.pack_into('<H',result,at,shifted(u16(image,at)))
    struct.pack_into('<H',result,200,(u16(image,200)+word_sum(result[256:512])-word_sum(image[256:512]))&65535)
    struct.pack_into('<H',result,202,word_sum(result[512:u16(result,270)]))
    encoded=bytes(v^f['key'][i%1280] for i,v in enumerate(result))
    final=bytearray(raw[:f['first']+4]);final.extend(encoded);final.extend(raw[f['second']:f['checksum']])
    final.extend(struct.pack('<H',(sum(encoded)+sum(f['payload']))&65535))
    for kind, body, record in f['records']:
        if kind in (0x1001,0x1002) and len(body)>=4:
            pc=u16(body,0)
            if kind==0x1002 and pc in insertion:
                point=shifted(pc,False)
                for item in insertion[pc]:
                    label=(item['label']+'\r\n').encode('cp1251')
                    final.extend(pack_record(kind,struct.pack('<HH',point,len(label))+label))
                    item['pc']=point;point+=len(bytes.fromhex(item['codeHex']))
            if shifted(pc)!=pc:
                if pack_record(kind,body)!=record:raise ValueError('Native metadata checksum differs')
                record=pack_record(kind,struct.pack('<H',shifted(pc))+body[2:])
        final.extend(record)
    final=bytes(final);checked=frame(final)
    if checked['image']!=bytes(result) or checked['payload']!=f['payload'] or source.read_bytes()!=raw:
        raise ValueError('Frame/source preservation failed')
    return final, {'sourceSHA256':sha(raw),'sourceBytes':len(raw),'candidateSHA256':sha(final),
                  'candidateBytes':len(final),'addedProgramBytes':delta,'remainingProgramBytes':u16(result,264)*2,
                  'newNetworks':pre+calls,'modifiedNetworks':modified,'registers':WORDS,
                  'retainedRegisters':list(RETAINED),'relays':BITS,'timers':[124,125],
                  'profile':PROFILE,'request':'R3216..3221 six WORDs; mask/seq/session/inverse/window/inverse',
                  'readOnlyStatus':'R3200..3231 32WORDs','port':3,'CL50Port2Changed':False,
                  'write':'FC06 PDU0x2000 value7; FUN150 address8193',
                  'verify':'FC03 PDU0x1000 qty7 -> existing per-drive RX buffer; qualified sample only on good tag/result',
                  'singleEdgeSystemModeRequired':True,'systemD4044Changed':False,
                  'newRUNOutputs':0,'unrelatedProgramAndTablesChanged':False,
                  'nativeF8Observed':False,'hardwareResetExecuted':False,
                  'limitations':'Offline candidate; native F7/memory/retention/F8 and stopped real-drive reset validation still required'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','out','report'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if len({v.resolve() for v in (a.source,a.out,a.report)})!=3 or any(v.is_symlink() for v in (a.source,a.out,a.report)):
        raise ValueError('Distinct regular paths required')
    if a.out.exists() or a.report.exists():raise ValueError('NEW output/report required')
    data,report=prepare(a.source)
    with a.out.open('xb') as f:f.write(data)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Created STOP-only VFD reset candidate:',len(data),sha(data))
    print('Added',report['addedProgramBytes'],'program bytes; free',report['remainingProgramBytes'],'bytes. Native checks remain.')


if __name__=='__main__':main()
