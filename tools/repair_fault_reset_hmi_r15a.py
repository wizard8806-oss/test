#!/usr/bin/env python3
"""Repair only the confirmed rejected r15 header, without changing its UI/C.

The r15 builder declared16pages but wrote only14 sceneCommonData pairs.
Append two default pairs BEFORE Scene1 and relocate the24 absolute pointers
and directory locator. Do not replace the HMI model. This tool is source
locked and creates a NEW file; opening/Compile still needs native SKTool.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from repair_skm_section_index import read_directory
from skm_project_header import read_project_header

REJECTED_SHA='f410a9c1e0fb9198c092f18b9b54b62207ff6d1d44d821f64564906fc6913a31'
REJECTED_BYTES=1480325
INSERT_AT=172
PAIR=struct.pack('>ii',0,-1)
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def prepare(source):
    source=Path(source);raw=source.read_bytes()
    if len(raw)!=REJECTED_BYTES or sha(raw)!=REJECTED_SHA:
        raise ValueError('Use exact rejected r15 SKM; preserve native saves for reviewed adaptation')
    header=read_project_header(raw,validate_rect=False)
    if header['model']!='SK-070HE' or header['pageCount']!=16 or header['countOffset']!=56:
        raise ValueError('Rejected header differs')
    if raw[60:INSERT_AT]!=PAIR*14 or struct.unpack_from('>4d',raw,INSERT_AT)!=(0.0,0.0,800.0,480.0):
        raise ValueError('Missing sceneCommonData boundary differs')
    directory=read_directory(raw);result=bytearray(raw[:INSERT_AT]+PAIR*2+raw[INSERT_AT:])
    corrections=[(directory['locatorOffset'],directory['offset'])]
    corrections +=[(directory['offset']+4+8*i,value) for i,value in enumerate(directory['entries'])]
    for at,value in corrections:
        if at<INSERT_AT or value<INSERT_AT:raise ValueError('Unreviewed pointer before insertion')
        if struct.unpack_from('>Q',raw,at)[0]!=value:raise ValueError('Original pointer differs')
        struct.pack_into('>Q',result,at+16,value+16)
    result=bytes(result);checked=read_directory(result);fixed=read_project_header(result)
    if fixed['model']!='SK-070HE' or fixed['resolution']!=(800.0,480.0) or fixed['common']!=[(0,-1)]*16:
        raise ValueError('Repaired model/resolution/common data differs')
    if checked['entries']!=[v+16 for v in directory['entries']]:raise ValueError('Directory relocation differs')
    inverse=bytearray(result)
    for at,value in corrections:struct.pack_into('>Q',inverse,at+16,value)
    del inverse[INSERT_AT:INSERT_AT+16]
    if bytes(inverse)!=raw or source.read_bytes()!=raw:raise ValueError('Complete inverse/source preservation failed')
    return result,dict(revision='r15a',sourceSHA256=sha(raw),sourceBytes=len(raw),candidateSHA256=sha(result),
        candidateBytes=len(result),insertOffset=INSERT_AT,insertBytes=16,addedSceneCommonPairs=2,
        pageCount=16,model=fixed['model'],resolution=list(fixed['resolution']),
        rejectedFirstRect=list(header['firstSceneRect']),fixedFirstRect=list(fixed['firstSceneRect']),
        relocatedDirectoryEntries=24,relocatedLocator=True,completeInversePreservation=True,
        everyOtherBytePreserved=True,macroAndHADUnchanged=True,PLCChanged=False,
        nativeOpenObserved=False,nativeCompileObserved=False,hardwareActions=0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    group=p.add_mutually_exclusive_group(required=True);group.add_argument('--out',type=Path);group.add_argument('--check',type=Path)
    a=p.parse_args();target=a.out or a.check
    if len({v.resolve() for v in (a.source,target,a.report)})!=3 or any(v.is_symlink() for v in (a.source,target,a.report)) or a.report.exists() or a.out is not None and target.exists():
        raise ValueError('Distinct regular paths and NEW output/report required')
    data,report=prepare(a.source)
    if a.check:
        if target.read_bytes()!=data:raise ValueError('Candidate differs from exact header repair')
    else:
        with target.open('xb') as f:f.write(data)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS' if a.check else 'Created','r15a:',len(data),sha(data),'SK-070HE/800x480/16pages; native open still required')
if __name__=='__main__':main()
