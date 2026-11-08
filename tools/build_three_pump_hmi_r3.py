#!/usr/bin/env python3
"""Historic r3 UI assembly; its standalone output was rejected by SKTool.

Only reviewed Qt QString fields, geometry mirrors and one complete existing
ND record are reused. Its directory was not relocated. The prepare function
is retained only as an in-memory intermediate for build_three_pump_hmi_r4.py.
Do not issue the historic r3 as a usable project.
"""
import hashlib
import json
from pathlib import Path
import struct

from apply_hmi_layout_recipe import qstring

SOURCE_SHA = 'ee8c98b9024e765cbc924782442cfe64db252c19f9f86078bca5f50c99d86cc9'
sha = lambda value: hashlib.sha256(value).hexdigest()


def descriptor(number):
    return 'R%d#1#6#1#%d#R#1#' % (number, number)


def visibility(number, equals=None):
    # Established ND10048 nonzero / BG10054 equality property templates.
    return ['1', '0', '1', '0', descriptor(number),
            '3' if equals is None else '2', '0',
            '0' if equals is None else str(equals), '0', '100']


class Edits:
    def __init__(self, raw):
        self.raw, self.items = raw, []

    def add(self, offset, old, new, label):
        if self.raw[offset:offset + len(old)] != old:
            raise ValueError('Reviewed field differs: ' + label)
        if old != new:
            self.items.append((offset, old, new, label))

    def text(self, old, new, start, stop, count, label):
        before, after = qstring(old), qstring(new)
        at, found = start, []
        while (at := self.raw.find(before, at, stop)) >= 0:
            found.append(at)
            at += len(before)
        if len(found) != count:
            raise ValueError('QString mirrors differ: ' + label)
        for at in found:
            self.add(at, before, after, label)

    def binding(self, old, new, start, stop, plain, compound, label):
        if plain:
            self.text('R' + str(old), 'R' + str(new), start, stop, plain, label)
        before, after = descriptor(old).encode('utf-16-be'), descriptor(new).encode('utf-16-be')
        at, found = start, []
        while (at := self.raw.find(before, at, stop)) >= 0:
            standalone = self.raw[at-4:at] == struct.pack('>I', len(before))
            packed = self.raw[at-2:at] == b'\x00\x03' and self.raw[at+len(before):at+len(before)+2] == b'\x00\x03'
            if not (standalone or packed) or len(before) != len(after):
                raise ValueError('Device descriptor boundary differs: ' + label)
            found.append(at)
            at += len(before)
        if len(found) != compound:
            raise ValueError('Device descriptor mirrors differ: ' + label)
        for at in found:
            self.add(at, before, after, label)

    def apply(self):
        ordered = sorted(self.items)
        for a, b in zip(ordered, ordered[1:]):
            if a[0] + len(a[1]) > b[0]:
                raise ValueError('Overlapping reviewed edits')
        result, cursor = bytearray(), 0
        for at, old, new, _ in ordered:
            result.extend(self.raw[cursor:at])
            result.extend(new)
            cursor = at + len(old)
        result.extend(self.raw[cursor:])
        return bytes(result)


def prepare(source, recipe_path):
    source = Path(source)
    raw = source.read_bytes()
    recipe = json.loads(Path(recipe_path).read_text(encoding='utf-8-sig'))
    if sha(raw) != SOURCE_SHA or len(raw) != 1321783:
        raise ValueError('Use exact countdown-r2 HMI; preserve native saves with other hashes')
    if recipe.get('format') != 'sktool-countdown-r2-reviewed-widgets' or recipe.get('sourceSHA256') != SOURCE_SHA:
        raise ValueError('Wrong reviewed widget recipe')
    objects = {o['id']: o for o in recipe['objects']}
    if len(objects) != 113:
        raise ValueError('Widget inventory differs')
    plan = Edits(raw)

    def common(obj, values):
        old = b''.join(qstring(v) for v in obj['visibilityValues'])
        new = b''.join(qstring(v) for v in values)
        # QString lengths are serialized individually; the common property
        # tuple retains ten fields. No object/list counts or opaque flags change.
        plan.add(obj['visibilityOffset'], old, new, obj['id'] + ' visibility')

    def geometry(obj, x, y, width=None, height=None):
        for offsets, old, new, label in (
            (obj['positionOffsets'], (obj['x'], obj['y']), (x, y), ' position'),
            (obj['sizeOffsets'], (obj['width'], obj['height']),
             (obj['width'] if width is None else width, obj['height'] if height is None else height), ' size')):
            for at in offsets:
                plan.add(at, struct.pack('>2d', *old), struct.pack('>2d', *new), obj['id'] + label)

    for obj in objects.values():
        if raw[obj['start']:obj['start']+4] != bytes.fromhex('00010017'):
            raise ValueError('Widget record header differs')
        if raw[obj['firstID']:obj['firstID']+len(qstring(obj['id']))] != qstring(obj['id']):
            raise ValueError('Widget identity differs')
        if obj['action'] == 'hide-fourth':
            # PLC owns R2860=3 in this fixed-three-pump build. All parts of the
            # fourth column, including hit targets and duplicate captions, hide.
            common(obj, visibility(2860, 4))
        elif obj['action'] == 'center-three-columns':
            geometry(obj, obj['newX'], obj['y'])

    # Two independent rows; each caption and its number use the SAME positive
    # remaining word. The producer zeros it unless its real pause is counting.
    for name, word, text, old, y in (
        ('Text3052', 2525, 'Сухой ход, с', 'ПУСК, с', 324),
        ('Text10052', 2526, 'Питание, с', 'с ', 354)):
        obj = objects[name]
        common(obj, visibility(word))
        geometry(obj, 648, y, 98, 20)
        plan.text(old, text, obj['start'], obj['stop'], 7, name + ' cause caption')

    dry = objects['ND10048']
    common(dry, visibility(2525))
    geometry(dry, 748, 324, 40, 20)
    plan.binding(2528, 2525, dry['firstID'], dry['stop'], 1, 2, 'dry seconds value')

    # Replace the obsolete dash MD with a complete reviewed ND record. This
    # retains the scene's object count, a unique ID/ordinal and the established
    # read-only integer format; no Qt widget schema is invented.
    replacement = recipe['recordReplacement']
    a, z = replacement['templateStart'], replacement['templateEnd']
    if (a, z) != (45492, 47620):
        raise ValueError('ND template bounds differ')
    local = Edits(raw[a:z])
    for at, before, after, label in plan.items:
        if a <= at < z:
            local.add(at-a, before, after, label)
    clone = local.apply()
    edit_clone = Edits(clone)
    edit_clone.text('ND10048', 'ND10050', 0, len(clone), 2, 'power ND identity')
    edit_clone.binding(2525, 2526, 0, len(clone), 1, 3, 'power seconds and visibility')
    before = struct.pack('>2d', 748, 324)
    for at in (p-a for p in dry['positionOffsets']):
        edit_clone.add(at, before, struct.pack('>2d', 748, 354), 'power ND position')
    trailer = qstring('65') + struct.pack('>d', 65)
    edit_clone.add(len(clone)-len(trailer), trailer,
                   qstring('66') + struct.pack('>d', 66), 'power ND scene ordinal')
    clone = edit_clone.apply()
    da, dz = replacement['destinationStart'], replacement['destinationEnd']
    if (da, dz) != (43564, 45492) or raw[44363:44381] != qstring('MD10050'):
        raise ValueError('Dash record bounds differ')
    plan.add(da, raw[da:dz], clone, 'replace inactive dash with independent power ND')

    for name in ('Text16008', 'MD3054', 'MD3056', 'MD10046', 'Text10044', 'MD10056', 'BG10054'):
        common(objects[name], visibility(2860, 4))

    # These are applied delay SETTINGS, not countdowns. Restore their original
    # words so idle values are never mistaken for an active timer.
    for name, old, new in (('ND12004', 2538, 2520), ('ND12012', 2539, 2521)):
        obj = objects[name]
        plan.binding(old, new, obj['firstID'], obj['stop'], 1, 2, name + ' applied delay')

    final = plan.apply()
    if source.read_bytes() != raw:
        raise ValueError('Source changed')
    ordered = sorted(plan.items)
    report = {
        'revision': 3, 'installedPumps': 3, 'sourceSHA256': SOURCE_SHA,
        'candidateSHA256': sha(final), 'candidateBytes': len(final),
        'edits': [{'sourceOffset': at, 'sourceBytes': len(old), 'targetBytes': len(new),
                   'sourceFieldSHA256': sha(old), 'targetFieldSHA256': sha(new), 'label': label}
                  for at, old, new, label in ordered],
        'hiddenFourthWidgets': [o['id'] for o in objects.values() if o['action'] == 'hide-fourth'],
        'centeredWidgets': [o['id'] for o in objects.values() if o['action'] == 'center-three-columns'],
        'timers': {'dry': {'value': 'R2525', 'caption': 'Сухой ход, с', 'visibleWhen': 'R2525 > 0'},
                   'power': {'value': 'R2526', 'caption': 'Питание, с', 'visibleWhen': 'R2526 > 0'}},
        'appliedDelayWords': ['R2520', 'R2521'], 'editDelayWordsPreserved': ['R2540', 'R2541'],
        'PLCChanged': False, 'requiredPLC_SHA256': recipe['unchangedPLC'],
        'sceneObjectCountChanged': False, 'controlBindingsChanged': False,
        'nativeHMIValidationObserved': False, 'equipmentActions': 0}
    return final, report


def main():
    raise SystemExit('HMI-r3 was rejected by SKTool (stale section index). Use build_three_pump_hmi_r4.py; preserve source.')


if __name__ == '__main__':
    main()
