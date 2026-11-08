#!/usr/bin/env python3
"""Check the fixed-three-pump candidate offline, including compiled boundaries.

This small interpreter is intentionally limited to the instructions exercised
below. It does not execute FUN150, model a serial bus, or replace native F8.
"""
import argparse
import json
from pathlib import Path
import struct

from build_three_pump_pdw_candidate import prepare,sha,SOURCE_SHA,RAM_TABLE
from check_native_drive_edit_02 import unpack
from build_setpoint_feedback_pdw_01 import layout
from validate_high_pressure_pdw_candidate import Component


class Machine:
    def __init__(self):
        self.regs={}
        self.bits={}

    def reg(self,word):
        if 0xa00<=word<0x2800 and not word%2:return ('R',(word-0xa00)//2)
        if 0x4000<=word<0x4800 and not word%2:return ('D',(word-0x4000)//2)
        raise ValueError('Unsupported register '+hex(word))

    def contact(self,address):
        if address>=0x810:return ('M',address-0x810)
        if address>=0x100:return ('Y',address-0x100)
        return ('X',address)

    def execute(self,code):
        w=list(struct.unpack('>'+'H'*(len(code)//2),code));i=0;s=[];temp={}
        def signed(value):return value-65536 if value&32768 else value
        while i<len(w):
            op=w[i]
            if op in (0xf47f,0xf67f):
                descriptor,a,b=w[i+1:i+4];a=signed(self.regs.get(self.reg(a),0))
                b=signed(b if op==0xf67f else self.regs.get(self.reg(b),0))
                choices=[(mode,descriptor-base) for mode,base in [('ORG',0x15),('LD',0x1b),('AND',0x21),('OR',0x27)] if base<=descriptor<=base+3]
                if len(choices)!=1:raise ValueError('Unsupported comparison')
                group,relation=choices[0]
                value=(a==b,a>b,a<b,a!=b)[relation]
                if group=='ORG':s=[value]
                elif group=='LD':s.append(value)
                elif group=='OR':s[-1]=s[-1] or value
                else:s[-1]=s[-1] and value
                i+=4
            elif op in (0xf4ac,0xf5ac):
                a,b=w[i+1:i+3]
                if s[-1]:self.regs[self.reg(b)]=(a if op==0xf5ac else self.regs.get(self.reg(a),0))&65535
                i+=3
            elif op in (0x4fe8,0x5feb):s=[op==0x4fe8];i+=1
            elif op==0xc400:temp[0]=s[-1];i+=1
            elif op==0x6400:s.append(temp[0]);i+=1
            elif op==0x7fe8:s.append(False);i+=1
            elif op==0x9fe7:s[-1]=False;i+=1
            elif op in (0x8fe2,0x8fe4,0x8fe6,0x8fe7,0x8fe8,0x8fe9,0x8fea,0x8feb):i+=1
            elif op==0xe200 or op&0xff00==0xe400:
                right,left=s.pop(),s.pop();s.append(left and right if op==0xe200 else left or right);i+=1
            elif op>>12 in (0,1,4,5,6,7,8,9,10,11,12):
                kind=op>>12;key=self.contact(op&0xfff);value=bool(self.bits.get(key,False))
                if kind in (5,7,9,11):value=not value
                if kind in (4,5):s=[value]
                elif kind in (6,7):s.append(value)
                elif kind in (8,9):s[-1]=s[-1] and value
                elif kind in (10,11):s[-1]=s[-1] or value
                elif kind==12:self.bits[key]=bool(s[-1])
                elif kind==0 and s[-1]:self.bits[key]=False
                elif kind==1 and s[-1]:self.bits[key]=True
                i+=1
            else:raise ValueError('Unimplemented test opcode '+hex(op))


def validate(source,candidate,vendor=None):
    old,new=unpack(source),unpack(candidate)
    expected,report=prepare(source)
    assert sha(old['bytes'])==SOURCE_SHA and new['bytes']==expected
    delta,point=report['insertedProgramBytes'],report['insertionPC']
    a,b=layout(old['bytes']),layout(new['bytes'])
    normal=bytearray(b['image'][:point]+b['image'][point+delta:]+b'\xff'*delta)
    for edit in reversed(report['edits']):
        pc=edit['pc'];after=bytes.fromhex(edit['newHex']);before=bytes.fromhex(edit['oldHex'])
        assert normal[pc:pc+len(after)]==after
        normal[pc:pc+len(before)]=before
    assert normal[512:]==a['image'][512:]
    assert old['tables']==new['tables'] and len(new['tables'])==9 and a['payload']==b['payload']
    assert new['bytes'][0x10c:0x11a]==b'PUMP_STATION_3' and new['bytes'][0xa0:0xa8]==b'FBs-24MC'
    additions={x['label'] for x in report['networks']}
    assert [(pc-(delta if pc>=point else 0),label) for pc,label in new['rungs'] if label not in additions]==old['rungs']

    def spans(obj,prefix):
        for i,(pc,label) in enumerate(obj['rungs']):
            if label.startswith(prefix):
                end=obj['rungs'][i+1][0] if i+1<len(obj['rungs']) else int.from_bytes(obj['image'][270:272],'little')-2
                yield label,obj['image'][pc:end]

    def code(prefix,contains=None):
        choices=[v for _,v in spans(new,prefix) if v and (contains is None or contains in v)]
        if len(choices)!=1:raise ValueError('Test anchor not unique: '+prefix)
        return choices[0]

    cases=[]
    def check(name,actual,expected):
        assert actual==expected,(name,actual,expected)
        cases.append(name)

    state=Machine();state.regs[('R',723)]=1;state.regs[('D',853)]=1;state.bits[('M',613)]=True
    for _,body in spans(new,'10.N3'):state.execute(body)
    check('fixed installed count/mask/picture',[state.regs[('R',x)] for x in (2860,2864,2867)],[3,7,1])
    check('fourth membership/history/link cleared',[state.regs[('R',723)],state.regs[('D',853)],state.bits[('M',613)]],[0,0,False])
    check('RAM header',[state.regs[('R',RAM_TABLE+i)] for i in range(2)],[0xa550,0x070e])
    rows=[[state.regs[('R',RAM_TABLE+2+7*j+k)] for k in range(7)] for j in range(14)]
    filtered=[row for row in old['tables']['R5000']['rows'] if row[0]<=3]
    check('complete interleaved schedule filtered',rows,filtered)
    check('normal poll has no address4',{row[0] for row in rows},{1,2,3})
    check('worker uses RAM table',bytes.fromhex('f31b20a84258') in code('65.00'),True)
    check('third frequency sample row remapped',bytes.fromhex('f67f00214258000d') in code('65.T019'),True)

    gates=[('65.P01','D',250,700),('65.36B','D',251,703),('65.F04','D',288,807),('65.K08','D',666,907)]
    for prefix,kind,address,bit in gates:
        for target in (0,1,2,3,4,5,65535):
            s=Machine();s.regs.update({('D',289):300,('D',667):400,('D',669):0,(kind,address):target})
            s.execute(code(prefix))
            check(prefix+' target '+str(target),s.bits[('M',bit)],target in (1,2,3))
    for cursor in (0,1,2,3,4,5,65535):
        s=Machine();s.regs[('R',2400)]=cursor;s.execute(code('65.M097'))
        check('manual cursor '+str(cursor),s.regs[('R',2400)],cursor if cursor in (1,2,3) else 1)

    for cursor in (3,4):
        s=Machine();s.bits.update({('M',780):True,('M',772):True,('M',745):True})
        s.regs.update({('D',278):cursor,('D',270):2})
        # Test the actual predicate/target assignment prefix only. The source
        # has an opaque control word in the unchanged phase-commit tail;
        # this limited interpreter must not silently skip/emulate that word.
        mode=code('60.140');assert mode.count(bytes.fromhex('ee82'))==1
        s.execute(mode.split(bytes.fromhex('ee82'))[0])
        check('mode queue leader assignment prefix '+str(cursor),s.regs.get(('D',280),0),2 if cursor==4 else 0)
        s=Machine();s.bits.update({('M',840):True,('M',860):True});s.regs[('D',403)]=cursor
        s.execute(code('65.G33'));check('frequency completion sentinel '+str(cursor),s.regs.get(('D',400),0),50 if cursor==4 else 0)

    for auto in (False,True):
        for permit in (False,True):
            s=Machine();s.bits.update({('M',221):permit,('M',320):auto,('M',321):not auto,('M',740):True})
            s.bits[('Y',4)]=True
            s.execute(code('10.N3',bytes.fromhex('4fe80104')))
            s.regs.update({('R',2499):27110,('R',2329):27110})
            for n in range(4):
                for group in (200,360,1630,1200,610):s.bits[('M',group+n)]=True
            for n in range(1,5):s.execute(code('90.0'+str(n+1)+' |',bytes.fromhex(('c10' if n<4 else '010')+str(n))))
            check('native RUN outputs AUTO='+str(auto)+' permit='+str(permit),[s.bits[('Y',n)] for n in range(1,5)],[permit]*3+[False])
    s=Machine();s.bits.update({('X',n):True for n in range(1,5)});s.execute(code('70.01'))
    check('physical ready slots1..3 only',[s.bits[('M',200+n)] for n in range(4)],[True,True,True,False])
    for links in range(8):
        for broken in range(8):
            s=Machine();s.bits[('M',613)]=True
            for i in range(3):s.bits[('M',610+i)]=bool(links&1<<i);s.bits[('M',640+i)]=bool(broken&1<<i)
            s.regs.update({('R',120):111,('R',122):222,('R',124):333,('R',126):444})
            for prefix in ('65.13','65.14','65.15','65.16','65.17'):s.execute(code(prefix))
            eligible=[i+1 for i in range(3) if links&1<<i and not broken&1<<i]
            check('pressure source links='+str(links)+' broken='+str(broken),s.regs[('R',130)],eligible[0] if eligible else 0)
    s=Machine();s.execute(code('95.A013'));s.execute(code('95.A017'))
    check('absent fourth drive alarms suppressed',[s.bits[('M',1558)],s.bits[('M',1562)]],[False,False])
    for prefix,flag in [('95.A010',1555),('95.A011',1556),('95.A012',1557)]:
        s=Machine();s.execute(code(prefix));check('installed drive alarm retained '+prefix,s.bits[('M',flag)],True)
    for row in (13,16):
        s=Machine();s.bits[('M',602)]=True;s.regs.update({('D',301):771,('D',300):row});s.execute(code('65.T019'))
        check('third telemetry row '+str(row),s.bits[('M',1742)],row==13)
    s=Machine();s.bits[('M',602)]=True;s.regs.update({('D',301):1027,('D',300):17});s.execute(code('65.T028'))
    check('fourth cached telemetry ignored',s.bits[('M',1743)],False)
    s=Machine();s.regs.update({('D',845):0,('D',853):1});s.execute(code('65.S17'))
    check('fourth stop probe never selected',s.regs[('D',845)],0)

    # Unchanged HP-r2 is executed against real compiled networks in the new file.
    hp=[body for _,body in spans(new,'20.HP')]+[code('20.03 |')]
    s=Component()
    for pv,expected_pair in [(500,(0,1)),(700,(0,1)),(701,(1,0)),(650,(1,0)),(501,(1,0)),(500,(0,1))]:
        check('retained HP cycle '+str(pv),s.cycle(hp,pv),expected_pair)

    graph_results=[];new_graphs=0
    if vendor:
        from check_fatek_network_graph import GraphChecker
        graph=GraphChecker(vendor)
        for _,body in spans(new,'10.N3'):graph.require(body);new_graphs+=1
        affected=set()
        for edit in report['edits']:
            pc=max(pc for pc,label in old['rungs'] if pc<=edit['pc']);affected.add(pc)
        for pc in sorted(affected):
            label=next(label for p,label in old['rungs'] if p==pc)
            stop=next((p for p,_ in old['rungs'] if p>pc),int.from_bytes(old['image'][270:272],'little')-2)
            np=pc+(delta if pc>=point else 0)
            before=graph.inspect(old['image'][pc:stop]);after=graph.inspect(new['image'][np:np+stop-pc])
            if before['roundTrip']:assert after['roundTrip'],(label,after)
            else:assert (before['nodeError'],before['errorFlag'])==(after['nodeError'],after['errorFlag']),(label,before,after)
            graph_results.append({'label':label,'original':before,'candidate':after})
    assert Path(source).read_bytes()==old['bytes']
    return dict(candidateSHA256=sha(new['bytes']),passed=len(cases),cases=cases,
                insertedNetworks=report['insertedNetworks'],newNetworkGraphPasses=new_graphs,
                editedSpanGraphEvidence=graph_results,allOtherProgramBytesPreserved=True,
                HPRevision2Preserved=True,staticTemplatesPreserved=9,normalPollRows=14,
                sourceUnchanged=True,nativeF8=False,serialExecution=False,HMIFileModified=False,equipmentActions=0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path);p.add_argument('--candidate',required=True,type=Path)
    p.add_argument('--vendor-dll',type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    if a.out.exists() or a.out.is_symlink() or a.out.resolve() in (a.source.resolve(),a.candidate.resolve()):raise ValueError('New report required')
    report=validate(a.source,a.candidate,a.vendor_dll)
    with a.out.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS:',report['passed'],'component checks;',report['newNetworkGraphPasses'],'new graph conversions; native F8/serial behavior remain.')


if __name__=='__main__':main()
