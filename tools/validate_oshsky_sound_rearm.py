"""Check actual SKTool X86 ABI, native sound transitions and original CL50 networks."""
import argparse
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from build_native_merge_r16 import macro_mirrors
from build_oshsky_sound_capture import build, network_inventory, plan
from check_native_drive_edit_02 import unpack
from validate_oshsky_stop4_capture import CPU
from build_cascade_r10 import d

HARNESS = r'''
#include <assert.h>
#include <stdlib.h>
int main(int argc,char **argv) {
    static unsigned short words[65536],rwi[65536];
    static unsigned char bits[65536];
    static unsigned int vars[128];
    IN state={(char*)vars,0,0,words,bits,rwi};
    IN *p=&state;
    int i,which=atoi(argv[1]);
    unsigned short initial=which==5?127:10;
    bits[60107]=1;bits[60185]=75;AlarmWords[0]=3;AlarmWords[4]=32;
    AlarmWords[1]=initial<<9;OshContract[0]=27110;
    words[60005]=0x2026;words[60004]=0x11;words[60003]=0x26;
    OshTelemetry[9]=27401;CascadeBlock[0]=27402;
    if (which==10) {
        AlarmWords[1]=0x0700; Macro_main(p);
        assert(bits[54210] && words[54210]==1);
        bits[54210]=0; Macro_main(p); assert(!bits[54210]);
        bits[800]=1; Macro_main(p);
        assert(bits[54210] && words[54210]==259 && bits[801]);
        for(i=0;i<100;++i) {Macro_main(p);assert(bits[54210] && words[54210]==259);}
        bits[54210]=0; Macro_main(p);assert(!bits[54210]);
        bits[800]=1;Macro_main(p);assert(bits[54210] && words[54210]==259);
        bits[60107]=0;Macro_main(p);assert(!bits[54210] && !words[54210]);
        bits[800]=1;Macro_main(p);assert(!bits[54210]);
        bits[60107]=1;Macro_main(p);assert(words[54210]<=1);
        bits[54210]=0;Macro_main(p);
        bits[800]=1;Macro_main(p);assert(bits[54210] && words[54210]==259);
        AlarmWords[1]=0x0900; Macro_main(p);assert(words[54210]<=1 && !bits[801] && bits[802]);
        return 0;
    }
    if (which==9) {
        AlarmWords[0]=7624; AlarmWords[1]=0x0700;
        Macro_main(p); assert(BootAck==1 && bits[802]);
        bits[800]=1; Macro_main(p);
        if (BootAck!=259) { fprintf(stderr,"Observed service word %u, expected 259\n",(unsigned)BootAck); return 19; }
        assert(bits[801] && !bits[802]);
        for(i=0;i<12;++i) { Macro_main(p); assert(BootAck==1 && bits[801]); }
        bits[800]=1; AlarmWords[1]=0x0900; Macro_main(p);
        assert(BootAck==1 && !bits[801] && bits[802]);
        return 0;
    }
    Macro_main(p);assert(bits[802] && bits[60117] && bits[60185]==75);
    bits[800]=1;Macro_main(p);
    assert(bits[801] && !bits[802] && !bits[60117] && BootAck==256+initial && !words[54180]);
    for(i=0;i<21600;i++){
        int sec=(i/4)%60;
        words[60000]=(sec/10)*16+sec%10;
        if(i%4==0){OshTelemetry[8]++;CascadeBlock[5]++;}
        Macro_main(p);assert(bits[801] && !bits[60117] && !words[54180]);
    }
    switch(which){
    case 0: return 0;
    case 1: bits[60107]=0;Macro_main(p);bits[60107]=1;Macro_main(p);
        assert(bits[801] && !bits[60117] && !words[54180]);return 0;
    case 2: AlarmWords[0]=7;break;
    case 3: AlarmWords[1]=11<<9;break;
    case 4: AlarmWords[0]=1;Macro_main(p);assert(bits[801]);AlarmWords[0]=3;break;
    case 5: AlarmWords[1]=1<<9;break;
    case 6: alarm_started=0;alarm_previous=0;alarm_muted=0;cl50_previous_generation=0;
        break;
    case 7: bits[60107]=0;bits[800]=1;Macro_main(p);assert(BootAck==0);
        bits[60107]=1;AlarmWords[1]=11<<9;break;
    case 8: AlarmWords[0]=0;Macro_main(p);assert(!bits[801]&&!bits[802]);AlarmWords[0]=3;break;
    }
    Macro_main(p);assert(bits[60117] && !bits[801] && bits[802] && !BootAck);
    assert(words[54180] && words[54195] && words[54160]==words[54181]);
    if(which==3||which==5||which==7)assert(words[54180]==2 && !words[54186]);
    if(which==2||which==4||which==8)assert(words[54180]==1 && words[54186]);
    if(which==5)assert(words[54188]==127 && words[54189]==1);
    { unsigned short first=words[54181]; AlarmWords[0]=9;Macro_main(p);assert(words[54181]==first); }
    return 0;
}
'''


def verify_hmi(skm, generated, toolchain, boot_priority=False, native_transfer=False):
    source=generated.read_text('utf8')
    header=source[source.index('#include "MacroInit.h"'):source.index('/* Native Variable')]
    data=skm.read_bytes()
    if native_transfer:
        from build_oshsky_sound_transfer import address, transfer_record
        assert data.count(transfer_record())==1 and data.count(address('R',2553))==1
        assert data.count(address('LW',54211))==1
    a,b=macro_mirrors(data)
    assert a==b
    c=a[4:].decode('utf-16-be').replace('\r','')
    assert c.count('LocalBit[60117] =')==1 and 'LocalBit[60185]' not in c
    with tempfile.TemporaryDirectory() as tmp:
        loc=Path(tmp);shutil.copy2(toolchain/'MacroInit.h',loc/'MacroInit.h')
        (loc/'test.c').write_text(header+c[c.index('/* Native Variable'):]+HARNESS,'utf8')
        env={**os.environ,'PATH':str(toolchain)+os.pathsep+os.environ.get('PATH','')}
        subprocess.run([toolchain/'gcc.exe','test.c','-o','test.exe'],cwd=loc,env=env,check=True)
        count=11 if native_transfer else (10 if boot_priority else 9)
        for i in range(count):
            subprocess.run([loc/'test.exe',str(i)],cwd=loc,env=env,check=True)
    return count


class SoundCPU(CPU):
    def execute(self,code):
        # The saved CL50 arithmetic uses subtraction of literal WORDs. Supply
        # that same operand to the test machine's normal 16-bit subtract opcode.
        words=list(struct.unpack('>'+'H'*(len(code)//2),code))
        if 0xf664 in words:
            pos=words.index(0xf664)
            self.regs[('D',4000)]=words[pos+2]
            words[pos:pos+3]=[0xf464,words[pos+1],d(4000)]
            code=struct.pack('>'+'H'*len(words),*words)
        super().execute(code)


def verify_plc(base, saved):
    source=network_inventory(base.read_bytes())
    built=network_inventory(build(base)[0])
    actual=network_inventory(saved.read_bytes())
    assert built[0]['image']==actual[0]['image'] and actual[1:]==built[1:]
    assert len(unpack(base)['tables'])==9
    tables=lambda frame: [body for kind,body,_ in frame['records'] if kind==0x1015]
    assert tables(source[0])==tables(actual[0])
    new=plan(source[2])
    original={k.split(' | ')[0]:k for k in source[2]}
    def step(m,key,native=True):
        full=original[key]
        for label,_ in new.get(full,[]):
            m.execute(actual[2][label.split(' | ')[0]])
        if native:m.execute(source[2][full])
    def scan(m,mask,token):
        m.set(R2550=mask&65535,R2551=mask>>16,R2676=token,R2363=mask.bit_count())
        for i in range(24):m.set(**{'M'+str(1550+i):(mask>>i)&1})
        step(m,'10.01',False)
        for i in range(77,141):step(m,'96.L%03d'%i)
        step(m,'96.L159',False)
        m.set(M1924=0)
    for i in range(24):
        m=SoundCPU()
        other=1<<((i+1)%24);extra=1<<i
        m.set(M1924=1,R2678=126,R2680=126<<9,R2840=456,R3203=123)
        scan(m,other,0);assert m.value('R2678')==127 and m.value('R3562')==0
        # Mutable transport failure/retry alone cannot unmute a stable alarm.
        scan(m,other,256+127);assert m.value('M1802') and m.value('R3604')
        m.set(D1320=0x105,D1321=0x406,M1810=1,M1811=1,R2665=2)
        for _ in range(3):scan(m,other,0)
        assert m.value('M1802') and m.value('R3562')==0
        scan(m,other|extra,256+127)
        assert m.value('R3562')==2 and m.value('R3579')==i+1
        assert (m.value('R3577') | (m.value('R3578')<<16))==extra
        assert (m.value('R3575') | (m.value('R3576')<<16))==other
        assert [m.value('R'+str(x)) for x in (3567,3568,3581,3582,3584)]==[127,1,1,0,12]
        assert m.value('R3595')==0x105 and m.value('R3598')==1
        frozen=[m.value('R'+str(x)) for x in range(3564,3604)]
        scan(m,other,256+127);assert not m.value('M1802')
        scan(m,other,257);assert m.value('M1802')
        m.set(M1924=1);scan(m,other,0)
        assert frozen==[m.value('R'+str(x)) for x in range(3564,3604)]
        assert m.value('R3563')==2
    return 24


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('base','pdw','skm','generated','toolchain'):ap.add_argument(name,type=Path)
    ap.add_argument('--boot-priority', action='store_true', help='Include the measured r3g startup/mute collision')
    ap.add_argument('--native-transfer', action='store_true', help='Verify the single native R2553 transfer and cancellation on link loss or a new generation')
    a=ap.parse_args()
    print('PLC', verify_plc(a.base,a.pdw), 'HMI',verify_hmi(a.skm,a.generated,a.toolchain,a.boot_priority,a.native_transfer))
