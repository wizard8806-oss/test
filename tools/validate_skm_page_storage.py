#!/usr/bin/env python3
"""Regress omitted page arrays with synthetic, non-vendor metadata."""
import struct
from skm_page_storage import read_page_storage,page_storage_extensions
from repair_skm_section_index import read_directory
from repair_page_storage_r15f import extend_with_directory
from validate_skm_project_header import fixture as header_fixture


def fixture(count,flags=None,words=None):
    # A locator, twenty-three opaque spans and the standard24-entry index.
    prefix=header_fixture(count);locator=len(prefix)
    sections=[b'x'+bytes([i])*3 for i in range(23)]
    sections[1]=bytes((i%2 for i in range(count if flags is None else flags)))
    sections[21]=b'p'*48+b'\0'*(4*(count if words is None else words))
    sections[22]=b't'*16
    entries=[];cursor=locator+8
    for section in sections:entries.append(cursor);cursor+=len(section)
    entries.append(cursor+196)
    return prefix+struct.pack('>Q',cursor)+b''.join(sections)+struct.pack('>I24Q',24,*entries)


def main():
    cases=[]
    for count in (1,14,16):
        result=read_page_storage(fixture(count))
        assert result['pageCount']==result['flagEntries']==result['wordEntries']==count
        cases.append('consistent arrays '+str(count))
    for label,raw in [('both stale',fixture(16,14,14)),('flag stale',fixture(16,14,16)),
                      ('word stale',fixture(16,16,14)),('extra entries',fixture(14,16,16))]:
        try:read_page_storage(raw)
        except ValueError:cases.append('reject '+label)
        else:raise AssertionError('Accepted '+label)
    before=fixture(16,14,14);result=extend_with_directory(before,16)
    a,b=read_directory(before),read_directory(result)
    for i in range(22):
        original=before[a['entries'][i]:a['entries'][i+1]]
        final=result[b['entries'][i]:b['entries'][i+1]]
        assert final==original+(b'\0'*2 if i==1 else b'\0'*8 if i==21 else b'')
    assert result[b['entries'][22]:b['entries'][22]+16]==before[a['entries'][22]:a['entries'][22]+16]
    assert len(result)==len(before)+10 and result[:a['entries'][0]-8]==before[:a['entries'][0]-8]
    cases.append('two+eight bytes, all opaque spans and relocated pointers preserved')
    assert extend_with_directory(result,16)==result
    cases.append('consistent target is idempotent')
    for label,raw,target in [('unequal arrays',fixture(16,14,15),16),('shrink',fixture(16),14),
                              ('different header',fixture(15,14,14),16)]:
        try:page_storage_extensions(raw,target)
        except ValueError:cases.append('reject '+label)
        else:raise AssertionError('Accepted '+label)
    print('PASS',len(cases),'page-storage regressions; native Open remains separate')


if __name__=='__main__':main()
