#!/usr/bin/env python3
"""Execute the actual Main summary C; does not test native UI/transport."""
import ctypes as ct
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


class Inputs(ct.Structure):
    _fields_ = [('map', ct.c_ushort), ('mode', ct.c_ushort * 1),
                ('rotation', ct.c_ushort * 12)]


def check():
    component = (ROOT / 'assets/hmi/modern-main-r20/main_overview.c').read_text()
    header = '''
typedef struct {unsigned short map, mode[1], rotation[12];} IN;
static unsigned short lw[60200];
static unsigned char lb[60200];
#define LocalWord lw
#define LocalBit lb
#define MapVersion (p->map)
#define MainModeData (p->mode)
#define MainRotationData (p->rotation)
'''
    suffix = '''
void seed(int a,int b,int c,int connected) {
 int i; for(i=0;i<60200;++i) {lw[i]=54321;lb[i]=0;}
 lw[903]=a;lw[904]=b;lw[905]=c;lb[60107]=connected;
}
void tick(IN *p) {MainOverview(p);}
unsigned short word(int i) {return lw[i];}
int unchanged(int a,int b,int c,int connected) {
 int i; for(i=0;i<60200;++i) {
  unsigned short expected=i==903?a:(i==904?b:(i==905?c:54321));
  if(!(i>=970&&i<=979)&&lw[i]!=expected) return 0;
  if(lb[i]!=(i==60107?connected:0)) return 0;
 } return 1;
}
'''
    cases = 0
    with tempfile.TemporaryDirectory(prefix='main-overview-host-') as name:
        folder = Path(name)
        (folder / 'test.c').write_text(header + component + suffix)
        subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared',
                        '-fPIC', str(folder / 'test.c'), '-o', str(folder / 'test.so')],
                       check=True, capture_output=True)
        lib = ct.CDLL(str(folder / 'test.so'))
        lib.seed.argtypes = [ct.c_int] * 4
        lib.tick.argtypes = [ct.POINTER(Inputs)]
        lib.word.argtypes, lib.word.restype = [ct.c_int], ct.c_ushort
        lib.unchanged.argtypes = [ct.c_int] * 4

        def run(states=(2,2,1), link=1, version=32, phase=1,
                interval=1440, elapsed=1060, mode=12):
            p = Inputs(); p.map=version; p.mode[0]=mode
            p.rotation[0],p.rotation[10],p.rotation[11]=interval,phase,elapsed
            before = bytes(p)
            lib.seed(*states, link)
            lib.tick(ct.byref(p))
            assert bytes(p) == before, 'Main summary changed a PLC input'
            assert lib.unchanged(*states, link), 'Unexpected write/command outside reserved LW'
            return p, tuple(lib.word(970 + i) for i in range(10))

        def expect(name, actual, wanted):
            nonlocal cases
            assert actual == wanted, (name, actual, wanted)
            cases += 1

        p,v = run()
        expect('real380 minutes remaining', v, (2,1,1,2,6,20,380,1,27135,1))
        for states,count,known in (((1,1,1),0,1),((2,2,2),3,1),((2,3,4),1,1),
                                   ((2,2,0),2,0),((0,0,0),0,0),((2,9,1),1,0)):
            _,v=run(states=states)
            expect('confirmed run count/unknown '+str(states),v[:2],(count,known))
        for link,version,state in ((0,32,2),(1,31,3),(1,0,3)):
            _,v=run(link=link,version=version)
            expect('link/map gate '+str((link,version)),v,
                   (0,0,state,0,0,0,0,0,27135,0))
        for phase,state in ((10,3),(11,6),(20,4),(30,5),(90,7),(91,8),(77,0)):
            _,v=run(phase=phase)
            expect('PLC rotation phase '+str(phase),v[3:8],(state,0,0,0,0))
        for mode in (0,10,11,20,21,22,90):
            _,v=run(mode=mode)
            expect('paused without AUTO run permission '+str(mode),v[3:8],(9,0,0,0,0))
        _,v=run(mode=65535)
        expect('unknown PLC mode',v[3],0)
        _,v=run(interval=0,elapsed=0)
        expect('disabled interval',v[3:8],(1,0,0,0,0))
        _,v=run(interval=0,elapsed=0,phase=10)
        expect('operator change still waits when timed change disabled',v[3],3)
        for interval,elapsed,state,hours,minutes,total in (
                (1,0,2,0,1,1),(1440,1440,2,0,0,0),(1440,1441,0,0,0,0),
                (32767,0,2,546,7,32767),(32768,0,8,0,0,0),
                (65535,0,8,0,0,0),(1440,65535,0,0,0,0)):
            _,v=run(interval=interval,elapsed=elapsed)
            expect('bounded remaining '+str((interval,elapsed)),v[3:8],
                   (state,hours,minutes,total,int(state==2)))
        _,v=run(phase=0,mode=0)
        expect('STOP phase0 pauses',v[3],9)
        _,v=run(phase=0,mode=12)
        expect('contradictory active mode/phase not a countdown',v[3],0)
        p,v=run()
        for _ in range(100):lib.tick(ct.byref(p))
        expect('no independent HMI countdown',tuple(lib.word(970+i) for i in range(10)),v)
        p.rotation[11] += 1; lib.tick(ct.byref(p))
        expect('only actual PLC minute changes remaining',lib.word(976),379)
    return cases


if __name__ == '__main__':
    print(f'PASS: {check()} Main summary C cases; native rendering/transport separate')
