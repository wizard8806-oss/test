#!/usr/bin/env python3
"""Compact full r15c to seven digital groups within the documented SK limit.

All messages and their PLC word/bit mappings are preserved. Only the two
alarm blocks and their absolute section pointers change. The PLC, C, Batch
tables, widgets, logo reference and original station group stay intact.
This source-locked NEW file still requires native Open/Compile acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from repair_skm_section_index import read_directory
from skm_alarm_catalog import (validate_alarm_catalog, compact_fault_definitions,
    read_definitions, directory_bytes, require_sk_group_limit, word_bit_semantics)
from skm_project_header import read_project_header

SOURCE_SHA='0141fa91f028144ad9fea5d256c464682860515d4d4c4eab0d80f658ae1ff930'
sha=lambda data:hashlib.sha256(data).hexdigest()


def prepare(source):
    source=Path(source);raw=source.read_bytes()
    if len(raw)!=1480911 or sha(raw)!=SOURCE_SHA:
        raise ValueError('Use exact full r15c; preserve other saves and diagnostic probes')
    catalog=validate_alarm_catalog(raw);definitions=catalog['definitions']
    if catalog['groupCount']!=13:raise ValueError('Expected thirteen groups in full r15c')
    old_definitions=raw[definitions['start']:definitions['end']]
    compacted=compact_fault_definitions(old_definitions)
    names=[g['name'] for g in read_definitions(compacted,0)['groups']]
    directory=catalog['directory']
    edits=[(definitions['start'],old_definitions,compacted),
        (directory['start'],raw[directory['start']:directory['end']],directory_bytes(names))]
    original_directory=read_directory(raw)
    def shifted(address):
        if any(at<=address<at+len(old) for at,old,new in edits):
            raise ValueError('Absolute pointer points inside a replacement')
        return address+sum(len(new)-len(old) for at,old,new in edits if address>=at+len(old))
    pointers=[(original_directory['locatorOffset'],original_directory['offset'])]
    pointers +=[(original_directory['offset']+4+8*i,value)
                for i,value in enumerate(original_directory['entries'])]
    result=bytearray(raw)
    for at,old,new in reversed(edits):result[at:at+len(old)]=new
    for position,value in pointers:
        if struct.unpack_from('>Q',raw,position)[0]!=value:raise ValueError('Original pointer differs')
        struct.pack_into('>Q',result,shifted(position),shifted(value))
    result=bytes(result);final=validate_alarm_catalog(result)
    require_sk_group_limit(final['groupCount'])
    if final['groupCount']!=final['directoryCount'] or final['groupCount']!=7:
        raise ValueError('Expected seven matching definitions/names')
    checked=read_directory(result)
    if checked['entries']!=[shifted(value) for value in original_directory['entries']]:
        raise ValueError('Section pointer relocation differs')
    if read_project_header(result)!=read_project_header(raw):raise ValueError('Project header changed')
    if word_bit_semantics(old_definitions)!=word_bit_semantics(compacted):
        raise ValueError('Alarm address/bit/message semantics changed')
    inverse=bytearray(result)
    for position,value in pointers:struct.pack_into('>Q',inverse,shifted(position),value)
    delta=0;final_edits=[]
    for at,old,new in edits:
        final_edits.append((at+delta,old,new));delta+=len(new)-len(old)
    for at,old,new in reversed(final_edits):inverse[at:at+len(new)]=old
    if bytes(inverse)!=raw or source.read_bytes()!=raw:raise ValueError('Complete inverse/source preservation failed')
    return result,dict(revision='r15d',sourceBytes=len(raw),sourceSHA256=sha(raw),
        candidateBytes=len(result),candidateSHA256=sha(result),
        sourceGroups=13,finalGroups=7,documentedSKGroupLimit=10,
        finalDirectoryEntries=7,finalCompanionEntries=7,
        alarmBitMappingsPreserved=len(word_bit_semantics(compacted)),
        completeInversePreservation=True,allMessagesPreserved=True,
        allUIAndMacrosUnchanged=True,PLCChanged=False,
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
    data,report=prepare(args.source)
    if args.check:
        if candidate.read_bytes()!=data:raise ValueError('Candidate differs from exact compaction')
    else:
        with candidate.open('xb') as stream:stream.write(data)
    with args.report.open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('PASS' if args.check else 'Created',candidate.resolve(),len(data),sha(data),
        '7 groups; native Open/Compile still required')


if __name__=='__main__':main()
