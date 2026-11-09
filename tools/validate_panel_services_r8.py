#!/usr/bin/env python3
"""Execute actual panel C and native PLC component; no field connections."""
import argparse
import ctypes as ct
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from build_panel_services_r8 import prepare,qs
from build_manual_no_sensor_pdw import NEW,OLD,frame,prepare as plc_prepare
from validate_three_pump_pdw_candidate import Machine


class Input(ct.Structure):
    _fields_=[('alarm',ct.c_ushort*5),('ack',ct.c_ushort),('telemetry',ct.c_ushort*13),
              ('roles',ct.c_ushort*7),('manual',ct.c_ushort*3),('leader',ct.c_ushort)]


def test_c(macro):
    header='''
typedef struct {unsigned short alarm[5],ack,telemetry[13],roles[7],manual[3],leader;} IN;
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
'''
    suffix='''
void reset_test(void) {
 int i;for(i=0;i<60200;i++){words[i]=0;bits[i]=0;}
 words[51000]=27128;
 alarm_previous=0;alarm_muted=0;alarm_started=0;
 cl50_previous_generation=0;cl50_pending_generation=0;
 helpers_started=0;boot_seen=0;manual_seen=0;manual_sync=0;
 for(i=0;i<3;i++){pump_anim_phase[i]=0;pump_anim_ticks[i]=0;}
 bits[60185]=99;
}
void run_tick(IN *p,int link,int mute){bits[60107]=link;if(mute)bits[800]=1;Macro_main(p);}
int get_bit(int i){return bits[i];} int get_word(int i){return words[i];}
void clear_nav(void){bits[810]=0;}
'''
    cases=[]
    with tempfile.TemporaryDirectory(prefix='panel-r8-c-') as folder:
        root=Path(folder);(root/'MacroInit.h').write_text(header)
        (root/'panel.c').write_text(Path(macro).read_text()+suffix)
        subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-fPIC','-shared',str(root/'panel.c'),'-o',str(root/'panel.so')],check=True,capture_output=True)
        lib=ct.CDLL(str(root/'panel.so'));lib.run_tick.argtypes=[ct.POINTER(Input),ct.c_int,ct.c_int]
        def fresh(version=32):
            lib.reset_test();p=Input();p.alarm[4]=version
            for i in range(3):p.telemetry[10+i]=1
            return p
        def tick(p,link=1,mute=0):
            before=bytes(p);lib.run_tick(ct.byref(p),link,mute)
            # BootAck is the sole pre-existing write variable; new inputs read-only.
            after=bytes(p);assert before[:10]==after[:10] and before[12:]==after[12:]
            assert lib.get_bit(60185)==99,'Undocumented buzzer bit written'
        for version in (0,31,27110,65535):
            p=fresh(version);p.alarm[0]=1;p.alarm[2]=1
            tick(p);tick(p);assert lib.get_bit(60117)==0 and lib.get_bit(810)==0
            cases.append('unknown map%d rejected' % version)
        p=fresh();tick(p);assert lib.get_word(820)==8 and lib.get_word(828)==32
        p.alarm[0]=1;tick(p);assert lib.get_bit(60117)==1 and lib.get_word(800)==2;cases.append('map32 alarm enables documented sound')
        tick(p,mute=1);assert lib.get_bit(60117)==0 and lib.get_word(800)==3;cases.append('mute current alarm')
        p.alarm[0]|=2;tick(p);assert lib.get_bit(60117)==1;cases.append('new different alarm sounds again')
        p.alarm[0]=0;tick(p);assert lib.get_bit(60117)==0;cases.append('all clear silences')
        p.alarm[0]=2;p.alarm[1]=1<<9;tick(p);tick(p,mute=1)
        assert p.ack==257 and lib.get_bit(60117)==0
        p.alarm[1]=2<<9;tick(p);assert lib.get_bit(60117)==1;cases.append('generation change unmutes same alarm')
        p=fresh();p.alarm[2]=1;tick(p);assert lib.get_bit(810)==0
        tick(p);assert lib.get_bit(810)==1;cases.append('startup manual zero sample then navigation edge')
        lib.clear_nav();tick(p);assert lib.get_bit(810)==0;cases.append('manual does not trap navigation')
        p.alarm[2]=0;tick(p);p.alarm[2]=1;tick(p);assert lib.get_bit(810)==1;cases.append('selector changes to manual')
        lib.clear_nav();tick(p,link=0);assert lib.get_bit(810)==0
        tick(p);assert lib.get_bit(810)==0;tick(p);assert lib.get_bit(810)==1;cases.append('reconnect resynchronizes manual edge')
        p=fresh();p.telemetry[0]=450;p.telemetry[10]=2;p.roles[4]=6;p.leader=1
        frames=[]
        for i in range(4):tick(p);frames.append(lib.get_word(900))
        assert frames==[1,2,3,4] and lib.get_word(906)==1
        tick(p,link=0);assert lib.get_word(900)==0 and lib.get_word(906)==0;cases.append('animation now accepts map32 and rejects lost link')
    return cases


def test_permit():
    cases=[]
    for x8,x9,name in ((0,0,'STOP'),(1,0,'AUTO'),(0,1,'MANUAL'),(1,1,'invalid selector')):
        for source in (0,1):
            for trip in (0,1):
                for strict in (0,1):
                    m=Machine();m.regs[('R',2878)]=strict;m.regs[('R',2871)]=trip
                    m.bits.update({('X',8):bool(x8),('X',9):bool(x9),('M',102):bool(source)})
                    m.execute(NEW)
                    assert m.bits[('M',221)]==bool(strict or (not x8 and x9 and not source and not trip))
                    cases.append('%s source%d trip%d strict%d' % (name,source,trip,strict))
    return cases


def validate_hmi(source,candidate,recipe,macro):
    raw=Path(source).read_bytes();final=Path(candidate).read_bytes();expected,report=prepare(source,recipe,macro);assert final==expected
    changes=report['edits'];restored=bytearray();cursor=0
    def shift(p):return p+sum(e['targetBytes']-e['sourceBytes'] for e in changes if e['sourceOffset']<p)
    for e in changes:
        at=shift(e['sourceOffset']);restored.extend(final[cursor:at]);restored.extend(raw[e['sourceOffset']:e['sourceOffset']+e['sourceBytes']]);cursor=at+e['targetBytes']
    restored.extend(final[cursor:]);assert bytes(restored)==raw
    spec=json.loads(Path(recipe).read_text());t=spec['table'];a=shift(t['start']);b=final[a:shift(t['stop'])]
    assert struct.unpack_from('>2d',b,28)==(768.,288.) and struct.unpack_from('>2d',b,85)==(16.,112.)
    widths=[66.,86.,86.,66.,464.];left=16.
    for i,start in enumerate((332,553,772,1007,1228)):
        assert struct.unpack_from('>2d',b,start+20)==(widths[i],24.)
        pos=b.index(qs('Text%d'%i))+len(qs('Text%d'%i))+4
        assert struct.unpack_from('>2d',b,pos)==(left,112.);left+=widths[i]
    assert left==784. and 112+288==400<404
    return {'exactSourceRestoration':True,'allUnlistedWidgetsAndBindingsPreserved':True,'alarmTableFits800x480':True,'eventColumnPixels':464,'nativeOpeningObserved':False}


def validate_plc(source,candidate):
    raw=Path(source).read_bytes();new=Path(candidate).read_bytes();expected,report=plc_prepare(source);assert new==expected
    a,b=frame(raw),frame(new);pc=report['pc'];delta=report['addedProgramBytes']
    restored=b['image'][:pc]+OLD+b['image'][pc+len(NEW):]+b'\xff'*delta
    assert restored[512:]==a['image'][512:] and a['payload']==b['payload']
    assert len(a['records'])==len(b['records'])
    for old,current in zip(a['records'],b['records']):
        assert old[0]==current[0]
        if old[0] in (0x1001,0x1002) and len(old[1])>=4:
            p=struct.unpack_from('<H',old[1])[0];q=struct.unpack_from('<H',current[1])[0]
            assert q==p+(delta if p>=pc+len(OLD) else 0) and old[1][2:]==current[1][2:]
        else:assert old==current
    rows=[(struct.unpack_from('<H',r[1])[0],r[1][4:].decode('cp1251').strip()) for r in b['records'] if r[0]==0x1002]
    code={}
    for i,(p,label) in enumerate(rows):code[label]=b['image'][p:rows[i+1][0] if i+1<len(rows) else struct.unpack_from('<H',b['image'],270)[0]-2]
    def get(prefix):
        found=[body for label,body in code.items() if label.startswith(prefix)];assert len(found)==1;return found[0]
    assert get('95.W032').startswith(bytes.fromhex('4fe8f5ac00201df4'))
    # Execute the original pressure detector and complete manual-start gate chain.
    hp=[body for label,body in code.items() if label.startswith('20.HP')]
    m=Machine();m.regs.update({('R',2868):200,('R',2874):27113,('R',101):300,('R',110):500})
    m.bits.update({('M',102):True,('M',1924):False,('X',8):False,('X',9):True})
    def pressure():
        for body in hp:m.execute(body)
        m.execute(NEW);return m.bits[('M',221)]
    assert pressure();m.regs[('R',101)]=701;assert not pressure() and m.regs[('R',2871)]==1
    m.bits[('M',102)]=False;assert not pressure(),'Disconnect cleared an HP trip'
    m.bits[('M',102)]=True;m.regs[('R',101)]=500;assert pressure() and m.regs[('R',2871)]==0
    m.bits[('M',102)]=False;assert pressure()
    m.bits.update({('M',301):True,('M',331):True,('M',610):True,('M',710):True,('M',1620):True,('X',1):True,('X',5):True,('X',6):True,('X',7):True})
    m.regs.update({('R',2329):27110,('R',2498):27110,('R',2499):27110,('D',260):8,('R',2180):250,('R',2190):250})
    gates=[get(p) for p in ('20.01','30.07','65.M046','65.M047','65.M048','65.M167','65.M168','95.M006')]
    def permitted():
        for body in gates:m.execute(body)
        return m.bits[('M',1530)]
    m.bits[('M',1572)]=True;assert permitted(),'AUTO follower-frequency warning blocked MANUAL'
    for x in (5,6,7):
        m.bits[('X',x)]=False;assert not permitted();m.bits[('X',x)]=True
    for key in (('M',331),('M',610),('M',710),('X',1)):
        m.bits[key]=False;assert not permitted();m.bits[key]=True
    for frequency in (0,99,501):m.regs[('R',2180)]=frequency;assert not permitted()
    # Exercise original start-latch and physical-output networks for all3 pumps.
    m.regs[('R',2180)]=250
    m.bits.update({('M',301):True,('M',331):True,('M',102):False})
    m.execute(NEW);m.execute(get('20.01'));m.execute(get('30.07'));m.execute(get('65.M046'))
    for i in range(3):
        m.bits.update({('X',i+1):True,('M',610+i):True,('M',710+i):True,('M',1620+i):True,('M',200+i):True,('M',380+i):True})
        m.regs.update({('D',260+i):8,('R',2180+i):250,('R',2190+i):250})
        for prefix in ('65.M%03d'%(47+7*i),'65.M%03d'%(48+7*i),'65.M%03d'%(167+5*i),'65.M%03d'%(168+5*i),'70.%02d'%(10+i),'90.%02d |'%(2+i)):
            m.execute(get(prefix))
        assert m.bits[('Y',i+1)],'Manual RUN output did not operate without a pressure source'
    m.bits[('X',6)]=False;m.execute(get('20.01'));m.execute(get('30.07'))
    for i in range(3):m.execute(get('90.%02d |'%(2+i)));assert not m.bits[('Y',i+1)]
    return {'oneNetworkChanged':True,'otherProgramBytesAndDataFramePreserved':True,'noNewBitsOrRegisters':True,
            'pressureTripSurvivesDisconnect':True,'highPressureTripAndAutoResetTested':True,'manualWithoutSensorPermitted':True,
            'all3OriginalManualStartAndRelayOutputNetworksExecuted':True,
            'dryRunPowerEstopReadyLinkArmFrequencyGuardsRetained':True,'followerFrequencyWarningDoesNotBlockManual':True,
            'nativeF8Observed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('hmi-source','hmi','recipe','macro','plc-source','plc','report'):p.add_argument('--'+name,type=Path)
    a=p.parse_args();root=Path(__file__).resolve().parents[1]
    results={'actualPanelCScenarios':test_c(a.macro or root/'assets/hmi/panel-services-r8/panel_services.c'),'compiledPLCTruthCases':test_permit()}
    if any((a.hmi_source,a.hmi,a.recipe,a.plc_source,a.plc,a.report)):
        if not all((a.hmi_source,a.hmi,a.recipe,a.macro,a.plc_source,a.plc,a.report)):p.error('Supply all candidate-validation paths')
        if a.report.exists() or a.report.resolve() in {v.resolve() for v in (a.hmi_source,a.hmi,a.recipe,a.macro,a.plc_source,a.plc)}:raise ValueError('NEW separate report required')
        results['hmi']=validate_hmi(a.hmi_source,a.hmi,a.recipe,a.macro);results['plc']=validate_plc(a.plc_source,a.plc)
        with a.report.open('x',encoding='utf8') as f:json.dump(results,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS:',len(results['actualPanelCScenarios']),'actual C scenarios;',len(results['compiledPLCTruthCases']),'compiled permit truth cases; native checks separate.')


if __name__=='__main__':main()
