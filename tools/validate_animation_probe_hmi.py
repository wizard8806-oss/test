#!/usr/bin/env python3
"""Verify diagnostic-only edits and compare instrumented/original macro behavior.

Host IN below tests instrumentation side effects only. It does NOT establish
the actual native pVar layout or diagnose the user's deployed animation.
"""
import argparse
import ctypes as ct
import itertools
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from build_animation_probe_hmi import prepare, instrument, scene, qs, sha, qscan


class Input(ct.Structure):
    _fields_ = [('alarm', ct.c_ushort*5), ('ack', ct.c_ushort),
                ('telemetry', ct.c_ushort*13), ('roles', ct.c_ushort*7),
                ('manual', ct.c_ushort*3), ('leader', ct.c_ushort)]


HEADER = '''
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
WRAPPER = '''
void reset_test(void) {
 int i;for(i=0;i<60200;i++){words[i]=0;bits[i]=0;}
 words[51000]=27128;words[926]=59999;
 alarm_previous=0;alarm_muted=0;alarm_started=0;
 cl50_previous_generation=0;cl50_pending_generation=0;
 helpers_started=0;boot_seen=0;manual_seen=0;manual_sync=0;
 for(i=0;i<3;i++){pump_anim_phase[i]=0;pump_anim_ticks[i]=0;}
}
void tick_test(IN *p,int link,int mute){bits[60107]=link;bits[800]=mute;Macro_main(p);}
unsigned short *words_test(void){return words;}
unsigned char *bits_test(void){return bits;}
'''


def host_check(macro):
    original = Path(macro).read_text().replace('\r\n', '\n').strip()
    cases = 0
    with tempfile.TemporaryDirectory(prefix='animation-probe-host-') as d:
        root = Path(d); (root/'MacroInit.h').write_text(HEADER)
        libs = []
        for n, c in enumerate((original, instrument(original))):
            p = root/('macro%d.c' % n); out = root/('macro%d.so' % n)
            p.write_text(c+'\n'+WRAPPER)
            subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared',
                            '-fPIC', str(p), '-o', str(out)], check=True, capture_output=True)
            lib = ct.CDLL(str(out)); lib.tick_test.argtypes = [ct.POINTER(Input), ct.c_int, ct.c_int]
            lib.words_test.restype = ct.POINTER(ct.c_ushort)
            lib.bits_test.restype = ct.POINTER(ct.c_ubyte)
            libs.append(lib)
        # Separate pumps, every pair, all three; mode/map/link/quality failures.
        for mask, manual, link, version in itertools.product(range(8), (0, 1), (0, 1), (0, 32)):
            for lib in libs:
                lib.reset_test()
            inputs = [Input(), Input()]
            for p in inputs:
                p.alarm[4] = version; p.alarm[2] = manual
                p.alarm[0] = 3  # pressure warnings do not gate frequency decoration
                for i in range(3):
                    p.telemetry[i] = (250+50*i) if mask & (1 << i) else 0
                    p.telemetry[10+i] = 2 if mask & (1 << i) else 1
            for tick in range(8):
                for lib, p in zip(libs, inputs):
                    lib.tick_test(ct.byref(p), link, tick == 3)
                assert bytes(inputs[0]) == bytes(inputs[1]), 'Instrumentation changed PLC write/input values'
                old = ct.string_at(libs[0].words_test(), 60200*2)
                new = ct.string_at(libs[1].words_test(), 60200*2)
                assert old[:920*2] == new[:920*2] and old[931*2:] == new[931*2:]
                assert ct.string_at(libs[0].bits_test(), 60200) == ct.string_at(libs[1].bits_test(), 60200)
                words = libs[1].words_test()
                assert [words[920+i] for i in range(3)] == list(inputs[1].telemetry[:3])
                assert [words[923+i] for i in range(3)] == list(inputs[1].telemetry[10:13])
                assert words[926] == tick and words[927] == version
                assert words[928] == 3 and words[929] == link and words[930] == 27119
            # Unknown quality must remain unknown, with captured raw frequency.
            for p in inputs:
                p.telemetry[10] = 0
            for lib, p in zip(libs, inputs):
                lib.tick_test(ct.byref(p), link, 0)
            assert libs[1].words_test()[923] == 0
            assert libs[1].words_test()[900] == 0 and libs[1].words_test()[903] == 0
            cases += 1
    return {'hostDifferentialCases': cases, 'macroTicksCompared': cases*9,
            'existingWordsBitsAndWriteInputsUnchanged': True,
            'probeInputSnapshotsAndWrapVerified': True, 'nativeABIValidated': False}


def validate(source, candidate, macro, fixture=False):
    expected, report = prepare(source, macro, fixture)
    final = Path(candidate).read_bytes()
    if final != expected:
        raise ValueError('Candidate differs from the diagnostic-only transformation')
    _, objects = scene(final, 13)
    if len(objects) != 71 or sum(o['id'].startswith('ND') for o in objects.values()) != 28:
        raise ValueError('Probe scene inventory differs')
    if any(o['id'].startswith(('NE', 'BB', 'FB')) for o in objects.values()):
        raise ValueError('Process command control added to diagnostic page')
    for f in report['fields']:
        matches = [o for o in objects.values() if o['id'].startswith('ND') and qs(f['address']) in o['raw']]
        if len(matches) != 1:
            raise ValueError('Display binding not unique: ' + f['address'])
        raw = matches[0]['raw']
        if struct.unpack_from('>2d', raw, 85) != (f['x'], f['y']):
            raise ValueError('Display geometry differs')
    for o in objects.values():
        x, y = struct.unpack_from('>2d', o['raw'], 85)
        w, h = struct.unpack_from('>2d', o['raw'], 28)
        if not (0 <= x and 0 <= y and x+w <= 800 and y+h <= 480):
            raise ValueError('Probe object does not fit the panel')
    _, main = scene(final, 1, 'SB')
    nav = [o for o in main.values() if qs('Диагностика') in o['raw']]
    if len(nav) != 1 or qs('Screen13') not in nav[0]['raw']:
        raise ValueError('Probe route differs')
    result = {'candidateSHA256': sha(final), 'candidateBytes': len(final),
              'fixtureOnly': fixture, 'sourceAndAllUnlistedBytesPreserved': True,
              'screens2Through12IncludingAlarmPagePreserved': True,
              'all28ReadOnlyBindingsUnique': True, 'allObjectsFit800x480': True,
              'nativeCompileObserved': False, 'animationFaultDiagnosed': False}
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'candidate', 'macro', 'report'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--fixture-source', action='store_true')
    p.add_argument('--host-check', action='store_true', help='requires cc; not required on Windows')
    a = p.parse_args()
    if len({v.resolve() for v in (a.source, a.candidate, a.macro, a.report)}) != 4 or a.report.exists() or a.report.is_symlink():
        raise ValueError('Distinct inputs and NEW report required')
    result = validate(a.source, a.candidate, a.macro, a.fixture_source)
    if a.host_check:
        result.update(host_check(a.macro))
    with a.report.open('x', encoding='utf8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2); f.write('\n')
    print('PASS diagnostic-only preservation, 28 bindings and 800x480 geometry.')
    if a.host_check:
        print('PASS', result['hostDifferentialCases'], 'host instrumentation cases; NOT native ABI proof.')


if __name__ == '__main__':
    main()
