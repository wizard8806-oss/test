#!/usr/bin/env python3
"""Split the confirmed failing original-alarm full control into two Open tests.

First undo only logo relinking. Second keep only the already isolated page
and macro changes, undoing the three existing-widget edits too. No new
production revision, PLC changes, native file execution or GUI claims.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from prepare_alarm_open_differential import replace_blocks
from skm_alarm_catalog import qs,validate_alarm_catalog,validate_alarm_identities
from skm_project_header import read_project_header

SOURCE_SHA='790f095467a359f1896938ab424bb4adb5365af2992ef68046e72d8a53d4700e'
LOGO_NEW='C:/Users/user/CodexProjects/pump-station/.worktrees/station002-fault-reset-local-15/assets/automatikakg.jpg'
LOGO_OLD='C:/Users/user/Desktop/Pump_HMI_35/automatikakg.jpg'
GROUP=re.compile(bytes.fromhex('00010017')+b'\x00\x00\x00[\x01-\x7f]'+bytes.fromhex('000100'))
OUTPUTS=('OPEN_OLD_LOGO.skm','OPEN_PAGES_AND_MACRO_ONLY.skm')
sha=lambda raw:hashlib.sha256(raw).hexdigest()
u32=lambda value:struct.pack('>I',value)


def widget(raw,identity,size):
    hits=[m.start() for m in re.finditer(re.escape(qs(identity)),raw)]
    if len(hits)!=2:raise ValueError('Expected two identity mirrors: '+identity)
    start=max(m.start() for m in GROUP.finditer(raw,0,hits[0]))
    end=next(m.start() for m in GROUP.finditer(raw,hits[-1]+len(qs(identity))))
    if end-start!=size:raise ValueError('Reviewed widget boundary differs: '+identity)
    return start,end,raw[start:end]


def properties(raw,identity,count):
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
    if len(found)!=1:raise ValueError('Reviewed property table differs: '+identity)
    return found[0]


def restore_properties(raw,identity,expected,replacement):
    start,end,values=properties(raw,identity,204)
    for index,value in expected.items():
        if values[index]!=value:raise ValueError('Unexpected current field: '+identity+' '+str(index))
    for index,value in replacement.items():values[index]=value
    return raw[:start]+u32(len(values))+b''.join(map(qs,values))+raw[end:]


def replace_exact(raw,old,new,count):
    if raw.count(qs(old))!=count:raise ValueError('QString mirror count differs: '+old)
    return raw.replace(qs(old),qs(new))


def prepare(source):
    source=Path(source);raw=source.read_bytes()
    if len(raw)!=1461495 or sha(raw)!=SOURCE_SHA:
        raise ValueError('Use exact failing CONTROL_FULL_ORIGINAL_ALARMS.skm')
    if raw.count(qs(LOGO_NEW))!=1:raise ValueError('Logo reference differs')
    logo_edit=(raw.index(qs(LOGO_NEW)),qs(LOGO_NEW),qs(LOGO_OLD))
    other=[]
    start,end,old=widget(raw,'SB6010',2379)
    new=restore_properties(old,'SB6010',{48:'12',49:'12',56:'Screen13',57:'12'},
                           {48:'3',49:'3',56:'Screen13',57:'3'})
    other.append((start,old,new))
    start,end,old=widget(raw,'SB24002',2335)
    new=restore_properties(old,'SB24002',{48:'14',49:'14',56:'Screen15',57:'14'},
                           {48:'12',49:'12',56:'Screen13',57:'12'})
    new=replace_exact(new,'Коды ПЧ','Запуски ПЛК',7)
    other.append((start,old,new))
    start,end,old=widget(raw,'ND8278',2305)
    new=replace_exact(old,'R3077#1#6#1#3077#R#1#','R2363#1#6#1#2363#R#1#',1)
    new=replace_exact(new,'R3077','R2363',1)
    other.append((start,old,new))
    outputs=[]
    for index,edits in enumerate(([logo_edit],[logo_edit]+other)):
        result=replace_blocks(raw,edits)
        if validate_alarm_catalog(result)['groupCount']!=1 or validate_alarm_identities(result)!=[0]:
            raise ValueError('Original alarm changed')
        if read_project_header(result)!=read_project_header(raw):raise ValueError('Header changed')
        outputs.append((result,dict(name=OUTPUTS[index],bytes=len(result),sha256=sha(result),
            pageCount=16,alarmGroups=1,undoLogoRelink=True,
            undoExistingWidgetEdits=bool(index),completeInversePreservation=True,nativeOpenObserved=False)))
    if source.read_bytes()!=raw:raise ValueError('Source changed')
    return outputs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.source.is_symlink() or args.out_dir.is_symlink() or args.out_dir.exists():
        raise ValueError('Regular source and NEW output folder required')
    outputs=prepare(args.source);args.out_dir.mkdir(parents=True,exist_ok=False)
    for data,meta in outputs:
        with (args.out_dir/meta['name']).open('xb') as stream:stream.write(data)
        print((args.out_dir/meta['name']).resolve(),meta['bytes'],meta['sha256'])
    report=dict(kind='TWO OPEN-ONLY CONTROLS; NOT production',sourceSHA256=SOURCE_SHA,
        outputs=[meta for data,meta in outputs],sourcePreserved=True,PLCChanged=False,
        nativeOpenObserved=False,hardwareActions=0)
    with (args.out_dir/'controls.json').open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')


if __name__=='__main__':main()
