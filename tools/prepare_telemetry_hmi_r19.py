#!/usr/bin/env python3
"""Patch only the existing animation macro; preserve RKF/native HMI settings.

Current input reuses the existing Batch16 R2500..2512 slots4..6 and marker9.
Numeric widgets still need native SKTool setup, as described by the delivery
task. A stage file is NOT a completed/deployable HMI release.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from build_native_merge_r16 import macro_mirrors
from build_animation_probe_hmi import apply
from repair_skm_section_index import read_directory
from skm_alarm_catalog import qs, validate_alarm_catalog, validate_alarm_identities
from skm_project_header import read_project_header

SOURCE_SHA = 'f09dd8243b032e964d325adef7337dfc10ba26ff762b81449b01fb96b0d353d5'
PLC_MARKER = 27133
HMI_MARKER = 27134
CAPTION = 'Частоты F: целое число × 0.1 Гц. Зонд должен показывать 27124.'
sha = lambda data: hashlib.sha256(data).hexdigest()


def replace_records(raw, changes):
    """Relocate the directory, including the native C mirror after its locator."""
    directory = read_directory(raw)
    changes = [(at, old, new, 'reviewed C/caption') for at, old, new in changes]

    def shifted(at):
        if any(p <= at < p + len(old) for p, old, _, _ in changes):
            raise ValueError('Directory points inside an edited record')
        return at + sum(len(new) - len(old) for p, old, new, _ in changes
                        if p + len(old) <= at)

    edits = list(changes)
    pointers = [(directory['locatorOffset'], directory['offset'])]
    pointers += [(directory['offset'] + 4 + 8 * i, value)
                 for i, value in enumerate(directory['entries'])]
    for at, value in pointers:
        edits.append((at, struct.pack('>Q', value), struct.pack('>Q', shifted(value)),
                      'absolute section pointer'))
    result = apply(raw, edits)
    if read_directory(result)['entries'] != [shifted(v) for v in directory['entries']]:
        raise ValueError('Relocated directory differs')
    inverse, delta = [], 0
    for at, old, new, label in sorted(edits):
        inverse.append((at + delta, new, old, label))
        delta += len(new) - len(old)
    if apply(result, inverse) != raw:
        raise ValueError('Full inverse/source preservation failed')
    return result


def patch_macro(text):
    newline = '\r\n' if '\r\n' in text else '\n'
    alarm_guard = '            && !(AlarmWords[0] & (1u << (9 + i)))' + newline
    state = '        ready = !(AlarmWords[0] & (1u << (5 + i)));'
    probe = 'LocalWord[930] = 27124u;'
    for anchor in (alarm_guard, state, probe):
        if text.count(anchor) != 1:
            raise ValueError('Reviewed animation anchor differs: ' + anchor.strip())
    for number in range(960, 966):
        if re.search(r'LocalWord\[\s*' + str(number) + r'\b', text):
            raise ValueError('Current-display LW already in use')
    text = text.replace(alarm_guard,
        '            /* R251x ages this poll independently of other FC03 errors. */' + newline)
    current = (f'        LocalWord[960 + i] = PumpAnimTelemetry[4 + i];{newline}'
               f'        LocalWord[963 + i] = (unsigned short)(valid{newline}'
               f'            && PumpAnimTelemetry[9] == {PLC_MARKER}u);{newline}')
    return text.replace(state, current + state).replace(probe, f'LocalWord[930] = {HMI_MARKER}u;')


def prepare(raw, expected_sha=SOURCE_SHA):
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha) or sha(raw) != expected_sha:
        raise ValueError('Use the explicitly pinned native source; preserve newer changes')
    header = read_project_header(raw)
    before = read_directory(raw)
    alarms = validate_alarm_catalog(raw)
    if (header['model'] != 'SK-070HE' or header['resolution'] != (800.0, 480.0)
            or header['pageCount'] not in (16, 17)
            or validate_alarm_identities(raw) != list(range(7))):
        raise ValueError('Unexpected native model/pages/alarm groups')
    old_block = macro_mirrors(raw)[0]
    c = old_block[4:].decode('utf-16-be')
    # Keep all generated aliases/variable tables. No new pVar input is added.
    if ('PumpAnimLeader[0]' not in c or '#define PANEL_MAP_VERSION 32u' not in c
            or 'quality = PumpAnimTelemetry[10 + i];' not in c):
        raise ValueError('Reviewed Batch16/quality contract differs')
    for number in range(960, 966):
        if qs('LW' + str(number)) in raw:
            raise ValueError('Current-display LW is already bound by a widget')
    updated = qs(patch_macro(c))
    marker = '#include "MacroInit.h"'.encode('utf-16-be')
    positions = [m.start() - 4 for m in re.finditer(re.escape(marker), raw)]
    if len(positions) != 2:
        raise ValueError('Two C mirrors required')
    edits = [(at, old_block, updated) for at in positions]
    old_caption = qs(CAPTION)
    new_caption = qs(CAPTION.replace('27124', str(HMI_MARKER)))
    captions = [m.start() for m in re.finditer(re.escape(old_caption), raw)]
    if not 1 <= len(captions) <= 7:
        raise ValueError('Probe caption differs')
    edits += [(at, old_caption, new_caption) for at in captions]
    result = replace_records(raw, edits)
    after = read_directory(result)
    after_alarms = validate_alarm_catalog(result)
    if read_project_header(result) != header or validate_alarm_identities(result) != list(range(7)):
        raise ValueError('Native header/alarm identities changed')
    for key in ('definitions', 'directory'):
        a, b = alarms[key], after_alarms[key]
        if raw[a['start']:a['end']] != result[b['start']:b['end']]:
            raise ValueError('Alarm catalog changed')
    # Sections0..16 contain settings/variables; section17 holds the C mirror.
    for index in range(17):
        a, z = before['entries'][index:index + 2]
        p, q = after['entries'][index:index + 2]
        if raw[a:z] != result[p:q]:
            raise ValueError('Opaque settings or variable tables changed')
    if macro_mirrors(result)[0] != updated:
        raise ValueError('C mirror reconstruction differs')
    return result, dict(sourceSHA256=sha(raw), candidateSHA256=sha(result),
        candidateBytes=len(result), sourceMacroQStringSHA256=sha(old_block),
        sourceMacroUTF16SHA256=sha(old_block[4:]), macroQStringSHA256=sha(updated),
        macroUTF16SHA256=sha(updated[4:]), hmiProbeMarker=HMI_MARKER,
        plcTelemetryMarker=PLC_MARKER, currentWords=['LW960', 'LW961', 'LW962'],
        currentQuality=['LW963', 'LW964', 'LW965'], currentUnit='raw x0.1 A',
        allUnlistedBytesPreservedByInverse=True, nativeSettingsAndRKFPreserved=True,
        variableTablesChanged=False, currentWidgetsStillRequireNativeSetup=True,
        readyGuardPreserved=True, nativeCompileObserved=False, deployable=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'out', 'report'):
        p.add_argument('--' + name, required=True, type=Path)
    p.add_argument('--source-sha256', default=SOURCE_SHA,
                   help='Explicit inspected source pin; default is accepted r18a')
    a = p.parse_args()
    if len({v.resolve() for v in (a.source, a.out, a.report)}) != 3 or any(
            v.is_symlink() for v in (a.source, a.out, a.report)) or a.out.exists() or a.report.exists():
        p.error('Distinct source and NEW regular output/report required')
    original = a.source.read_bytes()
    data, report = prepare(original, a.source_sha256.lower())
    if a.source.read_bytes() != original:
        raise ValueError('Source changed')
    with a.out.open('xb') as f:
        f.write(data)
    with a.report.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2); f.write('\n')
    print('Created HMI STAGE (current widgets/native checks pending):', len(data), sha(data))


if __name__ == '__main__':
    main()
