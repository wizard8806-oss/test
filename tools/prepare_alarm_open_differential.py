#!/usr/bin/env python3
"""Prepare diagnostic Open files after the full r15d rejection.

The native two-group sample gets just one generated R80 fault group.
The accepted HMI gets only the seven alarm groups and their directory.
Full r15d gets the accepted single alarm group and directory. No other
functional blocks change; all absolute section pointers are relocated.
These files isolate the refusal. Neither is a production repair.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from repair_skm_section_index import read_directory
from skm_alarm_catalog import validate_alarm_catalog, require_sk_group_limit, directory_bytes
from skm_project_header import read_project_header

ACCEPTED_SHA='359906cfd85975b9d2955f6b03b8f996761a7612fcbf37a23b95c8e5ee6c0b4c'
FULL_SHA='9a482900380d56f3bb86a625664ad09b10885fe6d9fd58b15262ef974c9bd8bb'
NATIVE_SHA='0ecac7d67dcfc42648f8f468098fadb7b84b782ae4fd6f70f944195ca0947c3f'
OUTPUTS=('OPEN_NATIVE_ONE_R80_GROUP.skm','OPEN_ONLY_ALARMS_7.skm','OPEN_FULL_WITH_ORIGINAL_ALARMS.skm')
sha=lambda data:hashlib.sha256(data).hexdigest()


def replace_blocks(raw,edits):
    edits=sorted(edits);directory=read_directory(raw);previous_end=0
    for at,old,new in edits:
        if not old or at<previous_end or raw[at:at+len(old)]!=old:
            raise ValueError('Overlapping or different source block')
        if at+len(old)>directory['locatorOffset']:
            raise ValueError('Replacement overlaps pointer table')
        previous_end=at+len(old)
    def shifted(address):
        if any(at<=address<at+len(old) for at,old,new in edits):
            raise ValueError('Absolute pointer points inside replacement')
        return address+sum(len(new)-len(old) for at,old,new in edits if address>=at+len(old))
    result=bytearray(raw)
    for at,old,new in reversed(edits):result[at:at+len(old)]=new
    pointers=[(directory['locatorOffset'],directory['offset'])]
    pointers +=[(directory['offset']+4+8*i,value) for i,value in enumerate(directory['entries'])]
    for position,value in pointers:
        if struct.unpack_from('>Q',raw,position)[0]!=value:raise ValueError('Source pointer differs')
        struct.pack_into('>Q',result,shifted(position),shifted(value))
    result=bytes(result);checked=read_directory(result)
    if checked['entries']!=[shifted(value) for value in directory['entries']]:
        raise ValueError('Relocated directory differs')
    if read_project_header(result)!=read_project_header(raw):raise ValueError('Header changed')
    inverse=bytearray(result)
    for position,value in pointers:struct.pack_into('>Q',inverse,shifted(position),value)
    delta=0;final_edits=[]
    for at,old,new in edits:
        final_edits.append((at+delta,old,new));delta+=len(new)-len(old)
    for at,old,new in reversed(final_edits):inverse[at:at+len(new)]=old
    if bytes(inverse)!=raw:raise ValueError('Complete inverse failed')
    return result


def prepare(accepted,full,native):
    if len(accepted)!=1273673 or sha(accepted)!=ACCEPTED_SHA:
        raise ValueError('Use exact user-accepted HMI, preserve other saves')
    if len(full)!=1480005 or sha(full)!=FULL_SHA:
        raise ValueError('Use exact full r15d, not a partial test or native SaveAs')
    if len(native)!=1298542 or sha(native)!=NATIVE_SHA:
        raise ValueError('Use exact operator-opened C_native_alarm_sample.skm')
    sources=(accepted,full);catalogs=[validate_alarm_catalog(raw) for raw in sources]
    if [c['groupCount'] for c in catalogs]!=[1,7]:raise ValueError('Unexpected source group counts')
    outputs=[]
    for base_index,donor_index in ((0,1),(1,0)):
        raw,donor=sources[base_index],sources[donor_index];edits=[]
        for key in ('definitions','directory'):
            before,after=catalogs[base_index][key],catalogs[donor_index][key]
            edits.append((before['start'],raw[before['start']:before['end']],donor[after['start']:after['end']]))
        result=replace_blocks(raw,edits);final=validate_alarm_catalog(result)
        require_sk_group_limit(final['groupCount'])
        if final['names']!=catalogs[donor_index]['names']:raise ValueError('Alarm donor differs')
        if result[:catalogs[base_index]['definitions']['start']]!=raw[:catalogs[base_index]['definitions']['start']]:
            raise ValueError('Earlier UI changed')
        outputs.append((result,dict(name=OUTPUTS[len(outputs)+1],bytes=len(result),sha256=sha(result),
            alarmGroups=final['groupCount'],pageCount=read_project_header(result)['pageCount'],
            completeInversePreservation=True,nativeOpenObserved=False)))
    native_catalog=validate_alarm_catalog(native);native_defs=native_catalog['definitions']
    if native_catalog['names']!=['События станции','Digital Alarm Login1']:
        raise ValueError('Native sample groups differ')
    station=native_defs['groups'][0];fault=catalogs[1]['definitions']['groups'][1]
    if fault['size']!=80 or fault['address']!='R3056':raise ValueError('Expected first R80 fault range')
    group_bytes=(struct.pack('>I',2)+native[station['start']:station['end']]
                 +full[fault['start']:fault['end']])
    native_directory=native_catalog['directory']
    edits=[(native_defs['start'],native[native_defs['start']:native_defs['end']],group_bytes),
        (native_directory['start'],native[native_directory['start']:native_directory['end']],
            directory_bytes([station['name'],fault['name']]))]
    result=replace_blocks(native,edits);final=validate_alarm_catalog(result)
    if final['groupCount']!=2 or final['names']!=[station['name'],fault['name']]:
        raise ValueError('R80-only result differs')
    outputs.insert(0,(result,dict(name=OUTPUTS[0],bytes=len(result),sha256=sha(result),
        alarmGroups=2,pageCount=read_project_header(result)['pageCount'],
        nativeBasePreservedOutsideAlarmBlocks=True,completeInversePreservation=True,nativeOpenObserved=False)))
    return outputs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accepted',type=Path,required=True)
    parser.add_argument('--full-r15d',type=Path,required=True)
    parser.add_argument('--native-sample',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args();paths=(args.accepted,args.full_r15d,args.native_sample,args.out_dir)
    if any(p.is_symlink() for p in paths) or args.out_dir.exists():
        raise ValueError('Regular sources and a NEW output folder required')
    before=[p.read_bytes() for p in paths[:3]];outputs=prepare(*before)
    if before!=[p.read_bytes() for p in paths[:3]]:raise ValueError('Source changed')
    args.out_dir.mkdir(parents=True,exist_ok=False)
    for data,metadata in outputs:
        with (args.out_dir/metadata['name']).open('xb') as stream:stream.write(data)
        print((args.out_dir/metadata['name']).resolve(),metadata['bytes'],metadata['sha256'])
    report=dict(kind='DIAGNOSTIC OPEN ONLY; no production repair',
        sources=[dict(bytes=len(raw),sha256=sha(raw)) for raw in before],
        outputs=[metadata for data,metadata in outputs],sourceFilesUnchanged=True,
        nativeOpenObserved=False,nativeCompileObserved=False,hardwareActions=0)
    with (args.out_dir/'probes.json').open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')


if __name__=='__main__':main()
