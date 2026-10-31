#!/usr/bin/env python3
"""Mutation checks for the read-only native-file comparator.

The positive candidate is an in-memory decoded-image fixture, not a generated
PDW, native compilation, PLC download or successful live feedback test.
"""
import copy
import json
import struct

from check_native_drive_edit_02 import unpack
from check_setpoint_feedback_01 import compare
from prepare_setpoint_feedback_01 import SOURCE, OUT, ANCHOR, networks


def candidate(old):
    plan = networks()
    index = next(i for i, (_, label) in enumerate(old['rungs']) if label == ANCHOR)
    start = old['rungs'][index][0]
    code = b''.join(bytes.fromhex(row['expectedCodeHex']) for row in plan)
    assert old['image'][-len(code):] == b'\xff' * len(code)
    new = copy.deepcopy(old)
    new['image'] = old['image'][:start] + code + old['image'][start:-len(code)]
    new['rungs'] = old['rungs'][:index] + [(start + number * 8, row['label']) for number, row in enumerate(plan)]
    new['rungs'] += [(pc + len(code), label) for pc, label in old['rungs'][index:]]
    return new, index, start


def main():
    old = unpack(SOURCE)
    result, _, _ = candidate(old)
    assert compare(old, result)['addedNetworksVerified'] == 7
    reports = [dict(case='correct_decoded_image_fixture', passed=True)]
    cases = ['wrong_confirmed_pressure_source', 'write_to_working_setpoint', 'wrong_flags_word',
             'clock_contact_instead_of_unconditional', 'swapped_networks', 'missing_network',
             'changed_existing_mode_network', 'changed_old_drive_table', 'changed_map_version',
             'extra_network', 'wrong_rung_PC']
    for case in cases:
        new, index, start = candidate(old)
        image = bytearray(new['image'])
        if case == 'wrong_confirmed_pressure_source':
            struct.pack_into('>H', image, start + 2 * 8 + 4, 0x4000 + 2 * 675)
        elif case == 'write_to_working_setpoint':
            struct.pack_into('>H', image, start + 6, 0x0a00 + 2 * 2100)
        elif case == 'wrong_flags_word':
            struct.pack_into('>H', image, start + 6 * 8 + 4, 0x097c)
        elif case == 'clock_contact_instead_of_unconditional':
            struct.pack_into('>H', image, start, 0x4f92)
        elif case == 'swapped_networks':
            new['rungs'][index], new['rungs'][index + 1] = new['rungs'][index + 1], new['rungs'][index]
        elif case == 'missing_network':
            new['rungs'].pop(index + 3)
        elif case == 'changed_existing_mode_network':
            pc = next(pc for pc, label in new['rungs'] if label == '95.052 | HMI_MODE_AUTO_SELECTED')
            image[pc + 5] ^= 1
        elif case == 'changed_old_drive_table':
            new['tables']['R5000']['rows'][0][2] = 1
        elif case == 'changed_map_version':
            pc = next(pc for pc, label in new['rungs'] if label == ANCHOR)
            image[pc + 5] ^= 1
        elif case == 'extra_network':
            new['rungs'].insert(index, (start, '95.SP000 | EXTRA'))
        elif case == 'wrong_rung_PC':
            pc, label = new['rungs'][index + 1]
            new['rungs'][index + 1] = (pc + 2, label)
        new['image'] = bytes(image)
        try:
            compare(old, new)
        except ValueError as e:
            reports.append(dict(case=case, passed=True, rejection=str(e)))
        else:
            raise AssertionError('Comparator accepted unsafe/incorrect fixture: ' + case)
    report = dict(date='2026-10-31', comparatorCases=reports,
                  generatedPDW=False, nativeF8Tested=False, livePLCFeedbackTested=False,
                  evidenceScope='Expected block fixture plus eleven decoded-image mutations; separate vendor formatter confirms each proposed MOV')
    (OUT / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('PASS', len(reports), 'feedback comparator cases; no PDW/PLC modifications.')


if __name__ == '__main__':
    main()
