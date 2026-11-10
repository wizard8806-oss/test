#!/usr/bin/env python3
"""Regress the r15 alarm-definition/name-directory cardinality mismatch.

Synthetic minimal metadata only. The real two-group native sample is
validated privately; this test does not claim native editor execution.
"""
import struct
from skm_alarm_catalog import validate_alarm_catalog,read_definitions

u32=lambda value:struct.pack('>I',value)
def qstring(value):
    data=value.encode('utf-16-be');return u32(len(data))+data


def fixture(count=2,directory_count=None,companion_count=None):
    names=['События станции']+['Native sample '+str(i) for i in range(1,count)]
    prefix=qstring('SKTOOL-V7.1.0.80')+qstring('SK-070HE')+u32(1)+struct.pack('>ii4d',0,-1,0.,0.,800.,480.)
    rows=[]
    for index,name in enumerate(names):
        n=1;address='R2550' if index==0 else 'LB1';number='2550' if index==0 else '1';kind='R' if index==0 else 'LB'
        protocol=bytes((1,6,1)) if index==0 else bytes((0,0,100));word=1 if index==0 else 0
        rows.append(struct.pack('>HH',n,0)+bytes((0,1,1))+qstring(name)+qstring(address)+protocol
            +qstring(number)+qstring(kind)+bytes((word,))+u32(1)+b'\x01'+u32(1)+b'\x00'
            +u32(1)+u32(1)+qstring('TEST '+str(index))+u32(1)+qstring('0\x01'))
    take=count if directory_count is None else directory_count
    catalog=b''.join(qstring('B%02d:%s'%(i,name)) for i,name in enumerate(names[:take]))
    catalog+=b'\0'*(4*(take if companion_count is None else companion_count))
    return prefix+u32(count)+b''.join(rows)+u32(0)+b'\0'*16+catalog+u32(1)+u32(0)+u32(0)


def main():
    cases=[]
    for count in (1,2,13):
        raw=fixture(count);result=validate_alarm_catalog(raw)
        assert result['groupCount']==result['directoryCount']==count
        assert result['directory']['companionCount']==count
        cases.append('valid'+str(count)+' definitions/names/companions')
    def reject(label,raw):
        try:validate_alarm_catalog(raw)
        except ValueError:cases.append(label)
        else:raise AssertionError('Accepted inconsistent alarm metadata: '+label)
    reject('original r15 defect:13 definitions/1 directory name',fixture(13,1))
    reject('2 definitions/1 directory name',fixture(2,1))
    reject('missing companion entry',fixture(2,2,1))
    good=fixture();bad=good.replace(qstring('B01:Native sample 1'),qstring('B02:Native sample 1'))
    reject('wrong group identity',bad)
    parsed=validate_alarm_catalog(good);at=parsed['directory']['end']-8
    bad=bytearray(good);bad[at]=1;reject('unreviewed nonzero companion',bytes(bad))
    at=parsed['directory']['sceneMapStart'];bad=bytearray(good);bad[at:at+4]=u32(0);reject('misaligned scene map',bytes(bad))
    bad=bytearray(good);bad[-4:]=u32(1);reject('wrong scene-map pair',bytes(bad))
    at=read_definitions(good)['groups'][1]['keyboardEnd'];bad=bytearray(good);bad[at:at+4]=u32(2)
    reject('definition size/flags mismatch',bytes(bad))
    reject('truncated second definition',good[:read_definitions(good)['groups'][1]['end']-5])
    print('PASS',len(cases),'digital-alarm catalog regressions; native Open remains separate')
if __name__=='__main__':main()
