"""Bounded tests of the saved recorder and the selected original r3 networks.

FUN150 completion/error, acknowledgement and timer expiry are injected at their
native output boundary. This does not emulate an RTU bus or a physical drive.
"""
import argparse
from pathlib import Path

from build_oshsky_stop4_capture import build, FIELDS, MAGIC, SLOTS, plan, network_inventory
from check_native_drive_edit_02 import unpack
from validate_three_pump_pdw_candidate import Machine
from validate_drive_reset_r15 import Machine as AddressDecoder


class CPU(Machine):
    reg = AddressDecoder.reg
    contact = AddressDecoder.contact

    def __init__(self):
        super().__init__()
        # The shared decoder already passes the other native wire-length words.
        # These two additional horizontal links occur in the original mode worker.
        for operand in (0xfe3,0xfe5):
            self.bits[self.contact(operand)] = True

    def set(self, **values):
        for name, value in values.items():
            bank = self.regs if name[0] in 'RD' else self.bits
            bank[(name[0],int(name[1:]))] = value

    def value(self, name):
        bank = self.regs if name[0] in 'RD' else self.bits
        return bank.get((name[0],int(name[1:])),0)

    def slot(self, kind):
        return dict(zip(FIELDS,[self.value('R'+str(SLOTS[kind]+i)) for i in range(len(FIELDS))]))


def verify(source, saved, samples=None):
    compiled, stats = build(source)
    part, rows, actual, _ = network_inventory(saved.read_bytes())
    expected, erows, nets, _ = network_inventory(compiled)
    assert part['image']==expected['image'] and rows==erows and actual==nets
    assert unpack(source)['tables']==unpack(saved)['tables']
    _, _, original, _ = network_inventory(source.read_bytes())
    before = plan(original)

    def step(m, key, native=True):
        if key not in original:
            matches=[k for k in original if k.split(' | ')[0]==key]
            assert len(matches)==1,(key,matches)
            key=matches[0]
        for label,_ in before.get(key,[]):
            m.execute(actual[label.split(' | ')[0]])
        if native:
            m.execute(actual[key])

    def outputs(m):
        for i in range(4):
            n=167+i*5
            for off in range(4):
                step(m,f'65.M{n+off:03}')
            key=next(k for k in original if k.startswith(f'90.0{i+2} | PUMP{i+1}_RUN_OUTPUT') and len(original[k])>2)
            step(m,key)
        step(m,'95.A018')
        step(m,'95.M042')
        step(m,'95.M043',False)

    def new():
        m=CPU()
        m.set(M1924=1)
        step(m,'10.01',False)
        m.set(M1924=0,M1600=1,M321=1,M221=1,R2499=27110,R2498=27110,R2329=27110,
              R2503=350,R2513=2,R2840=411,R2183=350,R2193=350)
        for i in range(4):
            for bank,n in [('X',1),('M',200),('M',610),('M',710),('M',1610),('M',1614),
                           ('M',1620),('M',360),('Y',1)]:
                m.set(**{bank+str(n+i):1})
            m.set(**{'D'+str(260+i):8,'R'+str(2180+i):350,'R'+str(2190+i):350})
        outputs(m)
        assert m.value('R3206')==1 and m.value('R3200')==MAGIC
        return m

    def select(m,t):
        m.set(R2401=t,M1604=1,M1601=0,M1602=0,M667=0,M1629=0,M1628=0,
              M694=0,M668=0,M683=0,M693=0,M671=0,M681=0,M691=0,T66=0,T90=0)
        for i in range(4):
            m.set(**{'M'+str(1640+i):int(i==t-1),'M'+str(1644+i):0})
        for i in range(76,86):step(m,f'65.M{i:03}')
        assert m.value('R2402')==t and m.value('M1601') and m.value('R2405')==10
        m.set(M694=1)
        step(m,'65.36')
        step(m,'65.36A',False)
        m.set(M694=0)
        assert m.value('D251')==t and m.value('R3208')==m.value('R3207')!=0

    def stop_ack(m,t,ok=True):
        m.set(M693=1,D360=0 if ok else 256,D361=t*256+3,D240=3,D243=0,
              M691=int(not ok),M702=0,M696=1,M703=1)
        step(m,'65.50')
        step(m,'65.51')
        m.set(M693=0)

    def write_ack(m,t,ok=True):
        m.set(M668=1,M671=int(not ok),D320=0 if ok else 256,D321=t*256+6)
        step(m,'65.40')
        step(m,'65.41')
        m.set(M668=0)

    def read_ack(m,t,value=8,ok=True):
        m.set(M683=1,M681=int(not ok),D340=0 if ok else 256,D341=t*256+3,D232=value)
        step(m,'65.44')
        step(m,'65.45')
        step(m,'65.57')
        for i in range(58,62):step(m,'65.'+str(i))

    def finish(m):
        step(m,'65.M100')
        for suffix in 'ABCD':step(m,'65.M101'+suffix)
        for i in range(101,118):step(m,f'65.M{i:03}')
        outputs(m)

    cases=[]
    m=new()
    for t in range(1,5):
        select(m,t); stop_ack(m,t); write_ack(m,t); read_ack(m,t); finish(m)
        assert m.value('M1628') and not m.value('M1629')
        assert m.value('R3207')==t
        assert all(m.value('R'+str(j))==t for j in [3208,3209,3210,3211])
        assert not m.slot('mode4')['sequence'] and not m.slot('other_mode')['sequence']
    cases.append('manual selection 1-2-3-4 and accepted stop/write/read for each')
    for t in range(1,5):
        for failure,code in [('write',10),('read',11),('mismatch',12),('timer',13),('stop',14),('deadline',15)]:
            m=new();select(m,t)
            if failure=='stop':stop_ack(m,t,False)
            elif failure=='timer':
                m.set(M665=1,T66=1);step(m,'65.47');step(m,'65.48',False)
            elif failure=='deadline':m.set(T90=1)
            else:
                stop_ack(m,t);write_ack(m,t,failure!='write')
                if failure not in ('write','stop'):
                    read_ack(m,t,6 if failure=='mismatch' else 8,failure!='read')
            finish(m)
            slot='mode4' if t==4 else 'other_mode'
            v=m.slot(slot)
            assert (v['cause'],v['target'],v['R2405'],v['M1601'])==(code,t,10,1),(failure,t,v)
            assert m.value(f'R{2389+t}')==100 and m.value('M1563')
            assert [bool(m.value('Y'+str(i))) for i in range(1,5)]==[i!=t for i in range(1,5)]
            m.set(D251=1,D231=6,D232=6,D341=0x0103,M1629=0,M667=0)
            step(m,'65.M116',False)
            assert m.slot(slot)==v
            cases.append(f'P{t} {failure} and snapshot survives later reply')
    for pollrow in (7,14,15,17):
        m=new();m.set(D300=0x0100|pollrow,D301=0x0403,M601=1,M602=1)
        step(m,'65.08 | VFD2_COMM_OK_RESET#2')
        step(m,'65.62');step(m,'65.M069');step(m,'65.M070');step(m,'65.M071',False)
        outputs(m);poll=m.slot('poll4');drop=m.slot('drop4')
        assert (poll['sequence'],drop['sequence'],poll['Y4'],drop['Y4'])==(1,2,1,0)
        assert (drop['M613'],drop['M713'],drop['M1633'],drop['M363'],drop['R2513'])==(0,0,0,0,2)
        assert (drop['M1533'],drop['M1637'],drop['R2183'],drop['R2193'])==(0,0,350,350)
        m.set(M601=0);step(m,'65.11');step(m,'65.M069');step(m,'65.M073')
        assert m.value('M1643') and not m.value('Y4')
        select(m,4);stop_ack(m,4,False);finish(m)
        assert m.slot('mode4')['sequence']==3 and m.slot('poll4')==poll and m.slot('drop4')==drop
        if samples is not None and pollrow==14:
            for kind in SLOTS:
                samples[kind]=m.slot(kind)
        cases.append(f'FC03 row {pollrow}, fresh F/Q, drop, recovery, requeue, rejected stop-check, no restart')
    for lost in ['X4','M713','M613','M707']:
        m=new();m.set(**{lost:int(lost=='M707')});step(m,'65.M069');step(m,'65.M070')
        outputs(m);assert m.slot('drop4')['sequence']==1 and not m.value('Y4')
        m.set(X4=1,M613=1,M713=1,M707=0,M1623=1);step(m,'65.M069');outputs(m)
        assert not m.value('Y4') and not m.value('M363')
        cases.append(lost+' drop and no spontaneous restart')
    m=new();select(m,4);m.set(D251=1,D231=6,D232=6,D341=0x0103,M683=1,M681=0)
    step(m,'65.44');step(m,'65.45');m.set(T90=1);finish(m)
    v=m.slot('mode4')
    assert v['target']==4 and v['D251']==1 and v['read_gen']==0 and v['cause']==15
    cases.append('stale other-target readback cannot be attributed to slot4')
    for target in range(1,5):
        m=new();select(m,target)
        m.set(M683=1,M681=0,D341=(target%4+1)*256+3,D232=8)
        step(m,'65.44',False)
        assert m.value('R3210')==0
        m.set(D341=target*256+6)
        step(m,'65.44',False)
        assert m.value('R3210')==0
        cases.append(f'P{target} completion with wrong reply slave/function gets no generation tag')
    m=new();select(m,4);write_ack(m,4,False);finish(m);v=m.slot('mode4')
    m.set(M1924=1);step(m,'10.01',False)
    assert m.slot('mode4')==v and m.value('R3206')==0
    cases.append('retained RAM / CPU first scan preserves record and invalidates previous running edge')
    return stats,cases


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('saved',type=Path)
    a=p.parse_args()
    stats,cases=verify(a.source,a.saved)
    print(stats)
    for name in cases:print('PASS',name)
