#!/usr/bin/env python3
"""Check static active tabs, unchanged routes and SKM structure for HMI-r6."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from build_three_pump_hmi_r6 import prepare, qstring
from repair_skm_section_index import read_directory


def validate(source, candidate, recipe_path):
    raw, final = Path(source).read_bytes(), Path(candidate).read_bytes()
    recipe = json.loads(Path(recipe_path).read_text())
    expected, report = prepare(source, recipe_path)
    assert final == expected
    edits = report['edits']
    def shifted(at):
        return at+sum(e['targetBytes']-e['sourceBytes'] for e in edits if e['sourceOffset'] < at)
    restored, cursor = bytearray(), 0
    for e in edits:
        at = shifted(e['sourceOffset'])
        restored.extend(final[cursor:at])
        end = at+e['targetBytes']
        assert hashlib.sha256(final[at:end]).hexdigest() == e['targetSHA256']
        p = e['sourceOffset']
        restored.extend(raw[p:p+e['sourceBytes']])
        cursor = end
    restored.extend(final[cursor:])
    assert bytes(restored) == raw
    replaced = {o['oldID']: o for o in recipe['replacements']}
    unchanged = []
    for obj in recipe['originalNavigation']:
        a, z = obj['start'], obj['stop']
        record = final[shifted(a):shifted(z)]
        if obj['id'] in replaced:
            r = replaced[obj['id']]
            assert record[:8] == bytes.fromhex('0001001700000002')
            assert record.count(qstring(r['newID'])) == 1
            assert record.count(qstring(r['caption'])) == 7
            assert qstring('0+96+160') in record
            assert bytes.fromhex('01ffff00006060a0a00000') in record
            assert 'Screen'.encode('utf-16-be') not in record
            assert obj['id'].encode('utf-16-be') not in final
            g = r['geometry']
            assert struct.unpack_from('>2d', record, 28) == (g['width'], g['height'])
            assert struct.unpack_from('>2d', record, 85) == (g['x'], g['y'])
            assert record.endswith(qstring(str(r['ordinal']))+struct.pack('>d', r['ordinal']))
        else:
            assert record == raw[a:z]
            assert qstring(obj['target']) in record
            unchanged.append(obj)
    assert len(unchanged) == 94 and len(replaced) == 14
    assert all(int(o['target'][6:]) != o['screen'] for o in unchanged)
    # Removing self links and redundant Graph->24h links must not change any
    # reachable screen, including explicit return buttons from nested windows.
    def reachable(rows, start):
        visited, todo = {start}, [start]
        while todo:
            current = todo.pop()
            for o in rows:
                target = int(o['target'][6:])
                if o['screen'] == current and target not in visited:
                    visited.add(target)
                    todo.append(target)
        return visited
    for n in range(1, 15):
        assert reachable(recipe['originalNavigation'], n) == reachable(unchanged, n)
    assert any(o['screen'] == 5 and o['target'] == 'Screen3' for o in unchanged)
    assert any(o['screen'] == 13 and o['target'] == 'Screen9' for o in unchanged)
    for n in (8, 10, 11, 12):
        assert len([o for o in unchanged if o['screen'] == n and o['caption'] in ('1 ч', '6 ч', '12 ч', '24 ч')]) == 3
    # Exact preservation outside14 navigation records includes all command,
    # settings/apply widgets, timer fields, images and data bindings.
    a, b = read_directory(raw), read_directory(final)
    for i in range(22):
        assert raw[a['entries'][i]:a['entries'][i+1]] == final[b['entries'][i]:b['entries'][i+1]]
    for h in recipe['sceneHeaders']:
        p = h['countOffset']
        assert struct.unpack_from('>I', final, shifted(p))[0] == h['count']
    group = re.compile(bytes.fromhex('00010017')+b'\x00\x00\x00[\x01-\x09]'+bytes.fromhex('000100'))
    for i, h in enumerate(recipe['sceneHeaders']):
        p = h['countOffset']+4
        z = recipe['sceneHeaders'][i+1]['countOffset'] if i+1 < 14 else a['locatorOffset']
        assert len(list(group.finditer(raw, p, z))) == len(list(group.finditer(final, shifted(p), shifted(z))))
    assert source.read_bytes() == raw
    return {'replacedCurrentButtons': 14, 'unchangedNavigationButtons': 94,
            'remainingSelfTransitions': 0, 'all14ScreenReachabilityPreserved': True,
            'graphRangeSelectionsPreserved': True, 'explicitNestedReturnsPreserved': True,
            'sceneCountsAndGroupCountsPreserved': True, 'metadataSectionsPreserved': 22,
            'allNonNavigationBytesPreserved': True, 'directoryAndEOFCorrect': True,
            'nativeR6OpenObserved': False, 'nativeR6LayoutObserved': False, 'PLCChanged': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'candidate', 'recipe', 'report'):
        p.add_argument('--'+name, required=True, type=Path)
    a = p.parse_args()
    if a.report.exists() or a.report.is_symlink() or a.report.resolve() in {v.resolve() for v in (a.source, a.candidate, a.recipe)}:
        raise ValueError('New distinct report required')
    report = validate(a.source, a.candidate, a.recipe)
    with a.report.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('PASS: 14 static tabs; 94 unchanged links; no self-transition; 14-scene reachability and directory preserved.')
    print('Native SKTool opening/layout/click behavior still require observation.')


if __name__ == '__main__':
    main()
