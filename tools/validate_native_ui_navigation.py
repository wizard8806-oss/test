#!/usr/bin/env python3
"""Check static audit against broken bindings and ensure private code stays out."""
import json
import struct
import tempfile
from pathlib import Path

from _runtime import ROOT
from audit_native_ui_navigation import audit, pages
from build_native_operator_console_01 import Builder, catalog
from validate_process_display_01 import serialize_scripts
from validate_radio_install_01 import parse_scripts, hashes


def main():
    b=Builder(catalog(ROOT/'ui/native-console/catalog.json')).build()
    original=parse_scripts((ROOT/'source/scada-native-08/Scripts.ssc').read_bytes())
    prototype=next(r[2] for r in original if r[1]=='ProcessSpPlus_OnClick')
    rows=list(original)
    for event in b.events:
        rows.append((event['id'],event['name'],prototype,event['body'].splitlines()))
    results=[]
    with tempfile.TemporaryDirectory(prefix='ui-navigation-audit-') as tmp:
        project=Path(tmp);(project/'Scripts').mkdir()
        for case in ['normal','unbound','wrong_link','disabled_event','missing_page','private_code','duplicate_script','truncated']:
            data=bytearray(b.pages);current=list(rows)
            marker=struct.pack('<HI',4,len('UiMessages0'))+b'UiMessages0'
            body=data.index(marker)+len(marker)
            if case=='unbound':struct.pack_into('<q',data,body+75,-1)
            if case=='wrong_link':struct.pack_into('<q',data,body+75,3)
            if case=='disabled_event':
                id_=struct.unpack_from('<q',data,body+75)[0];i=next(i for i,r in enumerate(current) if r[0]==id_)
                row=current[i];meta=bytearray(row[2]);meta[6]=0;current[i]=(*row[:2],bytes(meta),row[3])
            if case=='missing_page':
                i=next(i for i,r in enumerate(current) if r[1]=='UiMainNav0_OnClick')
                row=current[i];current[i]=(*row[:3],["begin UiGoPage('PageUiAbsent',GetClientName); end."])
            if case=='private_code':
                row=current[0];current[0]=(*row[:3],['DO_NOT_EXPORT_SYNTHETIC_PRIVATE_BODY'])
            if case=='duplicate_script':current.append(current[-1])
            script=serialize_scripts(current)
            if case=='truncated':script=script[:-4]
            (project/'Pages.spg').write_bytes(data);(project/'Scripts/Scripts.ssc').write_bytes(script)
            before=hashes(project)
            if case in ['duplicate_script','truncated']:
                try:audit(project)
                except ValueError:pass
                else:raise AssertionError('Malformed native stream accepted')
            else:
                result=audit(project)
                assert 'DO_NOT_EXPORT_SYNTHETIC_PRIVATE_BODY' not in json.dumps(result)
                assert result['buttons']==44 and result['runtimeNavigationVerified'] is False
                if case in ['normal','private_code']:assert not result['findings'],result['findings']
                else:assert result['findings'],case
            assert before==hashes(project),case
            results.append(case)
    print('PASS navigation audit cases='+str(len(results))+' '+','.join(results)+'; source preserved, no code bodies exported')


if __name__=='__main__':main()
