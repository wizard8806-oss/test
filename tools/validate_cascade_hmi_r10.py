#!/usr/bin/env python3
"""Check native widget preservation and eight-row cascade layout, not GUI rendering."""
import argparse
import json
from pathlib import Path
import re
import struct
from build_cascade_hmi_r10 import prepare,qs,GROUP,descriptor
from repair_skm_section_index import read_directory


def validate(source,candidate):
    raw=Path(source).read_bytes();final=Path(candidate).read_bytes();expected,report=prepare(source)
    assert final==expected
    restored,cursor=bytearray(),0
    def shifted(pos):return pos+sum(e['targetBytes']-e['sourceBytes'] for e in report['edits'] if e['offset']<pos)
    for e in report['edits']:
        a=e['offset'];at=shifted(a)
        restored.extend(final[cursor:at]);restored.extend(raw[a:a+e['sourceBytes']]);cursor=at+e['targetBytes']
    restored.extend(final[cursor:]);assert bytes(restored)==raw
    directory=read_directory(final);start=final.index(qs('Screen2')+b'\xff'*4)+len(qs('Screen2'))+4
    assert struct.unpack_from('>I',final,start)[0]==53
    end=shifted(335684)+sum(e['targetBytes'] for e in report['edits'] if e['offset']==335684 and not e['sourceBytes'])
    starts=[m.start() for m in GROUP.finditer(final,start+4,end)]
    assert len(starts)==53;objects={}
    for a,z in zip(starts,starts[1:]+[end]):
        s=final[a:z]
        found=[]
        for m in re.finditer(rb'\x00\x00\x00[\x08-\x40]',s):
            n=int.from_bytes(m[0],'big')
            if n%2:continue
            try:name=s[m.start()+4:m.start()+4+n].decode('utf-16-be')
            except UnicodeError:continue
            if re.fullmatch(r'(?:NE|ND|Text|BB|MD|SB)[0-9]+',name):found.append(name)
        assert len(set(found))==1;objects[found[0]]=s
    for name,reg in (('NE71006',2888),('NE71016',2887)):
        block=objects[name]
        assert block.count(qs(descriptor(reg)))==2 and block.count(qs('R'+str(reg)))==2
        assert qs(descriptor(2886)) in block and qs('27116') in block
        assert qs('M1464#1#2#1#1464#M#0#') in block,'STOP/edit enable lost'
    for name,reg in (('ND71002',2885),('ND71012',2884)):
        assert qs('R'+str(reg)) in objects[name] and qs(descriptor(reg)) in objects[name]
    rows=[('NE5026',76.),('NE5034',108.),('NE5042',140.),('NE5050',172.),
          ('NE71006',204.),('NE5058',236.),('NE5066',268.),('NE71016',300.)]
    for name,y in rows:
        block=objects[name];x,actual_y=struct.unpack_from('>2d',block,85);width,height=struct.unpack_from('>2d',block,28)
        assert actual_y==y and height==28 and 0<x<x+width<800
    assert all(y+28<rows[i+1][1] for i,(_,y) in enumerate(rows[:-1]))
    # Read-only displays are to the right, labels to the left, with no
    # fourth column. Footer and service controls keep their source bytes.
    assert qs('Задержка 2-го ведомого, с') in objects['Text71000']
    assert qs('Быстрый останов ведомых ниже, Гц') in objects['Text71010']
    for input_name,fallback_name in (('NE71006','Text71004'),('NE71016','Text71014')):
        input_z=struct.unpack_from('>d',objects[input_name],len(objects[input_name])-8)[0]
        fallback_z=struct.unpack_from('>d',objects[fallback_name],len(objects[fallback_name])-8)[0]
        assert input_z>fallback_z,'Fallback dash would cover the new input'
    return {'eightRowsFit':True,'newSettingBindingsChecked':True,'STOPApplyEnablePreserved':True,
            'allOtherBytesRestoredExactly':True,'sectionDirectoryValid':True,'nativeRenderingObserved':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','candidate','report'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();result=validate(a.source,a.candidate)
    with a.report.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS: eight cascade rows, bindings, directory and exact unrelated-byte preservation; GUI check remains.')


if __name__=='__main__':main()
