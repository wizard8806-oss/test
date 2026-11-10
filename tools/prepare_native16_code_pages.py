#!/usr/bin/env python3
"""Put only the two added page bodies into the operator-opened native16.

Keep its native scene headers, arrays, alarm groups, C/Batch, existing UI
and logo link. This isolates the new widgets from the rest of full r15f.
It is an Open-only diagnostic, not a production r15g or a complete repair.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from prepare_alarm_open_differential import replace_blocks
from skm_alarm_catalog import qs,validate_alarm_catalog
from skm_page_storage import read_page_storage

NATIVE_SHA='671ce4309579da4e2d5109c6910b35a08f2baaf7b702dbaca800f373e910c738'
DONOR_SHA='2fe47083c0fbbb2fc9d31342c1ab76d3b220c81afa0f60c61d1ea4eed2c9676e'
GROUP=re.compile(bytes.fromhex('00010017')+b'\x00\x00\x00[\x01-\x7f]'+bytes.fromhex('000100'))
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def count_at(raw,number):
    anchor=qs('Screen'+str(number))+b'\xff'*4
    if raw.count(anchor)!=1:raise ValueError('Reviewed scene anchor differs')
    return raw.index(anchor)+len(anchor)


def prepare(native,donor):
    native,donor=Path(native),Path(donor);raw=native.read_bytes();full=donor.read_bytes()
    if len(raw)!=1299291 or sha(raw)!=NATIVE_SHA:raise ValueError('Use exact operator-opened C_native_16pages.skm')
    if len(full)!=1480015 or sha(full)!=DONOR_SHA:raise ValueError('Use exact full r15f only as page-body donor')
    read_page_storage(raw);read_page_storage(full)
    counts=[count_at(raw,i) for i in (15,16)];donor_counts=[count_at(full,i) for i in (15,16)]
    if any(raw[at:at+4]!=b'\0'*4 for at in counts) or counts[1]-103!=counts[0]+4:
        raise ValueError('Expected the two native empty scenes')
    trailer=qs('92043')+struct.pack('>d',92043)
    if full.count(trailer)!=1:raise ValueError('Reviewed last-widget boundary differs')
    ends=[donor_counts[1]-103,full.index(trailer)+len(trailer)]
    changes=[];bodies=[]
    for index,(start,end,expected) in enumerate(zip(donor_counts,ends,(34,43))):
        block=full[start:end];rows=block[4:];groups=list(GROUP.finditer(rows))
        if (int.from_bytes(block[:4],'big')!=expected or len(groups)!=expected
                or not groups or groups[0].start()!=0):raise ValueError('Page-body inventory differs')
        changes.append((counts[index],b'\0'*4,block));bodies.append(block)
    result=replace_blocks(raw,changes);read_page_storage(result)
    for index,number in enumerate((15,16)):
        at=count_at(result,number);block=bodies[index]
        if result[at:at+len(block)]!=block:raise ValueError('Copied page body differs')
        if result[at-103:at]!=raw[counts[index]-103:counts[index]]:raise ValueError('Native scene header changed')
    before,after=validate_alarm_catalog(raw),validate_alarm_catalog(result)
    for field in ('definitions','directory'):
        a,b=before[field],after[field]
        if raw[a['start']:a['end']]!=result[b['start']:b['end']]:raise ValueError('Native alarms changed')
    if native.read_bytes()!=raw or donor.read_bytes()!=full:raise ValueError('Input changed')
    return result,dict(kind='ONE OPEN-ONLY native-base UI control; NOT production',
        nativeSourceSHA256=NATIVE_SHA,donorSHA256=DONOR_SHA,
        candidateBytes=len(result),candidateSHA256=sha(result),
        pageCount=16,addedObjectCounts=[34,43],alarmGroups=2,nativeSceneHeadersPreserved=True,
        completeInversePreservation=True,allOtherNativePayloadsPreserved=True,
        PLCChanged=False,nativeOpenObserved=False,nativeCompileObserved=False,hardwareActions=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',type=Path,required=True);parser.add_argument('--donor',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    target=parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--out',type=Path);target.add_argument('--check',type=Path)
    args=parser.parse_args();candidate=args.out or args.check;paths=(args.native,args.donor,candidate,args.report)
    if (len({p.resolve() for p in paths})!=4 or any(p.is_symlink() for p in paths)
            or args.report.exists() or (args.out and candidate.exists())):
        raise ValueError('Distinct regular inputs and NEW output/report required')
    result,report=prepare(args.native,args.donor)
    if args.check:
        if candidate.read_bytes()!=result:raise ValueError('Control differs from reviewed native-base transform')
    else:
        with candidate.open('xb') as stream:stream.write(result)
    with args.report.open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('PASS' if args.check else 'Created',candidate.resolve(),len(result),sha(result),'OPEN-ONLY; native outcome pending')


if __name__=='__main__':main()
