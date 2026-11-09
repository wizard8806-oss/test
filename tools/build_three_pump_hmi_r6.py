#!/usr/bin/env python3
"""Replace redundant current-section HMI buttons with flat static labels.

Exact r5 source. Reuse a complete existing Text widget; preserve all other
routes, control widgets and scene counts. Relocate the section directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from repair_skm_section_index import read_directory

SOURCE_SHA = '1d6449d8884fb9f44e3c6a2c71193d044788d8c2832e884c88e44c0707bdf3a3'
sha = lambda data: hashlib.sha256(data).hexdigest()


def qstring(text):
    value = text.encode('utf-16-be')
    return struct.pack('>I', len(value)) + value


def apply_edits(raw, edits):
    ordered = sorted(edits)
    for a, b in zip(ordered, ordered[1:]):
        if a[0]+len(a[1]) > b[0]:
            raise ValueError('Overlapping typed changes')
    result, cursor = bytearray(), 0
    for at, old, new, _ in ordered:
        if raw[at:at+len(old)] != old:
            raise ValueError('Reviewed field differs')
        result.extend(raw[cursor:at])
        result.extend(new)
        cursor = at+len(old)
    result.extend(raw[cursor:])
    return bytes(result)


def replace_qstrings(raw, old, new, count, label):
    before, after = qstring(old), qstring(new)
    at, found = 0, []
    while (at := raw.find(before, at)) >= 0:
        found.append((at, before, after, label))
        at += len(before)
    if len(found) != count:
        raise ValueError('QString mirrors differ: '+label)
    return found


def prepare(source, recipe_path):
    source = Path(source)
    raw = source.read_bytes()
    if len(raw) != 1254272 or sha(raw) != SOURCE_SHA:
        raise ValueError('Use exact latest r5; preserve any newer native save')
    directory = read_directory(raw)
    recipe = json.loads(Path(recipe_path).read_text(encoding='utf-8-sig'))
    if recipe.get('format') != 'sktool-r5-static-current-navigation' or recipe.get('sourceSHA256') != SOURCE_SHA:
        raise ValueError('Wrong navigation recipe')
    if len(recipe['originalNavigation']) != 108 or len(recipe['replacements']) != 14:
        raise ValueError('Navigation inventory differs')
    template = recipe['template']
    block = raw[template['start']:template['stop']]
    if sha(block) != template['recordSHA256'] or block[:8] != bytes.fromhex('0001001700000002'):
        raise ValueError('Static Text template differs')
    at = template['idOffset']
    if block[at:at+len(qstring(template['id']))] != qstring(template['id']):
        raise ValueError('Static Text identity differs')
    edits, replacement_records = [], []
    for obj in recipe['replacements']:
        start, stop = obj['start'], obj['stop']
        old_record = raw[start:stop]
        if sha(old_record) != obj['recordSHA256'] or qstring(obj['oldID']) not in old_record or qstring(obj['target']) not in old_record:
            raise ValueError('Reviewed screen-button record differs')
        if obj['newID'].encode('utf-16-be') in raw:
            raise ValueError('Static label ID already exists')
        local = []
        old, new = template['geometry'], obj['geometry']
        for slots, keys, label in (('positionOffsets', ('x', 'y'), 'position'), ('sizeOffsets', ('width', 'height'), 'size')):
            before = struct.pack('>2d', *(old[k] for k in keys))
            after = struct.pack('>2d', *(new[k] for k in keys))
            for offset in template[slots]:
                local.append((offset, before, after, label))
        local += replace_qstrings(block, template['id'], obj['newID'], 1, 'new Text ID')
        local += replace_qstrings(block, template['caption'], obj['caption'], 7, 'current section caption')
        local += replace_qstrings(block, template['oldColor'], template['newColor'], 1, 'selected blue text color')
        local.append((template['cachedColorOffset'], bytes.fromhex(template['cachedColorBefore']),
                      bytes.fromhex(template['cachedColorAfter']), 'cached QColor ARGB16'))
        before = qstring(str(template['ordinal'])) + struct.pack('>d', template['ordinal'])
        after = qstring(str(obj['ordinal'])) + struct.pack('>d', obj['ordinal'])
        local.append((len(block)-len(before), before, after, 'original scene ordinal'))
        new_record = apply_edits(block, local)
        if b'\x00S\x00c\x00r\x00e\x00e\x00n' in new_record or qstring(obj['oldID']) in new_record:
            raise ValueError('Static label still contains a screen transition')
        edits.append((start, old_record, new_record, obj['oldID']+' -> '+obj['newID']))
        replacement_records.append({'screen': obj['screen'], 'oldID': obj['oldID'], 'newID': obj['newID'],
                                    'caption': obj['caption'], 'oldTarget': obj['target'],
                                    'sourceBytes': len(old_record), 'targetBytes': len(new_record)})
    delta = sum(len(new)-len(old) for _, old, new, _ in edits)
    if any(at+len(old) > directory['locatorOffset'] for at, old, _, _ in edits):
        raise ValueError('UI edit extends into metadata')
    for i, value in enumerate(directory['entries']):
        at = directory['offset']+4+8*i
        edits.append((at, struct.pack('>Q', value), struct.pack('>Q', value+delta), 'section directory %d' % i))
    edits.append((directory['locatorOffset'], struct.pack('>Q', directory['offset']),
                  struct.pack('>Q', directory['offset']+delta), 'directory back-pointer'))
    final = apply_edits(raw, edits)
    current = read_directory(final)
    if current['entries'] != [v+delta for v in directory['entries']]:
        raise ValueError('Section relocation differs')
    if source.read_bytes() != raw:
        raise ValueError('Source changed')
    return final, {'revision': 6, 'sourceSHA256': SOURCE_SHA, 'sourceBytes': len(raw),
                   'candidateSHA256': sha(final), 'candidateBytes': len(final),
                   'flatStaticCurrentLabels': replacement_records, 'remainingScreenButtons': 94,
                   'originalSceneCountsPreserved': True, 'directoryRelocationDelta': delta,
                   'directoryAndEOFCorrect': True, 'controlBindingsChanged': False, 'PLCChanged': False,
                   'edits': [{'sourceOffset': at, 'sourceBytes': len(old), 'targetBytes': len(new),
                              'sourceSHA256': sha(old), 'targetSHA256': sha(new), 'label': label}
                             for at, old, new, label in sorted(edits)],
                   'nativeOpenObserved': False, 'nativeLayoutObserved': False, 'equipmentActions': 0}


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
    print('Built NEW HMI-r6:', len(result), 'bytes;', report['candidateSHA256'])
    print('14 current buttons replaced by static blue labels; other routes retained. Native checks remain.')


if __name__ == '__main__':
    main()
