#!/usr/bin/env python3
"""Check complete widget rollback and preservation; not native GUI acceptance."""
import argparse
import json
from pathlib import Path
import re
import struct
from restore_alarm_widget_r11 import prepare,START,STOP,ORIGINAL_WIDGET_SHA,sha,qs
from repair_skm_section_index import read_directory


def validate(source,candidate,reference=None):
    raw=Path(source).read_bytes();final=Path(candidate).read_bytes();expected,report=prepare(source)
    assert final==expected;widget=final[START:START+5817]
    assert sha(widget)==ORIGINAL_WIDGET_SHA
    if reference:
        original=Path(reference).read_bytes()
        assert sha(original)=='61ec747e1ff6629d931063e8df429255071fe1f8229cf1bd6b66e772658fe25d'
        assert widget==original[895030:900847],'Independent known-visible whole widget differs'
    restored,cursor=bytearray(),0
    def shifted(p):return p+sum(e['targetBytes']-e['sourceBytes'] for e in report['edits'] if e['sourceOffset']<p)
    for e in report['edits']:
        p=e['sourceOffset'];at=shifted(p)
        restored.extend(final[cursor:at]);restored.extend(raw[p:p+e['sourceBytes']]);cursor=at+e['targetBytes']
    restored.extend(final[cursor:]);assert bytes(restored)==raw,'Unlisted r10 bytes changed'
    a,b=read_directory(raw),read_directory(final)
    for start,stop,newstart,newstop in zip(a['entries'][:-2],a['entries'][1:-1],b['entries'][:-2],b['entries'][1:-1]):
        assert raw[start:stop]==final[newstart:newstop],'Metadata section changed'
    # All native135 property entries, including common visibility, station,
    # widths and five-language title/font tables, are exactly the original.
    at,count=4344,struct.unpack_from('>I',widget,4340)[0];assert count==135
    properties=[]
    for _ in range(count):
        n=struct.unpack_from('>I',widget,at)[0];assert n%2==0
        properties.append(widget[at+4:at+4+n].decode('utf-16-be'));at+=4+n
    assert properties[98]=='36' and 'HADStation' in properties
    assert all(qs(s) in final for s in ('Задержка 1-го ведомого, с','Задержка 2-го ведомого, с','Быстрый останов ведомых ниже, Гц'))
    marker='#include "MacroInit.h"'.encode('utf-16-be')
    def macros(data):
        result=[]
        for m in re.finditer(re.escape(marker),data):
            pos=m.start()-4;n=struct.unpack_from('>I',data,pos)[0];result.append(data[pos+4:pos+4+n])
        return result
    assert len(macros(raw))==2 and macros(raw)==macros(final)
    return {'wholeOriginalWidgetRestored':True,'comparedToIndependentR7':bool(reference),
            'all135OriginalNativePropertiesRestored':True,'allOtherR10BytesRestoredExactly':True,
            'cascadeEightRowsMacrosAndAlarmDefinitionsPreserved':True,'metadataDirectoryAndEOFValid':True,
            'originalLargeBoundsRestored':True,'nativeGridObserved':False,'nativeFittingCompleted':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','candidate','report'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--reference',type=Path);a=p.parse_args();result=validate(a.source,a.candidate,a.reference)
    with a.report.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS whole original widget and unrelated-byte preservation. Native grid and fitting still required.')


if __name__=='__main__':main()
