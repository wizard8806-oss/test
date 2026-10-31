#!/usr/bin/env python3
"""Read-only native-counter comparison against the accepted map32 PDW."""
import argparse
import hashlib
import json
from pathlib import Path

from check_native_drive_edit_02 import unpack
from prepare_plc_alive_counter_03 import EXPECTED, OUT, SOURCE


def check(path):
    old = unpack(SOURCE)
    if hashlib.sha256(old['bytes']).hexdigest() != EXPECTED:
        raise ValueError('Heartbeat baseline changed')
    new = unpack(path)
    old_labels = [name for _, name in old['rungs']]
    new_labels = [name for _, name in new['rungs']]
    index = old_labels.index('95.W032 | WORD_STATUS_VERSION')
    label = '95.A100 | PLC_ALIVE_COUNTER'
    if new_labels != old_labels[:index] + [label] + old_labels[index:]:
        raise ValueError('Expected exactly one labelled network before95.W032')
    pc = old['rungs'][index][0]
    if new['rungs'][index][0] != pc:
        raise ValueError('Counter inserted at unexpected position')
    following_pc = new['rungs'][index + 1][0]
    code = new['image'][pc:following_pc]
    expression_form = bytes.fromhex('e0004f927fe8f6642030ffff2030')
    compact_form = bytes.fromhex('4f92f09620305feb')
    if code not in (expression_form, compact_form):
        raise ValueError('Counter uses an unreviewed encoding; actual=' + code.hex())
    dialog_confirmed = False
    dialog_path = OUT / 'native-counter-dialog-observation-2026-10-30.json'
    if dialog_path.exists():
        dialog = json.loads(dialog_path.read_text())
        dialog_confirmed = (dialog.get('candidateSHA256') == hashlib.sha256(new['bytes']).hexdigest()
                            and dialog.get('functionNumber') == 15 and dialog.get('Pulse') is True
                            and dialog.get('32bits') is False and dialog.get('D') == 'R2840')
    semantics_confirmed = code == expression_form or dialog_confirmed
    delta = len(code)
    expected_pcs = [p if i < index else p + delta for i, (p, _) in enumerate(old['rungs'])]
    actual_pcs = [p for i, (p, _) in enumerate(new['rungs']) if i != index]
    if expected_pcs != actual_pcs:
        raise ValueError('Unexpected other rung movement')
    if old['tables'] != new['tables']:
        raise ValueError('An existing table changed')
    if len(old['image']) != len(new['image']):
        raise ValueError('Image allocation changed; review manually')
    if old['image'][512:pc] != new['image'][512:pc]:
        raise ValueError('Program changed before new network')
    if old['image'][pc:-delta] != new['image'][following_pc:]:
        raise ValueError('Other program bytes changed after insertion; review relocation before acceptance')
    return dict(candidate=path.name, sha256=hashlib.sha256(new['bytes']).hexdigest(),
                oneCounterRungStructurallyMatches=True, addedBytes=delta,
                counterEncoding=code.hex(),
                compactNativeForm=code == compact_form,
                pulseAndWidthConfirmed=semantics_confirmed,
                nativeFunctionDialogConfirmed=dialog_confirmed,
                otherProgramBodyPreserved=True, nineTablesUnchanged=True,
                mapVersionRemains32=True, nativeF8Observed=False,
                PLCDownloadObserved=False, counterProgressObserved=False,
                deployable=False,
                changedHeaderOffsets=[i for i in range(512) if old['image'][i] != new['image'][i]],
                evidenceScope='Strict code/table comparison; native execution and actual PLC counter still require bench confirmation')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = check(args.candidate)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('Counter structure/table comparison passed; pulse/width confirmed=' + str(result['pulseAndWidthConfirmed']) + '; native runtime proof still pending.')


if __name__ == '__main__':
    main()
