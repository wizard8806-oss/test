#!/usr/bin/env python3
"""Read-only checks of compiled countdown observation and typed HMI edits.

Models display calculations from snapshots of the existing controller;
does not model the restart controller, serial link, HMI engine or equipment.
"""
import argparse
import hashlib
import json
from pathlib import Path

from build_restart_countdown_pdw import prepare as plc_prepare,DISPLAY_REGISTERS
from build_restart_countdown_hmi import prepare as hmi_prepare,SOURCE_R1,qstring
from apply_hmi_layout_recipe import transform as layout_r1
from build_setpoint_feedback_pdw_01 import layout
from check_native_drive_edit_02 import unpack
from validate_three_pump_pdw_candidate import Machine


def validate(plc_source,plc_candidate,hmi_source,hmi_candidate,recipe_path,vendor=None):
    before=unpack(plc_source);after=unpack(plc_candidate)
    expected,report=plc_prepare(plc_source)
    assert after['bytes']==expected
    a,b=layout(before['bytes']),layout(after['bytes'])
    point,delta=report['insertionPC'],report['insertedProgramBytes']
    normalized=b['image'][:point]+b['image'][point+delta:]+b'\xff'*delta
    assert normalized[512:]==a['image'][512:]
    assert a['payload']==b['payload'] and before['tables']==after['tables']
    labels={row['label'] for row in report['networks']}
    assert [(pc-(delta if pc>=point else 0),label) for pc,label in after['rungs'] if label not in labels]==before['rungs']
    codes=[]
    for i,(pc,label) in enumerate(after['rungs']):
        if label in labels:codes.append(after['image'][pc:after['rungs'][i+1][0]])
    assert len(codes)==len(labels)
    cases=[]

    def observe(name,dry=False,power=False,ds=15,ps=15,de=0,pe=0,timer=0,
                water=True,mains=True,auto=True,emergency=False,boot=False,
                pressure=True,hp=True,leader=True,stopped=True,context=True):
        m=Machine();dry=bool(dry and auto and not emergency);power=bool(power and auto and not emergency)
        pending=dry or power;count_context=auto and not emergency and not boot
        valid_dry=15<=ds<=3600;valid_power=15<=ps<=3600
        dry_enabled=count_context and dry and water and valid_dry
        power_enabled=count_context and power and mains and valid_power
        dry_done=not dry or (dry_enabled and de==ds)
        power_done=not power or (power_enabled and pe==ps)
        both_done=dry_done and power_done and valid_dry and valid_power
        old_status=5 if pending else 0
        if dry and water and not dry_done:old_status=3
        if power and mains and not power_done:old_status=4
        if dry and not water:old_status=1
        if power and not mains:old_status=2
        if pending and not (valid_dry and valid_power):old_status=7
        if auto and emergency:old_status=6
        m.regs.update({('R',2520):ds&65535,('R',2521):ps&65535,('R',2522):de&65535,
                       ('R',2523):pe&65535,('R',2524):old_status,('T',96):timer&65535})
        m.bits.update({('M',1753):dry,('M',1754):power,('M',1757):pending,
                       ('M',1760):valid_dry,('M',1761):valid_power,
                       ('M',1764):dry_enabled,('M',1765):power_enabled,('M',1766):count_context,
                       ('M',1773):pending and auto and not emergency and water and mains and pressure and hp,
                       ('M',1774):leader,('M',1775):stopped and context,('M',1776):both_done,
                       ('M',1924):boot,('X',6):water,('X',7):mains})
        original_regs=dict(m.regs);original_bits=dict(m.bits)
        for code in codes:m.execute(code)
        # The extension may only add/overwrite its reserved display words.
        assert all(m.regs[key]==value for key,value in original_regs.items())
        assert m.bits==original_bits
        assert all(key[0]=='R' and key[1] in DISPLAY_REGISTERS for key in m.regs.keys()-original_regs.keys())
        assert m.regs[('R',2537)]==27115
        result={n:m.regs[('R',n)] for n in DISPLAY_REGISTERS}
        cases.append(name)
        return result

    def equals(state,expected):
        assert all(state[key]==value for key,value in expected.items()),(state,expected)

    equals(observe('idle does not promise restart'),{2528:0,2533:0,2532:0,2538:15,2539:15})
    for elapsed in range(16):
        s=observe('dry elapsed '+str(elapsed),dry=True,de=elapsed)
        equals(s,{2525:max(0,15-elapsed),2528:17-elapsed,2533:1,2532:3,2538:17-elapsed,2539:15})
    for elapsed in (0,1,30,59,60):
        equals(observe('power elapsed '+str(elapsed),power=True,ps=60,pe=elapsed),
               {2526:max(0,60-elapsed),2528:62-elapsed,2533:1,2532:4,2539:62-elapsed})
    for de,pe,total in [(0,0,62),(20,55,12),(30,59,3),(30,60,2)]:
        equals(observe('both delays '+str((de,pe)),dry=True,power=True,ds=30,ps=60,de=de,pe=pe),
               {2528:total,2538:total,2539:total,2533:1,2532:4})
    for timer,seconds in [(0,2),(1,2),(9,2),(10,1),(11,1),(19,1)]:
        equals(observe('final stability tenths '+str(timer),dry=True,de=15,timer=timer),
               {2528:seconds,2533:1,2538:seconds,2532:3})
    equals(observe('completed timer never displays start in0',dry=True,de=15,timer=20),{2528:0,2533:0,2532:5})
    equals(observe('pending consumed after rearm',timer=20),{2528:0,2533:0,2532:0})
    equals(observe('dry fault remains active',dry=True,water=False,de=10),{2528:0,2533:0,2532:1})
    equals(observe('power fault remains active',power=True,mains=False,pe=10),{2528:0,2533:0,2532:2})
    equals(observe('water returns timer restarts from actual zero',dry=True,de=0),{2528:17,2533:1})
    equals(observe('power returns timer restarts from actual zero',power=True,pe=0),{2528:17,2533:1})
    for blocked in ('pressure','hp','leader','stopped','context'):
        equals(observe('other blocker '+blocked,dry=True,de=5,**{blocked:False}),{2528:0,2533:0,2532:5,2538:10})
    equals(observe('selector STOP cancels pending',dry=True,power=True,auto=False),{2528:0,2533:0,2532:0})
    equals(observe('emergency lock requires manual rearm',dry=True,emergency=True),{2528:0,2533:0,2532:6})
    equals(observe('boot has no countdown promise',power=True,boot=True),{2528:0,2533:0})
    for delay in (0,14,3601,65535):
        equals(observe('invalid dry setting '+str(delay),dry=True,ds=delay),{2528:0,2533:0,2532:7})
    for elapsed in (16,65535):
        equals(observe('invalid dry elapsed '+str(elapsed),dry=True,de=elapsed),{2528:0,2533:0})
    for timer in (21,65535):
        equals(observe('invalid stable timer '+str(timer),dry=True,de=15,timer=timer),{2528:0,2533:0})
    equals(observe('maximum delay fits unsigned display',power=True,ps=3600),{2528:3602,2533:1,2539:3602})
    equals(observe('nonactive timer snapshot cannot shorten future stability',dry=True,timer=19),{2528:17,2536:2})

    hmi,hmi_report=hmi_prepare(hmi_source,recipe_path)
    assert Path(hmi_candidate).read_bytes()==hmi
    raw=Path(hmi_source).read_bytes();recipe=json.loads(Path(recipe_path).read_text())
    if len(raw)==recipe['sourceBytes'] and hashlib.sha256(raw).hexdigest()==recipe['sourceSHA256']:raw,_=layout_r1(raw,recipe)
    assert hashlib.sha256(raw).hexdigest()==SOURCE_R1 and len(hmi)==len(raw)==1321783
    restored=bytearray(hmi)
    for edit in hmi_report['typedEdits']:
        start,length=edit['offset'],edit['bytes'];restored[start:start+length]=raw[start:start+length]
    assert bytes(restored)==raw
    assert hmi[46697:46703]==qstring('5') and hmi[46703:46709]==qstring('0')
    assert qstring('R2528') in hmi[45500:47628] and qstring('R2533#1#6#1#2533#R#1#') in hmi[45500:47628]
    assert qstring('R2538') in hmi[353301:355000] and qstring('R2539') in hmi[345455:347100]
    assert qstring('R2532') in hmi[334800:336000]
    assert qstring('R2540') in hmi[349000:350500] and qstring('R2541') in hmi[341000:342500]
    assert hmi[48311:48415]==raw[41046:41150]
    assert qstring('C:/Users/user/Documents/HMI/Samkoon/Насоска HMI/pumps-3.png') in hmi
    graphs=[]
    if vendor:
        from check_fatek_network_graph import GraphChecker
        from render_fatek_network_01 import render
        g=GraphChecker(vendor)
        for row,code in zip(report['networks'],codes):
            graphs.append({'label':row['label'],**g.require(code)})
            if row['label'].endswith('T96_VALUE_SNAPSHOT'):assert 'S :  T96' in render(code,Path(vendor))
    assert Path(plc_source).read_bytes()==before['bytes']
    return {'passed':len(cases),'cases':cases,'newGraphChecks':len(graphs),'graphEvidence':graphs,
            'PLCOriginalProgramPreserved':True,'PLCDataAndTablesPreserved':True,'controlWritesAdded':False,
            'HMITypedEdits':len(hmi_report['typedEdits']),'HMIOnlyDeclaredBytesChanged':True,
            'nativeF8':False,'nativeHMICompile':False,'offlineSimulator':False,'equipmentActions':0}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('plc-source','plc-candidate','hmi-source','hmi-candidate','recipe','out'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--vendor-dll',type=Path);a=p.parse_args()
    inputs=(a.plc_source,a.plc_candidate,a.hmi_source,a.hmi_candidate,a.recipe)
    if a.out.exists() or a.out.is_symlink() or a.out.resolve() in [x.resolve() for x in inputs]:raise ValueError('New report path required')
    result=validate(a.plc_source,a.plc_candidate,a.hmi_source,a.hmi_candidate,a.recipe,a.vendor_dll)
    with a.out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS:',result['passed'],'countdown snapshots;',result['newGraphChecks'],'graph conversions;',result['HMITypedEdits'],'typed HMI edits.')
    print('Native F8 / SKTool / Simulator / equipment checks remain separate.')


if __name__=='__main__':main()
