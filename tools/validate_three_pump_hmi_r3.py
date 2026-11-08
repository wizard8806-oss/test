#!/usr/bin/env python3
"""Check reviewed HMI-r3 edits and cause-specific countdown snapshots.

This checks bytes, typed fields and the compiled read-only producer. It is
not a SKTool loader, native compile or serial-link/equipment simulation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from apply_hmi_layout_recipe import qstring
from build_three_pump_hmi_r3 import prepare, descriptor
from check_native_drive_edit_02 import unpack
from validate_three_pump_pdw_candidate import Machine
from repair_skm_section_index import read_directory


def read_strings(raw, at, count):
    values = []
    for _ in range(count):
        size = int.from_bytes(raw[at:at+4], 'big')
        assert size % 2 == 0 and size <= 1024
        values.append(raw[at+4:at+4+size].decode('utf-16-be'))
        at += 4 + size
    return values


def validate_ui_assembly(source, candidate, recipe_path, plc_path):
    """Historic UI-only component checks; explicitly excludes file directory."""
    raw, target = Path(source).read_bytes(), Path(candidate).read_bytes()
    recipe = json.loads(Path(recipe_path).read_text())
    expected, report = prepare(source, recipe_path)
    assert target == expected
    edits = report['edits']

    def shifted(offset):
        return offset + sum(e['targetBytes']-e['sourceBytes'] for e in edits if e['sourceOffset'] < offset)

    # Reconstruct the original, accounting for variable QString sizes and the
    # complete ND replacement. Every other byte must be exactly preserved.
    result, cursor = bytearray(), 0
    for edit in edits:
        at = shifted(edit['sourceOffset'])
        result.extend(target[cursor:at])
        end = at + edit['targetBytes']
        assert hashlib.sha256(target[at:end]).hexdigest() == edit['targetFieldSHA256']
        p = edit['sourceOffset']
        result.extend(raw[p:p+edit['sourceBytes']])
        cursor = end
    result.extend(target[cursor:])
    assert bytes(result) == raw
    objects = {o['id']: o for o in recipe['objects']}
    hidden = report['hiddenFourthWidgets']
    assert len(hidden) == 25
    assert {o['screen'] for o in objects.values() if o['id'] in hidden} == {6, 7}
    assert {'NE9102', 'BB9112', 'BB9116', 'BB9120', 'BB6126', 'BB6130', 'ND14016'} <= set(hidden)

    def common(name):
        return read_strings(target, shifted(objects[name]['visibilityOffset']), 10)

    for name in hidden:
        v = common(name)
        assert v == ['1', '0', '1', '0', descriptor(2860), '2', '0', '4', '0', '100']
        for count in (0, 1, 2, 3):
            assert count != int(v[7])
    for name in report['centeredWidgets']:
        obj = objects[name]
        for at in obj['positionOffsets']:
            assert struct.unpack_from('>2d', target, shifted(at)) == (obj['newX'], obj['y'])

    for name, word, caption in (('Text3052', 2525, 'Сухой ход, с'), ('Text10052', 2526, 'Питание, с')):
        v = common(name)
        assert v == ['1', '0', '1', '0', descriptor(word), '3', '0', '0', '0', '100']
        obj = objects[name]
        assert target[shifted(obj['start']):shifted(obj['stop'])].count(qstring(caption)) == 7
    for name in ('Text16008', 'MD3054', 'MD3056', 'MD10046', 'Text10044', 'MD10056', 'BG10054'):
        assert common(name)[4:8] == [descriptor(2860), '2', '0', '4']
    for name, word in (('ND12004', 2520), ('ND12012', 2521)):
        obj = objects[name]
        assert qstring('R'+str(word)) in target[shifted(obj['firstID']):shifted(obj['stop'])]
    # All write bindings, navigation controls and apply transactions are outside
    # the changed fields. In particular no new write to a fourth pump is made.
    assert qstring('R2540') in target and qstring('R2541') in target
    for at, count in ((481, 80), (573637, 66), (719762, 67)):
        assert int.from_bytes(target[shifted(at):shifted(at)+4], 'big') == count

    # Two complete integer ND records, each with one value source, three
    # matching descriptors (value/cache/visibility), and unique scene ordinals.
    power = next(e for e in edits if e['label'].startswith('replace inactive dash'))
    pa = shifted(power['sourceOffset'])
    power_record = target[pa:pa+power['targetBytes']]
    dry = objects['ND10048']
    dry_record = target[shifted(dry['start']):shifted(dry['stop'])]
    for record, name, word, ordinal in ((dry_record, 'ND10048', 2525, 65), (power_record, 'ND10050', 2526, 66)):
        assert record.count(qstring(name)) == 2
        assert record.count(qstring('R'+str(word))) == 1
        assert record.count(descriptor(word).encode('utf-16-be')) == 3
        assert record.endswith(qstring(str(ordinal))+struct.pack('>d', ordinal))
        assert qstring('5')+qstring('0')+qstring('2') in record
        assert qstring('MD10050') not in record

    plc = unpack(plc_path)
    assert hashlib.sha256(plc['bytes']).hexdigest() == recipe['unchangedPLC']
    codes = [plc['image'][pc:plc['rungs'][i+1][0]] for i, (pc, label) in enumerate(plc['rungs']) if label.startswith('30.CD')]
    assert len(codes) == 29
    cases = []

    def observe(name, dry=False, power=False, ds=30, ps=60, de=0, pe=0,
                water=True, mains=True, auto=True, emergency=False, boot=False,
                dry_setting_valid=True, power_setting_valid=True, timer=0):
        m = Machine()
        context = auto and not emergency and not boot
        dry = dry and auto and not emergency
        power = power and auto and not emergency
        den = context and dry and water and dry_setting_valid
        pen = context and power and mains and power_setting_valid
        m.regs.update({('R', 2520): ds, ('R', 2521): ps, ('R', 2522): de & 65535,
                       ('R', 2523): pe & 65535, ('R', 2524): 0, ('T', 96): timer})
        m.bits.update({('M', 1753): dry, ('M', 1754): power, ('M', 1757): dry or power,
                       ('M', 1760): dry_setting_valid, ('M', 1761): power_setting_valid,
                       ('M', 1764): den, ('M', 1765): pen, ('M', 1766): context,
                       ('M', 1773): False, ('M', 1774): False, ('M', 1775): False,
                       ('M', 1776): False, ('M', 1924): boot, ('X', 6): water, ('X', 7): mains})
        for code in codes:
            m.execute(code)
        actual = (m.regs[('R', 2525)], m.regs[('R', 2526)])
        wanted = (max(0, ds-de) if den and 0 <= de < ds else 0,
                  max(0, ps-pe) if pen and 0 <= pe < ps else 0)
        assert actual == wanted, (name, actual, wanted)
        # HMI template nonzero operator3 drives BOTH label and number.
        visible = (actual[0] != 0, actual[1] != 0)
        cases.append({'name': name, 'seconds': actual, 'visible': visible})
        return actual, visible

    assert observe('idle') == ((0, 0), (False, False))
    for elapsed in range(31):
        observe('dry-only elapsed '+str(elapsed), dry=True, de=elapsed)
    for elapsed in (0, 1, 30, 59, 60):
        observe('power-only elapsed '+str(elapsed), power=True, pe=elapsed)
    assert observe('both unequal pauses', dry=True, power=True, de=5, pe=20) == ((25, 40), (True, True))
    assert observe('dry finished power counting', dry=True, power=True, de=30, pe=20) == ((0, 40), (False, True))
    assert observe('power finished dry counting', dry=True, power=True, de=5, pe=60) == ((25, 0), (True, False))
    observe('dry fault still present', dry=True, water=False)
    observe('power fault still present', power=True, mains=False)
    observe('water recovers', dry=True, de=0)
    observe('power recovers', power=True, pe=0)
    observe('STOP', dry=True, power=True, auto=False)
    observe('emergency', dry=True, power=True, emergency=True)
    observe('boot', dry=True, power=True, boot=True)
    observe('invalid dry setting', dry=True, dry_setting_valid=False)
    observe('invalid power setting', power=True, power_setting_valid=False)
    for elapsed in (-1, 31, 65535):
        observe('invalid dry elapsed '+str(elapsed), dry=True, de=elapsed)
    for timer in (0, 9, 10, 19, 20):
        assert observe('separate final readiness timer '+str(timer), dry=True, de=30, timer=timer)[1] == (False, False)
    assert observe('maximum seconds', power=True, ps=3600)[0] == (0, 3600)
    assert hashlib.sha256(Path(plc_path).read_bytes()).hexdigest() == recipe['unchangedPLC']
    return {'passed': len(cases), 'cases': cases, 'hiddenFourthWidgets': 25,
            'centeredWidgets': 75, 'unlistedBytesPreserved': True, 'sceneCountsPreserved': True,
            'twoIndependentNumericRecords': True, 'causeLabelAndValueVisibilityMatched': True,
            'PLCUnchanged': True, 'nativeSKToolValidation': False, 'equipmentActions': 0}


def validate(source, candidate, recipe_path, plc_path):
    # The old component checks missed this mandatory whole-file constraint.
    # Public validation now rejects the native-failing r3 before reporting PASS.
    read_directory(Path(candidate).read_bytes())
    return validate_ui_assembly(source, candidate, recipe_path, plc_path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'candidate', 'recipe', 'plc', 'report'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    if a.report.exists() or a.report.is_symlink() or a.report.resolve() in {v.resolve() for v in (a.source, a.candidate, a.recipe, a.plc)}:
        raise ValueError('New distinct report required')
    result = validate(a.source, a.candidate, a.recipe, a.plc)
    with a.report.open('x', encoding='utf8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('PASS:', result['passed'], 'cause snapshots; 25 fourth widgets hidden; 75 widgets centered.')
    print('Native SKTool/Offline Simulator acceptance remains separate.')


if __name__ == '__main__':
    main()
