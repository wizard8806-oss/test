#!/usr/bin/env python3
"""Verify the diagnostic removal copy; no claim of native page stability."""
import argparse
import json
from pathlib import Path
from prepare_alarm_page_rebuild_r12 import prepare,qs
from repair_skm_section_index import read_directory


def validate(source,candidate):
    raw=Path(source).read_bytes();final=Path(candidate).read_bytes();expected,report=prepare(source)
    assert final==expected
    restored,cursor=bytearray(),0
    def shifted(p):return p+sum(e['targetBytes']-e['sourceBytes'] for e in report['edits'] if e['sourceOffset']<p)
    for e in report['edits']:
        p=e['sourceOffset'];at=shifted(p)
        restored.extend(final[cursor:at]);restored.extend(raw[p:p+e['sourceBytes']]);cursor=at+e['targetBytes']
    restored.extend(final[cursor:]);assert bytes(restored)==raw
    a,b=read_directory(raw),read_directory(final)
    for start,stop,newstart,newstop in zip(a['entries'][:-2],a['entries'][1:-1],b['entries'][:-2],b['entries'][1:-1]):
        assert raw[start:stop]==final[newstart:newstop],'Metadata section changed'
    for title in ('Задержка 1-го ведомого, с','Задержка 2-го ведомого, с','Быстрый останов ведомых ниже, Гц'):
        assert qs(title) in final
    assert qs('HAD8288') not in final
    return {'onlyWholeHADAndScene9CountRemoved':True,'allOtherBytesRestoredExactly':True,
            'allMetadataAndAlarmDefinitionsPreserved':True,'directoryValid':True,
            'replacementAlarmControlPresent':False,'nativeEditorPageOpenObserved':False,
            'nativeCompileObserved':False,'fullPanelReadyForDownload':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','candidate','report'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();result=validate(a.source,a.candidate)
    with a.report.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print('PASS diagnostic removal preservation. Native page test and new alarm control still required.')


if __name__=='__main__':main()
