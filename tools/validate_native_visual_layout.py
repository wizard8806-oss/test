#!/usr/bin/env python3
"""Readable layout, file-copy preservation and refusal checks; no live SCADA."""
import math
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import prepare_native_ui_event_probe as candidate
from audit_native_ui_navigation import scripts
from build_native_operator_console_01 import parse_pages, visual_layout_pages, repair_visual_page_style, FONT_REGULAR18
from validate_native_ui_event_probe import fixture


def vendor_semantics():
    """Independent native enum/loader/getter proof, not the writer's constants."""
    from verify_scada_native_loader_01 import IMAGE,DATA,BASE
    from verify_scada_variable_metadata_native import EDITOR_SHA
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
    from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_EDX,UC_X86_REG_ESP,UC_X86_REG_EBP
    binary=IMAGE.read_bytes();assert hashlib.sha256(binary).hexdigest()==EDITOR_SHA
    marker=b'\x0bTM_FontType';p=binary.index(marker)+len(marker)
    assert binary[p]==1;p+=1
    low,high=struct.unpack_from('<ii',binary,p);p+=12
    enum={}
    for ordinal in range(low,high+1):
        size=binary[p];p+=1;enum[ordinal]=binary[p:p+size].decode('ascii');p+=size
    assert enum[4]=='ftMedium15' and enum[11]=='ftAsOwner'
    assert enum[FONT_REGULAR18]=='ftRegular18' and FONT_REGULAR18==16
    u=Uc(UC_ARCH_X86,UC_MODE_32)
    u.mem_map(BASE,(len(DATA)+4095)//4096*4096);u.mem_write(BASE,DATA)
    u.mem_map(0x20000000,0x20000);u.mem_map(0x30000000,0x20000)
    page,parent,frame,stack=0x30000000,0x30001000,0x20010000,0x2001ff00
    u.mem_write(frame-12,struct.pack('<I',page));u.mem_write(frame-16,struct.pack('<I',0x30002000))
    u.mem_write(page+0x130,struct.pack('<I',parent))
    selected=[0]
    def hook(machine,ip,size,user):
        if ip==0x8b21b0:
            machine.mem_write(machine.reg_read(UC_X86_REG_EDX),bytes(selected))
            sp=machine.reg_read(UC_X86_REG_ESP)
            ret=struct.unpack('<I',machine.mem_read(sp,4))[0]
            machine.reg_write(UC_X86_REG_ESP,sp+4)
            from unicorn.x86_const import UC_X86_REG_EIP
            machine.reg_write(UC_X86_REG_EIP,ret)
        elif ip==0x20000001:machine.emu_stop()
        elif not (0x129bd75<=ip<0x129bd86 or 0x129c28c<=ip<0x129c2b0):
            raise AssertionError('Unreviewed native path '+hex(ip))
    u.hook_add(UC_HOOK_CODE,hook)
    for flag in (0,1,2):
        selected[0]=flag
        u.reg_write(UC_X86_REG_ESP,stack);u.reg_write(UC_X86_REG_EBP,frame)
        u.emu_start(0x129bd75,0x129bd86,count=100)
        assert u.mem_read(page+0x13c,1)[0]==flag
        for inherited_hidden in (0,1):
            u.mem_write(parent+0x148,bytes([inherited_hidden]))
            u.mem_write(stack,struct.pack('<I',0x20000001))
            u.reg_write(UC_X86_REG_ESP,stack);u.reg_write(UC_X86_REG_EAX,page)
            u.emu_start(0x129c28c,0x20000002,count=100)
            expected=not inherited_hidden if flag==0 else flag==1
            assert bool(u.reg_read(UC_X86_REG_EAX)&255)==expected
    return 'native RTTI26 font values + FShowPagesPanel loader/getter6 cases PASS'


def review_copy_cases(folder):
    source=folder/'codex_diag_11_layout_20261103t000000z';fixture(source)
    raw=(source/'Pages.spg').read_bytes();deployed=bytearray(raw)
    for page in parse_pages(raw):
        for obj in page['objects']:
            assert raw.count(obj['record'])==1
            offset=raw.index(obj['record'])+6+len(obj['name'].encode())+31
            deployed[offset]=11  # Reproduce the actual previous wrong ordinal.
    (source/'Pages.spg').write_bytes(deployed)
    (source/'CodexProbeManifest.json').write_text('{"privateOldManifest":true}')
    before=candidate.inventory(source)
    pins=[before['Pages.spg'],before['Scripts/Scripts.ssc']]
    for suffix,probe_id,native in [('font0001',None,False),('probe001','UINAV11-REVIEW0001',False),('native01',None,True)]:
        out=folder/('codex_diag_11_review_'+suffix)
        report=candidate.prepare_layout_review(source,out,*pins,probe_id=probe_id,native_navigation=native)
        assert candidate.inventory(source)==before
        assert report['geometryUnchanged']==(not native) and not report['runtimeNavigationVerified']
        assert report['replacedPreparationManifests']==['CodexProbeManifest.json']
        assert 'CodexProbeManifest.json' not in report['candidateSHA256']
        old=parse_pages((source/'Pages.spg').read_bytes());new=parse_pages((out/'Pages.spg').read_bytes())
        removed=0
        for a,b in zip(old,new):
            h=bytearray(b['header']);h[-5]=a['header'][-5];assert h==a['header']
            assert b['header'][-5]==(1 if native else a['header'][-5])
            lookup={o['name']:o for o in a['objects']}
            remaining={o['name'] for o in b['objects']}
            missing=set(lookup)-remaining;removed+=len(missing)
            if native:
                import re
                assert all(re.fullmatch(r'Ui(?:Main|Overview0|Alarms|Charts|Settings)Nav[0-4]|UiDiagNav[0-3]',n) for n in missing)
            else:assert not missing
            for z,y in enumerate(b['objects']):
                x=lookup[y['name']]
                restored=bytearray(y['record']);offset=6+len(y['name'].encode())+31
                assert restored[offset]==16;restored[offset]=x['body'][31]
                if native:
                    base=offset-31
                    x0,y0,w0,h0=struct.unpack_from('<4f',y['body'],8)
                    assert 0<=x0 and 64<=y0 and w0>0 and h0>0 and x0+w0<=1920 and y0+h0<=1080
                    restored[base+8:base+24]=x['body'][8:24]
                    restored[base+32:base+36]=x['body'][32:36]
                    layer=offset-31+54
                    assert struct.unpack_from('<I',restored,layer)[0]==z
                    restored[layer:layer+4]=x['body'][54:58]
                assert restored==x['record']
        assert removed==(29 if native else 0)
        assert repair_visual_page_style((out/'Pages.spg').read_bytes(),native)==(out/'Pages.spg').read_bytes()
        result_audit=candidate.audit(out)
        assert result_audit['buttons']==(15 if native else 44) and not result_audit['findings']
        if os.environ.get('CODEX_PAGE_LOADER')=='1':
            from verify_scada_native_loader_01 import read_pages
            assert len(read_pages(out/'Pages.spg')['objects'])==(102 if native else 131)
        source_scripts=(source/'Scripts/Scripts.ssc').read_bytes()
        expected_scripts=(candidate.patch_scripts(source_scripts,probe_id) if probe_id else
                          candidate.pressure_display_scripts(source_scripts) if native else source_scripts)
        assert (out/'Scripts/Scripts.ssc').read_bytes()==expected_scripts
        for n,digest in before.items():
            if n in ['Pages.spg','Scripts/Scripts.ssc','CodexProbeManifest.json'] or n.startswith('Scripts/Compiled/'):continue
            assert candidate.SHA((out/n).read_bytes())==digest,n
    for label,kwargs in [('bad_digest',{'expected_pages_sha':'0'*64}),('invalid_digest',{'expected_pages_sha':'x'}),
                          ('probe_and_native',{'probe_id':'UINAV11-REVIEW0002','native_navigation':True})]:
        out=folder/('codex_diag_11_review_'+label)
        args=dict(expected_pages_sha=pins[0],expected_scripts_sha=pins[1]);args.update(kwargs)
        try:candidate.prepare_layout_review(source,out,**args)
        except ValueError:pass
        else:raise AssertionError('Expected refusal '+label)
        assert not out.exists() and candidate.inventory(source)==before


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
                    assert after['body'][31]==FONT_REGULAR18==16
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
        review_copy_cases(folder)
    if os.environ.get('CODEX_PAGE_LOADER')=='1':print(vendor_semantics())
    print('PASS native layout:4 resolution scenarios/131 controls; original loader='+
          str(os.environ.get('CODEX_PAGE_LOADER')=='1')+'; private copy +5 refusal cases; source/archive/events/metadata preserved; no Windows GUI proof')


if __name__=='__main__':main()
