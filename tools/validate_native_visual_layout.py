#!/usr/bin/env python3
"""Readable layout, file-copy preservation and refusal checks; no live SCADA."""
import math
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import prepare_native_ui_event_probe as candidate
from audit_native_ui_navigation import scripts
from build_native_operator_console_01 import parse_pages, visual_layout_pages
from validate_native_ui_event_probe import fixture


def main():
    root = Path(__file__).resolve().parents[1]
    entry = subprocess.run([sys.executable,'-I','-B',str(root/'tools/prepare_native_ui_event_probe.py'),
        '--project','unused','--out','unused','--mode','visual-layout'],capture_output=True,text=True)
    assert entry.returncode != 0 and 'both native project dimensions' in entry.stderr
    old_pins = candidate.PINS
    with tempfile.TemporaryDirectory(prefix='native-layout-checks-') as tmp:
        folder=Path(tmp); source=folder/'source';fixture(source)
        raw=(source/'Pages.spg').read_bytes(); old=parse_pages(raw)
        cases=[]
        for width,height,client_w,client_h in [(1920,1080,1366,768),(1366,768,1366,768),
                (1440,920,1366,768),(3840,2160,1920,1080)]:
            revised=visual_layout_pages(raw,width,height,client_w,client_h)
            new=parse_pages(revised);fit=min(client_w/width,client_h/height)
            count=0
            for a,b in zip(old,new):
                assert a['header']==b['header'] and len(a['objects'])==len(b['objects'])
                for before,after in zip(a['objects'],b['objects']):
                    count+=1
                    assert before['name']==after['name'] and before['caption']==after['caption']
                    # Exactly geometry + FontType/FontScale, not events, permissions,
                    # z-order, bindings, colours, identities, strings or tail flags.
                    restored=bytearray(after['body'])
                    for start,end in [(8,24),(31,36)]:restored[start:end]=before['body'][start:end]
                    assert restored==before['body']
                    assert after['record'][-9:]==before['record'][-9:]
                    x,y,w,h=struct.unpack_from('<4f',after['body'],8)
                    assert x>=0 and y>=0 and w>0 and h>0 and x+w<=width+.01 and y+h<=height+.01
                    is_backdrop=not before['caption'] and struct.unpack_from('<f',before['body'],12)[0]==0
                    if not is_backdrop:
                        assert y*fit>=64-.01 and (y+h)*fit<=(height*fit-24)+.01
                    else:assert y==0 and math.isclose(h,height)
                    if after['name']=='UiRow0Pressure':
                        assert 13.5 <= 18*struct.unpack_from('<f',after['body'],32)[0]*fit <= 14.5
                    if after['name']=='UiOverview0Heading':
                        assert 24 <= 18*struct.unpack_from('<f',after['body'],32)[0]*fit <= 25
            assert count==131
            path=folder/f'layout-{width}-{height}.spg';path.write_bytes(revised)
            if os.environ.get('CODEX_PAGE_LOADER')=='1':
                from verify_scada_native_loader_01 import read_pages
                assert len(read_pages(path)['objects'])==131
            cases.append((width,height,client_w,client_h))
        try:
            candidate.PINS={n:candidate.SHA((source/n).read_bytes()) for n in old_pins}
            before=candidate.inventory(source); out=folder/'codex_diag_11_layout_test0001'
            report=candidate.prepare_visual_layout(source,out,1920,1080)
            assert candidate.inventory(source)==before
            assert report['purpose']=='visual-layout-first-pass' and not report['visualAcceptancePassed']
            assert not report['dimensionsMeasuredByHelper'] and report['hardwareCommands']==0
            assert report['commandPrecisionUnchanged'] and report['pressureDecimals']==1
            for n,digest in before.items():
                if n in ['Pages.spg','Scripts/Scripts.ssc'] or n.startswith('Scripts/Compiled/'):continue
                assert candidate.SHA((out/n).read_bytes())==digest,n
            assert not (out/'Scripts/Compiled/program.exs').exists()
            old_scripts=scripts((source/'Scripts/Scripts.ssc').read_bytes())
            new_scripts=scripts((out/'Scripts/Scripts.ssc').read_bytes())
            assert len(old_scripts)==len(new_scripts)==48
            for id_,row in old_scripts.items():
                assert (row['name'],row['meta'])==(new_scripts[id_]['name'],new_scripts[id_]['meta'])
                if row['name'] not in ['StationDiagnostics','OperatorConsole']:assert row==new_scripts[id_]
            # Existing display tests independently check all ten format-only edits.
            snapshot=candidate.inventory(out)
            for kind in ['existing','wrong_name','edited_source','invalid_dimensions']:
                target=out if kind=='existing' else folder/('codex_diag_11_layout_'+kind)
                if kind=='wrong_name':target=folder/'codex_diag_11_display_test0001'
                if kind=='edited_source':(source/'Pages.spg').write_bytes(raw+b'changed')
                try:candidate.prepare_visual_layout(source,target,0 if kind=='invalid_dimensions' else 1920,1080)
                except ValueError:pass
                else:raise AssertionError('Expected refusal: '+kind)
                if kind=='existing':assert candidate.inventory(out)==snapshot
                else:assert not target.exists()
                (source/'Pages.spg').write_bytes(raw)
            assert candidate.inventory(source)==before
            assert not list(folder.glob('.event-probe-*'))
        finally:candidate.PINS=old_pins
    print('PASS native layout:4 resolution scenarios/131 controls; original loader='+
          str(os.environ.get('CODEX_PAGE_LOADER')=='1')+'; private copy +5 refusal cases; source/archive/events/metadata preserved; no Windows GUI proof')


if __name__=='__main__':main()
