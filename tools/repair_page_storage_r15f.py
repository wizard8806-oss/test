#!/usr/bin/env python3
"""Extend the two stale page arrays in exact full r15e; preserve all payloads.

This is based on the user's native16-page reference, not guessed padding.
The two reviewed insertions add 2+8 bytes; 24 absolute entries and their
locator are relocated. Native Open/Compile remain separate acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from repair_skm_section_index import read_directory
from skm_page_storage import read_page_storage,page_storage_extensions
from skm_alarm_catalog import validate_alarm_catalog,validate_alarm_identities

SOURCE_SHA='2198325315f9b9a6918f483f07f164f855ef454fb3454d7363fe73b6e3fb171d'
NATIVE16_SHA='671ce4309579da4e2d5109c6910b35a08f2baaf7b702dbaca800f373e910c738'
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def splice(raw,edits):
    output=bytearray();cursor=0
    for at,old,new,label in sorted(edits,key=lambda edit:edit[0]):
        if at<cursor or raw[at:at+len(old)]!=old:raise ValueError('Overlapping/different edit: '+label)
        output.extend(raw[cursor:at]);output.extend(new);cursor=at+len(old)
    output.extend(raw[cursor:]);return bytes(output)


def extend_with_directory(raw,target_count):
    directory=read_directory(raw);edits=page_storage_extensions(raw,target_count)
    def shifted(address):
        return address+sum(len(new) for at,old,new,label in edits if at<=address)
    pointers=[(directory['locatorOffset'],directory['offset'])]
    pointers.extend((directory['offset']+4+8*i,value) for i,value in enumerate(directory['entries']))
    changes=edits+[(at,struct.pack('>Q',value),struct.pack('>Q',shifted(value)),'directory pointer') for at,value in pointers]
    result=splice(raw,changes);final=read_directory(result)
    if final['entries']!=[shifted(value) for value in directory['entries']]:raise ValueError('Directory relocation differs')
    inverse=[];delta=0
    for at,old,new,label in sorted(changes,key=lambda edit:edit[0]):
        inverse.append((at+delta,new,old,label));delta+=len(new)-len(old)
    if splice(result,inverse)!=raw:raise ValueError('Complete inverse failed')
    read_page_storage(result)
    return result


def prepare(source):
    source=Path(source);raw=source.read_bytes()
    if len(raw)!=1480005 or sha(raw)!=SOURCE_SHA:raise ValueError('Use exact FULL r15e; preserve native saves/controls')
    before=read_page_storage(raw,require_consistent=False)
    if (before['pageCount'],before['flagEntries'],before['wordEntries'])!=(16,14,14):
        raise ValueError('Expected known stale16/14/14 page storage')
    result=extend_with_directory(raw,16);after=read_page_storage(result)
    if validate_alarm_catalog(result)['groupCount']!=7 or validate_alarm_identities(result)!=list(range(7)):
        raise ValueError('Seven alarm groups changed')
    locator=read_directory(raw)['locatorOffset']
    if result[:locator]!=raw[:locator] or result[locator+8:before['flagEnd']]!=raw[locator+8:before['flagEnd']]:
        raise ValueError('Earlier project payload changed')
    if source.read_bytes()!=raw:raise ValueError('Source changed')
    return result,dict(sourceBytes=len(raw),sourceSHA256=sha(raw),candidateBytes=len(result),candidateSHA256=sha(result),
        native16ReferenceSHA256=NATIVE16_SHA,pageStorageBefore=before,pageStorageAfter=after,
        insertedBytes=10,flagEntriesAdded=2,wordEntriesAdded=2,relocatedDirectoryEntries=24,
        allPayloadsPreservedByFullInverse=True,alarmGroups=7,PLCChanged=False,
        nativeOpenObserved=False,nativeCompileObserved=False,hardwareActions=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    target=parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--out',type=Path);target.add_argument('--check',type=Path)
    args=parser.parse_args();candidate=args.out or args.check;paths=(args.source,candidate,args.report)
    if (len({path.resolve() for path in paths})!=3 or any(path.is_symlink() for path in paths)
            or args.report.exists() or (args.out and candidate.exists())):
        raise ValueError('Distinct regular paths and NEW output/report required')
    result,report=prepare(args.source)
    if args.check:
        if candidate.read_bytes()!=result:raise ValueError('Candidate differs from exact page-storage repair')
    else:
        with candidate.open('xb') as stream:stream.write(result)
    with args.report.open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('PASS' if args.check else 'Created',candidate.resolve(),len(result),sha(result),'Native Open/Compile pending')


if __name__=='__main__':main()
