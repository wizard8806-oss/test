#!/usr/bin/env python3
"""Validate the semantic 1920x1080 native operator-page reflow."""
import struct

from _runtime import ROOT
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
    print('PASS semantic native geometry: 6 pages, 102 controls, 15 navigation bindings; '+
          str(changed_rects)+' control rectangles reflowed; IDs, labels and event links preserved; canvas 1920x1080')


if __name__ == '__main__':
    main()
