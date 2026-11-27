"""Exercise the saved Oshsky source and the actual SKTOOL X86 register layout offline."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from build_native_merge_r16 import macro_mirrors
from build_oshsky_cascade_r3 import network_inventory
from build_oshsky_native_fault import AUX, CORE, build
from build_vfd_fault_export_r14 import inventory
from validate_oshsky_sound_rearm import SoundCPU, verify_hmi


def plc_cases(source, saved):
    built, _ = build(source)
    actual, _, native, _ = network_inventory(saved.read_bytes())
    assert actual['image'] == network_inventory(built)[0]['image']
    def tables(part):
        return [record for kind, _, record in part['records'] if kind == 0x1015]
    source_part = network_inventory(source.read_bytes())[0]
    assert len(tables(actual)) == 9 and tables(source_part) == tables(actual)
    names = [k.split(' | ')[0] for _, k in inventory(saved.read_bytes())[1] if k.startswith('65.CNF')]
    init = [k for k in names if 39 <= int(k[-3:]) <= 48]
    publish = [k for k in names if 49 <= int(k[-3:]) <= 78]
    assert len(init) == 10 and len(publish) == 30
    assert len(CORE) == 8 and sorted(CORE + AUX) == list(range(18))
    cpu = SoundCPU()
    cpu.set(R2893=1, R2840=65000)
    for key in init:
        cpu.execute(native[key])
    assert cpu.value('R3610') == 27428 and cpu.value('R3629') == 38107
    def sample(raw, valid, replies):
        for i in range(4):
            cpu.set(**{f'R{2801+8*i}':raw[i], f'M{1744+i}':replies[i], f'M{1748+i}':valid[i]})
        for k in publish:
            cpu.execute(native[k])
        return [cpu.value(f'R{3612+i}') for i in range(4)]
    ones = [1]*4
    codes = [9,52,4317,65535]
    assert sample(codes,ones,ones) == codes and cpu.value('R3628') == 1
    assert sample(codes,ones,ones) == codes and cpu.value('R3628') == 0
    for i in range(4):
        q = ones.copy(); q[i] = 0
        lose = codes.copy(); lose[i] = 0
        assert sample(lose,q,q) == codes and cpu.value(f'R{3616+i}') == 0
        assert sample(codes,ones,ones) == codes and cpu.value('R3628') == 0
    cpu.set(R3624=65535)
    assert sample([0,52,4317,65535],ones,ones)[0] == 0 and cpu.value('R3624') == 1
    assert cpu.value('R3628') == 0
    assert sample([32768,52,4317,65535],ones,ones)[0] == 32768 and cpu.value('R3628') == 1


DRIVER = r'''
#include <assert.h>
int main(void) {
    static unsigned short w[65536], rw[65536];
    static unsigned char b[65536];
    static unsigned int vars[128];
    IN io={(char*)vars,0,0,w,b,rw}; IN *p=&io;
    unsigned int i,k,events;
    unsigned short codes[4]={9,52,4317,65535};
    b[60107]=1; AlarmWords[4]=32; AlarmWords[0]=1; AlarmWords[1]=512;
    OshContract[0]=27110; OshFault[0]=27428; OshFault[1]=65534;
    w[60005]=0x2026; w[60004]=0x11;w[60003]=0x27;
    for(i=0;i<4;++i) { OshFault[2+i]=codes[i];OshFault[6+i]=1;
        OshFault[10+i]=65533;OshFault[14+i]=1; }
    Macro_main(p);assert(!w[54313]&&!w[51203]);
    OshFault[1]=65535;Macro_main(p);assert(w[54312]==15 && w[51203]==4 && w[54316]==5);
    for(i=0;i<4;++i) { assert(b[2160+i]&&b[2164+i]&&w[54300+i]==codes[i]);assert(w[54304+i]==2); }
    assert(!b[2172]&&!b[2173]&&b[2174]&&b[2175]);
    assert(w[51216]==4 && w[51218]==65535 && w[51219]==2026);
    b[800]=1;Macro_main(p);assert(b[801]&&!b[802]);events=w[54315];
    for(i=0;i<4;++i) {
        OshFault[1]=(unsigned short)(OshFault[1]+1);OshFault[6+i]=0;OshFault[2+i]=0;Macro_main(p);
        assert(!b[2160+i] && b[2168+i] && b[2176+i] && w[51203]==4 && w[51204+i]==codes[i]);
        assert(w[54312]==15 && b[801] && !b[802]);
        OshFault[6+i]=1;OshFault[2+i]=codes[i];Macro_main(p);
        assert(b[2160+i] && w[51203]==4 && w[54315]==events);
    }
    w[60000]=0x04;Macro_main(p);assert(!w[54313]&&!b[2164]&&w[51203]==4);
    b[60107]=0;Macro_main(p);assert(!b[2164]&&w[51203]==4&&b[801]);
    b[60107]=1;OshFault[1]=4;Macro_main(p);OshFault[1]=5;Macro_main(p);
    assert(w[54313]&&b[2160]&&!b[802]);
    OshFault[2]=52;AlarmWords[1]=1024;Macro_main(p);
    assert(w[51216]==1&&w[51217]==9&&w[51218]==52&&w[51203]==5&&b[802]);
    OshFault[2]=0;Macro_main(p);assert(!b[2160]&&b[2164]&&w[51203]==6&&w[51217]==52&&!w[51218]);
    assert(w[51216+9]==1&&w[51217+9]==9&&w[51218+9]==52);
    AlarmWords[4]=31;Macro_main(p);assert(!w[54313]&&!b[2164] && w[51203]==6);
    for(k=0;k<4;++k) assert(w[51204+k]==(k?codes[k]:0));
    return 0;
}
'''


def run(source, saved, hmi, generated, toolchain):
    plc_cases(source, saved)
    sound_cases = verify_hmi(hmi, generated, toolchain, True, True)
    text = generated.read_text('utf8')
    header = text[text.index('#include "MacroInit.h"'):text.index('/* Native Variable')]
    first, second = macro_mirrors(hmi.read_bytes())
    assert first == second
    macro = first[4:].decode('utf-16-be').replace('\r','')
    assert 'TEST_ONLY' not in macro and 'OshActiveAlarmCount' in macro
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        shutil.copy2(toolchain/'MacroInit.h',tmp)
        (tmp/'fault.c').write_text(header + macro[macro.index('/* Native Variable'):] + DRIVER,'utf8')
        env = {**os.environ,'PATH':str(toolchain) + os.pathsep + os.environ['PATH']}
        subprocess.run([toolchain/'gcc.exe','fault.c','-o','fault.exe'],cwd=tmp,env=env,check=True)
        subprocess.run([tmp/'fault.exe'],cwd=tmp,env=env,check=True,timeout=15)
    return sound_cases


if __name__ == '__main__':
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ('base','pdw','skm','generated','toolchain'):
        cli.add_argument(name,type=Path)
    a = cli.parse_args()
    print('Existing sound scenarios:',run(a.base,a.pdw,a.skm,a.generated,a.toolchain))
    print('Saved PLC publication and four-channel native HMI scenarios passed')
