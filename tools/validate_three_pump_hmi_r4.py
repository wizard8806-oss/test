#!/usr/bin/env python3
"""Regression: reject stale r3 directory and check repaired r4/UI preservation."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import tempfile

from build_three_pump_hmi_r3 import prepare as assemble_r3
from build_three_pump_hmi_r4 import prepare
from repair_skm_section_index import read_directory, repair_rejected_r3
from validate_three_pump_hmi_r3 import validate_ui_assembly


def validate(source_r2, candidate_r4, recipe, plc):
    raw = Path(source_r2).read_bytes()
    final = Path(candidate_r4).read_bytes()
    original = read_directory(raw)
    expected, report = prepare(source_r2, recipe)
    assert final == expected
    current = read_directory(final)
    intermediate, _ = assemble_r3(source_r2, recipe)
    try:
        read_directory(intermediate)
    except ValueError as e:
        assert 'Stale SKM absolute offsets/EOF' in str(e)
    else:
        raise AssertionError('Native-rejected r3 was accepted')
    repaired, proof = repair_rejected_r3(intermediate)
    assert repaired == final
    assert current['entries'] == [v+414 for v in original['entries']]
    assert current['locatorOffset'] == original['locatorOffset']+414
    assert current['offset'] == original['offset']+414
    assert current['entries'][-1] == len(final)
    assert struct.unpack_from('>Q', final, current['locatorOffset'])[0] == current['offset']
    # No project settings/macros/communications bytes are changed by the UI
    # edits: all22 metadata sections before the directory are exactly preserved.
    for i in range(22):
        assert raw[original['entries'][i]:original['entries'][i+1]] == final[current['entries'][i]:current['entries'][i+1]]
    restored = bytearray(final)
    for edit in proof['changes']:
        at = edit['offset']
        assert restored[at:at+8] == bytes.fromhex(edit['new'])
        restored[at:at+8] = bytes.fromhex(edit['old'])
    assert bytes(restored) == intermediate
    bad_cases = []
    for name, at in (('EOF', len(final)-1), ('directory count', current['offset']+3),
                     ('back-pointer', current['locatorOffset']+7),
                     ('directory order', current['offset']+11)):
        bad = bytearray(final)
        bad[at] ^= 0x80
        try:
            read_directory(bytes(bad))
        except ValueError:
            bad_cases.append(name)
        else:
            raise AssertionError('Corrupt directory accepted: '+name)
    # The UI bytes are EXACTLY those checked by the earlier58 producer/UI cases;
    # this temporary intermediate is never delivered as an openable native file.
    with tempfile.TemporaryDirectory(prefix='hmi-r4-components-') as temp:
        historic = Path(temp)/'rejected-ui-intermediate.skm'
        historic.write_bytes(intermediate)
        ui = validate_ui_assembly(source_r2, historic, recipe, plc)
    assert Path(source_r2).read_bytes() == raw
    return {'revision': 4, 'candidateSHA256': hashlib.sha256(final).hexdigest(),
            'candidateBytes': len(final), 'nativeRejectedR3FailsNewDirectoryCheck': True,
            'directoryEntriesRelocated': 24, 'directoryBackPointerCorrect': True,
            'EOFEqualsActualSize': True, 'metadataSectionsPreserved': 22,
            'r3UIBytesPreservedExcept25DirectoryWords': True,
            'corruptDirectoryCasesRejected': bad_cases, 'UIComponentChecks': ui,
            'nativeSKToolOpenObserved': False, 'equipmentActions': 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source-r2', 'candidate-r4', 'recipe', 'plc', 'report'):
        p.add_argument('--'+name, required=True, type=Path)
    a = p.parse_args()
    if a.report.exists() or a.report.is_symlink() or a.report.resolve() in {v.resolve() for v in (a.source_r2, a.candidate_r4, a.recipe, a.plc)}:
        raise ValueError('New distinct report required')
    result = validate(a.source_r2, a.candidate_r4, a.recipe, a.plc)
    with a.report.open('x', encoding='utf8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('PASS: rejected-r3 regression; 24 entries/back-pointer/EOF; 22 metadata sections; 58 UI snapshots.')
    print('Native SKTool opening/compile/Simulator still require observation.')


if __name__ == '__main__':
    main()
