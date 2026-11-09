#!/usr/bin/env python3
"""Prepare a NEW diagnostic HMI copy without the suspect HAD8288 object.

The user can see the restored r11 grid in Simulator, but opening Screen9
in the editor hangs. Remove that whole object for isolation/native rebuild.
This is NOT a complete HMI or an alarm-display fix: a native replacement
and successful page/Compile/Simulator checks are required before deployment.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from repair_skm_section_index import read_directory

SOURCE_SHA='3e6d60e52d3177d786fe72e89cb4cb64c842e16867974c4f8ca5a5fb1065b0d7'
SOURCE_BYTES=1287916
START,STOP=910836,916653
WIDGET_SHA='e830b58a30d24ea7698462b543a994e8b5af2d423de6e2cbacf92accfe33a9b1'
sha=lambda b:hashlib.sha256(b).hexdigest()
def qs(s):
    b=s.encode('utf-16-be');return struct.pack('>I',len(b))+b
def apply(raw,edits):
    out,cursor=bytearray(),0
    for at,old,new,label in sorted(edits,key=lambda e:e[0]):
        if at<cursor or raw[at:at+len(old)]!=old:raise ValueError('Differing/overlapping field: '+label)
        out.extend(raw[cursor:at]);out.extend(new);cursor=at+len(old)
    out.extend(raw[cursor:]);return bytes(out)


def prepare(source):
    raw=Path(source).read_bytes()
    if len(raw)!=SOURCE_BYTES or sha(raw)!=SOURCE_SHA:raise ValueError('Use exact r11; preserve other native saves')
    directory=read_directory(raw);widget=raw[START:STOP]
    if sha(widget)!=WIDGET_SHA or not widget.endswith(qs('8288')+struct.pack('>d',8288.)):
        raise ValueError('Whole suspect widget boundary differs')
    anchor=qs('Screen9')+b'\xff'*4
    if raw.count(anchor)!=1:raise ValueError('Scene9 header not unique')
    count_at=raw.index(anchor)+len(anchor)
    if struct.unpack_from('>I',raw,count_at)[0]!=19 or not count_at<START:
        raise ValueError('Scene9 item count differs')
    next_header=raw.index(qs('Screen10')+b'\xff'*4,count_at)
    if not STOP<next_header:raise ValueError('Widget outside Scene9')
    delta=START-STOP
    edits=[(START,widget,b'','remove only suspect HAD8288'),
           (count_at,struct.pack('>I',19),struct.pack('>I',18),'Scene9 item count')]
    entries=[v+(delta if v>=STOP else 0) for v in directory['entries']]
    for i,v in enumerate(directory['entries']):
        edits.append((directory['offset']+4+8*i,struct.pack('>Q',v),struct.pack('>Q',entries[i]),'section address'))
    edits.append((directory['locatorOffset'],struct.pack('>Q',directory['offset']),struct.pack('>Q',directory['offset']+delta),'directory locator'))
    final=apply(raw,edits)
    if read_directory(final)['entries']!=entries or qs('HAD8288') in final or Path(source).read_bytes()!=raw:
        raise ValueError('Directory/removal/source preservation differs')
    # The remaining18 normal groups retain their exact record bytes.
    group=re.compile(bytes.fromhex('00010017')+b'\x00\x00\x00[\x01-\x09]'+bytes.fromhex('000100'))
    if len(list(group.finditer(final,count_at+4,next_header+delta)))!=18:
        raise ValueError('Retained Scene9 widget inventory differs')
    return final,{'revision':12,'purpose':'diagnostic isolation and native alarm control rebuild',
                  'sourceSHA256':sha(raw),'candidateSHA256':sha(final),'candidateBytes':len(final),
                  'removedWidget':'HAD8288','removedBytes':len(widget),'scene9ItemsBefore':19,'scene9ItemsAfter':18,
                  'allOtherWidgetsMacrosAndAlarmDefinitionsPreserved':True,'PLCChanged':False,
                  'replacementAlarmControlPresent':False,'pageEditorHangCauseConfirmed':False,
                  'nativeScreen9OpenObserved':False,'nativeCompileObserved':False,
                  'fullPanelReadyForDownload':False,'equipmentActions':0,
                  'edits':[{'sourceOffset':at,'sourceBytes':len(old),'targetBytes':len(new),'label':label}
                           for at,old,new,label in sorted(edits,key=lambda e:e[0])]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','out','report'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    if len({v.resolve() for v in (a.source,a.out,a.report)})!=3 or any(v.exists() or v.is_symlink() for v in (a.out,a.report)):
        raise ValueError('Distinct source and NEW diagnostic output/report required')
    data,report=prepare(a.source)
    with a.out.open('xb') as f:f.write(data)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Created diagnostic r12 base:',len(data),'bytes;',sha(data))
    print('Alarm widget intentionally absent. Native page test/replacement required; not a deployable HMI.')


if __name__=='__main__':main()
