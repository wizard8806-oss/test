#!/usr/bin/env python3
"""Exercise actual compiled cascade networks; no serial or equipment model.

Optional private-file checks verify byte preservation and isolated vendor
node conversion. Host checks do not replace native F8/Compile or the bench.
"""
import argparse
import json
from pathlib import Path
import struct
from build_cascade_r10 import changes,w,r,d,MARKER,prepare,sha
from validate_three_pump_pdw_candidate import Machine
from build_manual_no_sensor_pdw import frame,u16


class CascadeMachine(Machine):
    """The source's four TU clock contacts have independent edge memory."""
    def __init__(self):super().__init__();self.edges={}
    def execute(self,code):
        if code[:2]==w(0xe000):
            op=struct.unpack_from('>H',code,2)[0]
            if op!=0x4f04:raise ValueError('Only original M1780 timer edge is modelled')
            value=bool(self.bits.get(('M',1780),False));old=self.edges.get(code,False);self.edges[code]=value
            code=w(0x4fe8 if value and not old else 0x5feb)+code[4:]
        return super().execute(code)


def code_inventory(raw):
    f=frame(raw);rows=[]
    for kind,body,_ in f['records']:
        if kind==0x1002 and body[4:6].isdigit():rows.append((u16(body,0),body[4:].decode('cp1251').strip()))
    codes={}
    for i,(pc,label) in enumerate(rows):
        stop=rows[i+1][0] if i+1<len(rows) else u16(f['image'],270)-2
        codes[label.split(' | ')[0]]=f['image'][pc:stop]
    return f,rows,codes


def validate(source,candidate,vendor=None):
    raw=Path(source).read_bytes();target=Path(candidate).read_bytes();expected,report=prepare(source)
    assert target==expected
    a,old_rows,old=code_inventory(raw);b,new_rows,new=code_inventory(target)
    edited,before=changes(old);added={row['label'] for row in report['newNetworks']}
    for prefix,body in old.items():assert new[prefix]==edited.get(prefix,body),prefix
    assert [label for _,label in new_rows if label not in added]==[label for _,label in old_rows]
    inverse=[(row['pc'],len(bytes.fromhex(row['codeHex'])),b'') for row in report['newNetworks']]
    for row in report['changedNetworks']:
        pc=next(pc for pc,label in new_rows if label.split(' | ')[0]==row['anchor'])
        inverse.append((pc,len(bytes.fromhex(row['afterHex'])),bytes.fromhex(row['beforeHex'])))
    restored,cursor=bytearray(),0
    for at,length,body in sorted(inverse):
        assert at>=cursor
        restored.extend(b['image'][cursor:at]);restored.extend(body);cursor=at+length
    restored.extend(b['image'][cursor:]);restored.extend(b'\xff'*report['addedProgramBytes'])
    assert bytes(restored)[512:]==a['image'][512:],'Unlisted code changed'
    assert a['payload']==b['payload']
    for (kind,body,record),(kind2,body2,record2) in zip(
            [x for x in a['records'] if x[0] not in (0x1001,0x1002)],
            [x for x in b['records'] if x[0] not in (0x1001,0x1002)]):assert record==record2
    for row in report['newNetworks']:assert b['image'][row['pc']:row['pc']+len(bytes.fromhex(row['codeHex']))]==bytes.fromhex(row['codeHex'])
    if vendor:
        from check_fatek_network_graph import GraphChecker
        graph=GraphChecker(vendor)
        for row in report['newNetworks']:graph.require(bytes.fromhex(row['codeHex']))
        for row in report['changedNetworks']:graph.require(bytes.fromhex(row['afterHex']))
    cases=[]
    def group(machine,anchor):
        for _,_,body in before.get(anchor,[]):machine.execute(body)
    def run(machine,anchor):group(machine,anchor);machine.execute(edited.get(anchor,old[anchor]))
    def fresh(leader=1):
        m=CascadeMachine();m.regs.update({('R',2884):200,('R',2885):30,('R',2886):MARKER,
            ('R',2120):30,('R',2121):480,('R',2122):220,('R',2123):10,('R',2124):30,('R',2125):10,
            ('D',270):leader,('D',870):1,('D',871):490,('R',111):50,('D',904):2 if leader==1 else 1})
        for i in range(3):m.bits.update({('Y',i+1):True,('X',i+1):True,('M',610+i):True,('M',750+i):True})
        m.bits.update({('M',470+leader-1):True,('M',740):True,('M',1140):True,('M',969):True,('M',854):True})
        return m
    for leader in (1,2,3):
        for fault in ('none','zero Hz','below limit','at limit','stopped status','stale','command','relay','ready','link','wrong leader'):
            m=fresh(leader)
            m.regs.update({('D',900):1,('D',901):2,('D',902):3,('D',903):2})
            for i in range(4):m.bits[('M',1210+i)]=True
            if fault=='zero Hz':m.regs[('D',871)]=0
            if fault=='below limit':m.regs[('D',871)]=199
            if fault=='at limit':m.regs[('D',871)]=200
            if fault=='stopped status':m.regs[('D',870)]=3
            if fault=='stale':m.bits[('M',1140)]=False
            if fault=='command':m.bits[('M',470+leader-1)]=False
            if fault=='relay':m.bits[('Y',leader)]=False
            if fault=='ready':m.bits[('X',leader)]=False
            if fault=='link':m.bits[('M',610+leader-1)]=False
            if fault=='wrong leader':m.regs[('D',270)]=4
            group(m,'65.C025');stopped=fault not in ('none','at limit')
            assert m.regs[('R',2890)]==int(stopped)
            assert [m.regs[('D',n)] for n in range(900,904)]==([0]*4 if stopped else [1,2,3,2])
            assert [m.bits[('M',1210+i)] for i in range(4)]==[not stopped]*4
            for i in range(3):m.execute(old['65.C%d'%(118+i)])
            expected_leader=(m.bits[('X',leader)] and m.bits[('M',610+leader-1)]
                             and m.bits[('M',470+leader-1)])
            assert m.bits[('M',1200+leader-1)]==expected_leader and all(
                not m.bits[('M',1200+i)] for i in range(3) if stopped and i!=leader-1)
            cases.append('leader%d %s immediate membership/output'%(leader,fault))
    m=fresh();m.regs[('D',871)]=0;group(m,'65.C025')
    m.execute(old['65.C118']);assert m.bits[('M',1200)],'Fast follower stop prevented leader startup'
    cases.append('leader can start from zero frequency')
    # Execute the original second-edge/reset/arm networks, plus the new
    # separate counters. Demand loss, stage change and reload reset both.
    def timer_scan(m,demand=True,clock=False):
        m.bits[('M',1780)]=clock;m.bits[('M',1241)]=demand;m.bits[('M',1242)]=True
        for n in (73,75,76,79,80,81,82):run(m,'65.C%03d'%n)
        group(m,'65.C083');run(m,'65.C087')
    m=fresh();group(m,'65.C001');m.regs[('D',906)]=0
    timer_scan(m,clock=False)
    for seconds in range(1,12):
        timer_scan(m,clock=True);timer_scan(m,clock=False)
        assert m.bits[('M',1260)]==(seconds>=11),(seconds,m.regs)
    assert m.regs[('D',910)]==10 and m.regs[('R',2896)]==0
    m.regs[('D',906)]=1;m.bits[('M',1265)]=True;timer_scan(m,clock=False);m.bits[('M',1265)]=False
    for seconds in range(1,32):
        timer_scan(m,clock=True);timer_scan(m,clock=False)
        assert m.bits[('M',1260)]==(seconds>=31),(seconds,m.regs)
    assert m.regs[('R',2896)]==30 and m.regs[('D',910)]==0
    timer_scan(m,demand=False);assert m.regs[('R',2896)]==0
    timer_scan(m,demand=True);assert not m.bits[('M',1260)]
    m.regs[('D',906)]=0;timer_scan(m);assert m.regs[('R',2896)]==0
    cases.extend(['first10s delay after clock synchronization','separate second30s counter starts at zero',
                  'second timer demand-loss reset','stage regression resets second counter'])
    # Apply is atomic with the old settings acceptance bit. Bad relations
    # reject the complete edit; Cancel never copies into active words.
    for first,second,stop,high,valid in ((10,30,200,480,True),(30,30,200,480,True),
            (30,29,200,480,True),(600,1,200,480,True),(10,0,200,480,False),(10,3601,200,480,False),(10,30,480,480,False),
            (10,30,99,480,False),(600,601,100,201,True)):
        m=fresh();m.regs.update({('R',2163):first,('R',2888):second,('R',2887):stop,('R',2161):high})
        group(m,'95.S034');assert m.regs[('R',2892)]==int(valid)
        cases.append('edit validation '+str((first,second,stop,high)))
    for edit in (True,False):
        m=fresh();m.regs[('R',2887)]=180;m.regs[('R',2888)]=50;m.bits[('M',1469)]=edit
        group(m,'95.S050');assert [m.regs[('R',n)] for n in (2884,2885)]==([180,50] if edit else [200,30])
    cases.append('apply gate/cancel preserve active settings')
    for first in (10,30,600):
        m=fresh();m.bits[('M',1924)]=True;m.regs[('R',2886)]=0;m.regs[('R',2123)]=first
        group(m,'65.C001');assert m.regs[('R',2885)]==30
        m.regs[('R',2885)]=2000;group(m,'65.C001');assert m.regs[('R',2885)]==2000
    cases.append('independent30s first-use default; retained edits preserved')
    # Exercise the complete old STOP/edit/apply acceptance chain with the
    # extension validators, rather than calling the new copy alone.
    for good in (True,False):
        m=fresh();m.bits.update({('M',1468):True,('M',1463):True,('M',1465):True})
        m.regs.update({('R',2160):30,('R',2161):480,('R',2162):220,
                      ('R',2163):10,('R',2164):30,('R',2165):10,
                      ('R',2887):180,('R',2888):40 if good else 0})
        for i in range(4):m.regs[('R',2170+i)]=1 if i<3 else 0
        m.regs[('R',2174)]=1440
        m.regs.update({('R',2540):60,('R',2541):60,('R',2542):27112})
        for n in (8,9,10):m.execute(old['95.R%03d'%n])
        for anchor in old:
            if '95.S028'<=anchor<'95.S039':run(m,anchor)
        assert m.bits[('M',1469)]==good
        for n in range(44,55):run(m,'95.S%03d'%n)
        assert [m.regs[('R',n)] for n in (2884,2885)]==([180,40] if good else [200,30])
    cases.append('complete STOP apply accepts/rejects all settings together')
    return {'cases':cases,'count':len(cases),'allOtherCodeNetworksAndDataPreserved':True,
            'vendorNodeConversions':len(report['newNetworks'])+len(report['changedNetworks']) if vendor else None,
            'nativeF8Observed':False,'serialOrPhysicalTimingModelled':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','candidate','vendor','report'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if not all((a.source,a.candidate)):p.error('Private source and candidate required')
    result=validate(a.source,a.candidate,a.vendor)
    if a.report:
        with a.report.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS:',result['count'],'compiled cascade component scenarios; native F8 separate.')


if __name__=='__main__':main()
