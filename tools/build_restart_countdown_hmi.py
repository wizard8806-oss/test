#!/usr/bin/env python3
"""Source-locked HMI countdown copy using existing, typed ND/MD widgets.

Same-size QString bindings/text and reviewed geometry mirrors only. Existing
numeric widgets/visibility templates are reused; no opaque object construction,
control writes, screen-count changes or unknown flags are patched.
Native SKTool/Simulator validation still required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from apply_hmi_layout_recipe import transform as layout_r1, qstring

SOURCE_DRAFT='7484c9475391201b37d408a68e63233b970a7d33c77e276cdbf7376539a2e5e7'
SOURCE_R1='d9f089f09b87fff4cb347664457fbfa171f297defd96a2fd713b65da23f43175'
SHA=lambda x:hashlib.sha256(x).hexdigest()


def prepare(source,recipe_path):
    source=Path(source);original=source.read_bytes();recipe=json.loads(Path(recipe_path).read_text(encoding='utf-8-sig'))
    if SHA(original)==SOURCE_DRAFT:raw,_=layout_r1(original,recipe)
    elif SHA(original)==SOURCE_R1:raw=original
    else:raise ValueError('Use exact reviewed HMI draft or accepted layout-r1; preserve newer native saves')
    if SHA(raw)!=SOURCE_R1:raise ValueError('Accepted layout-r1 was not reproduced')
    result=bytearray(raw);edits=[]

    def patch(offset,before,after,label):
        if len(before)!=len(after) or result[offset:offset+len(before)]!=before:raise ValueError('Typed field mismatch: '+label)
        result[offset:offset+len(before)]=after;edits.append({'offset':offset,'bytes':len(before),'label':label})

    def strings(old,new,start,stop,count,label):
        if len(old)!=len(new):raise ValueError('QString length must be preserved')
        before,after=qstring(old),qstring(new);positions=[];at=start
        while (at:=raw.find(before,at,stop))>=0:positions.append(at);at+=len(before)
        if len(positions)!=count:raise ValueError('QString mirror mismatch '+label+': '+str(positions))
        for offset in positions:patch(offset,before,after,label)

    def binding(old,new,start,stop,plain,compound,label):
        if plain:strings('R'+str(old),'R'+str(new),start,stop,plain,label+' address')
        if compound:
            before=('R%d#1#6#1#%d#R#1#'%(old,old)).encode('utf-16-be')
            after=('R%d#1#6#1#%d#R#1#'%(new,new)).encode('utf-16-be')
            positions=[];at=start
            while (at:=raw.find(before,at,stop))>=0:
                standalone=raw[at-4:at]==struct.pack('>I',len(before))
                packed=raw[at-2:at]==b'\x00\x03' and raw[at+len(before):at+len(before)+2]==b'\x00\x03'
                if not (standalone or packed):raise ValueError('Address descriptor delimiter differs')
                positions.append(at);at+=len(before)
            if len(positions)!=compound:raise ValueError('Device descriptor mirror count differs: '+label)
            for at in positions:patch(at,before,after,label+' device descriptor')

    # Reuse the uninstalled fourth channel's right-panel numeric readout.
    binding(2503,2528,45500,47628,1,2,'ND10048 total restart seconds')
    binding(2513,2533,45500,47628,0,1,'ND10048 existing nonzero visibility')
    binding(2513,2533,43572,45500,1,2,'MD10050 existing inactive dash')
    # Copy the established seconds format from ND12004:5 digits/0 decimals,
    # preserving font, data type and read-only nature of the numeric widget.
    if raw[353699:353699+6]!=qstring('5') or raw[353705:353705+6]!=qstring('0'):
        raise ValueError('Existing integer-seconds ND format changed')
    patch(46697,qstring('3'),qstring('5'),'ND10048 digit capacity from ND12004')
    patch(46703,qstring('1'),qstring('0'),'ND10048 integer seconds from ND12004')
    strings('Насос 4','ПУСК, с',141154,142550,7,'Text3052 countdown heading')
    strings('Гц','с ',42319,43572,7,'Text10052 seconds unit')
    strings('— А','   ',33439,34706,7,'Text16008 remove unused current placeholder')
    strings('Роль не подтверждена','Сухой ход / питание'.ljust(len('Роль не подтверждена')),137230,141154,6,'MD3054 disabled-slot caption')
    strings('Исключён из AUTO','С учётом защит'.ljust(len('Исключён из AUTO')),132266,137230,6,'MD3056 disabled-slot caption')

    # Hide the fourth bottom status with the same valid-only visibility block
    # already used by its BG10054. In the three-pump PLC R2513 always stays0.
    template=raw[41046:41150]
    expected=[qstring(x) for x in ['1','0','1','0','R2513#1#6#1#2513#R#1#','2','0','2','0','100']]
    if template!=b''.join(expected):raise ValueError('Shared visibility template differs')
    patch(48311,raw[48311:48415],template,'MD10046 copy existing BG10054 valid-only visibility')
    strings('НАСОС 4','       ',49812,51135,7,'Text10044 remove unused fourth caption')

    # Three approved pump images already exist. Only the external picture
    # reference changes; the image itself is not regenerated or edited.
    strings('C:/Users/user/Documents/HMI/Samkoon/Насоска HMI/pumps-4.png',
            'C:/Users/user/Documents/HMI/Samkoon/Насоска HMI/pumps-3.png',225604,226200,1,'ST0 existing external picture')
    objects={x['id']:x for x in recipe['objects']}
    placements={'Text10002':232,'MD10004':232,'Text10016':356,'MD10018':356,
                'Text10030':480,'MD10032':480,
                'MD10014':267.40625,'BG10012':267.40625,
                'MD10028':391.40625,'BG10026':391.40625,
                'MD10042':515.40625,'BG10040':515.40625}
    for name,new_x in placements.items():
        obj=objects[name]
        if raw[obj['graphicsEnd']:obj['graphicsEnd']+len(qstring(name))]!=qstring(name):raise ValueError('Graphic ID differs')
        before=struct.pack('>2d',obj['after']['x'],obj['after']['y'])
        after=struct.pack('>2d',new_x,obj['after']['y'])
        for offset in obj['positionOffsets']:patch(offset,before,after,name+' position for three-pump image')

    # Existing recovery settings page: pending-cause fields show the common
    # remaining wait; editable delay drafts R2540/R2541 stay untouched.
    binding(2520,2538,353301,355000,1,2,'ND12004 dry restart remaining')
    binding(2521,2539,345455,347100,1,2,'ND12012 power restart remaining')
    binding(2524,2532,334800,336000,1,2,'MD12018 countdown reason')
    for old,new in [
        ('Идёт пауза после восстановления подпора.','Обратный отсчёт пуска после сух. хода.'),
        ('Идёт пауза после восстановления питания.','Обратный отсчёт пуска после питания.'),
        ('Пауза завершена: ожидание готовности ПЧ.','Ожидание готовности и условий пуска.')]:
        if len(new)>len(old):raise ValueError('Status text too long')
        strings(old,new.ljust(len(old)),336000,341000,5,'MD12018 state text')

    ordered=sorted(edits,key=lambda x:x['offset'])
    for a,b in zip(ordered,ordered[1:]):
        if a['offset']+a['bytes']>b['offset']:raise ValueError('Overlapping typed edits')
    final=bytes(result)
    if len(final)!=len(raw) or source.read_bytes()!=original:raise ValueError('Size/source changed')
    report={'sourceSHA256':SHA(original),'acceptedLayoutSHA256':SOURCE_R1,
            'candidateSHA256':SHA(final),'candidateBytes':len(final),'typedEdits':ordered,
            'mainCountdownWord':'R2528','visibilityWord':'R2533','statusWord':'R2532',
            'settingsDryWord':'R2538','settingsPowerWord':'R2539',
            'externalPictureRequired':'C:/Users/user/Documents/HMI/Samkoon/Насоска HMI/pumps-3.png',
            'controlBindingsChanged':False,'nativeOpenObserved':False,'offlineSimulatorObserved':False,'equipmentActions':0}
    return final,report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path)
    p.add_argument('--recipe',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--report',required=True,type=Path);a=p.parse_args()
    if len({x.resolve() for x in (a.source,a.recipe,a.out,a.report)})!=4 or any(x.exists() or x.is_symlink() for x in (a.out,a.report)):raise ValueError('New distinct files required')
    result,report=prepare(a.source,a.recipe)
    with a.out.open('xb') as f:f.write(result)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Built new three-pump countdown HMI:',len(result),'bytes;',SHA(result))
    print('Native SKTool/Simulator validation required; original preserved.')


if __name__=='__main__':main()
