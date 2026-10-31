#!/usr/bin/env python3
"""Compare a user-saved native feedback extension without modifying it."""
import argparse
import hashlib
import json
from pathlib import Path

from check_native_drive_edit_02 import unpack
from prepare_setpoint_feedback_01 import SOURCE, EXPECTED, ANCHOR, networks


def compare(old, new):
    plan = networks()
    old_labels = [label for _, label in old['rungs']]
    new_labels = [label for _, label in new['rungs']]
    index = old_labels.index(ANCHOR)
    if new_labels != old_labels[:index] + [row['label'] for row in plan] + old_labels[index:]:
        raise ValueError('Expected exactly seven named networks before95.W032')
    start = old['rungs'][index][0]
    codes = [bytes.fromhex(row['expectedCodeHex']) for row in plan]
    position = start
    for number, (row, code) in enumerate(zip(plan, codes)):
        if new['rungs'][index + number][0] != position:
            raise ValueError('Unexpected feedback-network position')
        end = new['rungs'][index + number + 1][0]
        if new['image'][position:end] != code:
            raise ValueError('Wrong condition, MOV source/destination or execution flags in ' + row['label'])
        position = end
    delta = sum(map(len, codes))
    if position != start + delta:
        raise ValueError('Unexpected extension size')
    retained = [row for number, row in enumerate(new['rungs']) if not index <= number < index + len(plan)]
    expected = [(pc if number < index else pc + delta, label) for number, (pc, label) in enumerate(old['rungs'])]
    if retained != expected:
        raise ValueError('An existing network was changed or moved unexpectedly')
    if old['tables'] != new['tables']:
        raise ValueError('An existing Modbus table changed')
    if len(old['image']) != len(new['image']):
        raise ValueError('Image allocation changed; needs separate review')
    if old['image'][512:start] != new['image'][512:start]:
        raise ValueError('Existing program changed before feedback block')
    if old['image'][start:-delta] != new['image'][start + delta:]:
        raise ValueError('Existing program changed after feedback block')
    return dict(addedNetworksVerified=len(plan), addedProgramBytes=delta,
                allExistingNetworksPreserved=len(old['rungs']), allNineTablesPreserved=True,
                newDrivePollRequests=0, mapVersionRemains32=True,
                changedImageHeaderOffsets=[i for i in range(512) if old['image'][i] != new['image'][i]],
                scope='Strict network/MOV/body/table comparison; header deltas and native F8/runtime require separate observation')


def check(candidate):
    old = unpack(SOURCE)
    if hashlib.sha256(old['bytes']).hexdigest() != EXPECTED:
        raise ValueError('Baseline source changed')
    new = unpack(candidate)
    report = compare(old, new)
    report.update(candidate=candidate.name, candidateSHA256=hashlib.sha256(new['bytes']).hexdigest(),
                  nativeF8Observed=False, actualPLCUpdateObserved=False, actualFeedbackObserved=False,
                  checkerModifiedFiles=False)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = check(args.candidate)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Seven feedback MOVs match; all old program networks and nine tables preserved. No live action performed.')


if __name__ == '__main__':
    main()
