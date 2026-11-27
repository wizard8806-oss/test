"""Run the saved four-pump production macros on the vendor's local C target.

Arguments are r3d, r3e, the vendor X86/bin directory, and the generated
production AlarmSound.c retaining its seven native variable definitions.
Only temporary files are created. No PLC or panel connection.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from build_native_merge_r16 import macro_mirrors

HARNESS = r'''
#include <assert.h>
int main(void)
{
    static unsigned short words[65536], rwi[65536];
    static unsigned char bits[65536];
    static unsigned int vars[128];
    IN state={(char*)vars,0,0,words,bits,rwi};
    IN *p=&state;
    unsigned short hb=65530u;
    FILE *out=fopen(OUTFILE,"wb");
    int i,j,ph[4]={0},ticks[4]={0},visited[4]={0};
    assert(out);
    for(i=0;i<192;i++){
        int group=i/16;
        bits[60107]=group!=8;
        bits[800]=(i%19)==3;
        words[60000]=((i/4)%60)/10*16+(i/4)%10;
        words[60001]=0x34; words[60002]=0x16; words[60003]=0x26;
        words[60004]=0x11; words[60005]=0x2026;
        if(group!=10) ++hb;
        AlarmWords[4]=group==9?31:32;
        AlarmWords[0]=0; AlarmWords[1]=(1+(i/8)%7)*512;
        AlarmWords[2]=(group%2)==1;
        OshContract[0]=27110; CascadeMode[0]=12;
        for(j=0;j<4;j++){
            int run=(group<4?group==j:group!=7);
            int unknown=(group==5 && j==3);
            OshTelemetry[j]=run?150+100*j:0;
            OshTelemetry[4+j]=101+137*j;
            OshTelemetry[10+j]=unknown?0:(run?2:1);
        }
        OshTelemetry[8]=hb; OshTelemetry[9]=27401;
        CascadeBlock[0]=27402; CascadeBlock[1]=1; CascadeBlock[2]=4;
        CascadeBlock[3]=7; CascadeBlock[4]=10; CascadeBlock[5]=hb;
        Macro_main(p);
        for(j=0;j<4;j++){
            int f=OshTelemetry[j],q=OshTelemetry[10+j];
            int moving=bits[2100+j] && q==2 && f>0 && f<=5990;
            int expect=0;
            if(!moving){ph[j]=ticks[j]=0;}
            else{
                int div=f<200?3:(f<350?2:1);
                expect=1+ph[j];
                if(++ticks[j]>=div){ticks[j]=0;ph[j]=(ph[j]+1)%4;}
            }
#ifdef TEST_ROTOR
            assert(words[54140+j]==expect);
            if(expect)visited[j]|=1<<(expect-1);
            assert(words[54000+j]==101+137*j);
            if(group==8 || group==9 || (group==10 && i%16>=14))assert(!expect);
#endif
        }
        fwrite(words,2,54140,out);
        fwrite(words+54156,2,65536-54156,out);
        fwrite(bits,1,sizeof(bits),out);fwrite(vars,1,sizeof(vars),out);fwrite(rwi,1,sizeof(rwi),out);
    }
#ifdef TEST_ROTOR
    for(j=0;j<4;j++)assert(visited[j]==15);
#endif
    /* Exercise the real global entry point, including alias/RTC/freshness gates. */
    bits[60107]=1; AlarmWords[4]=32; AlarmWords[2]=0; OshContract[0]=27110;
    CascadeMode[0]=12; CascadeBlock[0]=27402;
    for(i=1;i<=2;i++){
        for(j=1;j<=4;j++){
            int sec,pump=(j+1)%4+1;
            for(sec=12;sec>=0;sec--){
                CascadeBlock[1]=sec?i:0; CascadeBlock[2]=sec?pump:0;
                CascadeBlock[3]=sec; CascadeBlock[4]=sec?12:0; CascadeBlock[5]=++hb;
                OshTelemetry[8]=hb;Macro_main(p);
                if(sec){
                    assert(bits[2111]==(i==1) && bits[2112]==(i==2));
                    assert(words[54010]==pump && words[54011]==sec && words[54012]==(sec>=10?2:1));
                }else assert(!bits[2111] && !bits[2112] && !words[54010] && !words[54011]);
            }
        }
    }
    return fclose(out);
}
'''


def verify(baseline, saved, toolchain, generated):
    full=generated.read_text('utf8',errors='replace')
    header=full[full.index('#include "MacroInit.h"'):full.index('/* Native Variable')]
    assert all(('#define '+name+' ') in header for name in (
        'AlarmWords','MapVersion','OshTelemetry','OshContract','CascadeMode','CascadeBlock','BootAck'))
    env={**os.environ,'PATH':str(toolchain)+os.pathsep+os.environ.get('PATH','')}
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        shutil.copy2(toolchain/'MacroInit.h',folder/'MacroInit.h')
        hashes=[]
        for i,file in enumerate((baseline,saved)):
            copies=macro_mirrors(file.read_bytes());assert len(copies)==2 and copies[0]==copies[1]
            code=copies[0][4:].decode('utf-16-be').replace('\r','')
            flags='#define OUTFILE "snap.bin"\n'+('#define TEST_ROTOR\n' if i else '')
            (folder/'verify.c').write_text(flags+header+code[code.index('/* Native Variable'):]+HARNESS,'utf8')
            subprocess.run([toolchain/'gcc.exe','verify.c','-o','verify.exe'],cwd=folder,env=env,check=True)
            subprocess.run([folder/'verify.exe'],cwd=folder,env=env,check=True)
            hashes.append(hashlib.sha256((folder/'snap.bin').read_bytes()).hexdigest())
        assert hashes[0]==hashes[1]
        return hashes[0]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('r3d','r3e','toolchain','generated'):p.add_argument(name,type=Path)
    a=p.parse_args();print(verify(a.r3d,a.r3e,a.toolchain,a.generated))
