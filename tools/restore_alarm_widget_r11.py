#!/usr/bin/env python3
"""Restore the ENTIRE known-visible alarm widget in a NEW r10 HMI copy.

The r9 single-field restoration did not restore the native grid. Undo all
r8 table edits, verify the original r7 widget hash, and preserve everything
else in r10. Original table bounds return too: native sizing/acceptance is
still required. No PLC, macro, alarm definition, or command is changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from repair_skm_section_index import read_directory

SOURCE_SHA='e7752b52bfbbc9e74f04391aa0aa9ffc09e9437cc189d55632a41401495c76f4'
SOURCE_BYTES=1287912
START,STOP=910836,916649
ORIGINAL_WIDGET_SHA='e830b58a30d24ea7698462b543a994e8b5af2d423de6e2cbacf92accfe33a9b1'
sha=lambda b:hashlib.sha256(b).hexdigest()
def qs(s):
    b=s.encode('utf-16-be');return struct.pack('>I',len(b))+b
def doubles(*values):return struct.pack('>'+'d'*len(values),*values)
def apply(raw,edits):
    out,cursor=bytearray(),0
    for at,old,new,label in sorted(edits,key=lambda e:e[0]):
        if at<cursor or raw[at:at+len(old)]!=old:raise ValueError('Differing or overlapping field: '+label)
        out.extend(raw[cursor:at]);out.extend(new);cursor=at+len(old)
    out.extend(raw[cursor:]);return bytes(out)


def restore_widget(current):
    if len(current)!=5813 or current[:8]!=bytes.fromhex('000100170000001a'):
        raise ValueError('Expected exact26-child HAD8288 record')
    # Equal-length cached graphics changes all precede the native list.
    edits=[(28,doubles(768.,288.),doubles(976.,360.),'body bounds'),
           (189,doubles(768.,24.),doubles(976.,22.5),'header bounds')]
    before,after=doubles(16.,112.),doubles(18.75,111.2)
    origins=[m.start() for m in re.finditer(re.escape(before),current[:4344])]
    if len(origins)!=22:raise ValueError('Original table-origin mirror inventory differs')
    edits.extend((at,before,after,'original origin') for at in origins)
    old_widths=[86.,126.,552.,126.,86.];new_widths=[66.,86.,86.,66.,464.]
    old_x,new_x=18.75,16.
    for i,start in enumerate((332,553,772,1007,1228)):
        edits.append((start+20,doubles(new_widths[i],24.),doubles(old_widths[i],22.5),'title size'))
        at=current.index(qs('Text%d'%i))+len(qs('Text%d'%i))+4
        if i:edits.append((at,doubles(new_x,112.),doubles(old_x,111.2),'title position'))
        old_x+=old_widths[i];new_x+=new_widths[i]
    lines=[m.start() for m in re.finditer(bytes.fromhex('0001001100000002'),current[:4344])]
    if len(lines)!=19:raise ValueError('Original table-line inventory differs')
    for i,start in enumerate(lines[:15]):
        new_y=24.+17.6*i;old_y=22.5*(i+1)
        edits.append((start+8,doubles(0.,new_y,768.,new_y),doubles(0.,old_y,976.,old_y),'row line'))
    for i,start in enumerate(lines[15:]):
        new_x=sum(new_widths[:i+1]);old_x=sum(old_widths[:i+1])
        edits.append((start+8,doubles(new_x,0.,new_x,288.),doubles(old_x,0.,old_x,360.),'column line'))
    # Restore the original native widths as a whole typed tuple, including
    # the original QString lengths. All other135 native properties stay.
    before=b''.join(qs(s) for s in ('66','86','464','86','66'))
    after=b''.join(qs(s) for s in ('86','126','552','126','86'))
    if current.count(before)!=1 or current[5062:5062+len(before)]!=before:
        raise ValueError('Reviewed column-width tuple differs')
    edits.append((5062,before,after,'original native widths'))
    restored=apply(current,edits)
    if len(restored)!=5817 or sha(restored)!=ORIGINAL_WIDGET_SHA:
        raise ValueError('Whole widget did not exactly match known-visible r7')
    return restored


def prepare(source):
    raw=Path(source).read_bytes()
    if len(raw)!=SOURCE_BYTES or sha(raw)!=SOURCE_SHA:
        raise ValueError('Use exact r10 candidate; preserve any newer native save')
    directory=read_directory(raw);widget=raw[START:STOP]
    if qs('HAD8288') not in widget or raw[STOP:STOP+4]!=bytes.fromhex('00010017'):
        raise ValueError('Whole widget boundary differs')
    original=restore_widget(widget);delta=len(original)-len(widget)
    edits=[(START,widget,original,'whole HAD8288 restoration')]
    expected=[v+(delta if v>=STOP else 0) for v in directory['entries']]
    for i,v in enumerate(directory['entries']):
        edits.append((directory['offset']+4+8*i,struct.pack('>Q',v),struct.pack('>Q',expected[i]),'section address'))
    edits.append((directory['locatorOffset'],struct.pack('>Q',directory['offset']),struct.pack('>Q',directory['offset']+delta),'directory locator'))
    final=apply(raw,edits)
    if read_directory(final)['entries']!=expected or Path(source).read_bytes()!=raw:
        raise ValueError('Directory or source preservation differs')
    return final,{'revision':11,'sourceBytes':len(raw),'sourceSHA256':sha(raw),
                  'candidateBytes':len(final),'candidateSHA256':sha(final),
                  'widget':'HAD8288','wholeOriginalWidgetSHA256':sha(original),'originalWidgetBytes':len(original),
                  'originalBoundsRestored':[18.75,111.2,976.,360.],
                  'otherR10WidgetsMacrosAndAlarmDefinitionsPreserved':True,'PLCChanged':False,
                  'cascadeEightRowsAndIndependentDelaysPreserved':True,
                  'nativeGridObserved':False,'nativeFittingCompleted':False,'equipmentActions':0,
                  'edits':[{'sourceOffset':at,'sourceBytes':len(old),'targetBytes':len(new),'label':label}
                           for at,old,new,label in sorted(edits,key=lambda e:e[0])]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','out','report'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    if len({v.resolve() for v in (a.source,a.out,a.report)})!=3 or any(v.exists() or v.is_symlink() for v in (a.out,a.report)):
        raise ValueError('Distinct source and NEW output/report required')
    data,report=prepare(a.source)
    with a.out.open('xb') as f:f.write(data)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Created NEW alarm-widget restoration r11:',len(data),'bytes;',sha(data))
    print('Whole original widget restored; original large bounds returned too. Native grid/fitting acceptance remains.')


if __name__=='__main__':main()
