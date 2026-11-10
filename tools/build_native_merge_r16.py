#!/usr/bin/env python3
"""Merge full alarms/navigation into the user's native-saved code-page base.

Preserve its scene headers, layout, C/Batch and16-page metadata. Borrow
only alarm definitions/catalog from exact r15f. The optional alarms-only
mode is a diagnostic fallback, not a production release.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from prepare_alarm_open_differential import replace_blocks
from skm_alarm_catalog import qs,validate_alarm_catalog,validate_alarm_identities,word_bit_semantics
from skm_page_storage import read_page_storage

SOURCE_SHA='506dec71f62efadca3cc6660707306d2076c4122a83f24b1568c908a95c29b4a'
DONOR_SHA='2fe47083c0fbbb2fc9d31342c1ab76d3b220c81afa0f60c61d1ea4eed2c9676e'
LOGO_OLD='C:/Users/user/Desktop/Pump_HMI_35/automatikakg.jpg'
LOGO_TARGET='C:/Users/user/Documents/HMI/Samkoon/Automatika визитка print.jpg'
GROUP=re.compile(bytes.fromhex('00010017')+b'\x00\x00\x00[\x01-\x7f]'+bytes.fromhex('000100'))
NEW_BUTTONS=('SB91030','SB91031','SB91032','SB91033','SB92040','SB92041','SB92042')
sha=lambda raw:hashlib.sha256(raw).hexdigest()
u32=lambda value:struct.pack('>I',value)


def widget(raw,identity):
    hits=[m.start() for m in re.finditer(re.escape(qs(identity)),raw)]
    if len(hits)!=2:raise ValueError('Expected two widget-name mirrors: '+identity)
    start=max(m.start() for m in GROUP.finditer(raw,0,hits[0]))
    end=next(m.start() for m in GROUP.finditer(raw,hits[-1]+len(qs(identity))))
    return start,raw[start:end]


def properties(raw,identity,count=204):
    found=[]
    for match in re.finditer(re.escape(u32(count)),raw):
        pos=match.start()+4;values=[]
        try:
            for _ in range(count):
                if pos+4>len(raw):raise ValueError()
                size=int.from_bytes(raw[pos:pos+4],'big');pos+=4
                if size%2 or size>4000 or pos+size>len(raw):raise ValueError()
                values.append(raw[pos:pos+size].decode('utf-16-be'));pos+=size
            if values[19]==identity:found.append((match.start(),pos,values))
        except (ValueError,UnicodeError):pass
    if len(found)!=1:raise ValueError('Reviewed property vector differs: '+identity)
    return found[0]


def route(raw,identity,target):
    if not 1<=target<=16:raise ValueError('Unreviewed navigation target')
    start,end,values=properties(raw,identity)
    for index in (48,49,57,60):values[index]=str(target-1)
    values[56]='Screen'+str(target)
    return raw[:start]+u32(len(values))+b''.join(map(qs,values))+raw[end:]


def macro_mirrors(raw):
    marker='#include "MacroInit.h"'.encode('utf-16-be');blocks=[]
    for match in re.finditer(re.escape(marker),raw):
        at=match.start()-4;size=int.from_bytes(raw[at:at+4],'big');blocks.append(raw[at:at+4+size])
    if len(blocks)!=2 or blocks[0]!=blocks[1]:raise ValueError('Two identical C-source mirrors required')
    return blocks


def prepare(source,donor,alarms_only=False,logo_target=LOGO_TARGET):
    source,donor=Path(source),Path(donor);raw=source.read_bytes();full=donor.read_bytes()
    if len(raw)!=1461830 or sha(raw)!=SOURCE_SHA:raise ValueError('Use exact user-saved C_native_code_pages.skm')
    if len(full)!=1480015 or sha(full)!=DONOR_SHA:raise ValueError('Use exact full r15f only as alarm donor')
    if not logo_target.lower().endswith(('.jpg','.jpeg','.png')) or '\0' in logo_target:raise ValueError('Invalid logo reference')
    logo_target=logo_target.replace('\\','/')
    storage=read_page_storage(raw);read_page_storage(full)
    before,target=validate_alarm_catalog(raw),validate_alarm_catalog(full)
    if before['groupCount']!=2 or target['groupCount']!=7:raise ValueError('Reviewed alarm source counts differ')
    a,b=before['definitions']['groups'][0],target['definitions']['groups'][0]
    if raw[a['start']:a['end']]!=full[b['start']:b['end']]:raise ValueError('Original station alarm differs')
    edits=[]
    for field in ('definitions','directory'):
        a,b=before[field],target[field]
        edits.append((a['start'],raw[a['start']:a['end']],full[b['start']:b['end']]))
    if not alarms_only:
        for identity,destination in [('SB6010',13),('SB24002',15)]+[(name,None) for name in NEW_BUTTONS]:
            start,old=widget(raw,identity)
            if destination is None:
                name=properties(old,identity)[2][56]
                if not re.fullmatch(r'Screen[0-9]+',name):raise ValueError('Navigation name differs')
                destination=int(name[6:])
            new=route(old,identity,destination)
            if identity=='SB24002':
                if new.count(qs('Запуски ПЛК'))!=7:raise ValueError('Boot/code button caption mirrors differ')
                new=new.replace(qs('Запуски ПЛК'),qs('Коды ПЧ'))
            if new!=old:edits.append((start,old,new))
        start,old=widget(raw,'ND8278');a,b='R2363'.encode('utf-16-be'),'R3077'.encode('utf-16-be')
        if old.count(a)!=3 or len(a)!=len(b):raise ValueError('Counter address mirrors differ')
        edits.append((start,old,old.replace(a,b)))
        if raw.count(qs(LOGO_OLD))!=1:raise ValueError('Original logo reference differs')
        edits.append((raw.index(qs(LOGO_OLD)),qs(LOGO_OLD),qs(logo_target)))
    result=replace_blocks(raw,edits);after=validate_alarm_catalog(result)
    if read_page_storage(result)['pageCount']!=16 or validate_alarm_identities(result)!=list(range(7)):
        raise ValueError('Page/alarm identity count changed')
    if macro_mirrors(result)!=macro_mirrors(raw):raise ValueError('Native C-source changed')
    old=target['definitions'];new=after['definitions']
    if word_bit_semantics(full[old['start']:old['end']])!=word_bit_semantics(result[new['start']:new['end']]):
        raise ValueError('Alarm word/bit/message semantics changed')
    if not alarms_only:
        for identity in ('SB6010','SB24002')+NEW_BUTTONS:
            _,block=widget(result,identity);v=properties(block,identity)[2]
            if any(v[i]!=str(int(v[56][6:])-1) for i in (48,49,57,60)):
                raise ValueError('Navigation mirrors remain inconsistent')
        _,block=widget(result,'ND8278')
        if 'R2363'.encode('utf-16-be') in block or block.count('R3077'.encode('utf-16-be'))!=3:
            raise ValueError('Counter address not updated consistently')
    if source.read_bytes()!=raw or donor.read_bytes()!=full:raise ValueError('Input changed')
    return result,dict(kind='ALARMS-ONLY DIAGNOSTIC' if alarms_only else 'FULL native-base r16 candidate',
        sourceBytes=len(raw),sourceSHA256=sha(raw),alarmDonorSHA256=sha(full),candidateBytes=len(result),candidateSHA256=sha(result),
        pageCount=16,alarmGroups=7,alarmGroupIds=list(range(7)),alarmBitMappings=268,
        sceneHeadersLayoutAndCFromNativeSource=True,completeInversePreservation=True,
        allNavigationMirrorsUpdated=not alarms_only,activeCounter='source preserved' if alarms_only else 'R3077',
        logoReference=LOGO_OLD if alarms_only else logo_target,logoBytesEmbedded=False,
        nativeLoadingSaverSettingsConfigured=False,PLCChanged=False,nativeOpenObserved=False,
        nativeCompileObserved=False,hardwareActions=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--donor',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True);parser.add_argument('--alarms-only',action='store_true')
    parser.add_argument('--logo-target',default=LOGO_TARGET)
    target=parser.add_mutually_exclusive_group(required=True);target.add_argument('--out',type=Path);target.add_argument('--check',type=Path)
    args=parser.parse_args();candidate=args.out or args.check;paths=(args.source,args.donor,candidate,args.report)
    if (len({p.resolve() for p in paths})!=4 or any(p.is_symlink() for p in paths)
            or args.report.exists() or (args.out and candidate.exists())):
        raise ValueError('Distinct regular paths and NEW output/report required')
    data,report=prepare(args.source,args.donor,args.alarms_only,args.logo_target)
    if args.check:
        if candidate.read_bytes()!=data:raise ValueError('Candidate differs from exact native-base merge')
    else:
        with candidate.open('xb') as stream:stream.write(data)
    with args.report.open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('PASS' if args.check else 'Created',candidate.resolve(),len(data),sha(data),'Native acceptance pending')


if __name__=='__main__':main()
