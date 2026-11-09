#!/usr/bin/env python3
"""Create a separate diagnostic HMI, retaining the user's native alarm page.

Replace only Screen13 contents, route main Diagnostics to it, and publish
read-only macro-input snapshots in unused LW920..930. Does not fix animation
or access hardware. The exact native source must be preserved separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from repair_skm_section_index import read_directory

NATIVE_SHA = '562b049266e9fb3ede17a870c928392f2ff008eed816463a075f9fd05ef54958'
FIXTURE_SHA = 'e5ae403199a9fc774a80e95905babc876a443b1e792c1e391b1a6a817c64606a'
GROUP = re.compile(bytes.fromhex('00010017') + b'\x00\x00\x00[\x01-\x09]' + bytes.fromhex('000100'))
IDENTITY = re.compile(r'(?:ND|NE|SB|BB|MD|Text|BG|FB|TS|DD|ST)[0-9]+')
sha = lambda b: hashlib.sha256(b).hexdigest()


def qs(s):
    b = s.encode('utf-16-be')
    return struct.pack('>I', len(b)) + b


def apply(raw, edits):
    out, cursor = bytearray(), 0
    for at, old, new, label in sorted(edits, key=lambda e: e[0]):
        if at < cursor or raw[at:at+len(old)] != old:
            raise ValueError('Overlapping/differing field: ' + label)
        out.extend(raw[cursor:at]); out.extend(new); cursor = at + len(old)
    out.extend(raw[cursor:])
    return bytes(out)


def strings(raw, old, new, count):
    found = [m.start() for m in re.finditer(re.escape(qs(old)), raw)]
    if len(found) != count:
        raise ValueError('QString mirrors differ: ' + old)
    return [(at, qs(old), qs(new), old) for at in found]


def qscan(raw, maximum=160):
    for m in re.finditer(rb'\x00\x00\x00[\x02-\xa0]', raw):
        n = int.from_bytes(m[0], 'big'); at = m.start()
        if n % 2 or n > maximum or at + 4 + n > len(raw):
            continue
        try:
            s = raw[at+4:at+4+n].decode('utf-16-be')
        except UnicodeError:
            continue
        yield at, s, at + 4 + n


def scene(raw, number, select_prefix=None):
    anchor = qs('Screen' + str(number)) + b'\xff' * 4
    if raw.count(anchor) != 1:
        raise ValueError('Scene header is not unique')
    count_at = raw.index(anchor) + len(anchor)
    stop = raw.index(qs('Screen' + str(number+1)) + b'\xff' * 4, count_at)
    starts = [m.start() for m in GROUP.finditer(raw, count_at+4, stop)]
    count = struct.unpack_from('>I', raw, count_at)[0]
    if len(starts) != count or starts[0] != count_at+4:
        raise ValueError('Scene inventory differs')
    records = {}
    for i, (a, z) in enumerate(zip(starts, starts[1:] + [stop])):
        b = raw[a:z]
        names = {s for _, s, _ in qscan(b) if IDENTITY.fullmatch(s)}
        if select_prefix and not any(s.startswith(select_prefix) for s in names):
            continue
        if len(names) != 1:
            raise ValueError('Native widget identity differs')
        trailers = [(p, e+8, int(s)) for p, s, e in qscan(b, 12)
                    if re.fullmatch(r'[0-9]{1,6}', s) and e+8 <= len(b)
                    and struct.unpack_from('>d', b, e)[0] == int(s)]
        if not trailers:
            raise ValueError('Native z-order trailer missing')
        p, e, ordinal = max(trailers, key=lambda t: t[1])
        if i+1 < len(starts) and e != len(b):
            raise ValueError('Widget boundary differs')
        name = names.pop()
        if name in records:
            raise ValueError('Duplicate widget identity')
        records[name] = {'start': a, 'stop': a+e, 'raw': b[:e], 'ordinal': ordinal,
                         'trailer': p, 'id': name}
    return count_at, records


def geometry(raw, x, y, width, height):
    edits = []
    for at, new, label in ((85, (x, y), 'position'), (28, (width, height), 'size')):
        old = raw[at:at+16]
        found = [m.start() for m in re.finditer(re.escape(old), raw)]
        if len(found) not in (2, 3):
            raise ValueError('Geometry mirrors differ: ' + label)
        edits += [(p, old, struct.pack('>2d', *new), label) for p in found]
    return apply(raw, edits)


def instrument(source):
    old = '        quality = PumpAnimTelemetry[10 + i];'
    new = old + '\n        LocalWord[920 + i] = frequency;\n        LocalWord[923 + i] = quality;'
    call = '    PumpAnimation(p);'
    addition = '''
    /* Diagnostic copy only: raw inputs of the SAME invocation, no PLC writes. */
    LocalWord[926] = (unsigned short)((LocalWord[926] + 1u) % 60000u);
    LocalWord[927] = MapVersion;
    LocalWord[928] = AlarmWords[0];
    LocalWord[929] = (LocalBit[60107] != 0);
    LocalWord[930] = 27119u;'''
    if source.count(old) != 1 or source.count(call) != 1:
        raise ValueError('Expected macro instrumentation anchors differ')
    return source.replace(old, new).replace(call, call + addition)


def prepare(source, macro, fixture=False):
    source, macro = Path(source), Path(macro)
    raw = source.read_bytes()
    expected = FIXTURE_SHA if fixture else NATIVE_SHA
    if sha(raw) != expected:
        raise ValueError('Different source: preserve it; do not weaken the source guard')
    if not fixture and qs('HAD1794244624') not in raw:
        raise ValueError('User-created native alarm control missing')
    directory = read_directory(raw)
    main_count, main = scene(raw, 1, 'SB')
    count_at, original = scene(raw, 13)
    if struct.unpack_from('>I', raw, main_count)[0] != 79 or len(original) != 80:
        raise ValueError('Current main/diagnostic scene differs')
    text, number = original['Text25002'], original['ND25004']
    expected_macro = macro.read_text(encoding='utf8').replace('\r\n', '\n').strip()
    marker = '#include "MacroInit.h"'.encode('utf-16-be')
    positions = [m.start()-4 for m in re.finditer(re.escape(marker), raw)]
    if len(positions) != 2:
        raise ValueError('Expected exactly two macro-source mirrors')
    edits = []
    for at in positions:
        n = struct.unpack_from('>I', raw, at)[0]
        c = raw[at+4:at+4+n].decode('utf-16-be')
        if c.replace('\r\n', '\n').strip() != expected_macro:
            raise ValueError('Current macro differs: preserve native edits for review')
        updated = instrument(expected_macro).replace('\n', '\r\n') + '\r\n'
        edits.append((at, qs(c), qs(updated), 'macro snapshot mirror'))
    for n in range(920, 931):
        if qs('LW'+str(n)) in raw or ('LocalWord['+str(n)).encode('utf-16-be') in raw:
            raise ValueError('Probe local storage already referenced')
    next_id = 88000
    added, fields = [], []

    def clone(template, prefix, xywh):
        nonlocal next_id
        name, ordinal = prefix+str(next_id), next_id
        next_id += 1
        if name.encode('utf-16-be') in raw:
            raise ValueError('Probe widget identity already exists')
        b = template['raw']; old_trailer = b[template['trailer']:]
        b = apply(b, [(template['trailer'], old_trailer,
                       qs(str(ordinal))+struct.pack('>d', ordinal), 'new z ordinal')])
        b = apply(b, strings(b, template['id'], name, 2 if prefix == 'ND' else 1))
        return geometry(b, *xywh)

    def label(caption, x, y, w=90, h=18):
        b = clone(text, 'Text', (x, y, w, h))
        added.append(apply(b, strings(b, 'Макрос r8', caption, 7)))

    def display(address, x, y, w=84, h=28):
        b = clone(number, 'ND', (x, y, w, h))
        kind = 'LW' if address.startswith('LW') else 'R'
        n = int(address[len(kind):])
        descriptor = ('LW%d#0#1#100#%d#LW#1#' if kind == 'LW'
                      else 'R%d#1#6#1#%d#R#1#') % (n, n)
        added.append(apply(b, strings(b, 'LW820', address, 1)
                           + strings(b, 'LW820#0#1#100#820#LW#1#', descriptor, 1)))
        fields.append({'address': address, 'x': x, 'y': y, 'width': w, 'height': h})

    label('АНИМАЦИЯ: ПЛК И МАКРОС', 16, 10, 768, 28)
    label('Частоты F: целое число × 0.1 Гц. Зонд должен показывать 27119.', 16, 44, 600)
    display('LW930', 688, 42)
    titles = ['F ПЛК', 'Q ПЛК', 'F макр.', 'Q макр.', 'Кадр', 'Статус', 'RX F*', 'Код*']
    for j, title in enumerate(titles):
        label(title, 80+86*j, 86, 78)
    for i in range(3):
        y = 116+66*i
        label('ПЧ '+str(i+1), 16, y, 62, 28)
        addresses = ['R'+str(2500+i), 'R'+str(2510+i), 'LW'+str(920+i),
                     'LW'+str(923+i), 'LW'+str(900+i), 'LW'+str(903+i), 'R'+str(2803+8*i),
                     'R'+str(2801+8*i)]
        for j, address in enumerate(addresses):
            x = 80+86*j
            display(address, x, y, 78)
            label(address, x, y+30, 78, 16)
    for row, entries in enumerate((
            [('Карта ПЛК', 'R2554'), ('Карта макр.', 'LW927'), ('Связь HMI', 'LW929')],
            [('Аварии ПЛК', 'R2550'), ('Аварии макр.', 'LW928'), ('Снимок', 'LW926')])):
        for col, (caption, address) in enumerate(entries):
            x, y = 16+250*col, 320+36*row
            label(caption, x, y, 108, 28)
            display(address, x+112, y, 86)
    label('Q: 0 нет данных, 1 стоп, 2 работа. Кадр: 0 стоп, 1..4 вращение.', 16, 396, 768)
    label('* RX F и код — сырые буферы ПЧ; их актуальность здесь не подтверждается.', 16, 416, 768)
    # Preserve all existing footer navigation in this temporary diagnostic page.
    footer = [v['raw'] for v in original.values()
              if struct.unpack_from('>2d', v['raw'], 85)[1] >= 436]
    if len(footer) != 2 or not all(qs('Screen'+str(n)) in b''.join(footer) for n in (1, 9)):
        raise ValueError('Diagnostic footer inventory differs')
    new_body = b''.join(added + footer)
    start = min(v['start'] for v in original.values())
    stop = max(v['stop'] for v in original.values())
    edits += [(start, raw[start:stop], new_body, 'temporary Screen13 diagnostics'),
              (count_at, struct.pack('>I', len(original)),
               struct.pack('>I', len(added)+len(footer)), 'diagnostic item count')]
    nav = [v for v in main.values() if v['id'].startswith('SB') and qs('Диагностика') in v['raw']]
    if len(nav) != 1:
        raise ValueError('Main Diagnostics navigation differs')
    v = nav[0]
    targets = {s for _, s, _ in qscan(v['raw']) if re.fullmatch('Screen[0-9]+', s)}
    if len(targets) != 1:
        raise ValueError('Main Diagnostics target differs')
    target = targets.pop()
    edits.append((v['start'], v['raw'], apply(v['raw'], strings(v['raw'], target, 'Screen13', 1)),
                  'temporary main Diagnostics route'))
    changes = sorted(edits, key=lambda e: e[0])
    def shifted(at):
        if any(p < at < p+len(old) for p, old, _, _ in changes):
            raise ValueError('Section address inside an edited record')
        return at + sum(len(new)-len(old) for p, old, new, _ in changes if p < at)
    entries = [shifted(v) for v in directory['entries']]
    for i, v in enumerate(directory['entries']):
        edits.append((directory['offset']+4+8*i, struct.pack('>Q', v),
                      struct.pack('>Q', entries[i]), 'section directory'))
    edits.append((directory['locatorOffset'], struct.pack('>Q', directory['offset']),
                  struct.pack('>Q', shifted(directory['offset'])), 'directory locator'))
    final = apply(raw, edits)
    if read_directory(final)['entries'] != entries or source.read_bytes() != raw:
        raise ValueError('Directory/source preservation failed')
    for n in range(2, 13):
        left, right = qs('Screen'+str(n))+b'\xff'*4, qs('Screen'+str(n+1))+b'\xff'*4
        if raw[raw.index(left):raw.index(right)] != final[final.index(left):final.index(right)]:
            raise ValueError('Existing screen changed: ' + str(n))
    # Invert every listed mutation: exact proof that no unlisted bytes changed.
    inverse, delta = [], 0
    for at, old, new, name in sorted(edits, key=lambda e: e[0]):
        inverse.append((at+delta, new, old, name)); delta += len(new)-len(old)
    if apply(final, inverse) != raw:
        raise ValueError('Unexpected unlisted modification')
    return final, {'purpose': 'temporary read-only animation probe; not an animation fix',
                   'fixtureOnly': fixture, 'sourceSHA256': sha(raw), 'sourceBytes': len(raw),
                   'candidateSHA256': sha(final), 'candidateBytes': len(final),
                   'userNativeAlarmControlPreserved': not fixture,
                   'screens2Through12PreservedExactly': True,
                   'allUnlistedBytesPreserved': True, 'newPLCWriteInputs': 0, 'PLCChanged': False,
                   'probeLocalWords': 'LW920..930', 'probeSignature': 27119,
                   'navigation': 'Main Diagnostics -> Screen13', 'diagnosticSceneItems': len(added)+len(footer),
                   'fields': fields, 'nativeCompileObserved': False, 'equipmentActions': 0,
                   'edits': [{'sourceOffset': p, 'sourceBytes': len(old), 'targetBytes': len(new),
                              'label': name} for p, old, new, name in sorted(edits, key=lambda e: e[0])]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'macro', 'out', 'report'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--fixture-source', action='store_true', help='research-only base without user HAD; never deploy')
    a = p.parse_args()
    if len({v.resolve() for v in (a.source, a.macro, a.out, a.report)}) != 4:
        raise ValueError('Distinct paths required')
    if any(v.exists() or v.is_symlink() for v in (a.out, a.report)):
        raise ValueError('NEW output/report required; preserve existing work')
    final, report = prepare(a.source, a.macro, a.fixture_source)
    with a.out.open('xb') as f:
        f.write(final)
    with a.report.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2); f.write('\n')
    print('Created diagnostic copy:', len(final), 'bytes;', sha(final))
    print('Native Compile/reopen required. No hardware access; animation not fixed.')


if __name__ == '__main__':
    main()
