#!/usr/bin/env python3
"""Add two cascade settings to a NEW r9 HMI, preserving its other screens.

Reuse complete native input/display/text widgets and the STOP edit session.
The two new inputs require the PLC extension marker27116. All section
addresses and EOF are relocated. Native SKTool acceptance remains separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from repair_skm_section_index import read_directory

SOURCE_SHA='1b38484782f2c325d3f731f70d2b6079a6d94a033388b2789ab7bb7ad7f4321e'
sha=lambda b:hashlib.sha256(b).hexdigest()
GROUP=re.compile(bytes.fromhex('00010017')+b'\x00\x00\x00[\x01-\x09]'+bytes.fromhex('000100'))
def qs(s):
    b=s.encode('utf-16-be');return struct.pack('>I',len(b))+b
def descriptor(n):return 'R%d#1#6#1#%d#R#1#'%(n,n)
def apply(raw, edits):
    out,cursor=bytearray(),0
    for at,old,new,label in sorted(edits,key=lambda v:v[0]):
        if at<cursor or raw[at:at+len(old)]!=old:raise ValueError('Differing/overlapping field: '+label)
        out.extend(raw[cursor:at]);out.extend(new);cursor=at+len(old)
    out.extend(raw[cursor:]);return bytes(out)
def strings(raw,old,new,count):
    needle=qs(old);positions=[m.start() for m in re.finditer(re.escape(needle),raw)]
    if len(positions)!=count:raise ValueError('QString mirrors differ: '+old)
    return [(at,needle,qs(new),old) for at in positions]
def geometry(raw,xy,wh=None):
    edits=[]
    for old,new,label,counts in ((struct.unpack_from('>2d',raw,85),xy,'position',(2,3)),
                                  (struct.unpack_from('>2d',raw,28),wh,'size',(2,3))):
        if new is None:continue
        needle=struct.pack('>2d',*old);positions=[m.start() for m in re.finditer(re.escape(needle),raw)]
        if len(positions) not in counts:raise ValueError('Geometry mirrors differ')
        edits += [(at,needle,struct.pack('>2d',*new),label) for at in positions]
    return apply(raw,edits)


def prepare(source):
    raw=Path(source).read_bytes()
    if len(raw)!=1272222 or sha(raw)!=SOURCE_SHA:raise ValueError('Use exact alarm-table r9; preserve other native saves')
    directory=read_directory(raw)
    at=raw.index(qs('Screen2')+b'\xff'*4)+len(qs('Screen2'))+4
    if struct.unpack_from('>I',raw,at)[0]!=45:raise ValueError('Cascade scene count differs')
    stop=335684;starts=[m.start() for m in GROUP.finditer(raw,at+4,stop)]
    if len(starts)!=45:raise ValueError('Cascade scene widget inventory differs')
    objects={}
    for a,z in zip(starts,starts[1:]+[stop]):
        block=raw[a:z]
        ids=[]
        for m in re.finditer(rb'\x00\x00\x00[\x08-\x40]',block):
            n=int.from_bytes(m[0],'big')
            if n%2:continue
            try:name=block[m.start()+4:m.start()+4+n].decode('utf-16-be')
            except UnicodeError:continue
            if re.fullmatch(r'(?:NE|ND|Text|BB|MD|SB)[0-9]+',name):ids.append(name)
        if not ids or len(set(ids))!=1:raise ValueError('Widget identity differs')
        name=ids[0];ordinal=int(re.search(r'\d+$',name)[0])
        if not block.endswith(qs(str(ordinal))+struct.pack('>d',ordinal)):raise ValueError('Native widget boundary differs')
        objects[name]=(a,z,block)
    edits=[];changed=[]
    # Eight 28px rows. Existing footer/buttons/status remain in place.
    row_y={5020:76.,5028:108.,5036:140.,5044:172.,5052:236.,5060:268.}
    for label,y in row_y.items():
        for name in ('Text%d'%label,'ND%d'%(label+2),'Text%d'%(label+4),'NE%d'%(label+6)):
            a,z,block=objects[name];x=struct.unpack_from('>2d',block,85)[0];width=struct.unpack_from('>2d',block,28)[0]
            current=geometry(block,(x,y),(width,28.))
            if name=='Text5044':current=apply(current,strings(current,'Выдержка добавления, с','Задержка 1-го ведомого, с',7))
            if name=='Text5036':current=apply(current,strings(current,'Частота ведущего для снятия, Гц','Частота снятия с выдержкой, Гц',7))
            edits.append((a,block,current,name));changed.append(name)
    a,z,block=objects['Text5068'];current=geometry(block,(18.75,334.),(762.5,18.))
    current=apply(current,strings(current,'Снятие: частота ниже добавления. Зона возврата меньше недобора давления.',
                                  'Задержки независимы. Быстрый останов — без выдержки снятия.',7))
    edits.append((a,block,current,'cascade help'))
    added=[]
    def clone(name,newname,y,oldreg=None,newreg=None,caption=None,limits=None):
        block=objects[name][2];x=struct.unpack_from('>2d',block,85)[0];width=struct.unpack_from('>2d',block,28)[0]
        current=geometry(block,(x,y),(width,28.))
        if limits:
            oldlo,oldhi,newlo,newhi=limits
            current=apply(current,[(1078,qs(oldlo)+qs(oldhi),qs(newlo)+qs(newhi),'input bounds')])
        current=apply(current,strings(current,name,newname,2 if name.startswith(('NE','ND')) else 1))
        oldnum=re.search(r'\d+$',name)[0];newnum=re.search(r'\d+$',newname)[0]
        trailer=qs(oldnum)+struct.pack('>d',int(oldnum))
        current=apply(current,[(len(current)-len(trailer),trailer,qs(newnum)+struct.pack('>d',int(newnum)),'ordinal')])
        if oldreg is not None:
            current=apply(current,strings(current,'R'+str(oldreg),'R'+str(newreg),2 if name.startswith('NE') else 1)
                          +strings(current,descriptor(oldreg),descriptor(newreg),2 if name.startswith('NE') else 1))
        if caption:current=apply(current,strings(current,caption[0],caption[1],7))
        if limits:
            current=apply(current,strings(current,descriptor(2329),descriptor(2886),1)+strings(current,'27110','27116',1))
        added.append(current)
    # Preserve native input-over-dash stacking. The ordinal is explicit;
    # raising the fallback Text above its input would obscure the value.
    clone('NE5050','NE71006',204.,2163,2888,limits=('1','600','1','3600'))
    clone('Text5048','Text71004',204.)
    clone('ND5046','ND71002',204.,2123,2885)
    clone('Text5044','Text71000',204.,caption=('Выдержка добавления, с','Задержка 2-го ведомого, с'))
    clone('NE5042','NE71016',300.,2162,2887,limits=('200','499','100','499'))
    clone('Text5040','Text71014',300.)
    clone('ND5038','ND71012',300.,2122,2884)
    clone('Text5036','Text71010',300.,caption=('Частота ведущего для снятия, Гц','Быстрый останов ведомых ниже, Гц'))
    if any(str(i).encode('utf-16-be') in raw for i in (71000,71002,71004,71006,71010,71012,71014,71016)):
        raise ValueError('New widget identity already exists')
    edits.append((stop,b'',b''.join(added),'two new setting rows'))
    edits.append((at,struct.pack('>I',45),struct.pack('>I',53),'cascade item count'))
    def shifted(pos):return pos+sum(len(new)-len(old) for p,old,new,_ in edits if p<pos)
    entries=[shifted(v) for v in directory['entries']]
    for i,v in enumerate(directory['entries']):edits.append((directory['offset']+4+8*i,struct.pack('>Q',v),struct.pack('>Q',entries[i]),'section directory'))
    edits.append((directory['locatorOffset'],struct.pack('>Q',directory['offset']),struct.pack('>Q',shifted(directory['offset'])),'back-pointer'))
    final=apply(raw,edits)
    if read_directory(final)['entries']!=entries or Path(source).read_bytes()!=raw:raise ValueError('Directory/source preservation differs')
    return final,{'revision':10,'sourceSHA256':sha(raw),'candidateSHA256':sha(final),'candidateBytes':len(final),
                  'cascadeRows':8,'addedWidgets':8,'allOtherScreensAndMacrosPreserved':True,'alarmTableR9Preserved':True,
                  'newInputPLCMarker':'R2886=27116','nativeOpenCompileObserved':False,'equipmentActions':0,
                  'edits':[{'offset':p,'sourceBytes':len(old),'targetBytes':len(new),'label':label} for p,old,new,label in sorted(edits,key=lambda v:v[0])]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','out','report'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    if len({v.resolve() for v in (a.source,a.out,a.report)})!=3 or any(v.exists() or v.is_symlink() for v in (a.out,a.report)):raise ValueError('Distinct source and NEW output/report required')
    data,report=prepare(a.source)
    with a.out.open('xb') as f:f.write(data)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Built NEW cascade HMI r10:',len(data),'bytes;',sha(data),'; native SKTool check remains.')


if __name__=='__main__':main()
