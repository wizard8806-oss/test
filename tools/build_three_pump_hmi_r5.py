#!/usr/bin/env python3
"""Remove whole fourth-pump widget records from a NEW fixed-three-pump HMI.

Exact native-opened r4 source only. Update three scene item counts and all
absolute section addresses/EOF. Existing first-three controls are preserved.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct

from repair_skm_section_index import read_directory

SOURCE_SHA = '2375cf125dff7568292b501fddcab73fa9320e02023d2d0f6b0a5a719c0656ba'
REMOVED_IDS = {
    1: {'Text16008', 'MD3054', 'MD3056', 'MD10046', 'Text10044', 'MD10056', 'BG10054'},
    6: {'ND14016', 'Text14014', 'BB6130', 'Text6128', 'BB6126', 'Text6124',
        'MD6122', 'Text6120', 'MD6118', 'Text6116', 'Text6114'},
    7: {'BB9120', 'Text9118', 'BB9116', 'Text9114', 'BB9112', 'Text9110',
        'MD9108', 'ND9106', 'Text9104', 'NE9102', 'Text9100', 'Text9098',
        'MD9096', 'Text9094'}}
GROUP = re.compile(bytes.fromhex('00010017') + b'\x00\x00\x00[\x01-\x09]' + bytes.fromhex('000100'))
sha = lambda value: hashlib.sha256(value).hexdigest()


def qstring(text):
    value = text.encode('utf-16-be')
    return struct.pack('>I', len(value)) + value


def prepare(source, recipe_path):
    source = Path(source)
    raw = source.read_bytes()
    if len(raw) != 1322197 or sha(raw) != SOURCE_SHA:
        raise ValueError('Use exact delivered r4; preserve other native saves')
    directory = read_directory(raw)
    recipe = json.loads(Path(recipe_path).read_text(encoding='utf-8-sig'))
    if recipe.get('format') != 'sktool-r4-remove-fourth-pump-records' or recipe.get('sourceSHA256') != SOURCE_SHA:
        raise ValueError('Wrong removal recipe')
    removed = recipe['objectsToRemove']
    if len(removed) != 32 or {n: {o['id'] for o in removed if o['screen'] == n} for n in REMOVED_IDS} != REMOVED_IDS:
        raise ValueError('Fourth-pump inventory differs')
    ranges = sorted((o['start'], o['stop']) for o in removed)
    for a, b in zip(ranges, ranges[1:]):
        if a[1] > b[0]:
            raise ValueError('Overlapping removal records')
    delta = -sum(z-a for a, z in ranges)
    if delta != -67925:
        raise ValueError('Unexpected removed-record size')

    def shifted(at):
        if any(a < at < z for a, z in ranges):
            raise ValueError('Retained address points into a removed record')
        return at - sum(z-a for a, z in ranges if z <= at)

    edits = []
    for obj in removed:
        a, z, name = obj['start'], obj['stop'], obj['id']
        record = raw[a:z]
        if sha(record) != obj['recordSHA256'] or raw[a:a+4] != bytes.fromhex('00010017') or raw[z:z+4] != bytes.fromhex('00010017'):
            raise ValueError('Whole widget record boundary differs: '+name)
        anchor = obj['firstID']
        trailer = qstring(str(obj['ordinal'])) + struct.pack('>d', obj['ordinal'])
        if raw[anchor:anchor+len(qstring(name))] != qstring(name) or not record.endswith(trailer):
            raise ValueError('Widget identity/ordinal differs: '+name)
        edits.append((a, record, b'', 'remove entire '+name))

    headers = recipe['sceneHeaders']
    if [h['screen'] for h in headers] != list(range(1, 15)):
        raise ValueError('Expected original14 scenes')
    counts = Counter(o['screen'] for o in removed)
    for i, h in enumerate(headers):
        at = h['countOffset']
        anchor = qstring('Screen'+str(h['screen'])) + b'\xff'*4
        if raw[at-len(anchor):at] != anchor or struct.unpack_from('>I', raw, at)[0] != h['beforeCount']:
            raise ValueError('Scene header differs')
        if h['afterCount'] != h['beforeCount']-counts[h['screen']]:
            raise ValueError('Scene item count differs')
        if counts[h['screen']]:
            stop = headers[i+1]['countOffset']
            if len(list(GROUP.finditer(raw, at+4, stop))) != h['beforeCount']:
                raise ValueError('Source scene group count differs')
            edits.append((at, struct.pack('>I', h['beforeCount']), struct.pack('>I', h['afterCount']), 'scene%d item count' % h['screen']))
    # All metadata follows the removed UI records. Rewrite only the typed
    # directory/back-pointer words; do not search/replace arbitrary integers.
    for i, value in enumerate(directory['entries']):
        at = directory['offset']+4+8*i
        edits.append((at, struct.pack('>Q', value), struct.pack('>Q', shifted(value)), 'section directory %d' % i))
    at = directory['locatorOffset']
    edits.append((at, struct.pack('>Q', directory['offset']), struct.pack('>Q', shifted(directory['offset'])), 'directory back-pointer'))
    ordered = sorted(edits)
    for a, b in zip(ordered, ordered[1:]):
        if a[0]+len(a[1]) > b[0]:
            raise ValueError('Overlapping file edits')
    result, cursor = bytearray(), 0
    for at, old, new, _ in ordered:
        if raw[at:at+len(old)] != old:
            raise ValueError('Source field mismatch')
        result.extend(raw[cursor:at])
        result.extend(new)
        cursor = at+len(old)
    result.extend(raw[cursor:])
    final = bytes(result)
    current = read_directory(final)
    if len(final) != len(raw)+delta or current['entries'] != [shifted(v) for v in directory['entries']]:
        raise ValueError('Relocated directory differs')
    for i, h in enumerate(headers):
        if counts[h['screen']]:
            a, z = shifted(h['countOffset'])+4, shifted(headers[i+1]['countOffset'])
            if len(list(GROUP.finditer(final, a, z))) != h['afterCount']:
                raise ValueError('Result scene group count differs')
    for obj in removed:
        if obj['id'].encode('utf-16-be') in final:
            raise ValueError('Removed widget ID still exists')
    if source.read_bytes() != raw:
        raise ValueError('Source changed')
    return final, {'revision': 5, 'sourceSHA256': SOURCE_SHA, 'sourceBytes': len(raw),
                   'candidateSHA256': sha(final), 'candidateBytes': len(final),
                   'removedWidgets': [{'id': o['id'], 'screen': o['screen']} for o in removed],
                   'removedRecordBytes': -delta, 'sceneCounts': {str(h['screen']): h['afterCount'] for h in headers},
                   'directoryEntriesRelocated': 24, 'backPointerAndEOFCorrect': True,
                   'edits': [{'sourceOffset': at, 'sourceBytes': len(old), 'targetBytes': len(new),
                              'sourceSHA256': sha(old), 'targetSHA256': sha(new), 'label': label}
                             for at, old, new, label in ordered],
                   'primaryThreeControlsChanged': False, 'timerWidgetsChanged': False,
                   'PLCChanged': False, 'nativeOpenObserved': False, 'nativeSimulatorObserved': False,
                   'equipmentActions': 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'recipe', 'out', 'report'):
        p.add_argument('--'+name, required=True, type=Path)
    a = p.parse_args()
    if len({v.resolve() for v in (a.source, a.recipe, a.out, a.report)}) != 4 or any(v.exists() or v.is_symlink() for v in (a.out, a.report)):
        raise ValueError('New distinct output/report paths required')
    result, report = prepare(a.source, a.recipe)
    with a.out.open('xb') as f:
        f.write(result)
    with a.report.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('Built NEW HMI-r5:', len(result), 'bytes;', report['candidateSHA256'])
    print('32 fourth-slot records removed; scene counts/directory/EOF checked. Native validation remains.')


if __name__ == '__main__':
    main()
