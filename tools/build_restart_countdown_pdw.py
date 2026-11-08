#!/usr/bin/env python3
"""Publish restart countdowns in a NEW fixed-three-pump PLC copy.

Read-only observation of existing restart flags/counters and T96: no change
to delays, reset/arm requests, safety logic, poll tables or physical outputs.
Only reserved display words and compiler-local TR0 are written.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_setpoint_feedback_pdw_01 import build,layout
from check_native_drive_edit_02 import unpack

SOURCE_SHA='a6e9c5c057ad324635c10e73b61f25ceb08604c4651eaaf943880f2dc176c745'
ANCHOR='40.01 | PID_INPUTS'
DISPLAY_REGISTERS=[2525,2526,2528]+list(range(2532,2540))


def words(*v):return struct.pack('>'+'H'*len(v),*v)
def r(n):return 0xa00+2*n
def sha(data):return hashlib.sha256(data).hexdigest()
def bit(op,n):return words({'ORG':0x4000,'AND':0x8000,'ANDN':0x9000}[op]+0x810+n)
def x(op,n):return words({'AND':0x8000,'ANDN':0x9000}[op]+n)
def cmp(op,relation,left,right,immediate=True):
    return words(0xf67f if immediate else 0xf47f,
                 {'ORG':0x15,'AND':0x21}[op]+{'=':0,'>':1,'<':2,'<>':3}[relation],
                 r(left),right&65535 if immediate else r(right))
def mov(dst,value,immediate=True):return words(0xf5ac if immediate else 0xf4ac,value&65535 if immediate else r(value),r(dst))
def arithmetic(dst,left,right,subtract=False):
    # Same representable EN/carry topology accepted in HP-r2.
    return words(0xc400,0x8fe7,0x6400,0x9fe7,0xf464 if subtract else 0xf462,r(left),r(right),r(dst))


def networks():
    rows=[]
    def emit(name,code):rows.append({'label':'30.CD%03d | '%(len(rows)+1)+name,'expectedCodeHex':code.hex()})
    emit('DRY_REMAINING_ZERO',words(0x4fe8)+mov(2525,0))
    emit('POWER_REMAINING_ZERO',words(0x4fe8)+mov(2526,0))
    for pending,enabled,setpoint,elapsed,destination,label in [(1753,1764,2520,2522,2525,'DRY'),(1754,1765,2521,2523,2526,'POWER')]:
        condition=(bit('ORG',enabled)+bit('AND',pending)+cmp('AND','>',elapsed,-1)+cmp('AND','<',elapsed,setpoint,False))
        emit(label+'_REMAINING',condition+arithmetic(destination,setpoint,elapsed,True))
    emit('MAX_DELAY_DRY',words(0x4fe8)+mov(2534,2525,False))
    emit('MAX_DELAY_POWER',cmp('ORG','>',2526,2534,False)+mov(2534,2526,False))
    # Vendor formatter/graph checker identifies source0450 as word T96;
    # reading its value does not write/reset its timer or its contact.
    emit('T96_VALUE_SNAPSHOT',words(0x4fe8,0xf4ac,0x0450,r(2535)))
    emit('STABILITY_DEFAULT_TWO_SECONDS',words(0x4fe8)+mov(2536,2))
    emit('STABILITY_ONE_SECOND',bit('ORG',1776)+cmp('AND','>',2535,9)+cmp('AND','<',2535,20)+mov(2536,1))
    emit('STABILITY_COMPLETE',bit('ORG',1776)+cmp('AND','>',2535,19)+mov(2536,0))
    emit('COUNTDOWN_DISABLED_DEFAULT',words(0x4fe8)+mov(2533,0))
    ready=(bit('ORG',1773)+bit('AND',1774)+bit('AND',1775)+bit('AND',1760)+bit('AND',1761)+bit('AND',1757)+bit('ANDN',1924))
    emit('COUNTDOWN_READY',ready+mov(2533,1))
    emit('INVALID_STABLE_TIMER_LOW',bit('ORG',1776)+cmp('AND','<',2535,0)+mov(2533,0))
    emit('INVALID_STABLE_TIMER_HIGH',bit('ORG',1776)+cmp('AND','>',2535,20)+mov(2533,0))
    emit('TOTAL_ZERO',words(0x4fe8)+mov(2528,0))
    emit('PRIMARY_WAIT_PLUS_STABILITY',cmp('ORG','=',2533,1)+cmp('AND','>',2534,0)+arithmetic(2528,2534,2536))
    emit('FINAL_STABILITY_WAIT',cmp('ORG','=',2533,1)+bit('AND',1776)+mov(2528,2536,False))
    emit('NO_ZERO_TIME_START_PROMISE',cmp('ORG','=',2528,0)+mov(2533,0))
    emit('STATUS_EXISTING_REASON',words(0x4fe8)+mov(2532,2524,False))
    waiting=(bit('ORG',1766)+bit('AND',1757)+x('AND',6)+x('AND',7)+bit('AND',1760)+bit('AND',1761)+cmp('AND','=',2533,0))
    emit('STATUS_WAIT_OTHER_CONDITIONS',waiting+mov(2532,5))
    emit('STATUS_DRY_COUNTDOWN',cmp('ORG','=',2533,1)+bit('AND',1753)+mov(2532,3))
    emit('STATUS_POWER_COUNTDOWN',cmp('ORG','=',2533,1)+bit('AND',1754)+mov(2532,4))
    emit('DRY_DISPLAY_CONFIGURED_WHEN_IDLE',words(0x4fe8)+mov(2538,2520,False))
    emit('POWER_DISPLAY_CONFIGURED_WHEN_IDLE',words(0x4fe8)+mov(2539,2521,False))
    emit('DRY_DISPLAY_OWN_PAUSE',bit('ORG',1764)+mov(2538,2525,False))
    emit('POWER_DISPLAY_OWN_PAUSE',bit('ORG',1765)+mov(2539,2526,False))
    emit('DRY_DISPLAY_TOTAL',cmp('ORG','=',2533,1)+bit('AND',1753)+mov(2538,2528,False))
    emit('POWER_DISPLAY_TOTAL',cmp('ORG','=',2533,1)+bit('AND',1754)+mov(2539,2528,False))
    emit('COUNTDOWN_INTERFACE_MARKER',words(0x4fe8)+mov(2537,27115))
    return rows


def prepare(source):
    source=Path(source);raw=source.read_bytes()
    if sha(raw)!=SOURCE_SHA:raise ValueError('Use exact fixed-three-pump r1; preserve other native saves')
    obj=unpack(source);part=layout(raw);end=int.from_bytes(part['image'][270:272],'little')
    if len(obj['rungs'])!=1991 or len(obj['tables'])!=9:raise ValueError('Source inventory differs')
    for n in DISPLAY_REGISTERS:
        if any(part['image'][p:p+2]==words(r(n)) for p in range(512,end,2)):raise ValueError('Display word has a possible source reference')
        for name,table in obj['tables'].items():
            ranges=[(int(name[1:]),4+8*len(table['rows']))]+[(row[4],row[2]) for row in table['rows'] if row[3]==12]
            if any(start<=n<start+length for start,length in ranges):raise ValueError('Display word overlaps a table/buffer')
    plan=networks();result,_,evidence=build(raw,plan,ANCHOR)
    if source.read_bytes()!=raw:raise ValueError('Source changed')
    report={'revision':2,'installedPumps':3,'sourceSHA256':SOURCE_SHA,'sourceBytes':len(raw),
            'candidateSHA256':sha(result),'candidateBytes':len(result),'insertedNetworks':len(plan),
            'insertionPC':next(pc for pc,label in obj['rungs'] if label==ANCHOR),
            'insertedProgramBytes':sum(len(bytes.fromhex(row['expectedCodeHex'])) for row in plan),
            'displayRegisters':DISPLAY_REGISTERS,'networks':plan,'restartControlChanged':False,
            'physicalOutputsChanged':False,'HMIFileModified':False,'nativeF8Observed':False,
            'equipmentActions':0,'formatEvidence':evidence}
    return result,report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path);p.add_argument('--report',required=True,type=Path);a=p.parse_args()
    if len({x.resolve() for x in (a.source,a.out,a.report)})!=3 or any(x.exists() or x.is_symlink() for x in (a.out,a.report)):raise ValueError('New distinct files required')
    result,report=prepare(a.source)
    with a.out.open('xb') as f:f.write(result)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Built restart countdown PLC copy:',len(result),'bytes;',sha(result))
    print('Existing control/outputs preserved. Native F8/HMI/physical checks remain.')


if __name__=='__main__':main()
