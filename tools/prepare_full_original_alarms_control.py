#!/usr/bin/env python3
"""Create ONE Open-only control from exact full r15e, with its original alarm.

Keep the full UI, reset/code pages, C/Batch, logo reference and all other
changes. Remove only added digital-alarm definitions and directory entries.
This is a diagnostic control, NOT a production revision or completed fix.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from prepare_alarm_open_differential import replace_blocks
from skm_alarm_catalog import validate_alarm_catalog,validate_alarm_identities,directory_bytes
from skm_project_header import read_project_header

SOURCE_SHA='2198325315f9b9a6918f483f07f164f855ef454fb3454d7363fe73b6e3fb171d'
CONTROL_SHA='790f095467a359f1896938ab424bb4adb5365af2992ef68046e72d8a53d4700e'
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def prepare(source):
    source=Path(source);raw=source.read_bytes()
    if len(raw)!=1480005 or sha(raw)!=SOURCE_SHA:
        raise ValueError('Use exact FULL r15e; preserve other saves and diagnostic copies')
    catalog=validate_alarm_catalog(raw)
    if validate_alarm_identities(raw)!=list(range(7)):
        raise ValueError('Expected seven correctly numbered r15e groups')
    definitions=catalog['definitions'];directory=catalog['directory'];original=definitions['groups'][0]
    if original['name']!='События станции' or original['address']!='R2550' or original['size']!=25:
        raise ValueError('Original station alarm differs')
    kept=raw[original['start']:original['end']]
    edits=[(definitions['start'],raw[definitions['start']:definitions['end']],struct.pack('>I',1)+kept),
        (directory['start'],raw[directory['start']:directory['end']],directory_bytes([original['name']]))]
    result=replace_blocks(raw,edits);final=validate_alarm_catalog(result)
    if final['groupCount']!=1 or validate_alarm_identities(result)!=[0]:
        raise ValueError('Control must contain only original group0')
    only=final['definitions']['groups'][0]
    if result[only['start']:only['end']]!=kept:raise ValueError('Original definition changed')
    if read_project_header(result)['pageCount']!=16:raise ValueError('Full sixteen-page UI not preserved')
    if len(result)!=1461495 or sha(result)!=CONTROL_SHA:
        raise ValueError('Control differs from independently prepared historical D')
    if source.read_bytes()!=raw:raise ValueError('Source changed')
    return result,dict(purpose='ONE OPEN-ONLY CONTROL; NOT production and NOT a completed repair',
        sourceBytes=len(raw),sourceSHA256=sha(raw),controlBytes=len(result),controlSHA256=sha(result),
        pageCount=16,alarmGroups=1,originalR2550Preserved=True,
        completeInversePreservation=True,allOtherFunctionalBlocksPreserved=True,
        PLCChanged=False,nativeOpenObserved=False,nativeCompileObserved=False,hardwareActions=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    target=parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--out',type=Path);target.add_argument('--check',type=Path)
    args=parser.parse_args();candidate=args.out or args.check;paths=(args.source,candidate,args.report)
    if len({p.resolve() for p in paths})!=3 or any(p.is_symlink() for p in paths) or args.report.exists() or (args.out and candidate.exists()):
        raise ValueError('Distinct regular paths and NEW output/report required')
    result,report=prepare(args.source)
    if args.check:
        if candidate.read_bytes()!=result:raise ValueError('Control differs from expected transformation')
    else:
        with candidate.open('xb') as stream:stream.write(result)
    with args.report.open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('PASS' if args.check else 'Created',candidate.resolve(),len(result),sha(result),
          'OPEN-ONLY control; native result still needed')


if __name__=='__main__':main()
