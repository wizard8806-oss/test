#!/usr/bin/env python3
"""Build a NEW three-pump PLC copy with staged delays and fast follower stop.

Exact working manual-r3 source only. No connection to a PLC. New settings
use the existing STOP/edit/apply transaction. The original first-stage
counter stays; the second stage has a separate counter and independent preset.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_manual_no_sensor_pdw import frame, pack_record, word_sum, u16

SOURCE_SHA = '3b1ffdac9646a525b3e2113bc60c93bdaa3efc3b48ada20ee3b5246d5ca6ad9c'
MARKER = 27116
REGISTERS = list(range(2884, 2899))
sha = lambda b: hashlib.sha256(b).hexdigest()
def w(*v): return struct.pack('>'+'H'*len(v), *v)
def r(n): return 0xa00+2*n
def d(n): return 0x4000+2*n
def bit(mode, n, kind='M'):
    return w({'ORG':0x4000,'ORGN':0x5000,'AND':0x8000,'ANDN':0x9000,
              'OR':0xa000,'ORN':0xb000,'OUT':0xc000,'SET':0x1000,'RST':0}[mode]
             + ({'M':0x810,'Y':0x100,'X':0}[kind]+n))
def cmp(mode, rel, a, b, immediate=True):
    return w(0xf67f if immediate else 0xf47f,
             {'ORG':0x15,'AND':0x21,'OR':0x27}[mode]+{'=':0,'>':1,'<':2,'<>':3}[rel],a,b&65535)
def mov(a, b, immediate=True): return w(0xf5ac if immediate else 0xf4ac,b&65535,a)
def add(a, left, right):
    return w(0xc400,0x8fe7,0x6400,0x9fe7,0xf462,left,right,a)


def changes(codes):
    """Source-anchored replacements and insertions; labels are public logic only."""
    edits, before = {}, {}
    def insert(anchor, name, code):
        before.setdefault(anchor,[]).append(('65.NC' if anchor.startswith('65.') else '95.NC',name,code))
    def append(anchor, code): edits[anchor] = codes[anchor][:-2]+code+codes[anchor][-2:]
    boot = bit('ORG',1924)+cmp('AND','<>',r(2886),MARKER)
    insert('65.C001','DEFAULT_FAST_STOP_20HZ',boot+mov(r(2884),200))
    insert('65.C001','DEFAULT_SECOND_DELAY_30S',boot+mov(r(2885),30))
    insert('65.C001','CASCADE_EXTENSION_MARKER',boot+mov(r(2886),MARKER))
    insert('65.C001','COUNTER_INCREMENT_ONE',w(0x4fe8)+mov(r(2895),1))
    def valid(stop, second, high):
        return (cmp('ORG','>',r(stop),99)+cmp('AND','<',r(stop),500)
                +cmp('AND','<',r(stop),r(high),False)
                +cmp('AND','>',r(second),0)+cmp('AND','<',r(second),3601))
    insert('65.C007','PARAMETERS_INVALID_DEFAULT',w(0x4fe8)+mov(r(2891),0))
    insert('65.C007','PARAMETERS_VALID',valid(2884,2885,2121)+mov(r(2891),1))
    append('65.C007',cmp('AND','=',r(2891),1))
    append('65.C016',cmp('OR','<>',r(2884),r(2893),False)+cmp('OR','<>',r(2885),r(2894),False))
    for current, previous in ((2884,2893),(2885,2894)):
        insert('65.C023','SNAPSHOT_R'+str(current),w(0x4fe8)+mov(r(previous),r(current),False))
    # A missing/stopped/stale leader never leaves followers latched. This
    # affects follower memberships only; the leader can still start itself.
    insert('65.C025','FOLLOWERS_BLOCKED_DEFAULT',w(0x4fe8)+mov(r(2890),1))
    insert('65.C025','ABOVE_LIMIT_DEFAULT',w(0x4fe8)+mov(r(2898),0))
    insert('65.C025','ABOVE_OR_EQUAL_LIMIT',cmp('ORG','>',d(871),r(2884),False)+cmp('OR','=',d(871),r(2884),False)+mov(r(2898),1))
    common=(bit('ORG',740)+bit('AND',1140)+cmp('AND','=',d(870),1)
            +cmp('AND','>',d(871),0)+cmp('AND','<',d(871),501)
            +cmp('AND','=',r(2898),1))
    insert('65.C025','FRESH_LEADER_ABOVE_LIMIT',common+mov(r(2890),0))
    insert('65.C025','INVALID_LEADER_NUMBER',cmp('ORG','<',d(270),1)+cmp('OR','>',d(270),3)+mov(r(2890),1))
    for i in range(3):
        for mode,n,kind in (('LEADER_COMMAND',470+i,'M'),('RELAY',i+1,'Y'),
                            ('READY',i+1,'X'),('LINK',610+i,'M')):
            insert('65.C025','LEADER%d_%s_LOST'%(i+1,mode),
                   cmp('ORG','=',d(270),i+1)+bit('ANDN',n,kind)+mov(r(2890),1))
    for n in range(900,904):
        insert('65.C025','FAST_CLEAR_D'+str(n),cmp('ORG','=',r(2890),1)+mov(d(n),0))
    for n in range(1210,1214):
        insert('65.C025','FAST_CLEAR_M'+str(n),cmp('ORG','=',r(2890),1)+bit('RST',n))
    append('65.C069',cmp('AND','=',r(2890),0))
    # Existing change/availability/demand gates reset the first counter.
    # The separate second counter cannot inherit elapsed first-stage time.
    insert('65.C075','FIRST_COUNTER_STAGE_RESET',cmp('ORG','<>',d(906),0)+mov(d(910),0))
    insert('65.C075','SECOND_COUNTER_RESET',bit('ORGN',1244)+cmp('OR','<>',d(906),1)+mov(r(2896),0))
    def snapshot(anchor, suffix):
        insert(anchor,'FIRST_PRESET_'+suffix,w(0x4fe8)+mov(r(2889),r(2123),False))
        insert(anchor,'FIRST_ELAPSED_'+suffix,w(0x4fe8)+mov(r(2897),d(910),False))
        insert(anchor,'SECOND_PRESET_'+suffix,cmp('ORG','=',d(906),1)+mov(r(2889),r(2885),False))
        insert(anchor,'SECOND_ELAPSED_'+suffix,cmp('ORG','=',d(906),1)+mov(r(2897),r(2896),False))
    snapshot('65.C079','BEFORE_TICK')
    old=codes['65.C079'];assert old.count(w(d(910),r(2123)))==1
    edits['65.C079']=old.replace(w(d(910),r(2123)),w(r(2897),r(2889)))
    old=codes['65.C082'];assert old[:2]==bit('ORG',1248)
    edits['65.C082']=old[:2]+cmp('AND','=',d(906),0)+add(d(910),d(910),r(2895))
    insert('65.C083','SECOND_COUNTER_ELAPSED',bit('ORG',1248)+cmp('AND','=',d(906),1)+add(r(2896),r(2896),r(2895)))
    snapshot('65.C087','AFTER_TICK')
    old=codes['65.C087'];assert old.count(w(d(910),r(2123)))==2
    edits['65.C087']=old.replace(w(d(910),r(2123)),w(r(2897),r(2889)))
    for active, shadow in ((2884,2887),(2885,2888)):
        insert('95.S021','EDIT_COPY_R'+str(active),bit('ORG',1467)+mov(r(shadow),r(active),False))
        insert('95.S050','APPLY_R'+str(active),bit('ORG',1469)+mov(r(active),r(shadow),False))
    insert('95.S034','EDIT_INVALID_DEFAULT',w(0x4fe8)+mov(r(2892),0))
    insert('95.S034','EDIT_PARAMETERS_VALID',valid(2887,2888,2161)+mov(r(2892),1))
    append('95.S034',cmp('AND','=',r(2892),1))
    return edits, before


def prepare(source):
    raw=Path(source).read_bytes()
    if len(raw)!=185409 or sha(raw)!=SOURCE_SHA: raise ValueError('Use exact working manual-r3; preserve all other saves')
    part=frame(raw);image=part['image'];end=u16(image,270)
    rows=[]
    for kind, body, _ in part['records']:
        if kind==0x1002 and len(body)>4:
            label=body[4:].decode('cp1251').strip()
            if label[:2].isdigit():rows.append((u16(body,0),label))
    if len(rows)!=2020 or rows!=sorted(rows): raise ValueError('Source network inventory differs')
    codes={};bounds={}
    for i,(pc,label) in enumerate(rows):
        stop=rows[i+1][0] if i+1<len(rows) else end-2
        prefix=label.split(' | ')[0]
        if prefix in codes: continue
        codes[prefix]=image[pc:stop];bounds[prefix]=(pc,stop)
    for n in REGISTERS:
        if any(image[p:p+2]==w(r(n)) for p in range(512,end,2)):
            raise ValueError('Possible existing reference in new register range')
        if ('R'+str(n)).encode('ascii') in raw: raise ValueError('Metadata reference in new register range')
    edits,before=changes(codes);operations=[];new_rows=[];serial=0
    for anchor, group in before.items():
        pc=bounds[anchor][0];code=b''
        for prefix,name,body in group:
            serial+=1;label=prefix+'%03d | '%serial+name
            new_rows.append({'sourcePC':pc,'relativePC':len(code),'label':label,'codeHex':body.hex()});code+=body
        operations.append((pc,pc,code,anchor+' additions'))
    for anchor, body in edits.items():
        a,z=bounds[anchor];operations.append((a,z,body,anchor))
    operations.sort(key=lambda x:(x[0],x[1]));delta=sum(len(b)-(z-a) for a,z,b,_ in operations)
    if delta<=0 or image[-delta:]!=b'\xff'*delta or u16(image,264)<delta//2:raise ValueError('Program capacity differs')
    def shifted(pc):return pc+sum(len(b)-(z-a) for a,z,b,_ in operations if z<=pc)
    result=bytearray();cursor=0
    for a,z,b,_ in operations:
        if a<cursor:raise ValueError('Overlapping code edits')
        result.extend(image[cursor:a]);result.extend(b);cursor=z
    result.extend(image[cursor:len(image)-delta])
    struct.pack_into('<HH',result,262,u16(image,262)+delta//2,u16(image,264)-delta//2)
    for at in (268,270):struct.pack_into('<H',result,at,u16(image,at)+delta)
    struct.pack_into('<H',result,200,(u16(image,200)+word_sum(result[256:512])-word_sum(image[256:512]))&65535)
    struct.pack_into('<H',result,202,word_sum(result[512:u16(result,270)]))
    encoded=bytes(v^part['key'][i%1280] for i,v in enumerate(result))
    final=bytearray(raw[:part['first']+4]);final.extend(encoded);final.extend(raw[part['second']:part['checksum']]);final.extend(struct.pack('<H',(sum(encoded)+sum(part['payload']))&65535))
    for kind,body,record in part['records']:
        if kind in (0x1001,0x1002) and len(body)>=4:
            pc=u16(body,0)
            if pack_record(kind,body)!=record:raise ValueError('Unexpected metadata checksum')
            if kind==0x1002:
                for added in (v for v in new_rows if v['sourcePC']==pc):
                    # Inserted block precedes the old network, after all earlier operations.
                    start=pc+sum(len(b)-(z-a) for a,z,b,_ in operations if z<pc or (z==pc and a<pc))
                    label=(added['label']+'\r\n').encode('cp1251');newpc=start+added['relativePC']
                    final.extend(pack_record(kind,struct.pack('<HH',newpc,len(label))+label))
                    added['pc']=newpc
            newpc=shifted(pc)
            if newpc!=pc:record=pack_record(kind,struct.pack('<H',newpc)+body[2:])
        final.extend(record)
    final=bytes(final);check=frame(final)
    if check['image']!=bytes(result) or check['payload']!=part['payload'] or Path(source).read_bytes()!=raw:raise ValueError('Native round trip/source preservation differs')
    report={'revision':10,'sourceSHA256':sha(raw),'candidateSHA256':sha(final),'candidateBytes':len(final),
            'addedProgramBytes':delta,'registers':REGISTERS,'marker':MARKER,
            'stopThresholdDefaultHz':20,'secondDelayDefaultSeconds':30,'stageDelayPresetsIndependent':True,
            'newNetworks':new_rows,'changedNetworks':[{'anchor':a,'beforeHex':codes[a].hex(),'afterHex':b.hex()} for a,b in edits.items()],
            'manualPressureExceptionPreserved':True,'pollTablesChanged':False,'physicalOutputNetworksChanged':False,
            'nativeF8Observed':False,'equipmentActions':0}
    return final,report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','out','report'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    if len({v.resolve() for v in (a.source,a.out,a.report)})!=3 or any(v.exists() or v.is_symlink() for v in (a.out,a.report)):raise ValueError('Distinct source and NEW output/report required')
    data,report=prepare(a.source)
    with a.out.open('xb') as f:f.write(data)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Built NEW cascade r10:',len(data),'bytes;',sha(data),'; native F8 remains.')


if __name__=='__main__':main()
