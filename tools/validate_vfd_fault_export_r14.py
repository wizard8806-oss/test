#!/usr/bin/env python3
"""Exercise actual fault-export networks and prove old PLC bytes preserved.

No FUN150 bus, power-loss hardware, retain configuration or native F8 is
modelled. A sample is supplied only through the existing qualified pulse.
"""
import argparse
import json
from pathlib import Path

from build_vfd_fault_export_r14 import prepare, inventory, networks, REGISTERS, RETAINED, MARKER
from validate_three_pump_pdw_candidate import Machine


def component_checks():
    rows = networks(); cases = []
    def scan(m, boot=False, samples=(False,)*3, caches=(False,)*3, codes=(0,)*3):
        m.bits[('M', 1924)] = boot
        for i in range(3):
            m.bits[('M', 1744+i)] = samples[i]; m.bits[('M', 1748+i)] = caches[i]
            m.bits[('X', i+1)] = False  # native fault reads must work with READY off
            m.regs[('R', 2801+8*i)] = codes[i]
        for v in rows:
            m.execute(bytes.fromhex(v['codeHex']))
            assert m.regs.get(('R', 3049), 0) in (0, MARKER), 'Contract used as scratch storage'
            assert m.regs[('R', 2363)] == 2 and m.regs[('R', 2840)] == 777, 'Old control/readout modified'
    def fresh():
        m = Machine(); m.regs[('R', 2363)] = 2; m.regs[('R', 2840)] = 777
        scan(m, boot=True)
        assert m.regs[('R', 2847)] == MARKER and m.regs[('R', 2848)] == (MARKER ^ 65535)
        return m
    def values(m, begin, count=3):
        return [m.regs.get(('R', begin+i), 0) for i in range(count)]
    for i in range(3):
        for code in range(1, 81):
            m = fresh(); pulses=[False]*3; pulses[i]=True; codes=[0]*3; codes[i]=code
            scan(m, samples=pulses, caches=pulses, codes=codes)
            assert values(m, 3040)[i] == code and values(m, 3043)[i] == 1
            assert values(m, 3050)[i] == 2 and values(m, 3053)[i] == code
            expected=[0]*15; expected[5*i+(code-1)//16]=1 << ((code-1)%16)
            assert values(m,3056,15)==expected
            assert values(m,3071)==[0]*3 and m.regs[('R',3075)]==1<<i
            assert m.regs[('R',3077)]==3
            cases.append('drive%d raw%d correct bit/identity/READY-off' % (i+1, code))
    for mask in range(8):
        m=fresh();pulses=[bool(mask & (1<<i)) for i in range(3)]
        scan(m,samples=pulses,caches=pulses,codes=(52,20,53))
        assert values(m,3040)==[c if p else 0 for c,p in zip((52,20,53),pulses)]
        assert m.regs[('R',3075)]==mask and m.regs[('R',3077)]==2+sum(pulses)
        cases.append('independent drive mask%d'%mask)
    for code in (81, 255, 32768, 65535):
        m=fresh();scan(m,samples=(True,False,False),caches=(True,False,False),codes=(code,0,0))
        assert values(m,3056,15)==[0]*15 and values(m,3071)==[1,0,0]
        assert values(m,3040)[0]==code and values(m,3053)[0]==code
        cases.append('unknown unsigned code%d retained numerically'%code)
    m=fresh();scan(m,samples=(True,False,False),caches=(True,False,False),codes=(52,0,0))
    assert m.regs[('R',3059)]==8 and m.regs[('R',3076)]==1
    for _ in range(3):scan(m,samples=(True,False,False),caches=(True,False,False),codes=(52,0,0))
    assert m.regs[('R',3076)]==1 and m.regs[('R',3046)]==4
    cases.append('repeated same reply advances sample sequence without new alarm event')
    scan(m,codes=(0,0,0))
    assert m.regs[('R',3043)]==0 and m.regs[('R',3050)]==3
    assert m.regs[('R',3040)]==52 and m.regs[('R',3059)]==8 and m.regs[('R',3075)]==1
    cases.append('timeout keeps last fault and active event; validity becomes stale')
    retained={key:value for key,value in m.regs.items() if key[0]=='R' and key[1] in RETAINED}
    restarted=Machine();restarted.regs.update(retained);restarted.regs.update({('R',2363):2,('R',2840):777})
    scan(restarted,boot=True)
    assert restarted.regs[('R',3040)]==52 and restarted.regs[('R',3043)]==0
    assert restarted.regs[('R',3059)]==8 and restarted.regs[('R',3050)]==3
    cases.append('PLC restart restores confirmed fault from retained core without false recovery')
    scan(restarted,samples=(True,False,False),caches=(True,False,False),codes=(0,0,0))
    assert restarted.regs[('R',3040)]==0 and restarted.regs[('R',3050)]==1
    assert restarted.regs[('R',3053)]==52 and restarted.regs[('R',3059)]==0
    assert restarted.regs[('R',3075)]==0
    cases.append('only a fresh zero confirms recovery; last nonzero code kept')
    scan(restarted,caches=(True,False,False),codes=(65,0,0))
    assert restarted.regs[('R',3040)]==0
    cases.append('unqualified receive buffer cannot alter published code')
    restarted.regs[('R',2835)]=65535;restarted.regs[('R',3076)]=65535
    scan(restarted,samples=(True,False,False),caches=(True,False,False),codes=(65,0,0))
    assert restarted.regs[('R',3046)]==1 and restarted.regs[('R',3076)]==0
    assert restarted.regs[('R',3060)]==1
    cases.append('sample sequence wraps to1; alarm sequence wraps modulo65536')
    return cases


def validate(source,candidate,vendor=None):
    raw=Path(source).read_bytes();target=Path(candidate).read_bytes();expected,report=prepare(source)
    assert target==expected,'Candidate not exactly reconstructed'
    a,old=inventory(raw);b,new=inventory(target);at=report['insertionPC'];delta=report['addedProgramBytes']
    assert a['image'][512:]==b['image'][512:at]+b['image'][at+delta:]+b'\xff'*delta
    assert a['payload']==b['payload'] and a['key']==b['key']
    added={v['label'] for v in report['addedNetworks']}
    assert [name for _,name in old]==[name for _,name in new if name not in added]
    assert [record for kind,_,record in a['records'] if kind not in (0x1001,0x1002)]==[
        record for kind,_,record in b['records'] if kind not in (0x1001,0x1002)]
    conversions=None
    if vendor:
        from check_fatek_network_graph import GraphChecker
        checker=GraphChecker(vendor)
        for v in report['addedNetworks']:checker.require(bytes.fromhex(v['codeHex']))
        conversions=len(report['addedNetworks'])
    cases=component_checks()
    return {'candidateSHA256':report['candidateSHA256'],'candidateBytes':len(target),
            'cases':cases,'count':len(cases),'originalProgramAndDataTablesPreserved':True,
            'sourceUnchanged':Path(source).read_bytes()==raw,
            'vendorNodeConversions':conversions,'nativeF8Observed':False,
            'serialTimingAndHardwareRetentionTested':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','candidate','report'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--vendor',type=Path);a=p.parse_args()
    if a.report.exists() or a.report.is_symlink() or a.report.resolve() in (a.source.resolve(),a.candidate.resolve()):
        raise ValueError('NEW distinct report required')
    result=validate(a.source,a.candidate,a.vendor)
    with a.report.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS',result['count'],'native-fault component scenarios; old code/tables preserved.')
    if a.vendor:print('PASS',result['vendorNodeConversions'],'isolated vendor node conversions; NOT native F8.')


if __name__=='__main__':main()
