#!/usr/bin/env python3
"""Execute the inspected SKM's animation C, independent of the patch helper.

The host checks logic/read-only inputs, not SKTool's ABI, native widgets or
serial exchange. The private SKM stays outside Git. Old r17/r18 must fail.
"""
import argparse
import ctypes as ct
from pathlib import Path
import re
import subprocess
import tempfile

from build_native_merge_r16 import macro_mirrors


class Inputs(ct.Structure):
    _fields_ = [('alarm', ct.c_ushort * 5), ('telemetry', ct.c_ushort * 13),
                ('roles', ct.c_ushort * 7), ('manual', ct.c_ushort * 3),
                ('leader', ct.c_ushort * 1)]


def animation_source(raw):
    source = macro_mirrors(raw)[0][4:].decode('utf-16-be')
    match = re.search(r'static void PumpAnimation\(IN \*p\)\s*\{', source)
    if not match:
        raise ValueError('Expected the reviewed animation function')
    start, depth = match.end(), 1
    end = start
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return ('static unsigned short pump_anim_phase[3], pump_anim_ticks[3];\n'
            + source[match.start():end])


def check(path):
    path = Path(path)
    raw = path.read_bytes()
    header = '''
typedef struct { unsigned short alarm[5],telemetry[13],roles[7],manual[3],leader[1]; } IN;
static unsigned char lb[60200];
static unsigned short lw[60200];
#define LocalBit lb
#define LocalWord lw
#define AlarmWords (p->alarm)
#define MapVersion (p->alarm[4])
#define PANEL_MAP_VERSION 32u
#define PumpAnimTelemetry (p->telemetry)
#define PumpAnimRoles (p->roles)
#define PumpAnimManual (p->manual)
#define PumpAnimLeader (p->leader)
'''
    suffix = '''
void tick(IN *p, int connected) { lb[60107] = connected; PumpAnimation(p); }
unsigned short word(int i) { return lw[i]; }
int bits_unchanged(int connected) {
 int i; for(i=0;i<60200;++i) if(lb[i] != (i==60107 ? connected : 0)) return 0;
 return 1;
}
void reset(void) {
 int i; for(i=0;i<60200;++i) { lw[i]=54321; lb[i]=0; }
 for(i=0;i<3;++i) {pump_anim_phase[i]=0; pump_anim_ticks[i]=0;}
}
'''
    cases, failures = [], []
    with tempfile.TemporaryDirectory(prefix='telemetry-hmi-host-') as name:
        folder = Path(name)
        source = folder / 'animation.c'
        source.write_text(header + animation_source(raw) + suffix)
        library = folder / 'animation.so'
        subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                        '-fPIC', '-shared', str(source), '-o', str(library)],
                       check=True, capture_output=True)
        lib = ct.CDLL(str(library))
        lib.tick.argtypes = [ct.POINTER(Inputs), ct.c_int]
        lib.word.argtypes, lib.word.restype = [ct.c_int], ct.c_ushort
        lib.bits_unchanged.argtypes = [ct.c_int]

        def baseline():
            lib.reset()
            p = Inputs()
            p.alarm[4], p.telemetry[9] = 32, 27133
            for i in range(3):
                p.telemetry[10 + i], p.roles[i] = 1, 4
            return p

        def tick(p, connected=1):
            before = bytes(p)
            lib.tick(ct.byref(p), connected)
            assert bytes(p) == before, 'Animation wrote a PLC input'
            assert lib.bits_unchanged(connected), 'Animation wrote a command/local bit'
            allowed = set(range(900, 909)) | set(range(920, 926)) | set(range(960, 966))
            assert all(lib.word(i) == 54321 for i in range(60200) if i not in allowed), \
                'Undeclared local word write'
            return tuple([lib.word(base + i) for i in range(3)]
                         for base in (900, 903, 906, 960, 963))

        def expect(name, actual, wanted):
            cases.append(name)
            if actual != wanted:
                failures.append(f'{name}: {actual} != {wanted}')

        p = baseline()
        expect('valid zero current/stopped differs from unknown', tick(p),
               ([0]*3, [1]*3, [0]*3, [0]*3, [1]*3))
        for pump in range(3):
            p = baseline()
            p.telemetry[pump], p.telemetry[10 + pump] = 450, 2
            p.telemetry[4 + pump] = 47
            p.leader[0], p.roles[4 + pump] = pump + 1, 6
            p.alarm[0] |= 1 << (9 + pump)  # unrelated poll's generic comm alarm
            for step in range(8):
                frames, state, leader, current, quality = tick(p)
                expect(f'P{pump+1} fresh running survives generic alarm tick{step}',
                       (frames[pump], state[pump], leader[pump], current[pump], quality[pump]),
                       (1 + step % 4, 2, 1, 47, 1))
                expect(f'P{pump+1} other channels independent tick{step}',
                       [(frames[j], state[j], current[j], quality[j]) for j in range(3) if j != pump],
                       [(0, 1, 0, 1)] * 2)
            for frequency, quality, state in ((0,1,1),(1,2,2),(5990,2,2),
                                               (5991,2,0),(65535,2,0),
                                               (0,2,0),(250,1,0),(250,0,0),(250,3,0)):
                p = baseline()
                p.telemetry[pump], p.telemetry[10 + pump] = frequency, quality
                p.telemetry[4 + pump] = 1234
                result = tick(p)
                expect(f'P{pump+1} own quality/frequency Q{quality} F{frequency}',
                       (result[1][pump], result[4][pump]), (state, int(state != 0)))
            for current in (0, 47, 1234, 65535):
                p = baseline(); p.telemetry[4 + pump] = current
                result = tick(p)
                expect(f'P{pump+1} uint16 current {current}',
                       (result[3][pump], result[4][pump]), (current, 1))
            p = baseline(); p.alarm[0] |= 1 << (5 + pump)
            p.telemetry[pump], p.telemetry[10 + pump], p.telemetry[4 + pump] = 450, 2, 87
            result = tick(p)
            expect(f'P{pump+1} not-ready stops green but retains valid measurement',
                   (result[0][pump], result[1][pump], result[2][pump], result[3][pump], result[4][pump]),
                   (0, 4, 0, 87, 1))
            for manual, role in ((False,5),(False,8),(True,4),(True,5)):
                p = baseline()
                p.alarm[2] = int(manual)
                (p.manual if manual else p.roles)[pump] = role
                expect(f'P{pump+1} preparing manual{manual} role{role}', tick(p)[1][pump], 3)
        for connected, map_version in ((0,32),(1,31),(1,0)):
            p = baseline(); p.alarm[4] = map_version
            result = tick(p, connected)
            expect(f'global link/map gate {connected}/{map_version}',
                   (result[0],result[1],result[4]), ([0]*3,[0]*3,[0]*3))
        p = baseline(); p.telemetry[9] = 0
        result = tick(p)
        expect('old PLC marker hides current without faking zero/losing old frequency',
               (result[1],result[4]), ([1]*3,[0]*3))
        p = baseline(); p.telemetry[:3] = (150,300,500); p.telemetry[10:13] = (2,2,2)
        p.telemetry[4:7] = (17,204,389)
        for step in range(6):
            result = tick(p)
            expect(f'all channels independent raw current tick{step}', result[3], [17,204,389])
        p.telemetry[10] = 0
        result = tick(p)
        expect('own telemetry loss invalidates only its channel',
               (result[1],result[4]), ([0,2,2],[0,1,1]))
        p.telemetry[10] = 2
        expect('recovery restores its channel', tick(p)[1], [2,2,2])
    assert path.read_bytes() == raw, 'Source changed'
    if failures:
        raise AssertionError(f'{len(failures)}/{len(cases)} cases failed:\n'
                             + '\n'.join(failures))
    return len(cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Private SKM, stage or native SaveAs')
    args = parser.parse_args()
    print(f'PASS: {check(args.source)} actual C animation/current cases; native/serial checks separate')
