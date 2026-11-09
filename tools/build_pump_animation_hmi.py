#!/usr/bin/env python3
"""Create a new r7 HMI from exact r6; reuse complete native multi-state widgets.

No PLC change. Read-only input symbols, HMI-local animation words, and a small
original vector font. Native opening/compilation remains a separate check.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from repair_skm_section_index import read_directory

SOURCE_SHA = 'e8c1a0f6ca3684f301728b97f43d481a252cb89cd5b6296ccac8b4f76fce7ade'
FONT_SHA = '70c76c96778838c13b384cee32578b6ef967ef0774165b02bf5173f4dd862f22'
sha = lambda b: hashlib.sha256(b).hexdigest()


def qs(s):
    b = s.encode('utf-16-be')
    return struct.pack('>I', len(b)) + b


def edits_apply(raw, edits):
    ordered = sorted(edits, key=lambda e: e[0])
    out, cursor = bytearray(), 0
    for at, old, new, label in ordered:
        if at < cursor or raw[at:at+len(old)] != old:
            raise ValueError('Overlapping or differing source field: ' + label)
        out.extend(raw[cursor:at])
        out.extend(new)
        cursor = at+len(old)
    out.extend(raw[cursor:])
    return bytes(out)


def string_edits(raw, old, new, count, label):
    before, after = qs(old), qs(new)
    positions, at = [], 0
    while (at := raw.find(before, at)) >= 0:
        positions.append(at)
        at += len(before)
    if len(positions) != count:
        raise ValueError('QString mirrors differ: ' + label)
    return [(p, before, after, label) for p in positions]


def widget(template, name, address, ordinal, xywh, captions, colors, fills, font='Arial', size=10):
    """Clone the native five-state MD3022. Typed properties and cached Qt mirrors."""
    x, y, w, h = xywh
    e = []
    for at in (28, 189, 350):
        e.append((at, struct.pack('>2d', 136., 22.), struct.pack('>2d', w, h), 'size'))
    for at in (85, 246, 505):
        e.append((at, struct.pack('>2d', 16., 340.), struct.pack('>2d', x, y), 'position'))
    e += string_edits(template, 'MD3022', name, 1, 'identity')
    e += string_edits(template, 'R2304', 'LW%d' % address, 1, 'local monitor')
    e += string_edits(template, 'R2304#1#6#1#2304#R#1#',
                      'LW%d#0#1#100#%d#LW#1#' % (address, address), 2, 'local descriptor')
    # Cached text primitive for initial state, plus five-language/state tables.
    e.append((366, qs('Не выбран'), qs(captions[0]), 'cached initial caption'))
    e.append((388, qs('Arial'), qs(font), 'cached font family'))
    e.append((410, struct.pack('>i', 15), struct.pack('>i', size), 'cached font pixel size'))
    def qcolor(rgb):
        return b'\x01\xff\xff' + b''.join(struct.pack('>H', v*257) for v in rgb) + b'\0\0'
    def rgb(s):
        return [int(v) for v in s.split('+')]
    e.append((430, bytes.fromhex('01ffff18182c2c3b3b0000'), qcolor(rgb(colors[0])), 'cached foreground'))
    # These are complete native QString property tables, not a new widget type.
    bg = b''.join(qs('0') + qs('237+240+242')*3 for _ in range(5))
    bgnew = b''.join(qs('1' if fill else '0') + qs(fill or '237+240+242')*3 for fill in fills)
    e.append((1149, bg, bgnew, 'five fill states'))
    fg = b''.join(qs('24+44+59')+qs('0')+qs('15') for _ in range(5))
    fgnew = b''.join(qs(c)+qs('0')+qs('15') for c in colors)
    e.append((1575, fg, fgnew, 'five foreground states'))
    oldtext = b''.join((qs('12')+qs(s)+qs('Arial'))*5 for s in
                       ('Не выбран', 'Насос 1', 'Насос 2', 'Насос 3', 'Насос 4'))
    newtext = b''.join((qs(str(size))+qs(s)+qs(font))*5 for s in captions)
    e.append((1745, oldtext, newtext, 'five languages in five states'))
    trailer = qs('12')+struct.pack('>d', 12.)
    e.append((len(template)-len(trailer), trailer, qs(str(ordinal))+struct.pack('>d', ordinal), 'scene z ordinal'))
    return edits_apply(template, e)


VARIABLES = (
    ('PumpAnimTelemetry', 'Batch 16-Bit Unsigned Int', '26', '2500'),
    ('PumpAnimRoles', 'Batch 16-Bit Unsigned Int', '14', '2320'),
    ('PumpAnimManual', 'Batch 16-Bit Unsigned Int', '6', '2380'),
    ('PumpAnimLeader', '16-Bit Unsigned Int', '', '2304'),
)


def variable_entry(name, kind, size, address):
    return (qs(name)+qs(kind)+qs(size)+qs('R')+qs('R'+address)+b'\x01\x06\x01'
            +qs(address)+qs('R')+b'\x01\0\0\0\0')


def prepare(source, recipe, macro_path):
    raw = Path(source).read_bytes()
    if len(raw) != 1240334 or sha(raw) != SOURCE_SHA:
        raise ValueError('Use exact latest r6; preserve any newer native save')
    spec = json.loads(Path(recipe).read_text(encoding='utf-8-sig'))
    if spec['format'] != 'sktool-r6-pump-animation-r7' or spec['sourceSHA256'] != SOURCE_SHA:
        raise ValueError('Wrong r7 source recipe')
    directory = read_directory(raw)
    objects = {o['id']: o for o in spec['objects']}
    for o in objects.values():
        if sha(raw[o['start']:o['stop']]) != o['sha256']:
            raise ValueError('Reviewed source widget differs: '+o['id'])
    t = objects['MD3022']
    template = raw[t['start']:t['stop']]
    e, added = [], []
    for i in range(3):
        x = 232.+124*i
        o = objects['MD%d' % (10004+14*i)]
        status = widget(template, o['id'], 903+i, o['ordinal'], (x, 418., 88., 18.),
                        ['Нет данных', 'Остановлен', 'Работа', 'Подготовка', 'ПЧ не готов'],
                        ['24+44+59']*2+['255+255+255', '24+44+59', '255+255+255'],
                        ['224+215+197', '199+208+214', '46+153+90', '242+193+77', '200+74+74'])
        e.append((o['start'], raw[o['start']:o['stop']], status, 'pump%d status' % (i+1)))
        added.append(widget(template, 'MD7001%d' % i, 900+i, 81+2*i,
                            (259.+124*i, 108., 34., 38.),
                            ['\ue001', '\ue001', '\ue002', '\ue003', '\ue004'],
                            ['132+149+163']+['50+209+125']*4, [None]*5, 'Pump Station Rotor', 28))
        added.append(widget(template, 'MD7002%d' % i, 906+i, 82+2*i,
                            (x, 376., 88., 18.), ['', 'ВЕДУЩИЙ', '', '', ''],
                            ['255+212+89']*5, [None]*5))
    insert = spec['screen1InsertOffset']
    if raw[insert-14:insert] != qs('1')+struct.pack('>d', 1.):
        raise ValueError('Main scene final native widget boundary differs')
    e.append((insert, b'', b''.join(added), 'six new display-only widgets'))
    header = spec['sceneHeaders'][0]
    if header['count'] != 73:
        raise ValueError('Main scene source count differs')
    e.append((header['countOffset'], struct.pack('>I', 73), struct.pack('>I', 79), 'main scene item count'))
    # The existing alarm/boot/manual source stays intact outside two insertions.
    source_positions = (1206094, 1223999)
    old_sources = []
    for at in source_positions:
        n = struct.unpack_from('>I', raw, at)[0]
        old_sources.append(raw[at+4:at+4+n].decode('utf-16-be'))
    if old_sources[0] != old_sources[1] or 'PumpAnimation' in old_sources[0]:
        raise ValueError('Original macro source mirrors differ')
    original = old_sources[0]
    addition = Path(macro_path).read_text(encoding='utf-8').replace('\r\n', '\n').replace('\n', '\r\n')
    marker, call = 'void Macro_main(IN *p)', '    MarcoInit\r\n'
    if original.count(marker) != 1 or original.count(call) != 1:
        raise ValueError('Existing macro entry differs')
    updated = original.replace(marker, addition+'\r\n'+marker).replace(call, call+'    PumpAnimation(p);\r\n')
    for at in source_positions:
        e.append((at, qs(original), qs(updated), 'macro source mirror'))
    # Keep the original three variables first, including their original W BootAck.
    at = 1221442
    n = struct.unpack_from('>I', raw, at)[0]
    packed = raw[at+4:at+4+n].decode('utf-16-be')
    expected = ('AlarmWords#Batch 16-Bit Unsigned Int#10#R#R#2550#0:Fatek FB Series:6#1#'
                'MapVersion#16-Bit Unsigned Int##R#R#2554#0:Fatek FB Series:6#1#'
                'BootAck#16-Bit Unsigned Int##W#R#2553#0:Fatek FB Series:6#1#')
    if packed != expected:
        raise ValueError('Existing packed variable table differs')
    extra = ''.join('%s#%s#%s#R#R#%s#0:Fatek FB Series:6#1#' % v for v in VARIABLES)
    e.append((at, qs(packed), qs(packed+extra), 'packed read-only variable table'))
    e.append((1239364, struct.pack('>I', 3), struct.pack('>I', 7), 'native variable count'))
    original_entries = (variable_entry('AlarmWords', 'Batch 16-Bit Unsigned Int', '10', '2550')
                        + variable_entry('MapVersion', '16-Bit Unsigned Int', '', '2554')
                        + variable_entry('BootAck', '16-Bit Unsigned Int', '', '2553').replace(qs('R'), qs('W'), 1))
    if raw[1239368:1239726] != original_entries:
        raise ValueError('Native variable entry schema differs')
    e.append((1239726, b'', b''.join(variable_entry(*v) for v in VARIABLES), 'four read-only native input variables'))
    # General cumulative relocation: macro edits are inside metadata sections.
    def shifted(value):
        if any(at < value < at+len(old) for at, old, _, _ in e):
            raise ValueError('Section address points inside an edited field')
        return value+sum(len(new)-len(old) for at, old, new, _ in e if at < value)
    relocated = [shifted(v) for v in directory['entries']]
    for i, value in enumerate(directory['entries']):
        e.append((directory['offset']+4+8*i, struct.pack('>Q', value), struct.pack('>Q', relocated[i]), 'directory entry%d' % i))
    e.append((directory['locatorOffset'], struct.pack('>Q', directory['offset']),
              struct.pack('>Q', shifted(directory['offset'])), 'directory back-pointer'))
    final = edits_apply(raw, e)
    result_directory = read_directory(final)
    if result_directory['entries'] != relocated or Path(source).read_bytes() != raw:
        raise ValueError('Directory relocation or source preservation failed')
    for i in range(3):
        bar = objects['BG%d' % (10012+14*i)]
        if raw[bar['start']:bar['stop']] not in final:
            raise ValueError('Existing frequency bar was changed')
    return final, {'revision': 7, 'sourceSHA256': sha(raw), 'sourceBytes': len(raw),
                   'candidateSHA256': sha(final), 'candidateBytes': len(final),
                   'fontSHA256': FONT_SHA, 'newReadOnlyVariables': [v[0] for v in VARIABLES],
                   'newLocalWords': 'LW900..908', 'newDisplayWidgets': 6, 'updatedStatusWidgets': 3,
                   'existingFrequencyBarsPreserved': True, 'PLCChanged': False,
                   'nativeOpenObserved': False, 'nativeCompileObserved': False, 'equipmentActions': 0,
                   'edits': [{'sourceOffset': at, 'sourceBytes': len(old), 'targetBytes': len(new),
                              'sourceSHA256': sha(old), 'targetSHA256': sha(new), 'label': label}
                             for at, old, new, label in sorted(e, key=lambda v: v[0])]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'recipe', 'macro', 'out', 'report'):
        p.add_argument('--'+name, required=True, type=Path)
    a = p.parse_args()
    paths = [v.resolve() for v in (a.source, a.recipe, a.macro, a.out, a.report)]
    if len(set(paths)) != len(paths) or any(v.exists() or v.is_symlink() for v in (a.out, a.report)):
        raise ValueError('Distinct source and NEW output/report paths required')
    final, report = prepare(a.source, a.recipe, a.macro)
    with a.out.open('xb') as f:
        f.write(final)
    with a.report.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('Built new r7 HMI:', len(final), 'bytes;', report['candidateSHA256'])
    print('Install supplied rotor font before native opening/Compile/Offline Simulator. PLC unchanged.')


if __name__ == '__main__':
    main()
