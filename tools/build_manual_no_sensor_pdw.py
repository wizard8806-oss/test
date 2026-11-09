#!/usr/bin/env python3
"""Source-locked fixed-three-pump PLC copy: MANUAL may run without pressure data.

One pressure-permit network changes. AUTO remains strict; a latched high-
pressure trip cannot be bypassed by disconnecting the pressure sensor.
Power, dry-run, emergency stop, drive readiness and frequency gates stay.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

SOURCE_SHA='780267f80d2f107c584ded1e8f48a63c65ad23d977255cdcbe895ed2b791b73b'
ANCHOR='20.03 | PRESSURE_BELOW_LIMIT'
OLD=bytes.fromhex('f67f0015207c0001c8ed')
# (strict pressure permit) OR
# (physical MANUAL: !X8 & X9, no pressure source !M102, no latched HP).
NEW=bytes.fromhex('f67f0015207c00018fe4700880099876f67f0021206e0000e426c8ed')
sha=lambda b:hashlib.sha256(b).hexdigest()
u16=lambda b,p:struct.unpack_from('<H',b,p)[0]


def word_sum(b):
    if len(b)%2:raise ValueError('Odd word range')
    return sum(struct.unpack('<'+'H'*(len(b)//2),b))&65535


def frame(raw):
    if raw[:33]!=b'Fatek WinProladder, File Format 1\r\n'[:33]:raise ValueError('Wrong PDW format')
    first=0x106+u16(raw,0x102);second=first+4+0xa000;checksum=second+4+0x6100
    if raw[first:first+4]!=struct.pack('<HH',0x180a,0xa000) or raw[second:second+4]!=struct.pack('<HH',0x180b,0x6100):raise ValueError('Wrong native frames')
    encoded,payload=raw[first+4:second],raw[second+4:checksum]
    if (sum(encoded)+sum(payload))&65535!=u16(raw,checksum):raise ValueError('Native byte checksum differs')
    seed=payload[-256:];key=bytes(seed[i%256]^b'FATEK'[i%5] for i in range(1280))
    image=bytes(v^key[i%1280] for i,v in enumerate(encoded))
    if image[:8]!=b'FBS40003' or word_sum(image[512:u16(image,270)])!=u16(image,202):raise ValueError('Decoded word checksum differs')
    records=[];at=checksum+2
    while at<len(raw):
        kind,size=struct.unpack_from('<HH',raw,at);end=at+size+6
        if end>len(raw):raise ValueError('Truncated metadata')
        records.append((kind,raw[at+4:end-2],raw[at:end]));at=end
    if not records or records[-1][0]!=0xffff:raise ValueError('Missing EOF')
    return {'first':first,'second':second,'checksum':checksum,'payload':payload,'key':key,'image':image,'records':records}


def pack_record(kind,body):
    if kind==0x1001:check=sum(body)&65535
    elif kind==0x1002:check=(sum(body[:4])+sum(v if v<128 else v-256 for v in body[4:]))&65535
    else:raise ValueError('Only known PC records may change')
    return struct.pack('<HH',kind,len(body))+body+struct.pack('<H',check)


def prepare(source):
    raw=Path(source).read_bytes()
    if len(raw)!=185409 or sha(raw)!=SOURCE_SHA:raise ValueError('Use exact three-pump/countdown r2; preserve other saves')
    old=frame(raw)
    selected=[r for r in old['records'] if r[0]==0x1002 and r[1][4:].decode('cp1251').strip()==ANCHOR]
    if len(selected)!=1:raise ValueError('Pressure-permit anchor not unique')
    pc=u16(selected[0][1],0);delta=len(NEW)-len(OLD);end=pc+len(OLD)
    if old['image'][pc:end]!=OLD or old['image'][-delta:]!=b'\xff'*delta:raise ValueError('Existing pressure permit/capacity differs')
    image=bytearray(old['image'][:pc]+NEW+old['image'][end:-delta])
    used,free=u16(image,262),u16(image,264)
    if free<delta//2:raise ValueError('Insufficient code capacity')
    struct.pack_into('<HH',image,262,used+delta//2,free-delta//2)
    for at in (268,270):
        if u16(image,at)<end:raise ValueError('Unexpected unit bounds')
        struct.pack_into('<H',image,at,u16(image,at)+delta)
    header_delta=word_sum(image[256:512])-word_sum(old['image'][256:512])
    struct.pack_into('<H',image,200,(u16(old['image'],200)+header_delta)&65535)
    struct.pack_into('<H',image,202,word_sum(image[512:u16(image,270)]))
    encoded=bytes(v^old['key'][i%1280] for i,v in enumerate(image))
    body=bytearray(raw[:old['first']+4]);body.extend(encoded);body.extend(raw[old['second']:old['checksum']]);body.extend(struct.pack('<H',(sum(encoded)+sum(old['payload']))&65535))
    shifted=0
    for kind,data,record in old['records']:
        if kind in (0x1001,0x1002) and len(data)>=4 and u16(data,0)>=end:
            if pack_record(kind,data)!=record:raise ValueError('Source metadata checksum differs')
            record=pack_record(kind,struct.pack('<H',u16(data,0)+delta)+data[2:]);shifted+=1
        body.extend(record)
    final=bytes(body);check=frame(final)
    if check['image']!=bytes(image) or check['payload']!=old['payload'] or len(check['records'])!=len(old['records']):raise ValueError('Native reconstruction differs')
    if Path(source).read_bytes()!=raw:raise ValueError('Source changed')
    return final,{'revision':3,'purpose':'physical MANUAL without pressure source; AUTO pressure guard retained','sourceBytes':len(raw),'sourceSHA256':SOURCE_SHA,
                  'candidateBytes':len(final),'candidateSHA256':sha(final),'changedNetwork':ANCHOR,'pc':pc,'originalCodeHex':OLD.hex(),'replacementCodeHex':NEW.hex(),
                  'addedProgramBytes':delta,'shiftedMetadataPCs':shifted,'newBitsOrRegisters':0,'pressureTripLatchAndResetChanged':False,
                  'otherProtectionOrPhysicalOutputNetworksChanged':False,'nativeF8Observed':False,'equipmentActions':0}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','out','report'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    if len({v.resolve() for v in (a.source,a.out,a.report)})!=3 or any(v.exists() or v.is_symlink() for v in (a.out,a.report)):raise ValueError('Distinct source and NEW output/report required')
    final,report=prepare(a.source)
    with a.out.open('xb') as f:f.write(final)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Built NEW PLC manual-no-sensor candidate:',len(final),'bytes;',report['candidateSHA256'])
    print('One pressure-permit network changed. Native F8/bench behavior remain; no equipment action.')


if __name__=='__main__':main()
