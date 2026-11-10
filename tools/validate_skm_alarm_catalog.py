#!/usr/bin/env python3
"""Regress the r15 alarm-definition/name-directory cardinality mismatch.

Synthetic minimal metadata only. The real two-group native sample is
validated privately; this test does not claim native editor execution.
"""
import struct
from skm_alarm_catalog import (validate_alarm_catalog,read_definitions,
    require_sk_group_limit,compact_fault_definitions,word_bit_semantics,
    validate_alarm_identities,with_sequential_alarm_ids)

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
    for count in (1,7,10):
        require_sk_group_limit(count);cases.append('SK limit accepts '+str(count))
    for count in (0,11,13):
        try:require_sk_group_limit(count)
        except ValueError:cases.append('SK limit rejects '+str(count))
        else:raise AssertionError('Unsupported SK group count accepted')
    def row(name,base,size,messages):
        return (struct.pack('>HH',size,0)+bytes((0,1,1))+qstring(name)
            +qstring('R'+str(base))+bytes((1,6,1))+qstring(str(base))+qstring('R')+b'\x01'
            +u32(size)+bytes(i%2 for i in range(size))+u32(size)+b'\0'*size
            +u32(2)+b''.join(u32(size)+b''.join(qstring(str(language)+':'+m) for m in messages) for language in range(2))
            +u32(2)+qstring('0\x01')+qstring('1\x01'))
    rows=[row('События станции',2550,25,[str(i) for i in range(25)])]
    for drive in (1,2,3):
        for start,size in ((1,32),(33,32),(65,16)):
            rows.append(row('ПЧ%d коды %d..%d'%(drive,start,start+size-1),
                3056+5*(drive-1)+(start-1)//16,size,[str(i) for i in range(start,start+size)]))
        rows.append(row('ПЧ%d неизвестный код'%drive,3070+drive,1,['unknown']))
    definitions=u32(13)+b''.join(rows);compacted=compact_fault_definitions(definitions)
    assert read_definitions(compacted,0)['count']==7
    assert word_bit_semantics(definitions)==word_bit_semantics(compacted)
    assert len(word_bit_semantics(compacted))==268
    cases.append('13 to 7 preserves 268 bits, flags and both message languages')
    for old,new in ((qstring('R3058'),qstring('R3059')),(qstring('ПЧ1 коды 33..64'),qstring('unexpected'))):
        try:compact_fault_definitions(definitions.replace(old,new))
        except ValueError:cases.append('refuse unreviewed compaction source')
        else:raise AssertionError('Unreviewed compaction accepted')
    for count in (1,2,7,10):
        original=fixture(count);fixed=with_sequential_alarm_ids(original)
        assert validate_alarm_identities(fixed)==list(range(count))
        assert with_sequential_alarm_ids(fixed)==fixed
        groups=read_definitions(original)['groups'];allowed={g['start']+4 for g in groups[1:]}
        changes={i for i,(a,b) in enumerate(zip(original,fixed)) if a!=b}
        assert len(original)==len(fixed) and changes==allowed
        cases.append('unique native group numbers and exact byte changes '+str(count))
        if count>1:
            try:validate_alarm_identities(original)
            except ValueError:cases.append('reject original duplicate group0 count'+str(count))
            else:raise AssertionError('Duplicate alarm group number accepted')
    old=compacted;fixed=with_sequential_alarm_ids(old,0)
    assert word_bit_semantics(old)==word_bit_semantics(fixed)
    cases.append('renumbering preserves all word/bit/message semantics')
    print('PASS',len(cases),'digital-alarm catalog regressions; native Open remains separate')
if __name__=='__main__':main()
