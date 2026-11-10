#!/usr/bin/env python3
"""Verify exact SKM transformation, native records and C protocol behavior.

Host structs deliberately do not claim SKTool ABI validation. No HMI/PLC or
serial hardware is accessed. Use native Compile and later bench acceptance.
"""
import argparse
import ctypes as ct
import itertools
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from build_fault_reset_hmi_r15 import prepare,source_macro,extend_macro,scene,qs,sha,properties,LOGO_TARGET
from skm_project_header import read_project_header

class Input(ct.Structure):
    _fields_=[('alarm',ct.c_ushort*5),('ack',ct.c_ushort),('telemetry',ct.c_ushort*13),
              ('roles',ct.c_ushort*7),('manual',ct.c_ushort*3),('leader',ct.c_ushort*1),
              ('fault',ct.c_ushort*40),('reset',ct.c_ushort*32),('request',ct.c_ushort*6)]
HEADER='''
typedef struct {unsigned short alarm[5],ack,telemetry[13],roles[7],manual[3],leader[1],fault[40],reset[32],request[6];} IN;
static unsigned short words[60200]; static unsigned char bits[60200];
unsigned short *LocalWord=words; unsigned char *LocalBit=bits;
#define MarcoInit LocalWord=words; LocalBit=bits;
#define AlarmWords (p->alarm)
#define MapVersion (p->alarm[4])
#define BootAck (p->ack)
#define PumpAnimTelemetry (p->telemetry)
#define PumpAnimRoles (p->roles)
#define PumpAnimManual (p->manual)
#define PumpAnimLeader (p->leader)
#define NativeFaultData (p->fault)
#define DriveResetData (p->reset)
#define DriveResetRequest (p->request)
'''
WRAPPER='''
void reset_test(void) {
 int i;
 for(i=0;i<60200;i++){words[i]=0;bits[i]=0;}
 words[51000]=27128;alarm_previous=0;alarm_muted=0;alarm_started=0;
 cl50_previous_generation=0;cl50_pending_generation=0;
 helpers_started=0;boot_seen=0;manual_seen=0;manual_sync=0;
 for(i=0;i<3;i++){pump_anim_phase[i]=0;pump_anim_ticks[i]=0;}
 EXTENSION_RESET
}
void tick_test(IN *p,int link,int mute){bits[60107]=link;bits[800]=mute;Macro_main(p);}
unsigned short *words_test(void){return words;}
unsigned char *bits_test(void){return bits;}
'''
RESET='''
 native_alarm_mask=0;native_event_seq=0;reset_session=0;reset_window=0;
 reset_window_age=65535;reset_pending_ticks=0;reset_started=0;reset_window_live=0;
 reset_pending=0;reset_target=0;
 for(i=0;i<3;i++){native_sample_seq[i]=0;native_sample_age[i]=65535;}
 for(i=0;i<6;i++){reset_frame[i]=0;}
'''

def host_checks(old):
    results=[];diff=0
    with tempfile.TemporaryDirectory(prefix='fault-reset-r15-') as temp:
        root=Path(temp);(root/'MacroInit.h').write_text(HEADER)
        libs=[]
        for n,source in enumerate((old,extend_macro(old))):
            c=root/('macro%d.c'%n);so=root/('macro%d.so'%n)
            c.write_text(source+'\n'+WRAPPER.replace('EXTENSION_RESET',RESET if n else ''))
            subprocess.run(['cc','-std=c89','-Wall','-Wextra','-Werror','-shared','-fPIC',str(c),'-o',str(so)],check=True,capture_output=True)
            lib=ct.CDLL(str(so));lib.tick_test.argtypes=[ct.POINTER(Input),ct.c_int,ct.c_int]
            lib.words_test.restype=ct.POINTER(ct.c_ushort);lib.bits_test.restype=ct.POINTER(ct.c_ubyte);libs.append(lib)
        for mask,manual,link,version in itertools.product(range(8),(0,1),(0,1),(0,32)):
            for lib in libs:lib.reset_test()
            inputs=[Input(),Input()]
            for p in inputs:
                p.alarm[4]=version;p.alarm[2]=manual;p.alarm[0]=3
                for i in range(3):p.telemetry[i]=250+50*i if mask&(1<<i) else 0;p.telemetry[10+i]=2 if mask&(1<<i) else 1
            for tick in range(9):
                for lib,p in zip(libs,inputs):lib.tick_test(ct.byref(p),link,tick==3)
                assert bytes(inputs[0])==bytes(inputs[1]),'Changed old write inputs'
                a=ct.string_at(libs[0].words_test(),60200*2);b=ct.string_at(libs[1].words_test(),60200*2)
                assert a[:940*2]==b[:940*2] and a[959*2:]==b[959*2:],'Changed old words'
                assert ct.string_at(libs[0].bits_test(),60200)==ct.string_at(libs[1].bits_test(),60200),'Changed old bits'
            diff+=1
        lib=libs[1];words=lib.words_test();bits=lib.bits_test()
        def fresh():
            lib.reset_test();p=Input();p.alarm[4]=32;p.fault[9]=27120;p.reset[0]=27131
            p.reset[15]=123;p.reset[25]=10;p.reset[27]=1;p.reset[9]=7
            for i in range(3):p.fault[3+i]=1;p.fault[6+i]=1;p.fault[10+i]=1
            lib.tick_test(ct.byref(p),1,0);p.reset[25]=11;lib.tick_test(ct.byref(p),1,0);return p
        def tick(p,link=1,mute=0):lib.tick_test(ct.byref(p),link,mute)
        for drive in (1,2,3):
            p=fresh();bits[1249+drive]=1;tick(p)
            frame=list(p.request);assert frame==[1<<(drive-1),1,123,123^65535,11,11^65535]
            for window in (12,13):p.reset[25]=window;tick(p);assert list(p.request)==frame,'Refreshed frozen nonce'
            p.reset[22]=frame[1];p.reset[23]=frame[0];p.reset[6+drive-1]=1;tick(p)
            assert p.request[0]==0 and words[950+drive-1]==1
            p.reset[6+drive-1]=2;tick(p);assert words[950+drive-1]==2
            results.append('drive%d explicit frozen frame/ack/result'%drive)
        for reason in ('link','map','session','contract','clock'):
            p=fresh();bits[1250]=1;tick(p);assert p.request[0]==1
            if reason=='link':tick(p,0)
            elif reason=='map':p.alarm[4]=0;tick(p)
            elif reason=='session':p.reset[15]+=1;tick(p)
            elif reason=='contract':p.reset[0]=0;tick(p)
            else:
                for _ in range(18):tick(p)
            assert p.request[0]==0,reason
            results.append(reason+' loss cancels without replay')
        for reason in ('stop','permit','busy','unconfirmed','two_buttons'):
            p=fresh()
            if reason=='stop':p.reset[27]=0
            if reason=='permit':p.reset[9]=0
            if reason=='busy':p.reset[1]=20
            if reason=='unconfirmed':lib.reset_test();tick(p)
            bits[1250]=1
            if reason=='two_buttons':bits[1251]=1
            tick(p);assert p.request[0]==0
            results.append('local reject '+reason)
        p=fresh();bits[1250]=1;tick(p)
        for _ in range(13):tick(p)
        assert p.request[0]==0 and words[950]==4
        for _ in range(8):p.reset[25]+=1;tick(p);assert p.request[0]==0
        results.append('local timeout never retries')
        p=fresh();p.reset[22]=65535;bits[1252]=1;tick(p);assert p.request[1]==1
        results.append('sequence wrap skips zero')
        lib.reset_test();p=Input();p.alarm[4]=32;p.fault[9]=27120;p.reset[0]=27131;p.reset[15]=123;p.reset[25]=10
        bits[1250]=1;tick(p);assert p.request[0]==0
        results.append('startup clears retained click')
        p=fresh();p.alarm[0]=64;p.fault[1]=52;p.fault[35]=2;p.fault[36]=1;p.fault[11]=2;tick(p)
        assert bits[60117]==1 and words[957]==2
        tick(p,mute=1);assert bits[60117]==0 and p.fault[1]==52
        p.fault[1]=53;p.fault[36]=2;tick(p);assert bits[60117]==1
        tick(p,mute=1);p.fault[9]=0;tick(p);assert bits[60117]==0
        p.fault[9]=27120;p.alarm[0]=0;p.fault[35]=0;p.fault[1]=0;p.fault[11]=1;tick(p)
        assert bits[801]==0 and bits[802]==0
        results.append('A52 mute, changed code unmutes, invalid profile holds, fresh recovery')
        p=fresh();p.fault[1]=65535;p.fault[35]=2;p.fault[36]=1;p.fault[11]=2;tick(p)
        assert bits[60117]==1
        for _ in range(25):tick(p)
        assert words[957]==3
        results.append('unknown65535 sounds; frozen sample gets stale label')
        # Couple the actual C request frame to the actual PLC reset networks.
        # The serial device remains an explicit test double; this is not ABI
        # or physical acceptance. HMI ticks every 300 ms in this bounded test.
        from validate_drive_reset_r15 import Machine
        from build_drive_reset_r15 import make_plan
        from build_vfd_fault_export_r14 import networks
        pre,calls=make_plan();pre=[bytes.fromhex(v['codeHex']) for v in pre]
        calls=[bytes.fromhex(v['codeHex']) for v in calls]
        fault=[bytes.fromhex(v['codeHex']) for v in networks()]
        for drive in (1,2,3):
            m=Machine();m.regs.update({('R',2363):2,('R',2840):777})
            for relay in (305,827,947,1033,1936):m.bits[('M',relay)]=True
            m.bits[('T',51)]=True;lib.reset_test();p=Input();p.alarm[4]=32
            for cycle in range(130):
                m.advance();m.bits[('M',1924)]=cycle==0
                for code in pre:m.execute(code)
                for code in calls:m.execute(code)
                for i in range(3):m.bits[('M',1744+i)]=m.bits.get(('M',1830+i),False)
                for code in fault:m.execute(code)
                if cycle==0:
                    for i in range(3):
                        m.bits[('M',1748+i)]=True
                        m.regs[('R',2832+i)]=52;m.regs[('R',2835+i)]=1
                if cycle%3==0:
                    for i in range(40):p.fault[i]=m.regs.get(('R',3040+i),0)
                    for i in range(32):p.reset[i]=m.regs.get(('R',3200+i),0)
                    if cycle==60:bits[1249+drive]=1
                    tick(p)
                    for i in range(6):m.regs[('R',3216+i)]=p.request[i]
            assert m.transmissions==[(drive,3,8193,1),(drive,1,4097,7)]
            assert words[949+drive]==2 and m.regs[('R',3201)]==0
            results.append('C+PLC integration, drive%d one reset and confirmed read'%drive)
    return dict(hostDifferentialCases=diff,macroTicksCompared=9*diff,protocolCases=results,
                c89WarningsAsErrors=True,nativeABIValidated=False)


def validate(source,candidate,logo_target=LOGO_TARGET,host=False):
    raw=Path(source).read_bytes();expected,build=prepare(source,logo_target);target=Path(candidate).read_bytes()
    assert target==expected
    header=read_project_header(target);source_header=read_project_header(raw)
    assert header['pageCount']==16 and len(header['common'])==16
    assert header['model']==source_header['model']=='SK-070HE'
    assert header['firstSceneRect']==source_header['firstSceneRect']==(0.0,0.0,800.0,480.0)
    # Original HAD is byte-identical; its large group is never reconstructed.
    import build_fault_reset_hmi_r15 as builder
    def had(b):
        start=b.index(qs('HAD1794244624'))
        group=max(m.start() for m in builder.GROUP.finditer(b,0,start))
        trailer=qs('8288')+struct.pack('>d',8288)
        # Use next top-level widget group, rather than assuming HAD's ordinal.
        end=next(m.start() for m in builder.GROUP.finditer(b,start))
        return b[group:end]
    assert had(raw)==had(target)
    # New page16 is last: append a read-only header sentinel for inventory only.
    inspect=target[:target.index(qs('Screen16'))]+target[target.index(qs('Screen16')):]
    ui_end=next(e['offset'] for e in build['edits'] if e['label']=='new pages15/16')
    shift=sum(e['newBytes']-e['oldBytes'] for e in build['edits'] if e['offset']<ui_end)
    added_size=next(e['newBytes'] for e in build['edits'] if e['label']=='new pages15/16')
    end=ui_end+shift+added_size
    inspect=target[:end]+qs('Screen17')+b'\xff'*4+target[end:]
    counts={}
    for number in (15,16):
        _,objects=scene(inspect,number);counts[number]=len(objects)
        assert len(objects)==build['newPageObjects'][str(number)]
        for obj in objects.values():
            x,y=struct.unpack_from('>2d',obj['raw'],85);w,h=struct.unpack_from('>2d',obj['raw'],28)
            assert 0<=x and 0<=y and x+w<=800 and y+h<=480
            if obj['id'].startswith('SB'):
                vals=properties(obj['raw'],obj['id'])[2]
                assert vals[48]==vals[49]==vals[57]==str(int(vals[56][6:])-1)
            if obj['id'].startswith('MD'):
                vals=properties(obj['raw'],obj['id'])[2]
                if vals[22] in ('LW956','LW957','LW958'):
                    assert vals[85]=='180+230+190' and vals[89]=='245+160+160','Healthy green / active fault red'
                elif vals[22] in ('LW950','LW951','LW952'):
                    assert vals[89]=='180+230+190','Confirmed reset green'
    for number,identity in ((1,'SB6010'),(9,'SB24002')):
        _,objects=scene(target,number,'SB');v=properties(objects[identity]['raw'],identity)[2]
        assert v[48]==v[49]==v[57]==str(int(v[56][6:])-1)
    assert len([v for v in build['readInputs']])==8 and build['writeInputs'][-1]['name']=='BootAck'
    assert build['batchPrefixBytesBeforeBootAck']%4==0
    _,old=source_macro(raw);result=dict(candidateSHA256=sha(target),candidateBytes=len(target),newPageCounts=counts,
        fullInverseAndUnlistedBytesPreserved=True,HADPreserved=True,allGeometryFits800x480=True,
        allReadInputsBatch16=True,BootAckWLastAligned=True,model=header['model'],resolution=list(header['resolution']),
        sequentialHeaderAnd16CommonPairsVerified=True,nativeCompileObserved=False,hardwareActions=0)
    if host:result.update(host_checks(old))
    assert Path(source).read_bytes()==raw
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','candidate','report'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--logo-target',default=LOGO_TARGET);p.add_argument('--host-check',action='store_true');a=p.parse_args()
    if a.report.exists() or a.report.is_symlink() or a.report.resolve() in (a.source.resolve(),a.candidate.resolve()):raise ValueError('New report required')
    result=validate(a.source,a.candidate,a.logo_target,a.host_check)
    with a.report.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS exact HMI preservation/geometry/bindings',result.get('hostDifferentialCases',0),'host cases; NOT native ABI')
if __name__=='__main__':main()
