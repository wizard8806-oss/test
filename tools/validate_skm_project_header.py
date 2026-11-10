#!/usr/bin/env python3
"""Regression: declared pages require their sceneCommonData pairs.

The former r15 had a valid model QString and trailing directory but native
SKTool reported 0x0. A sequential prefix check must reject that layout.
Synthetic fixtures contain no native project or vendor bytes.
"""
import struct
from skm_project_header import read_project_header


def qs(value):
    b=value.encode('utf-16-be');return struct.pack('>I',len(b))+b


def fixture(count,entries=None,rect=(0.,0.,800.,480.)):
    return (qs('SKTOOL-V7.1.0.80')+qs('SK-070HE')+struct.pack('>I',count)
        +struct.pack('>ii',0,-1)*(count if entries is None else entries)
        +struct.pack('>4d',*rect)+b'\x00'*512)


def main():
    cases=[]
    for count in (1,14,16):
        result=read_project_header(fixture(count))
        assert result['pageCount']==count and len(result['common'])==count
        assert result['firstSceneRect']==(0.,0.,800.,480.) and result['model']=='SK-070HE'
        cases.append('valid '+str(count)+' pages')
    for label,raw in (
        ('former r15 count16 entries14',fixture(16,14)),
        ('too many common entries',fixture(14,16)),
        ('zero resolution',fixture(16,rect=(0.,0.,0.,0.))),
        ('NaN resolution',fixture(16,rect=(0.,0.,float('nan'),480.))),
        ('nonpixel resolution',fixture(16,rect=(0.,0.,799.5,480.))),
        ('truncated stream',fixture(16)[:150]),
        ('zero count',fixture(0)),
        ('overflow count',fixture(1001,0))):
        try:read_project_header(raw)
        except ValueError:cases.append('reject '+label)
        else:raise AssertionError('Malformed prefix accepted: '+label)
    former=fixture(16,14);fixed=former[:172]+struct.pack('>ii',0,-1)*2+former[172:]
    assert fixed==fixture(16) and read_project_header(fixed)['resolution']==(800.,480.)
    cases.append('adding exactly16 missing bytes restores stream alignment')
    print('PASS',len(cases),'sequential SKM-header regressions; not native Open/Compile')
if __name__=='__main__':main()
