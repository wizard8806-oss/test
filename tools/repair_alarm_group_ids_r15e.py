#!/usr/bin/env python3
"""Repair the six duplicate alarm-group numbers in exact full r15d.

The user's native7.1 LB1 and R3056/80 samples store group numbers0,1.
Our producer copied the original header's number0 into every added group.
This repair assigns1..6 and changes ONLY six bytes. All payload, text,
UI, C/Batch tables, pointer locations and PLC stay intact. Native Open
and Compile acceptance of the full project are still required.
"""
import argparse
import hashlib
import json
from pathlib import Path
from skm_alarm_catalog import (validate_alarm_catalog,validate_alarm_identities,
    with_sequential_alarm_ids,word_bit_semantics)
from repair_skm_section_index import read_directory
from skm_project_header import read_project_header

SOURCE_SHA='9a482900380d56f3bb86a625664ad09b10885fe6d9fd58b15262ef974c9bd8bb'
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def prepare(source):
    source=Path(source);raw=source.read_bytes()
    if len(raw)!=1480005 or sha(raw)!=SOURCE_SHA:
        raise ValueError('Use exact full r15d; preserve native saves and diagnostic probes')
    catalog=validate_alarm_catalog(raw);definitions=catalog['definitions']
    if catalog['groupCount']!=7 or [g['groupId'] for g in definitions['groups']]!=[0]*7:
        raise ValueError('Expected seven groups with duplicated number0 in r15d')
    result=with_sequential_alarm_ids(raw);ids=validate_alarm_identities(result)
    expected=[(g['start']+4,0,g['index']) for g in definitions['groups'][1:]]
    actual=[(index,old,new) for index,(old,new) in enumerate(zip(raw,result)) if old!=new]
    if len(raw)!=len(result) or actual!=expected or ids!=list(range(7)):
        raise ValueError('Change exceeds the six reviewed group-number bytes')
    if read_directory(result)!=read_directory(raw) or read_project_header(result)!=read_project_header(raw):
        raise ValueError('Header/pointer directory changed')
    final=validate_alarm_catalog(result)
    if final['directory']!=catalog['directory']:raise ValueError('Alarm name directory changed')
    first,last=definitions['start'],definitions['end']
    if word_bit_semantics(raw[first:last])!=word_bit_semantics(result[first:last]):
        raise ValueError('Alarm word/bit/message semantics changed')
    inverse=bytearray(result)
    for position,old,new in expected:inverse[position]=old
    if bytes(inverse)!=raw or source.read_bytes()!=raw:raise ValueError('Inverse/source preservation failed')
    return result,dict(revision='r15e',sourceSHA256=sha(raw),sourceBytes=len(raw),
        candidateSHA256=sha(result),candidateBytes=len(result),changedBytes=6,
        changes=[dict(offset=position,old=old,new=new) for position,old,new in expected],
        alarmGroupIds=ids,alarmBitMappingsPreserved=268,
        allOtherBytesPreserved=True,completeInversePreservation=True,PLCChanged=False,
        nativeOpenObserved=False,nativeCompileObserved=False,hardwareActions=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    target=parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--out',type=Path);target.add_argument('--check',type=Path)
    args=parser.parse_args();candidate=args.out or args.check
    paths=(args.source,candidate,args.report)
    if len({p.resolve() for p in paths})!=3 or any(p.is_symlink() for p in paths) or args.report.exists() or (args.out and candidate.exists()):
        raise ValueError('Distinct regular paths and NEW output/report required')
    result,report=prepare(args.source)
    if args.check:
        if candidate.read_bytes()!=result:raise ValueError('Candidate differs from six-byte repair')
    else:
        with candidate.open('xb') as stream:stream.write(result)
    with args.report.open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('PASS' if args.check else 'Created',candidate.resolve(),len(result),sha(result),
        'group numbers0..6; native Open/Compile still required')


if __name__=='__main__':main()
