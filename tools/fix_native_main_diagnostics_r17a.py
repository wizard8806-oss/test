#!/usr/bin/env python3
"""Restore Main Diagnostics -> Screen4 in the operator's saved native r17.

Change only SB6010's five route fields and relocate absolute offsets.
Preserve the animation probe on Screen13, reachable from the VFD code page.
No alarm, macro, logo, startup, PLC or operator-layout changes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from build_native_merge_r16 import macro_mirrors, properties, route, widget
from prepare_alarm_open_differential import replace_blocks
from repair_skm_section_index import read_directory
from skm_alarm_catalog import qs, validate_alarm_catalog, validate_alarm_identities
from skm_page_storage import read_page_storage
from skm_project_header import read_project_header


SOURCE_BYTES = 1479825
SOURCE_SHA = 'befe204512d8c1cf93baf93bb2c3b870e7c087ae8fd7e53e286ebef02162aa6d'
MACRO_SHA = 'e02de39aca683e81fedf743b3de9e434404605c47301f0d441d30ae572ce61e5'
ROUTE_FIELDS = (48, 49, 56, 57, 60)
CAPTION_FIELDS = (154, 157, 160, 163, 166, 201)
sha = lambda data: hashlib.sha256(data).hexdigest()


def prepare(raw, source_sha256=None):
    expected_sha = SOURCE_SHA if source_sha256 is None else source_sha256.lower()
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha) or sha(raw) != expected_sha:
        raise ValueError('Source differs from the pinned native SHA256; preserve newer operator edits')
    if source_sha256 is None and len(raw) != SOURCE_BYTES:
        raise ValueError('Received native r17 size differs')
    header = read_project_header(raw)
    before_dir = read_directory(raw)
    read_page_storage(raw)
    before_alarms = validate_alarm_catalog(raw)
    if (header['model'] != 'SK-070HE' or header['resolution'] != (800.0, 480.0)
            or header['pageCount'] != 16 or validate_alarm_identities(raw) != list(range(7))):
        raise ValueError('Reviewed native page/alarm counts differ')
    if sha(macro_mirrors(raw)[0]) != MACRO_SHA:
        raise ValueError('Native macro differs from the reviewed r17; do not substitute an older source')

    page4 = raw.index(qs('Screen4') + b'\xff' * 4)
    page5 = raw.index(qs('Screen5') + b'\xff' * 4, page4)
    if raw[page4:page5].count(qs('ДИАГНОСТИКА СТАНЦИИ')) != 7:
        raise ValueError('Station diagnostics is not on the reviewed Screen4')

    start, old = widget(raw, 'SB6010')
    old_start, old_end, old_values = properties(old, 'SB6010')
    # Native Save may clear unused language copies. Identify the caption in
    # actual text-property slots rather than requiring seven cached copies.
    caption_fields = [i for i in CAPTION_FIELDS if old_values[i] == 'Диагностика']
    preview_copies = (old[:old_start] + old[old_end:]).count(qs('Диагностика'))
    if (not caption_fields or preview_copies not in (0, 1)
            or old.count(qs('Диагностика')) != len(caption_fields) + preview_copies):
        raise ValueError('Main Diagnostics caption is missing from the reviewed native text fields')
    if (old_values[56] not in {'Screen' + str(i) for i in range(1, 17)}
            or any(old_values[i] not in {str(n) for n in range(16)} for i in (48, 49, 57, 60))):
        raise ValueError('Unreviewed Main Diagnostics route field format')
    new = route(old, 'SB6010', 4)
    new_start, new_end, new_values = properties(new, 'SB6010')
    if new_values[56] != 'Screen4' or any(new_values[i] != '3' for i in (48, 49, 57, 60)):
        raise ValueError('Station diagnostics route not updated consistently')
    if any(a != b for i, (a, b) in enumerate(zip(old_values, new_values)) if i not in ROUTE_FIELDS):
        raise ValueError('Unrelated button property changed')
    if old[:old_start] != new[:new_start] or old[old_end:] != new[new_end:]:
        raise ValueError('Button geometry/caption/non-property data changed')

    result = replace_blocks(raw, [(start, old, new)])
    after_dir = read_directory(result)
    after_alarms = validate_alarm_catalog(result)
    if read_project_header(result) != header or read_page_storage(result)['pageCount'] != 16:
        raise ValueError('Native header/page storage changed')
    if macro_mirrors(result) != macro_mirrors(raw):
        raise ValueError('Macro changed')
    for key in ('definitions', 'directory'):
        a, b = before_alarms[key], after_alarms[key]
        if raw[a['start']:a['end']] != result[b['start']:b['end']]:
            raise ValueError('Alarm groups/catalog changed')
    if validate_alarm_identities(result) != list(range(7)):
        raise ValueError('Alarm identities changed')
    for index in range(22):
        a, z = before_dir['entries'][index:index + 2]
        p, q = after_dir['entries'][index:index + 2]
        if raw[a:z] != result[p:q]:
            raise ValueError('Native opaque settings changed')

    # Complete inverse independently proves preservation outside this button
    # and the required pointer relocations, including unknown native settings.
    restored = replace_blocks(result, [(start, new, old)])
    if restored != raw:
        raise ValueError('Complete inverse/source preservation failed')
    _, probe_button = widget(result, 'SB91032')
    if properties(probe_button, 'SB91032')[2][56] != 'Screen13':
        raise ValueError('VFD code page probe access changed')

    return result, dict(
        kind='r17a single Main Diagnostics route fix', sourceBytes=len(raw),
        sourceSHA256=sha(raw), candidateBytes=len(result), candidateSHA256=sha(result),
        widget='SB6010', changedRouteFields=list(ROUTE_FIELDS),
        sourceSHAExplicitlyPinned=source_sha256 is not None,
        captionPropertyIndices=caption_fields,
        captionPreviewCopies=preview_copies,
        captionQStringCount=len(caption_fields) + preview_copies,
        oldTarget=old_values[56], oldRouteFields={str(i): old_values[i] for i in ROUTE_FIELDS},
        newTarget='Screen4', newZeroBasedIndex=3, alreadyCorrect=old == new,
        buttonCaptionGeometryAndOtherPropertiesPreserved=True,
        completeInversePreservation=True, nativeOpaqueSettingsPreserved=True,
        alarmsAndMacroPreserved=True, probeStillReachableFromCodePage=True,
        PLCChanged=False, nativeOpenObserved=False, nativeCompileObserved=False,
        offlineSimulatorObserved=False, hardwareActions=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', help='Pin the SHA of a newer native save after inspecting it; never overwrite it')
    parser.add_argument('--report', type=Path, required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--out', type=Path)
    target.add_argument('--check', type=Path)
    args = parser.parse_args()
    candidate = args.out or args.check
    paths = (args.source, candidate, args.report)
    if (len({path.resolve() for path in paths}) != 3 or any(path.is_symlink() for path in paths)
            or args.report.exists() or (args.out and candidate.exists())):
        raise ValueError('Distinct regular paths and NEW output/report required')
    original = args.source.read_bytes()
    data, report = prepare(original, args.source_sha256)
    if args.source.read_bytes() != original:
        raise ValueError('Source changed during inspection')
    if args.check:
        if candidate.read_bytes() != data:
            raise ValueError('Candidate differs from the single-button native fix')
    else:
        with candidate.open('xb') as stream:
            stream.write(data)
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print('PASS' if args.check else 'Created', candidate.resolve(), len(data), sha(data))


if __name__ == '__main__':
    main()
