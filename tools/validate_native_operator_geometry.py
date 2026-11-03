#!/usr/bin/env python3
"""Validate the semantic 1920x1080 native operator-page reflow."""
import struct
import tempfile
from pathlib import Path

from _runtime import ROOT
import prepare_native_ui_event_probe as candidate
from validate_native_ui_event_probe import fixture
from build_native_operator_console_01 import (
    Builder, catalog, native_navigation_grid_pages, parse_pages,
    repair_visual_page_style,
)


def main():
    built = Builder(catalog(ROOT/'ui/native-console/catalog.json')).build()
    original = parse_pages(built.pages)
    reviewed = native_navigation_grid_pages(
        repair_visual_page_style(built.pages, native_navigation=True), 1920, 1080)
    result = parse_pages(reviewed)
    assert len(result) == 6
    assert sum(len(p['objects']) for p in result) == 102
    before = {p['name']:{o['name']:o for o in p['objects']} for p in original}
    after = {p['name']:{o['name']:o for o in p['objects']} for p in result}
    assert set(before) == set(after)
    changed_rects = 0
    for page in result:
        assert page['header'][-5] == 1  # native page tabs explicitly visible
        old_page = before[page['name']]
        assert set(old_page) - {n for n in old_page if __import__('re').fullmatch(
            r'Ui(?:Main|Overview0|Alarms|Charts|Settings)Nav[0-4]|UiDiagNav[0-3]', n)} == set(after[page['name']])
        for obj in page['objects']:
            old = old_page[obj['name']]
            a, b = old['body'], obj['body']
            assert a[107:111] == b[107:111], 'UID changed: '+obj['name']
            assert a[75:83] == b[75:83], 'event link changed: '+obj['name']
            assert old['caption'] == obj['caption'], 'caption changed: '+obj['name']
            if a[8:24] != b[8:24]: changed_rects += 1
            x,y,w,h=struct.unpack_from('<4f',b,8)
            assert 0 <= x and 0 <= y and w > 0 and h > 0 and x+w <= 1920 and y+h <= 1080
            if obj['name'].endswith('Background'):
                assert (x,y,w,h) == (0.0,64.0,1920.0,1016.0)
    assert changed_rects > 0
    # The overview must not depend on page serialization order.
    swapped=list(reversed(parse_pages(repair_visual_page_style(built.pages,True))))
    reordered=built.pages[:12]+b''.join(p['header']+struct.pack('<I',len(p['objects']))+
        b''.join(o['record'] for o in p['objects']) for p in swapped)
    reflowed=native_navigation_grid_pages(reordered)
    assert {p['name']:p['objects'] for p in parse_pages(reflowed)}=={
        p['name']:p['objects'] for p in result}
    with tempfile.TemporaryDirectory(prefix='tab-clearance-') as tmp:
        area=Path(tmp);source=area/'codex_diag_11_review_grid_20261103t1030z';fixture(source)
        defective=bytearray(reviewed)
        for page in result:
            if page['name'] in ('PageProcess','PageUiOverview'):continue
            obj=next(o for o in page['objects'] if o['name'].endswith('Background'))
            position=reviewed.index(obj['record'])+6+len(obj['name'].encode())+8
            struct.pack_into('<4f',defective,position,0,0,1920,1080)
        (source/'Pages.spg').write_bytes(defective)
        before=candidate.inventory(source);out=area/'codex_diag_11_review_tabs_test0001'
        report=candidate.prepare_tab_clearance(source,out,before['Pages.spg'],before['Scripts/Scripts.ssc'])
        assert (out/'Pages.spg').read_bytes()==reviewed
        assert report['changedScripts']==[] and candidate.inventory(source)==before
        for name,digest in before.items():
            if name=='Pages.spg' or name.startswith('Scripts/Compiled/'):continue
            assert candidate.SHA((out/name).read_bytes())==digest
        from build_native_operator_console_01 import native_tab_clearance_pages
        assert native_tab_clearance_pages(reviewed)==reviewed
        invalid=bytearray(defective)
        first=next(o for o in result[0]['objects'] if o['name'].endswith('Background'))
        position=reviewed.index(first['record'])+6+len(first['name'].encode())+8
        struct.pack_into('<4f',invalid,position,0,12,1920,1068)
        try:native_tab_clearance_pages(bytes(invalid))
        except ValueError:pass
        else:raise AssertionError('Unexpected background accepted')
    print('PASS semantic native geometry: 6 pages, 102 controls, 15 navigation bindings; '+
          str(changed_rects)+' control rectangles reflowed; IDs, labels and event links preserved; canvas 1920x1080; page-order independent; four-background copy preserves scripts/resources')


if __name__ == '__main__':
    main()
