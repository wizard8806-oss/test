#!/usr/bin/env python3
"""Check r7 byte preservation and execute the actual decoration C on a host.

Host execution checks the C state machine, not SKTool's compiler, transport,
font generation or native rendering. Those remain explicit local checks.
"""
import argparse
import ctypes as ct
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from build_pump_animation_hmi import prepare, qs, VARIABLES, FONT_SHA
from repair_skm_section_index import read_directory


class Inputs(ct.Structure):
    _fields_ = [('alarm', ct.c_ushort*5), ('telemetry', ct.c_ushort*13),
                ('roles', ct.c_ushort*7), ('manual', ct.c_ushort*3), ('leader', ct.c_ushort)]


def exercise_c(macro):
    header = '''
typedef struct { unsigned short alarm[5],telemetry[13],roles[7],manual[3],leader; } IN;
static unsigned char lb[60200];
static unsigned short lw[60200];
#define LocalBit lb
#define LocalWord lw
#define AlarmWords (p->alarm)
#define MapVersion (p->alarm[4])
#define PumpAnimTelemetry (p->telemetry)
#define PumpAnimRoles (p->roles)
#define PumpAnimManual (p->manual)
#define PumpAnimLeader (p->leader)
'''
    suffix = '''
void tick(IN *p, int connected) { lb[60107] = connected; PumpAnimation(p); }
unsigned short word(int i) { return lw[i]; }
void reset(void) {
 int i; for(i=0;i<60200;++i) lw[i]=54321;
 for(i=0;i<3;++i) {pump_anim_phase[i]=0;pump_anim_ticks[i]=0;}
}
'''
    with tempfile.TemporaryDirectory(prefix='pump-animation-host-') as name:
        root = Path(name)
        source = root/'test.c'
        source.write_text(header+Path(macro).read_text()+suffix)
        subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-fPIC', '-shared',
                        str(source), '-o', str(root/'test.so')], check=True, capture_output=True)
        lib = ct.CDLL(str(root/'test.so'))
        lib.tick.argtypes = [ct.POINTER(Inputs), ct.c_int]
        lib.word.argtypes, lib.word.restype = [ct.c_int], ct.c_ushort
        cases = []
        def baseline():
            p = Inputs()
            p.alarm[4] = 31
            for i in range(3):
                p.telemetry[10+i] = 1
                p.roles[i] = 4
            lib.reset()
            return p
        def tick(p, connected=1):
            before = bytes(p)
            lib.tick(ct.byref(p), connected)
            assert bytes(p) == before, 'Animation changed a PLC input'
            assert all(lib.word(i) == 54321 for i in range(60200) if not 900 <= i <= 908), 'Undeclared HMI write'
            return ([lib.word(900+i) for i in range(3)], [lib.word(903+i) for i in range(3)],
                    [lib.word(906+i) for i in range(3)])
        p = baseline()
        assert tick(p) == ([0,0,0],[1,1,1],[0,0,0]); cases.append('all stopped')
        for i in range(3):
            p = baseline(); p.telemetry[i] = 450; p.telemetry[10+i] = 2
            for n in range(8):
                frames, states, leaders = tick(p)
                assert frames[i] == 1+n%4 and states[i] == 2
                assert all(frames[j] == 0 and states[j] == 1 for j in range(3) if j != i)
            p.telemetry[i] = 0; p.telemetry[10+i] = 1
            assert tick(p)[0][i] == 0
            cases.append('pump%d independent run/stop' % (i+1))
        for frequency, divider in ((100,3),(199,3),(200,2),(349,2),(350,1),(500,1)):
            p = baseline(); p.telemetry[0] = frequency; p.telemetry[10] = 2
            assert [tick(p)[0][0] for _ in range(12)] == [1+(n//divider)%4 for n in range(12)]
            cases.append('frequency%d tempo' % frequency)
        for quality, frequency in ((0,0),(0,450),(1,450),(2,0),(2,5991),(3,450),(65535,450)):
            p = baseline(); p.telemetry[0] = frequency; p.telemetry[10] = quality
            assert tick(p)[0][0] == 0 and tick(p)[1][0] == 0
            cases.append('invalid quality%d/frequency%d' % (quality,frequency))
        for reason in ('panel link','map version','drive link'):
            p = baseline(); p.telemetry[0] = 450; p.telemetry[10] = 2
            p.leader=1; p.roles[4]=6
            assert tick(p)[0][0] == 1
            if reason == 'map version': p.alarm[4]=30
            if reason == 'drive link': p.alarm[0]|=1<<9
            frames,states,leaders=tick(p, reason!='panel link')
            assert frames[0]==0 and states[0]==0 and leaders[0]==0
            cases.append(reason+' while running')
        for i in range(3):
            p=baseline(); p.alarm[0]=1<<(5+i)
            assert tick(p)[1][i]==4 and tick(p)[0][i]==0
            p.telemetry[i]=450;p.telemetry[10+i]=2
            assert tick(p)[1][i]==4 and tick(p)[0][i]==0
            cases.append('pump%d not ready overrides run' % (i+1))
        for mode in (0,1):
            for value in range(10):
                p=baseline();p.alarm[2]=mode
                (p.manual if mode else p.roles)[0]=value
                expected=3 if value in ((4,5) if mode else (5,8)) else 1
                assert tick(p)[1][0]==expected
                cases.append(('manual' if mode else 'auto')+' preparation%d' % value)
        for leader in (0,1,2,3,4):
            for role in (0,6,8):
                p=baseline();p.leader=leader
                for i in range(3):p.roles[4+i]=role
                assert tick(p)[2] == [int(leader==i+1 and role==6) for i in range(3)]
                cases.append('leader%d confirmed role%d' % (leader,role))
        p=baseline();p.telemetry[0]=450;p.telemetry[10]=2
        tick(p);tick(p);tick(p)
        tick(p,0)
        assert tick(p)[0][0]==1;cases.append('reconnect starts first frame')
        return {'executedCScenarios':len(cases), 'cases':cases,
                'writesLimitedToLW900Through908':True, 'allPLCInputsUnchanged':True,
                'nativeMacroCompileObserved':False}


def validate(source, candidate, recipe, macro):
    raw, final = Path(source).read_bytes(), Path(candidate).read_bytes()
    expected, report = prepare(source, recipe, macro)
    assert final == expected
    changes = report['edits']
    def shifted(at):
        return at+sum(e['targetBytes']-e['sourceBytes'] for e in changes if e['sourceOffset']<at)
    restored, cursor = bytearray(), 0
    for e in changes:
        at = shifted(e['sourceOffset'])
        restored.extend(final[cursor:at])
        end = at+e['targetBytes']
        assert hashlib.sha256(final[at:end]).hexdigest()==e['targetSHA256']
        restored.extend(raw[e['sourceOffset']:e['sourceOffset']+e['sourceBytes']])
        cursor = end
    restored.extend(final[cursor:])
    assert bytes(restored)==raw
    spec=json.loads(Path(recipe).read_text())
    for h in spec['sceneHeaders']:
        assert struct.unpack_from('>I',final,shifted(h['countOffset']))[0] == h['count']+(6 if h['screen']==1 else 0)
    # Original first-three bars and every navigation/timer/control record are
    # outside the small allowlist; reconstructing the source proves preservation.
    for name in ('BG10012','BG10026','BG10040'):
        o=next(o for o in spec['objects'] if o['id']==name)
        assert final[shifted(o['start']):shifted(o['stop'])]==raw[o['start']:o['stop']]
    for name in ('MD70010','MD70011','MD70012','MD70020','MD70021','MD70022'):
        assert final.count(qs(name))==1 and qs(name) not in raw
    for address in range(900,909):
        assert qs('LW%d' % address) not in raw
        assert final.count(qs('LW%d' % address))==1
    # Four newly declared variables must be read-only in BOTH config mirrors.
    for name,kind,size,address in VARIABLES:
        assert final.count(qs(name))==1
        assert (name+'#'+kind+'#'+size+'#R#R#'+address+'#').encode('utf-16-be') in final
    a,b=read_directory(raw),read_directory(final)
    changed_sections=[]
    for i in range(22):
        if raw[a['entries'][i]:a['entries'][i+1]] != final[b['entries'][i]:b['entries'][i+1]]:
            changed_sections.append(i)
    assert changed_sections==[17], changed_sections
    # Count actual added groups independently of the item's cached count.
    group=re.compile(bytes.fromhex('00010017')+b'\x00\x00\x00[\x01-\x09]'+bytes.fromhex('000100'))
    start,stop=spec['sceneHeaders'][0]['countOffset']+4,spec['sceneHeaders'][1]['countOffset']
    assert len(list(group.finditer(raw,start,stop)))==73
    assert len(list(group.finditer(final,shifted(start),shifted(stop))))==79
    assert Path(source).read_bytes()==raw
    return {**exercise_c(macro), 'sourceRestoredExactly':True, 'scene1Widgets':79,
            'other13SceneCountsPreserved':True,'existingFrequencyBarsPreserved':True,
            'navigationTimersControlsPreserved':True, 'changedMetadataSections':changed_sections,
            'directoryAndEOFValid':True,'nativeOpeningRenderingObserved':False,'PLCChanged':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','candidate','recipe','macro','report'):
        p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if not any((a.source,a.candidate,a.recipe,a.macro,a.report)):
        root=Path(__file__).resolve().parents[1]
        font=root/'assets/hmi/pump-animation/PumpStationRotor.ttf'
        assert hashlib.sha256(font.read_bytes()).hexdigest()==FONT_SHA
        assert FONT_SHA in (root/'tools/Install-PumpAnimationFont.ps1').read_text()
        report=exercise_c(root/'assets/hmi/pump-animation/pump_animation.c')
        print('PASS:',report['executedCScenarios'],'actual C scenarios; font asset/install checksum. Native checks separate.')
        return
    if not all((a.source,a.candidate,a.recipe,a.macro,a.report)):
        p.error('Use no arguments for C/font checks, or provide all five source/candidate/recipe/macro/report paths')
    if a.report.exists() or a.report.is_symlink() or a.report.resolve() in {v.resolve() for v in (a.source,a.candidate,a.recipe,a.macro)}:
        raise ValueError('NEW separate report required')
    report=validate(a.source,a.candidate,a.recipe,a.macro)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS:',report['executedCScenarios'],'actual C scenarios; byte preservation, bars, 14 scenes and directory.')
    print('Native SKTool compile/render/transport still require observation.')


if __name__=='__main__':main()
