#!/usr/bin/env python3
"""Repair the confirmed missing digital-alarm name directory in fullr15a.

The native7.1 sample confirms that definitions and editor-side Bxx names
have matching cardinality, with one opaque empty companion entry per group.
This source-locked repair adds the missing directory records and relocates
24section pointers/locator. Definitions, macros, controls and PLC stay intact.
It creates a NEW file; actual native Open/Compile remain separate checks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from repair_skm_section_index import read_directory
from skm_project_header import read_project_header
from skm_alarm_catalog import read_definitions,read_directory_for_names,directory_bytes,validate_alarm_catalog

SOURCES={
 'd08b5ec1358e84bdc640acdda30ed164038d57c6d3be39a1ad08d68e81176551':(1480341,'full-r15a'),
}
sha=lambda data:hashlib.sha256(data).hexdigest()


def prepare(source):
    source=Path(source);raw=source.read_bytes();digest=sha(raw)
    if digest not in SOURCES or len(raw)!=SOURCES[digest][0]:raise ValueError('Use exact rejected FULLr15a; preserve other saves and diagnostic files for review')
    header=read_project_header(raw);directory=read_directory(raw);definitions=read_definitions(raw)
    if definitions['count']!=13:raise ValueError('Expected13 fault groups in rejected candidate')
    names=[g['name'] for g in definitions['groups']]
    old_directory=read_directory_for_names(raw,names[:1]);at,end=old_directory['start'],old_directory['end']
    if raw[at:end]!=directory_bytes(names[:1]):raise ValueError('Rejected one-entry directory differs')
    replacement=directory_bytes(names);delta=len(replacement)-(end-at)
    if delta<=0:raise ValueError('No missing directory records')
    def shifted(address):
        if at<address<end:raise ValueError('Absolute pointer inside alarm directory')
        return address+(delta if address>=end else 0)
    result=bytearray(raw[:at]+replacement+raw[end:]);pointers=[(directory['locatorOffset'],directory['offset'])]
    pointers +=[(directory['offset']+4+8*i,value) for i,value in enumerate(directory['entries'])]
    for position,value in pointers:
        if struct.unpack_from('>Q',raw,position)[0]!=value:raise ValueError('Original pointer differs')
        struct.pack_into('>Q',result,shifted(position),shifted(value))
    result=bytes(result);checked=read_directory(result);catalog=validate_alarm_catalog(result)
    if checked['entries']!=[shifted(value) for value in directory['entries']]:raise ValueError('Directory relocation differs')
    if read_project_header(result)!=header:raise ValueError('Header changed')
    if read_definitions(result)['end']!=definitions['end'] or result[:at]!=raw[:at]:raise ValueError('Unexpected earlier/definition change')
    inverse=bytearray(result)
    for position,value in pointers:struct.pack_into('>Q',inverse,shifted(position),value)
    inverse[at:at+len(replacement)]=raw[at:end]
    if bytes(inverse)!=raw or source.read_bytes()!=raw:raise ValueError('Complete inverse/source preservation failed')
    return result,dict(revision='r15c',sourceKind=SOURCES[digest][1],sourceSHA256=digest,sourceBytes=len(raw),
        candidateSHA256=sha(result),candidateBytes=len(result),addedBytes=delta,
        sourceDefinitionCount=13,sourceNameDirectoryCount=1,finalDefinitionCount=catalog['groupCount'],
        finalNameDirectoryCount=catalog['directoryCount'],finalCompanionCount=catalog['directory']['companionCount'],
        directoryOffset=at,directorySourceBytes=end-at,directoryTargetBytes=len(replacement),
        updatedDirectoryEntries=24,updatedLocator=True,completeInversePreservation=True,
        alarmDefinitionsUnchanged=True,allEarlierUIAndMacrosUnchanged=True,PLCChanged=False,
        nativeOpenObserved=False,nativeCompileObserved=False,hardwareActions=0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    group=p.add_mutually_exclusive_group(required=True);group.add_argument('--out',type=Path);group.add_argument('--check',type=Path)
    a=p.parse_args();target=a.out or a.check
    if len({v.resolve() for v in (a.source,target,a.report)})!=3 or any(v.is_symlink() for v in (a.source,target,a.report)) or a.report.exists() or (a.out is not None and target.exists()):raise ValueError('Distinct regular paths and NEW output/report required')
    data,report=prepare(a.source)
    if a.check:
        if target.read_bytes()!=data:raise ValueError('Candidate differs from exact catalog repair')
    else:
        with target.open('xb') as f:f.write(data)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS' if a.check else 'Created','r15c:',len(data),sha(data),'13 definitions/13 directory records; native Open remains')
if __name__=='__main__':main()
