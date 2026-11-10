#!/usr/bin/env python3
"""Create native-Open isolation copies from exact accepted HMI3599.

These are diagnostic editor files, NOT a replacement production release.
Open-only: no Download/Simulator/process commands. Split the failed r15a
changes into independent pages/alarm/macro layers, preserving other bytes.
The known original is included as an exact same-session control.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from build_fault_reset_hmi_r15 import prepare,apply,SOURCE_SHA,SOURCE_BYTES
from repair_skm_section_index import read_directory
from skm_project_header import read_project_header

sha=lambda b:hashlib.sha256(b).hexdigest()
PAGES={'new pages15/16','root page count','new page common-data entries','page identity map'}
ALARMS={'native fault alarm groups'}
MACRO={'fault/reset C mirror','packed variables','native variables'}


def prepare_cases(source,extended=False):
    source=Path(source);raw=source.read_bytes()
    if len(raw)!=SOURCE_BYTES or sha(raw)!=SOURCE_SHA:raise ValueError('Exact last WORKING user source3599 required')
    full,review=prepare(source);directory=read_directory(raw)
    if sha(full)!='d08b5ec1358e84bdc640acdda30ed164038d57c6d3be39a1ad08d68e81176551':raise ValueError('Unexpected r15a reconstruction; review source/producer first')
    edits=[];delta=0
    for item in review['edits']:
        at,old_len,new_len,label=item['offset'],item['oldBytes'],item['newBytes'],item['label']
        new=full[at+delta:at+delta+new_len];old=raw[at:at+old_len]
        if not label.startswith('directory '):edits.append((at,old,new,label))
        delta+=new_len-old_len
    if apply(raw,[(e['offset'],raw[e['offset']:e['offset']+e['oldBytes']],
                  full[e['offset']+sum(x['newBytes']-x['oldBytes'] for x in review['edits'] if x['offset']<e['offset']):
                       e['offset']+sum(x['newBytes']-x['oldBytes'] for x in review['edits'] if x['offset']<e['offset'])+e['newBytes']],e['label'])
                  for e in review['edits']])!=full:raise ValueError('Producer edit reconstruction differs')
    all_labels={label for _,_,_,label in edits}
    plans=[('CONTROL_WORKING',set()),('A_PAGES_ONLY',PAGES),('B_ALARMS_ONLY',ALARMS),('C_MACRO_ONLY',MACRO)]
    if extended:plans += [('D_FULL_WITHOUT_ALARMS',all_labels-ALARMS),
                         ('E_FULL_WITHOUT_MACRO',all_labels-MACRO),
                         ('F_FULL_WITHOUT_PAGES',all_labels-PAGES-{'navigation SB24002'})]
    results=[]
    for name,labels in plans:
        selected=[edit for edit in edits if edit[3] in labels]
        def shifted(address):
            if any(at<address<at+len(old) for at,old,_,_ in selected):raise ValueError('Pointer inside edited field')
            return address+sum(len(new)-len(old) for at,old,new,_ in selected if at<=address)
        pointers=[]
        for i,address in enumerate(directory['entries']):
            pointers.append((directory['offset']+4+8*i,struct.pack('>Q',address),struct.pack('>Q',shifted(address)),'directory entry'+str(i)))
        pointers.append((directory['locatorOffset'],struct.pack('>Q',directory['offset']),struct.pack('>Q',shifted(directory['offset'])),'directory locator'))
        changes=selected+pointers;result=apply(raw,changes);checked=read_directory(result);header=read_project_header(result)
        if checked['entries']!=[shifted(n) for n in directory['entries']]:raise ValueError('Directory relocation differs')
        inverse=[];shift=0
        for at,old,new,label in sorted(changes,key=lambda x:x[0]):
            inverse.append((at+shift,new,old,label));shift+=len(new)-len(old)
        if apply(result,inverse)!=raw:raise ValueError('Full inverse failed: '+name)
        if not labels and result!=raw:raise ValueError('Control must be byte-identical')
        if header['resolution']!=(800.,480.) or header['pageCount']!=(16 if PAGES<=labels else 14):raise ValueError('Header/count differs')
        results.append((name,result,dict(name=name,file='OPEN_TEST_'+name+'.skm',bytes=len(result),sha256=sha(result),
                        changedLayers=sorted(labels),pageCount=header['pageCount'],model=header['model'],resolution=list(header['resolution']),
                        completeInversePreservation=True,nativeOpenObserved=False)))
    if source.read_bytes()!=raw:raise ValueError('Source changed')
    return results,dict(purpose='EDITOR OPEN ISOLATION ONLY; NOT production HMI; no Download/Simulator',
        sourceSHA256=SOURCE_SHA,sourceBytes=SOURCE_BYTES,producerR15aSHA256=sha(full),
        cases=[report for _,_,report in results],PLCChanged=False,hardwareActions=0,nativeOpenObserved=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--extended',action='store_true');a=p.parse_args()
    if a.out_dir.exists() or a.out_dir.is_symlink() or a.source.is_symlink():raise ValueError('NEW output directory and regular source required')
    cases,report=prepare_cases(a.source,a.extended)
    a.out_dir.mkdir(parents=True,exist_ok=False)
    for _,data,item in cases:
        with (a.out_dir/item['file']).open('xb') as f:f.write(data)
    with (a.out_dir/'open-isolation.json').open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Created',len(cases),'editor-Open isolation files; control is exact accepted source. Native outcomes pending.')
if __name__=='__main__':main()
