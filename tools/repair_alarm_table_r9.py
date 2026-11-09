#!/usr/bin/env python3
"""Restore the original HAD8288 service field corrupted by r8 resizing.

Only one QString changes, 24 -> the original36. Equal length, so every
other byte, macro, control, screen and absolute section address stays.
This is a new HMI file; the working PLC does not change.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from repair_skm_section_index import read_directory

SOURCE_SHA='587038bbe7f0bb59299e37fac092a6dd4ec484b9529bec2e8f78c05f69339280'
SOURCE_BYTES=1272222
FIELD_OFFSET=900368
sha=lambda b:hashlib.sha256(b).hexdigest()


def qs(s):
    b=s.encode('utf-16-be');return struct.pack('>I',len(b))+b


def prepare(source):
    raw=Path(source).read_bytes()
    if len(raw)!=SOURCE_BYTES or sha(raw)!=SOURCE_SHA:raise ValueError('Use exact r8; preserve any newer native save')
    directory=read_directory(raw)
    prefix=qs('0');tail=qs('5')+qs('10')+qs('Arial')+qs('Время')+qs('Дата')+qs('Событие')
    old,new=qs('24'),qs('36');at=FIELD_OFFSET
    if raw[at-len(prefix):at+len(old)+len(tail)]!=prefix+old+tail:raise ValueError('Reviewed alarm property boundary differs')
    final=raw[:at]+new+raw[at+len(old):]
    if read_directory(final)!=directory or Path(source).read_bytes()!=raw:raise ValueError('Source or directory preservation failed')
    assert final[:at]==raw[:at] and final[at+len(new):]==raw[at+len(old):]
    return final,{'revision':9,'sourceBytes':len(raw),'sourceSHA256':sha(raw),'candidateBytes':len(final),'candidateSHA256':sha(final),
                  'widget':'HAD8288','fieldOffset':at,'originalValueRestored':'36','allOtherBytesPreserved':True,
                  'directoryAndEOFUnchanged':True,'PLCChanged':False,'macroOrCommandBindingsChanged':False,
                  'nativeDisplayObserved':False,'equipmentActions':0}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','out','report'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    if len({v.resolve() for v in (a.source,a.out,a.report)})!=3 or any(v.exists() or v.is_symlink() for v in (a.out,a.report)):raise ValueError('Distinct input and NEW output/report required')
    final,report=prepare(a.source)
    with a.out.open('xb') as f:f.write(final)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Built NEW alarm-table r9 HMI:',len(final),'bytes;',report['candidateSHA256'])
    print('Original service field36 restored; all other bytes and working PLC preserved. Native grid check remains.')


if __name__=='__main__':main()
