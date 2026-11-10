#!/usr/bin/env python3
"""Extend the user-accepted native HMI; preserve its layout and rebuilt HAD.

All macro reads remain Batch16 and BootAck scalar W remains last. Adds
native fault alarm groups, code/reset page15 and restored boot-history16.
Logo path is relinked; native loading/saver settings still require SKTool.
No binary source, original logo or vendor code is published by this helper.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import build_animation_probe_hmi as ui
from reorder_animation_macro_r14a import VARIABLES, ORDER, entry, packed
from repair_skm_section_index import read_directory
from skm_project_header import read_project_header
from skm_page_storage import read_page_storage,page_storage_extensions
from skm_alarm_catalog import read_definitions,read_directory_for_names,directory_bytes,validate_alarm_catalog,compact_fault_definitions,require_sk_group_limit,with_sequential_alarm_ids,validate_alarm_identities

SOURCE_SHA='359906cfd85975b9d2955f6b03b8f996761a7612fcbf37a23b95c8e5ee6c0b4c'
SOURCE_BYTES=1273673
ROOT=Path(__file__).resolve().parents[1]
EXTENSION=ROOT/'assets/hmi/fault-reset-r15/fault_reset.c'
CATALOG=ROOT/'assets/hmi/native-vfd-faults-r14/catalog.json'
LOGO_OLD='C:/Users/user/Desktop/Pump_HMI_35/automatikakg.jpg'
LOGO_TARGET='C:/Users/user/CodexProjects/pump-station/.worktrees/station002-fault-reset-local-15/assets/automatikakg.jpg'
GROUP=re.compile(bytes.fromhex('00010017')+b'\x00\x00\x00[\x01-\x7f]'+bytes.fromhex('000100'))
qs,apply,geometry,qscan=ui.qs,ui.apply,ui.geometry,ui.qscan
sha=lambda b:hashlib.sha256(b).hexdigest()
u32=lambda n:struct.pack('>I',n)

def scene(raw,number,prefix=None):
    # HAD's native group contains more than nine children.
    original=ui.GROUP
    try:
        ui.GROUP=GROUP
        return ui.scene(raw,number,prefix)
    finally:ui.GROUP=original

def source_macro(raw):
    marker='#include "MacroInit.h"'.encode('utf-16-be')
    positions=[m.start()-4 for m in re.finditer(re.escape(marker),raw)]
    sources=[]
    for at in positions:
        n=int.from_bytes(raw[at:at+4],'big');sources.append(raw[at+4:at+4+n].decode('utf-16-be'))
    if len(sources)!=2 or sources[0]!=sources[1]:raise ValueError('Two identical C mirrors required')
    return positions,sources[0]

def extend_macro(old):
    extension=EXTENSION.read_text(encoding='utf8').replace('\r\n','\n')
    def replace_once(text,a,b):
        if text.count(a)!=1:raise ValueError('Macro anchor differs: '+a)
        return text.replace(a,b)
    new=replace_once(old,'void Macro_main(IN *p)',extension+'\nvoid Macro_main(IN *p)')
    new=replace_once(new,'    int cl50_new_generation;','    int cl50_new_generation;\n    int native_new_event;')
    new=replace_once(new,'    PumpAnimation(p);','    PumpAnimation(p);\n    native_new_event = NativeFaultService(p);\n    DriveResetService(p);')
    new=replace_once(new,'        current = 0u;','        current = alarm_previous & 0x07000000u;')
    new=replace_once(new,'    request = LocalBit[800];','    current = (current & 0x00ffffffu) | native_alarm_mask;\n    request = LocalBit[800];')
    new=replace_once(new,'|| (cl50_new_generation && current != 0u))','|| ((cl50_new_generation || native_new_event) && current != 0u))')
    return new

def variable_rows():
    previous=[VARIABLES[i] for i in ORDER]
    previous=[(n,'Batch 16-Bit Unsigned Int','2',m,a) if n in ('MapVersion','PumpAnimLeader') else (n,t,s,m,a) for n,t,s,m,a in previous]
    new=previous[:-1]+[
        ('NativeFaultData','Batch 16-Bit Unsigned Int','80','R','3040'),
        ('DriveResetData','Batch 16-Bit Unsigned Int','64','R','3200'),
        ('DriveResetRequest','Batch 16-Bit Unsigned Int','12','W','3216')]+previous[-1:]
    return previous,new

def properties(raw,name):
    for at in range(len(raw)-4):
        count=int.from_bytes(raw[at:at+4],'big')
        if not 45<=count<=350:continue
        pos=at+4;values=[]
        try:
            for _ in range(count):
                size=int.from_bytes(raw[pos:pos+4],'big');pos+=4
                if size>4000 or size%2 or pos+size>len(raw):raise ValueError()
                values.append(raw[pos:pos+size].decode('utf-16-be'));pos+=size
            if values[19]==name:return at,pos,values
        except (ValueError,UnicodeError):pass
    raise ValueError('Native property table missing: '+name)

def set_properties(raw,name,changes):
    start,end,values=properties(raw,name)
    for index,value in changes.items():values[index]=str(value)
    return raw[:start]+u32(len(values))+b''.join(qs(v) for v in values)+raw[end:]

def replace_string(raw,old,new,expected=None):
    count=raw.count(qs(old))
    if not count or expected is not None and count!=expected:raise ValueError('QString count differs: '+old+' '+str(count))
    return raw.replace(qs(old),qs(new))

def clone(template,identity,ordinal,x,y,width,height):
    raw=template['raw'];old=template['id']
    if raw.count(qs(old)) not in (1,2):raise ValueError('Identity mirror count differs')
    trailer=qs(str(template['ordinal']))+struct.pack('>d',template['ordinal'])
    if not raw.endswith(trailer):raise ValueError('Ordinal trailer differs')
    raw=raw[:-len(trailer)]+qs(str(ordinal))+struct.pack('>d',ordinal)
    raw=replace_string(raw,old,identity)
    return geometry(raw,x,y,width,height)

def pages(raw):
    _,probe=scene(raw,13);_,buttons=scene(raw,9,'SB');_,bits=scene(raw,9,'BB');_,lamps=scene(raw,1,'MD')
    serial=91000;widgets=[];bindings=[]
    def next_id(kind):
        nonlocal serial
        name=kind+str(serial);serial+=1
        if qs(name) in raw:raise ValueError('New ID already exists')
        return name
    def text(caption,x,y,w,h=24):
        name=next_id('Text');b=clone(probe['Text88003'],name,serial,x,y,w,h)
        widgets.append(replace_string(b,'F ПЛК',caption,7))
    def numeric(address,x,y,w=100,h=30):
        name=next_id('ND');b=clone(probe['ND88012'],name,serial,x,y,w,h)
        if address.startswith('R'):n=address[1:];desc=address+'#1#6#1#'+n+'#R#1#'
        else:n=address[2:];desc=address+'#0#1#100#'+n+'#LW#1#'
        b=replace_string(b,'R2500#1#6#1#2500#R#1#',desc)
        b=replace_string(b,'R2500',address)
        widgets.append(b);bindings.append((name,address))
    old_captions=('Нет данных','Остановлен','Работа','Подготовка','ПЧ не готов')
    def state(address,captions,x,y,w,h=30,colors=None):
        name=next_id('MD');b=clone(lamps['MD10004'],name,serial,x,y,w,h)
        b=replace_string(b,'LW903#0#1#100#903#LW#1#',address+'#0#1#100#'+address[2:]+'#LW#1#')
        b=replace_string(b,'LW903',address)
        for old,new in zip(old_captions,captions):b=replace_string(b,old,new,6 if old==old_captions[0] else 5)
        if colors is None:
            colors=('224+224+224','255+220+130','180+230+190','245+210+150','245+160+160')
        changes={}
        for i,color in enumerate(colors):
            changes.update({80+4*i:'1',81+4*i:color,82+4*i:color,83+4*i:color,
                            101+3*i:'0+0+0',102+3*i:'0',103+3*i:'14'})
        b=set_properties(b,name,changes);widgets.append(b);bindings.append((name,address))
    def screen_button(caption,target,x,y,w=184):
        name=next_id('SB');b=clone(buttons['SB24002'],name,serial,x,y,w,32)
        b=replace_string(b,'Запуски ПЛК',caption)
        b=set_properties(b,name,{48:target-1,49:target-1,56:'Screen'+str(target),57:target-1})
        widgets.append(b)
    def reset_button(drive,x,y,w=180):
        name=next_id('BB');b=clone(bits['BB18004'],name,serial,x,y,w,32)
        b=replace_string(b,'Отключить звук','Сброс ПЧ '+str(drive),13)
        b=replace_string(b,'LB800#0#0#100#800#LB#0#','LB'+str(1249+drive)+'#0#0#100#'+str(1249+drive)+'#LB#0#')
        b=replace_string(b,'LB800','LB'+str(1249+drive))
        widgets.append(b);bindings.append((name,'LB'+str(1249+drive)))
    text('КОДЫ И СБРОС АВАРИЙ ПЧ',8,8,784,28)
    text('Сброс разрешён в СТОП. Команда не запускает насос.',8,40,784)
    for caption,x,w in (('ПЧ',12,48),('Код',72,100),('Состояние данных',184,345),('Последний',550,110),('Обновления',672,116)):
        text(caption,x,74,w)
    fault_states=('Нет данных','Свежие: аварии нет','Свежие: см. журнал','Данные устарели','Нет связи / версии')
    result_states=('Сброс не запрошен','Выполняется','Сброс подтверждён','Переведите в СТОП','Не подтверждено')
    for i in range(3):
        y=104+96*i;text(str(i+1),12,y,48,30)
        numeric('R'+str(3040+i),72,y)
        state('LW'+str(956+i),fault_states,184,y,345,
              colors=('224+224+224','180+230+190','245+160+160','245+210+150','224+224+224'))
        numeric('R'+str(3053+i),556,y,100)
        numeric('R'+str(3046+i),680,y,100)
        reset_button(i+1,72,y+38)
        state('LW'+str(950+i),result_states,264,y+38,514,32)
    text('Число — код ПЧ; 52 = A52. Неизвестные коды сохраняются числом.',8,380,784)
    state('LW947',('Готово к запросу','Обмен выполняется','Сброс подтверждён','Требуется СТОП','Нет свежего подтверждения связи'),8,408,784,26)
    for i,(caption,target) in enumerate((('Станция',1),('Аварии',9),('Зонд',13),('Запуски ПЛК',16))):screen_button(caption,target,8+200*i,442)
    codes=list(widgets);widgets.clear();serial=92000
    text('ИСТОРИЯ ЗАПУСКОВ ПЛК',8,8,784,28)
    text('Записей:',8,48,140);numeric('LW51001',160,46,100)
    for i,label in enumerate(('Год','Месяц','День','Час','Минута','Секунда')):text(label,16+128*i,96,118)
    for row in range(5):
        for col in range(6):numeric('LW'+str(51002+6*row+col),16+128*col,130+50*row,118,32)
    text('Новые записи сверху. Время фиксирует панель при запуске ПЛК.',8,402,784)
    for i,(caption,target) in enumerate((('Станция',1),('Аварии',9),('Коды ПЧ',15))):screen_button(caption,target,8+264*i,442,250)
    history=list(widgets)
    count_at,_=scene(raw,13)
    prefix=raw[count_at-103:count_at+4]
    if len(prefix)!=107 or prefix.count(qs('Screen13'))!=1:raise ValueError('Page template prefix differs')
    def wrap(number,rows):return prefix[:-4].replace(qs('Screen13'),qs('Screen'+str(number)))+u32(len(rows))+b''.join(rows)
    return wrap(15,codes)+wrap(16,history),bindings,len(codes),len(history)

def alarm_groups(raw,catalog):
    name=qs('События станции')
    if raw.count(name)!=1:raise ValueError('Alarm group anchor differs')
    anchor=raw.index(name);start=anchor-7;count_at=start-4
    if raw[count_at:start]!=u32(1) or raw[start:anchor]!=bytes.fromhex('00190000000101'):
        raise ValueError('Original alarm-group header differs')
    p=anchor
    def readq():
        nonlocal p
        n=int.from_bytes(raw[p:p+4],'big');b=raw[p:p+4+n];p+=4+n;return b
    assert readq()==name
    if readq()!=qs('R2550'):raise ValueError('Original alarm address differs')
    if raw[p:p+3]!=bytes.fromhex('010601'):raise ValueError('Alarm protocol differs')
    p+=3
    if readq()!=qs('2550') or readq()!=qs('R') or raw[p]!=1:raise ValueError('Alarm key differs')
    p+=1
    for expected in (b'\x01'*24+b'\x00',b'\x00'*25):
        if raw[p:p+4]!=u32(25) or raw[p+4:p+29]!=expected:raise ValueError('Original alarm vector differs')
        p+=29
    if raw[p:p+8]!=u32(1)+u32(25):raise ValueError('Alarm language/messages count differs')
    p+=8
    for _ in range(25):readq()
    if raw[p:p+4]!=u32(1):raise ValueError('Alarm language keys differ')
    p+=4
    if readq()!=qs('0\x01'):raise ValueError('Alarm language key differs')
    if raw[p:p+4]!=u32(0):raise ValueError('Analog group boundary differs')
    original=raw[start:p]
    def group(label,base,messages):
        n=len(messages)
        return (struct.pack('>HH',n,0)+bytes.fromhex('000101')+qs(label)
            +qs('R'+str(base))+bytes.fromhex('010601')+qs(str(base))+qs('R')+b'\x01'
            +u32(n)+b'\x01'*n+u32(n)+b'\x00'*n+u32(1)+u32(n)+b''.join(map(qs,messages))
            +u32(1)+qs('0\x01'))
    groups=[];captions=[]
    for drive in (1,2,3):
        for part,(first,n) in enumerate(((1,32),(33,32),(65,16))):
            messages=[]
            for code in range(first,first+n):
                label='A52' if code==52 else str(code)
                messages.append('ПЧ %d: код %s — %s'%(drive,label,catalog['codes'].get(str(code),'Расшифровки нет')))
            base=3056+5*(drive-1)+2*part
            groups.append(group('ПЧ%d коды %d..%d'%(drive,first,first+n-1),base,messages));captions+=messages
        groups.append(group('ПЧ%d неизвестный код'%drive,3070+drive,
            ['ПЧ %d: неизвестный код — откройте «Коды ПЧ»'%drive]))
    compacted=with_sequential_alarm_ids(compact_fault_definitions(u32(13)+original+b''.join(groups)),0)
    return (count_at,raw[count_at:p],compacted,'native fault alarm groups'),captions

def prepare(source,logo_target=LOGO_TARGET):
    source=Path(source);raw=source.read_bytes()
    if len(raw)!=SOURCE_BYTES or sha(raw)!=SOURCE_SHA:raise ValueError('Use exact latest user-accepted SKM; newer saves need reviewed adaptation')
    if not logo_target.lower().endswith(('.jpg','.jpeg','.png')) or '\0' in logo_target:raise ValueError('Logo target invalid')
    logo_target=logo_target.replace('\\','/')
    header=read_project_header(raw)
    if header['pageCount']!=14 or header['model']!='SK-070HE' or header['resolution']!=(800.0,480.0) or header['common']!=[(0,-1)]*14:
        raise ValueError('Source page common-data header differs')
    directory=read_directory(raw);edits=[];positions,old_c=source_macro(raw);new_c=extend_macro(old_c)
    read_page_storage(raw)
    for at in positions:edits.append((at,qs(old_c),qs(new_c),'fault/reset C mirror'))
    before,after=variable_rows()
    for old,new,label in ((packed(before),packed(after),'packed variables'),
            (u32(len(before))+b''.join(map(entry,before)),u32(len(after))+b''.join(map(entry,after)),'native variables')):
        if raw.count(old)!=1:raise ValueError('Macro variable table differs')
        edits.append((raw.index(old),old,new,label))
    # Preserve all widget bytes except the explicit navigation/counter changes.
    for number,identity,prefix,target,caption in ((1,'SB6010','SB',13,None),(9,'SB24002','SB',15,'Коды ПЧ')):
        _,objects=scene(raw,number,prefix);obj=objects[identity];old=obj['raw']
        new=set_properties(old,identity,{48:target-1,49:target-1,56:'Screen'+str(target),57:target-1})
        if caption:new=replace_string(new,'Запуски ПЛК',caption)
        edits.append((obj['start'],old,new,'navigation '+identity))
    _,objects=scene(raw,9,'ND');obj=objects['ND8278'];old=obj['raw']
    new=replace_string(old,'R2363#1#6#1#2363#R#1#','R3077#1#6#1#3077#R#1#')
    new=replace_string(new,'R2363','R3077');edits.append((obj['start'],old,new,'display alarm count only'))
    addition,bindings,codes_n,history_n=pages(raw)
    ui_end=1220380
    trailer=qs('1003')+struct.pack('>d',1003)
    if not raw[:ui_end].endswith(trailer) or raw.count(trailer)!=1:raise ValueError('Last UI boundary differs')
    edits.append((ui_end,b'',addition,'new pages15/16'))
    if raw[56:60]!=u32(14):raise ValueError('Root page count differs')
    edits.append((56,u32(14),u32(16),'root page count'))
    # The count prefixes a sceneCommonData pair PER PAGE. Updating only
    # the count makes native readers consume16bytes of Scene1 as metadata.
    edits.append((header['commonEnd'],b'',struct.pack('>ii',0,-1)*2,'new page common-data entries'))
    old_map=u32(14)+b''.join(u32(i)+u32(i) for i in range(13,-1,-1))
    new_map=u32(16)+b''.join(u32(i)+u32(i) for i in range(15,-1,-1))
    if raw.count(old_map)!=1:raise ValueError('Page identity map differs')
    edits.append((raw.index(old_map),old_map,new_map,'page identity map'))
    # Native16-page SaveAs also extends two arrays outside the scene stream.
    edits.extend(page_storage_extensions(raw,16))
    group_edit,captions=alarm_groups(raw,json.loads(CATALOG.read_text(encoding='utf8')));edits.append(group_edit)
    source_groups=read_definitions(raw)
    source_names=[g['name'] for g in source_groups['groups']]
    name_directory=read_directory_for_names(raw,source_names)
    new_names=[g['name'] for g in read_definitions(group_edit[2],0)['groups']]
    edits.append((name_directory['start'],raw[name_directory['start']:name_directory['end']],
                  directory_bytes(new_names),'native alarm group directory'))
    if raw.count(qs(LOGO_OLD))!=1:raise ValueError('Brand background link differs')
    edits.append((raw.index(qs(LOGO_OLD)),qs(LOGO_OLD),qs(logo_target),'logo asset reference'))
    def shifted(address):
        if any(at<address<at+len(old) for at,old,_,_ in edits):raise ValueError('Directory pointer inside an edited field')
        return address+sum(len(new)-len(old) for at,old,new,_ in edits if at<=address)
    entries=[shifted(v) for v in directory['entries']];dir_at=shifted(directory['offset'])
    for i,(old,new) in enumerate(zip(directory['entries'],entries)):
        edits.append((directory['offset']+4+8*i,struct.pack('>Q',old),struct.pack('>Q',new),'directory entry'+str(i)))
    edits.append((directory['locatorOffset'],struct.pack('>Q',directory['offset']),struct.pack('>Q',dir_at),'directory locator'))
    result=apply(raw,edits);checked=read_directory(result)
    fixed_header=read_project_header(result)
    page_storage=read_page_storage(result)
    alarm_catalog=validate_alarm_catalog(result)
    alarm_ids=validate_alarm_identities(result)
    require_sk_group_limit(alarm_catalog['groupCount'])
    if alarm_catalog['groupCount']!=7 or alarm_catalog['directoryCount']!=7:
        raise ValueError('Alarm definitions/name directory do not match')
    if fixed_header['pageCount']!=16 or fixed_header['model']!=header['model'] or fixed_header['firstSceneRect']!=header['firstSceneRect']:
        raise ValueError('Final page count/model/first QRectF differs')
    if checked['entries']!=entries or checked['offset']!=dir_at:raise ValueError('Directory relocation differs')
    inverse=[];delta=0
    for at,old,new,label in sorted(edits,key=lambda v:v[0]):
        inverse.append((at+delta,new,old,label));delta+=len(new)-len(old)
    if apply(result,inverse)!=raw or source.read_bytes()!=raw:raise ValueError('Complete inverse/source preservation failed')
    return result,dict(sourceSHA256=sha(raw),sourceBytes=len(raw),candidateSHA256=sha(result),candidateBytes=len(result),
        readInputs=[dict(name=n,bytes=int(size),address='R'+addr) for n,t,size,mode,addr in after if mode=='R'],
        writeInputs=[dict(name=n,type=t,bytes=int(size or 2),address='R'+addr) for n,t,size,mode,addr in after if mode=='W'],
        batchPrefixBytesBeforeBootAck=216,BootAckWLast=True,allReadInputsBatch16=True,
        newPageObjects={'15':codes_n,'16':history_n},bindings=bindings,alarmGroups=7,alarmDirectoryEntries=7,
        alarmDirectoryCompanionEntries=7,documentedSKGroupLimit=10,newCodeMessages=len(captions),
        alarmGroupIds=alarm_ids,
        knownDescriptions=len(json.loads(CATALOG.read_text(encoding='utf8'))['codes']),unknownCodeNumeric=True,
        featureMarker=27130,resetMarker=27131,probe27124Preserved=True,
        model=fixed_header['model'],resolution=list(fixed_header['resolution']),sceneCommonPairs=16,
        pageFlagEntries=page_storage['flagEntries'],pageWordEntries=page_storage['wordEntries'],
        logoReference=logo_target,logoBytesEmbedded=False,nativeLoadingSaverSettingsConfigured=False,
        HAD1794244624Preserved=True,userMainLayoutPreserved=True,
        edits=[dict(offset=at,oldBytes=len(old),newBytes=len(new),label=label) for at,old,new,label in sorted(edits,key=lambda v:v[0])],
        completeInversePreservation=True,nativeCompileObserved=False,hardwareActions=0,
        remaining='Native Start Setting loading/saver; Compile/generated Batch16 aliases; simulator; later real stopped-drive reset acceptance')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','out','report'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--logo-target',default=LOGO_TARGET);a=p.parse_args()
    if len({v.resolve() for v in (a.source,a.out,a.report)})!=3 or any(v.is_symlink() for v in (a.source,a.out,a.report)) or a.out.exists() or a.report.exists():raise ValueError('NEW distinct regular output/report required')
    data,report=prepare(a.source,a.logo_target)
    with a.out.open('xb') as f:f.write(data)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Created fault/reset HMI:',len(data),sha(data),'Native Compile/loading settings remain.')
if __name__=='__main__':main()
