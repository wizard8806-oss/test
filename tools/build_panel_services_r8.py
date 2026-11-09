#!/usr/bin/env python3
"""Repair the exact r7 HMI: map32 services, native alarm sound, fitting alarm table.

Create a separate candidate. No PLC program, command or protection changes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from repair_skm_section_index import read_directory

SOURCE_SHA='61ec747e1ff6629d931063e8df429255071fe1f8229cf1bd6b66e772658fe25d'
sha=lambda b:hashlib.sha256(b).hexdigest()


def qs(s):
    b=s.encode('utf-16-be');return struct.pack('>I',len(b))+b


def apply(raw,edits):
    result,cursor=bytearray(),0
    for at,old,new,label in sorted(edits,key=lambda e:e[0]):
        if at<cursor or raw[at:at+len(old)]!=old:raise ValueError('Differing or overlapping field: '+label)
        result.extend(raw[cursor:at]);result.extend(new);cursor=at+len(old)
    result.extend(raw[cursor:]);return bytes(result)


def replace_strings(raw,old,new,count,label):
    needle=qs(old);positions=[m.start() for m in re.finditer(re.escape(needle),raw)]
    if len(positions)!=count:raise ValueError('QString mirrors differ: '+label)
    return [(p,needle,qs(new),label) for p in positions]


def alarm_table(raw,spec):
    t=spec['table'];b=raw[t['start']:t['stop']]
    if sha(b)!=t['sourceSHA256'] or b[:8]!=bytes.fromhex('000100170000001a'):
        raise ValueError('Native 26-child alarm table differs')
    edits=[]
    def put(at,old,new,label):edits.append((at,old,new,label))
    put(28,struct.pack('>2d',976.,360.),struct.pack('>2d',768.,288.),'outer dimensions')
    put(189,struct.pack('>2d',976.,22.5),struct.pack('>2d',768.,24.),'cached header dimensions')
    # Rectangles and all line primitives use the original shared table origin.
    before=struct.pack('>2d',18.75,111.2);after=struct.pack('>2d',16.,112.)
    positions=[m.start() for m in re.finditer(re.escape(before),b)]
    if len(positions)!=22:raise ValueError('Expected two rects, first title and19 lines')
    for at in positions:put(at,before,after,'table origin')
    old_widths=[86.,126.,552.,126.,86.]
    new_widths=[66.,86.,86.,66.,464.]
    old_x,new_x=18.75,16.
    for i,start in enumerate((332,553,772,1007,1228)):
        put(start+20,struct.pack('>2d',old_widths[i],22.5),struct.pack('>2d',new_widths[i],24.),'title%d size' % i)
        at=b.index(qs('Text%d' % i))+len(qs('Text%d' % i))+4
        if i:put(at,struct.pack('>2d',old_x,111.2),struct.pack('>2d',new_x,112.),'title%d origin' % i)
        old_x+=old_widths[i];new_x+=new_widths[i]
    lines=[m.start() for m in re.finditer(bytes.fromhex('0001001100000002'),b)]
    if len(lines)!=19:raise ValueError('Alarm table line inventory differs')
    for i,start in enumerate(lines[:15]):
        old_y=22.5*(i+1);new_y=24.+17.6*i
        put(start+8,struct.pack('>4d',0.,old_y,976.,old_y),struct.pack('>4d',0.,new_y,768.,new_y),'horizontal%d' % i)
    for i,start in enumerate(lines[15:]):
        old_x=sum(old_widths[:i+1]);new_x=sum(new_widths[:i+1])
        put(start+8,struct.pack('>4d',old_x,0.,old_x,360.),struct.pack('>4d',new_x,0.,new_x,288.),'vertical%d' % i)
    for at,old,new in zip((5062,5070,5080,5090,5100),('86','126','552','126','86'),('66','86','464','86','66')):
        put(at,qs(old),qs(new),'native column width')
    put(5226,qs('36'),qs('24'),'native header height')
    return apply(b,edits)


def prepare(source,recipe,macro):
    raw=Path(source).read_bytes();spec=json.loads(Path(recipe).read_text(encoding='utf-8-sig'))
    if len(raw)!=1271370 or sha(raw)!=SOURCE_SHA or spec['sourceSHA256']!=SOURCE_SHA:
        raise ValueError('Use exact r7; preserve newer native saves')
    if spec['format']!='sktool-r7-panel-services-r8':raise ValueError('Wrong r8 recipe')
    directory=read_directory(raw);edits=[]
    t=spec['table'];edits.append((t['start'],raw[t['start']:t['stop']],alarm_table(raw,spec),'fit complete alarm table'))
    for label in spec['labels']:edits+=replace_strings(raw,label['old'],label['new'],label['count'],'diagnostic caption')
    new=Path(macro).read_text(encoding='utf-8').replace('\r\n','\n').replace('\n','\r\n')
    if '#define PANEL_MAP_VERSION 32u' not in new or 'LocalBit[60117] = LocalBit[802];' not in new:
        raise ValueError('Expected map32/native alarm sound source')
    if re.search(r'LocalBit\[60185\]\s*=',new) or 'MapVersion == 31u' in new or 'MapVersion != 31u' in new:
        raise ValueError('Stale or undocumented alarm behavior')
    marker='#include "MacroInit.h"'.encode('utf-16-be');positions=[m.start()-4 for m in re.finditer(re.escape(marker),raw)]
    if len(positions)!=2:raise ValueError('Expected two C-source mirrors')
    original=[]
    for at in positions:
        n=struct.unpack_from('>I',raw,at)[0];old=raw[at+4:at+4+n].decode('utf-16-be');original.append(old)
        edits.append((at,qs(old),qs(new),'map32 services source mirror'))
    if original[0]!=original[1] or original[0].count('MapVersion == 31u')!=4:
        raise ValueError('Original r7 macro differs')
    def shifted(value):
        if any(at<value<at+len(old) for at,old,_,_ in edits):raise ValueError('Section inside edited field')
        return value+sum(len(new)-len(old) for at,old,new,_ in edits if at<value)
    target_entries=[shifted(v) for v in directory['entries']]
    for i,v in enumerate(directory['entries']):
        edits.append((directory['offset']+4+8*i,struct.pack('>Q',v),struct.pack('>Q',target_entries[i]),'directory%d' % i))
    edits.append((directory['locatorOffset'],struct.pack('>Q',directory['offset']),struct.pack('>Q',shifted(directory['offset'])),'back-pointer'))
    final=apply(raw,edits)
    if read_directory(final)['entries']!=target_entries or Path(source).read_bytes()!=raw:raise ValueError('Relocation or source preservation failed')
    return final,{'revision':8,'sourceBytes':len(raw),'sourceSHA256':sha(raw),'candidateBytes':len(final),'candidateSHA256':sha(final),
                  'mapVersionExpected':32,'documentedAlarmSoundBit':60117,'undocumentedBuzzerWritesRemoved':True,
                  'alarmTableBounds':[16,112,768,288],'alarmTextColumnPixels':464,'sceneCountsUnchanged':True,
                  'PLCChanged':False,'manualPermitsOrProtectionChanges':False,'nativeOpenCompileObserved':False,'equipmentActions':0,
                  'edits':[{'sourceOffset':at,'sourceBytes':len(old),'targetBytes':len(new),'sourceSHA256':sha(old),'targetSHA256':sha(new),'label':label} for at,old,new,label in sorted(edits,key=lambda e:e[0])]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','recipe','macro','out','report'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();paths=[v.resolve() for v in (a.source,a.recipe,a.macro,a.out,a.report)]
    if len(set(paths))!=5 or any(v.exists() or v.is_symlink() for v in (a.out,a.report)):raise ValueError('Distinct input and NEW output/report required')
    final,report=prepare(a.source,a.recipe,a.macro)
    with a.out.open('xb') as f:f.write(final)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Built NEW HMI-r8:',len(final),'bytes;',report['candidateSHA256'])
    print('Map32/native sound/table fixed; PLC and manual protection unchanged. Native verification remains.')


if __name__=='__main__':main()
