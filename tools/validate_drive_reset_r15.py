#!/usr/bin/env python3
"""Execute reset bytecode with a bounded asynchronous FUN150 test double.

Checks the actual added bytecode, ownership gates and immutable source bytes.
The serial double is not a real Port3, native F8 or drive acceptance test.
"""
import argparse
import json
from pathlib import Path
import struct
from build_drive_reset_r15 import prepare, inventory, make_plan
from build_vfd_fault_export_r14 import networks as fault_networks

class Machine:
    def __init__(self):
        self.regs={}; self.bits={}; self.timers={}; self.jobs={}; self.edges={}
        self.transmissions=[]; self.code_after=0; self.failure=None; self.latency=2
    def reg(self,v):
        if 0xa00<=v<0x2800 and v%2==0:return ('R',(v-0xa00)//2)
        if 0x4000<=v<0x6000 and v%2==0:return ('D',(v-0x4000)//2)
        if 0x390<=v<0x590 and v%2==0:return ('T',(v-0x390)//2)
        raise ValueError('Register '+hex(v))
    def get(self,v):return self.regs.get(self.reg(v),0)
    def put(self,v,n):self.regs[self.reg(v)]=n&65535
    def contact(self,v):
        if v>=0x810:return ('M',v-0x810)
        if v>=0x200:return ('T',v-0x200)
        if v>=0x100:return ('Y',v-0x100)
        return ('X',v)
    def mbus(self,sr,wr,en,abort):
        state=self.jobs.setdefault(sr,dict(active=False,error=False,done=False,remaining=0))
        if abort and state['active']:state.update(active=False,error=True,done=True)
        if en and not self.edges.get(sr,False):
            assert not state['active'], 'Retrigger of an active transaction'
            assert not any(s['active'] for k,s in self.jobs.items() if k!=sr),'Shared Port3 collision'
            assert self.bits.get(('M',1936),False)
            table=[self.get(sr+2*i) for i in range(10)]
            assert table[:2]==[0xa550,0x0701] and table[5]==12 and table[7]==4 and table[-1]==0
            slave,command,quantity,local,remote=table[2],table[3],table[4],table[6],table[8]
            assert slave in (1,2,3)
            if command==3:
                assert quantity==1 and remote==8193 and self.regs[('R',local)]==7
                assert not any(self.bits.get(('Y',i),False) for i in range(1,5))
            else:assert command==1 and quantity==7 and remote==4097 and local==2800+8*(slave-1)
            self.transmissions.append((slave,command,remote,quantity))
            state.update(active=True,error=False,done=False,remaining=self.latency,
                         wr=wr,slave=slave,command=command,local=local)
        self.edges[sr]=en
        return state
    def advance(self):
        for state in self.jobs.values():
            if not state['active'] or self.failure=='timeout':continue
            state['remaining']-=1
            if state['remaining']>0:continue
            command=state['command'];bad=self.failure==('write' if command==3 else 'read')
            state.update(active=False,error=bad,done=True)
            self.put(state['wr'],0x100 if bad else 0)
            self.put(state['wr']+2,(state['slave']<<8)|(6 if command==3 else 3))
            if self.failure==('write_tag' if command==3 else 'read_tag'):self.put(state['wr']+2,0)
            if command==1 and not bad:
                for i in range(7):self.regs[('R',state['local']+i)]=0
                self.regs[('R',state['local']+1)]=self.code_after
    def execute(self,code):
        words=list(struct.unpack('>'+'H'*(len(code)//2),code));i=0;s=[];tr={};outputs={}
        signed=lambda v:v-65536 if v&32768 else v
        while i<len(words):
            op=words[i]
            if op in (0xf47f,0xf67f):
                desc,a,b=words[i+1:i+4];a=signed(self.get(a));b=signed(b if op==0xf67f else self.get(b))
                choices=[(mode,desc-base) for mode,base in [('ORG',0x15),('LD',0x1b),('AND',0x21),('OR',0x27)] if base<=desc<=base+3]
                assert len(choices)==1
                mode,rel=choices[0];value=(a==b,a>b,a<b,a!=b)[rel]
                if mode=='ORG':s=[value]
                elif mode=='LD':s.append(value)
                elif mode=='AND':s[-1]=s[-1] and value
                else:s[-1]=s[-1] or value
                i+=4
            elif op in (0xf4ac,0xf5ac):
                a,b=words[i+1:i+3]
                if s[-1]:self.put(b,a if op==0xf5ac else self.get(a))
                i+=3
            elif op in (0xf462,0xf464):
                a,b,dst=words[i+1:i+4];carry=s.pop();assert not carry
                if s[-1]:self.put(dst,self.get(a)+self.get(b)*(1 if op==0xf462 else -1))
                i+=4
            elif op==0xf6c6:
                a,b,dst=words[i+1:i+4]
                if s[-1]:self.put(dst,self.get(a)&b)
                i+=4
            elif op==0xf4ce:
                a,b,n=words[i+1:i+4]
                if s[-1]:
                    values=[self.get(a+2*j) for j in range(n+1)]
                    for j,value in enumerate(values):self.put(b+2*j,value)
                i+=4
            elif op==0xfd81:
                limit,dst=words[i+1:i+3];key=self.reg(dst);assert key[0]=='T'
                self.timers[key]=min(limit,self.timers.get(key,0)+1) if s[-1] else 0
                self.regs[key]=self.timers[key];self.bits[key]=self.timers[key]>=limit;i+=3
            elif op==0xf31b:
                sr,wr=words[i+1:i+3];abort,ascii_mode,en=s[-1],s[-2],s[-3]
                assert not ascii_mode
                state=self.mbus(sr,wr,en,abort)
                outputs={0x6ffc:state['active'],0x6ffd:state['error'],0x6ffe:state['done']};i+=3
            elif op in (0x6ffc,0x6ffd,0x6ffe):s=[outputs[op]];i+=1
            elif op in (0x4fe8,0x5feb):s=[op==0x4fe8];i+=1
            elif op==0xc400:tr[0]=s[-1];i+=1
            elif op==0x6400:s.append(tr[0]);i+=1
            elif op==0x7fe8:s.append(False);i+=1
            elif op==0x9fe7:s[-1]=False;i+=1
            elif op in (0x8fe2,0x8fe4,0x8fe6,0x8fe7,0x8fe8,0x8fe9,0x8fea,0x8feb,0x8fec):i+=1
            elif op>>12 in (0,1,4,5,6,7,8,9,10,11,12):
                kind=op>>12;key=self.contact(op&4095);value=self.bits.get(key,False)
                if kind in (5,7,9,11):value=not value
                if kind in (4,5):s=[value]
                elif kind in (6,7):s.append(value)
                elif kind in (8,9):s[-1]=s[-1] and value
                elif kind in (10,11):s[-1]=s[-1] or value
                elif kind==12:self.bits[key]=bool(s[-1])
                elif s[-1]:self.bits[key]=kind==1
                i+=1
            else:raise ValueError('Unmodelled '+hex(op))


def component_checks():
    pre,calls=make_plan();pre=[bytes.fromhex(v['codeHex']) for v in pre];calls=[bytes.fromhex(v['codeHex']) for v in calls]
    published=[bytes.fromhex(v['codeHex']) for v in fault_networks()]
    cases=[]
    def scan(m,boot=False):
        m.advance();m.bits[('M',1924)]=boot
        for code in pre:m.execute(code)
        for code in calls:m.execute(code)
        for i in range(3):m.bits[('M',1744+i)]=m.bits.get(('M',1830+i),False)
        # Existing fault publisher consumes only the qualified reset-read pulse.
        for code in published:m.execute(code)
        assert m.regs[('R',2363)]==2 and m.regs[('R',2840)]==777
    def fresh():
        m=Machine();m.regs.update({('R',2363):2,('R',2840):777,('D',4044):0})
        for relay in (305,827,947,1033,1936):m.bits[('M',relay)]=True
        m.bits[('T',51)]=True
        scan(m,True)
        for i in range(3):
            m.bits[('M',1748+i)]=True
            m.regs[('R',2832+i)]=52;m.regs[('R',2835+i)]=1;m.regs[('R',2844+i)]=52
            m.regs[('R',3040+i)]=52;m.regs[('R',3043+i)]=1;m.regs[('R',3050+i)]=2
        scan(m);return m
    def request(m,drive=1,**overrides):
        session=m.regs[('R',3215)];window=m.regs[('R',3225)]
        fields=dict(mask=1<<(drive-1),seq=(m.regs.get(('R',3222),0)+1)&65535 or 1,
                    session=session,inverse=session^65535,window=window,winverse=window^65535)
        fields.update(overrides)
        for i,key in enumerate(('mask','seq','session','inverse','window','winverse')):m.regs[('R',3216+i)]=fields[key]
        return fields
    def finish(m):
        for _ in range(70):scan(m)
    # Exercise the mode predicate over the entire 16-bit system register domain.
    mode=[v for v in make_plan()[0] if v['label'].split(' | ')[1] in ('COPY_SYSTEM_EXECUTION_MODE','READ_SYSTEM_EXECUTION_MODE','SINGLE_TRANSACTION_MODE')]
    m=Machine()
    for value in range(65536):
        m.regs[('D',4044)]=value
        for row in mode:m.execute(bytes.fromhex(row['codeHex']))
        assert m.bits[('M',1835)]==not_continuous(value)
        assert m.regs[('D',4044)]==value
    cases.append('all65536 Port3 execution modes, D4044 read-only')
    for drive in (1,2,3):
        m=fresh();request(m,drive);finish(m)
        assert m.transmissions==[(drive,3,8193,1),(drive,1,4097,7)],m.transmissions
        assert m.regs[('R',3205)]==1 and m.regs[('R',3205+drive)]==2
        assert m.regs[('R',3040+drive-1)]==0 and m.regs[('R',3050+drive-1)]==1
        assert m.regs[('R',3201)]==0 and not m.bits[('M',1820)]
        cases.append('drive%d single reset+fresh zero, READY off'%drive)
        request(m,drive,seq=1);finish(m);assert len(m.transmissions)==2
        cases.append('drive%d duplicate seq never retransmits'%drive)
    for failure in ('write','read','write_tag','read_tag','timeout'):
        m=fresh();m.failure=failure;request(m);finish(m)
        assert m.regs[('R',3206)]==4 and m.regs[('R',3201)]==0,(failure,m.regs[('R',3201)])
        assert sum(command==3 for _,command,_,_ in m.transmissions)==1
        assert m.regs[('R',3040)]==52
        cases.append(failure+' does not claim recovery or retry')
    for remaining in (1,52,65535):
        m=fresh();m.code_after=remaining;request(m);finish(m)
        assert m.regs[('R',3206)]==4 and m.regs[('R',3214)]==remaining
        assert m.regs[('R',3040)]==remaining
        cases.append('fault remains '+str(remaining))
    for key,value,detail in (('mask',3,15),('window',999,14),('winverse',0,14)):
        m=fresh();request(m,**{key:value});finish(m)
        assert not m.transmissions and m.regs[('R',3224)]==detail
        cases.append('invalid '+key+' consumed without TX')
    for fields in ({'session':0},{'inverse':0},{'seq':0}):
        m=fresh();request(m,**fields);finish(m)
        assert not m.transmissions and m.regs.get(('R',3222),0)==0
        cases.append('invalid header '+str(fields))
    for reason in ('mode','run','output','selector','cache','freq','quality','clear','noport'):
        m=fresh()
        if reason=='mode':m.regs[('D',4044)]=0x5608
        if reason=='run':m.bits[('M',305)]=False
        if reason=='output':m.bits[('Y',2)]=True
        if reason=='selector':m.bits[('M',306)]=True
        if reason=='cache':m.bits[('M',1748)]=False
        if reason=='freq':m.regs[('R',2500)]=1
        if reason=='quality':m.bits[('M',1748)]=False;m.regs[('R',3043)]=0
        if reason=='clear':m.regs[('R',2832)]=0;m.regs[('R',3040)]=0
        if reason=='noport':m.bits[('M',1936)]=False
        request(m);finish(m);assert not m.transmissions,reason
        cases.append('blocked '+reason)
    for before in (1,4,8):
        m=fresh();m.latency=5;request(m)
        for _ in range(before):scan(m)
        m.bits[('M',305)]=False;finish(m)
        assert m.regs[('R',3206)]==3 and m.regs[('R',3201)]==0
        assert sum(v[1]==3 for v in m.transmissions)<=1
        cases.append('STOP loss at scan'+str(before)+' cancels')
    for relay in (600,665,664,669,694,670,680,690):
        m=fresh();m.bits[('M',relay)]=True;request(m)
        for _ in range(6):scan(m)
        assert not m.transmissions
        m.bits[('M',relay)]=False;finish(m)
        assert len(m.transmissions)==2
        cases.append('Port3 waits for worker M'+str(relay))
    m=fresh();old=request(m);scan(m,True);finish(m)
    assert not m.transmissions and m.regs[('R',3215)]!=old['session']
    cases.append('PLC restart invalidates queued session and clears frame')
    m=fresh();m.regs[('R',2857)]=65535;scan(m,True)
    assert m.regs[('R',3215)]==1
    cases.append('retained session wrap skips zero')
    return cases


def not_continuous(value):return not ((value>>8)==0x56 and (value&8))

def validate(source,candidate,vendor=None):
    raw=Path(source).read_bytes();expected,report=prepare(source);target=Path(candidate).read_bytes()
    assert target==expected
    a,old=inventory(raw);b,new=inventory(target)
    def spans(f,rows):return {label:f['image'][pc:rows[i+1][0] if i+1<len(rows) else int.from_bytes(f['image'][270:272],'little')-2] for i,(pc,label) in enumerate(rows)}
    before,after=spans(a,old),spans(b,new);patches={v['label']:v for v in report['modifiedNetworks']}
    additions={v['label'] for v in report['newNetworks']}
    assert [label for _,label in old]==[label for _,label in new if label not in additions]
    for label,body in before.items():
        assert after[label]==(bytes.fromhex(patches[label]['newHex']) if label in patches else body),label
    assert a['payload']==b['payload'] and a['key']==b['key']
    assert [v[2] for v in a['records'] if v[0] not in (0x1001,0x1002)]==[v[2] for v in b['records'] if v[0] not in (0x1001,0x1002)]
    structural=[]
    if vendor:
        from check_fatek_network_graph import GraphChecker
        g=GraphChecker(vendor)
        for item in report['newNetworks']:g.require(bytes.fromhex(item['codeHex']))
        for label,p in patches.items():
            previous=g.inspect(bytes.fromhex(p['oldHex']));current=g.inspect(bytes.fromhex(p['newHex']))
            if previous['roundTrip']:assert current['roundTrip'] and not current['nodeError'],(label,current)
            else:assert (previous['nodeError'],previous['errorFlag'])==(current['nodeError'],current['errorFlag'])
            structural.append(dict(label=label,original=previous,candidate=current))
    cases=component_checks()
    assert Path(source).read_bytes()==raw
    return dict(candidateSHA256=report['candidateSHA256'],candidateBytes=len(target),cases=cases,count=len(cases),
                newNetworks=len(additions),vendorChecked=bool(vendor),modifiedNetworkGraphs=structural,
                sourceProgramExceptListedGatesAndMetadataPreserved=True,dataAndNativeKeyPreserved=True,
                nativeF8Observed=False,hardwareResetExecuted=False,serialTestDouble=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','candidate','report'):p.add_argument('--'+name,type=Path)
    p.add_argument('--components-only',action='store_true')
    p.add_argument('--vendor',type=Path);a=p.parse_args()
    if a.components_only:
        if any((a.source,a.candidate,a.report,a.vendor)):p.error('Components-only takes no file arguments')
        print('PASS',len(component_checks()),'reset bytecode scenarios; no native F8/hardware')
        return
    if not all((a.source,a.candidate,a.report)):p.error('source/candidate/report required')
    if a.report.exists() or a.report.is_symlink() or a.report.resolve() in (a.source.resolve(),a.candidate.resolve()):raise ValueError('New report required')
    result=validate(a.source,a.candidate,a.vendor)
    with a.report.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS',result['count'],'reset scenarios; serial double only, native F8/hardware remain')
if __name__=='__main__':main()
