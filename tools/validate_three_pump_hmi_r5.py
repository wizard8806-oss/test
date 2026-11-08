#!/usr/bin/env python3
"""Check whole-record removal and reproduce the native-observed r4 overlap."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_three_pump_hmi_r5 import prepare, REMOVED_IDS, qstring, GROUP
from repair_skm_section_index import read_directory


def validate(source, candidate, recipe_path):
    raw, final = Path(source).read_bytes(), Path(candidate).read_bytes()
    recipe = json.loads(Path(recipe_path).read_text())
    expected, report = prepare(source, recipe_path)
    assert expected == final
    edits = report['edits']

    def shifted(at):
        return at + sum(e['targetBytes']-e['sourceBytes'] for e in edits if e['sourceOffset']+e['sourceBytes'] <= at)

    # Restore deleted records and typed count/directory words. Every remaining
    # byte must be unchanged, including binding caches and permission controls.
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
    for ids in REMOVED_IDS.values():
        for name in ids:
            assert name.encode('utf-16-be') not in final
    headers = recipe['sceneHeaders']
    bodies = {}
    for i, h in enumerate(headers):
        at = shifted(h['countOffset'])
        assert struct.unpack_from('>I', final, at)[0] == h['afterCount']
        if h['screen'] in REMOVED_IDS:
            end = shifted(headers[i+1]['countOffset'])
            body = final[at+4:end]
            assert len(list(GROUP.finditer(body))) == h['afterCount']
            bodies[h['screen']] = body
    assert len(recipe['retainedControls']) == 75
    for obj in recipe['retainedControls']:
        assert final[shifted(obj['start']):shifted(obj['stop'])] == raw[obj['start']:obj['stop']]
        for at in (obj['start']+28, obj['start']+85):
            assert final[shifted(at):shifted(at)+16] == raw[at:at+16]
    for word in recipe['retainedManualWrites']:
        assert qstring(word) in bodies[7], word
    for word in recipe['retainedPumpsWrites']:
        assert qstring(word) in bodies[6], word
    for word in ('R2183', 'R2383', 'R2397', 'R2423', 'M383', 'M387', 'M1663'):
        assert qstring(word) not in bodies[7], word
    for word in ('R2173', 'R723', 'M1493', 'M1497', 'R2206'):
        assert qstring(word) not in bodies[6], word

    objects = {o['id']: o for o in recipe['retainedControls']}
    def rect(obj):
        return obj['x'], obj['y'], obj['x']+obj['width'], obj['y']+obj['height']
    def intersects(a, b):
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
    collision_cases = []
    for third, fourth in (('BB9084', 'BB9112'), ('BB9088', 'BB9116'),
                           ('BB9092', 'BB9120'), ('NE9074', 'NE9102')):
        t = objects[third]
        f = next(o for o in recipe['objectsToRemove'] if o['id'] == fourth)
        x, y = struct.unpack_from('>2d', raw, f['start']+85)
        w, h = struct.unpack_from('>2d', raw, f['start']+28)
        assert intersects(rect(t), (x, y, x+w, y+h))
        assert qstring(fourth) not in bodies[7]
        collision_cases.append(third+' vs '+fourth)
    for row in (('BB9028', 'BB9056', 'BB9084'), ('BB9032', 'BB9060', 'BB9088'),
                ('BB9036', 'BB9064', 'BB9092'), ('NE9018', 'NE9046', 'NE9074')):
        rects = [rect(objects[name]) for name in row]
        assert all(not intersects(a, b) for i, a in enumerate(rects) for b in rects[i+1:])

    a, b = read_directory(raw), read_directory(final)
    assert b['entries'] == [v-67925 for v in a['entries']]
    for i in range(22):
        assert raw[a['entries'][i]:a['entries'][i+1]] == final[b['entries'][i]:b['entries'][i+1]]
    # New independent timer ND/labels are outside deleted records and preserved
    # by full-byte reconstruction; removal does not change their semantics.
    for name in ('ND10048', 'ND10050', 'Text3052', 'Text10052'):
        assert qstring(name) in bodies[1]
    assert qstring('R2525') in bodies[1] and qstring('R2526') in bodies[1]
    assert source.read_bytes() == raw
    return {'removedRecords': 32, 'manualFourthRecordsRemoved': 14, 'pumpsFourthRecordsRemoved': 11,
            'retiredMainRecordsRemoved': 7, 'primaryThreeRecordsPreserved': 75,
            'r4CollisionCasesReproducedAndRemoved': collision_cases,
            'threeControlColumnsDoNotIntersect': True, 'all14SceneCountsChecked': True,
            'changedSceneGroupCountsChecked': [73, 55, 53], 'allOtherBytesPreserved': True,
            'metadataSectionsPreserved': 22, 'directoryAndEOFCorrect': True,
            'nativeR5OpenObserved': False, 'nativeR5LayoutObserved': False, 'PLCChanged': False}


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
    print('PASS: 32 records removed; 75 primary widgets unchanged; 4 native-observed overlap cases eliminated.')
    print('Scene counts, directory/EOF and metadata checked; native r5 opening/layout remains separate.')


if __name__ == '__main__':
    main()
