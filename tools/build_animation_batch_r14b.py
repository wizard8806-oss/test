#!/usr/bin/env python3
"""Build a reviewed HMI with all native read inputs as UInt16 batches.

Live r14a retained one-word displacement after MapVersion, its sole scalar
before telemetry. Convert scalar reads to one-WORD batches, keep BootAck W
last, and use the leader's first WORD through its generated alias. No pVar
offsets, PLC changes or channel remapping. Native ABI/live acceptance remains.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from reorder_animation_macro_r14a import VARIABLES, ORDER, entry, packed, qs, SOURCE_SHA, SOURCE_BYTES
from repair_skm_section_index import read_directory

R14A_SHA = 'b56648e47a41cdd4eef981060da7a20a0a12cb062f6af9a4c1cf9faf69523323'
SIGNATURE = 27124
CAPTION = 'Частоты F: целое число × 0.1 Гц. Зонд должен показывать 27119.'
sha = lambda b: hashlib.sha256(b).hexdigest()


def apply(raw, edits):
    output = bytearray(); cursor = 0
    for at, old, new, label in sorted(edits, key=lambda v: v[0]):
        if at < cursor or raw[at:at+len(old)] != old:
            raise ValueError('Overlapping/different reviewed field: '+label)
        output.extend(raw[cursor:at]); output.extend(new); cursor = at+len(old)
    output.extend(raw[cursor:])
    return bytes(output)


def prepare(source):
    source = Path(source); raw = source.read_bytes(); digest = sha(raw)
    if len(raw) != SOURCE_BYTES or digest not in (SOURCE_SHA, R14A_SHA):
        raise ValueError('Use exact user r13 or r14a; preserve newer native edits for strict adaptation')
    directory = read_directory(raw)
    old_rows = list(VARIABLES if digest == SOURCE_SHA else [VARIABLES[i] for i in ORDER])
    new_rows = [VARIABLES[i] for i in ORDER]
    new_rows = [(name, 'Batch 16-Bit Unsigned Int', '2', mode, address)
                if name in ('MapVersion', 'PumpAnimLeader') else (name, kind, size, mode, address)
                for name, kind, size, mode, address in new_rows]
    edits = []
    for old, new, label in (
        (packed(old_rows), packed(new_rows), 'packed batch variable settings'),
        (struct.pack('>I', 7)+b''.join(map(entry, old_rows)),
         struct.pack('>I', 7)+b''.join(map(entry, new_rows)), 'native batch variable settings')):
        if raw.count(old) != 1:
            raise ValueError('Native variable schema/count differs: '+label)
        edits.append((raw.index(old), old, new, label))
    marker = '#include "MacroInit.h"'.encode('utf-16-be')
    positions = [m.start()-4 for m in re.finditer(re.escape(marker), raw)]
    if len(positions) != 2:
        raise ValueError('Two macro source mirrors required')
    sources = []
    replacements = [
        (' * MapVersion: 16-Bit Unsigned Int, R, FATEK R2554.',
         ' * MapVersion: Batch 16-Bit Unsigned Int, Bytes=2, R, FATEK R2554.'),
        ('Configure_MapVersion_as_16_Bit_Unsigned_Int_R2554',
         'Configure_MapVersion_as_Batch16_R2554_Bytes2'),
        ('Configure_PumpAnimLeader_UInt16_R2304_ReadOnly',
         'Configure_PumpAnimLeader_Batch16_R2304_Bytes2_ReadOnly'),
        ('PumpAnimLeader ==', 'PumpAnimLeader[0] =='),
        ('LocalWord[930] = 27119u;', 'LocalWord[930] = 27124u;'),
    ]
    for at in positions:
        n = struct.unpack_from('>I', raw, at)[0]
        c = raw[at+4:at+4+n].decode('utf-16-be'); sources.append(c); updated = c
        for old, new in replacements:
            if updated.count(old) != 1:
                raise ValueError('Reviewed C anchor differs: '+old)
            updated = updated.replace(old, new)
        edits.append((at, qs(c), qs(updated), 'leader batch alias/probe signature C mirror'))
    if sources[0] != sources[1]:
        raise ValueError('Source macro mirrors differ')
    old, new = qs(CAPTION), qs(CAPTION.replace('27119', str(SIGNATURE)))
    locations = [m.start() for m in re.finditer(re.escape(old), raw)]
    if len(locations) != 7:
        raise ValueError('Probe caption language/cache mirrors differ')
    edits += [(at, old, new, 'probe expected-signature caption') for at in locations]
    # All absolute directory pointers must track the changed QString lengths.
    def shifted(address):
        if any(at < address < at+len(old) for at, old, _, _ in edits):
            raise ValueError('Directory pointer lies inside an edited field')
        return address+sum(len(new)-len(old) for at, old, new, _ in edits if at < address)
    relocations = [shifted(v) for v in directory['entries']]
    dir_at, locator = shifted(directory['offset']), directory['locatorOffset']
    directory_edits = [(directory['offset']+4+8*i, struct.pack('>Q', old), struct.pack('>Q', new),
                        'section directory entry'+str(i))
                       for i, (old, new) in enumerate(zip(directory['entries'], relocations))]
    directory_edits.append((locator, struct.pack('>Q', directory['offset']), struct.pack('>Q', dir_at),
                            'directory back pointer'))
    edits += directory_edits
    result = apply(raw, edits)
    checked = read_directory(result)
    if checked['entries'] != relocations or checked['offset'] != dir_at:
        raise ValueError('Relocated directory differs')
    inverse = []; delta = 0
    for at, old, new, label in sorted(edits, key=lambda v: v[0]):
        inverse.append((at+delta, new, old, label)); delta += len(new)-len(old)
    if apply(result, inverse) != raw or source.read_bytes() != raw:
        raise ValueError('Full inverse/source preservation failed')
    if result[:min(locations)] != raw[:min(locations)]:
        raise ValueError('Main/alarm/earlier UI content changed')
    return result, {
        'sourceSHA256': digest, 'sourceBytes': len(raw),
        'candidateSHA256': sha(result), 'candidateBytes': len(result),
        'readInputs': [{'name': name, 'type': kind, 'bytes': size, 'address': 'R'+address}
                       for name, kind, size, mode, address in new_rows if mode == 'R'],
        'writeInputs': [{'name': name, 'type': kind, 'address': 'R'+address}
                        for name, kind, size, mode, address in new_rows if mode == 'W'],
        'allReadInputsAreUInt16Batches': True, 'singleWordReadBatchBytes': 2,
        'BootAckWLast': True, 'BootAckScalarWriteUnchanged': True,
        'MapVersionStillAliasedToAlarmWords4': True,
        'leaderAliasAccess': 'PumpAnimLeader[0]', 'probeSignature': SIGNATURE,
        'edits': [{'offset': at, 'oldBytes': len(old), 'newBytes': len(new), 'label': label}
                  for at, old, new, label in sorted(edits, key=lambda v: v[0])],
        'allUnlistedBytesPreservedByFullInversion': True,
        'mainUserLayoutAndHADPreserved': True, 'PLCChanged': False, 'newPLCWrites': 0,
        'logoOrFaultHMIImplemented': False, 'nativeCompileObserved': False,
        'nativeABIValidated': False, 'liveRetestPassed': False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'report'):
        p.add_argument('--'+name, type=Path, required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--out', type=Path); group.add_argument('--check', type=Path)
    a = p.parse_args(); target = a.out or a.check
    if len({v.resolve() for v in (a.source, target, a.report)}) != 3 or any(
            v.is_symlink() for v in (a.source, target, a.report)):
        raise ValueError('Distinct regular paths required')
    if a.report.exists() or (a.out is not None and target.exists()):
        raise ValueError('NEW output/report required; existing files preserved')
    result, report = prepare(a.source)
    if a.check is not None:
        if target.read_bytes() != result:
            raise ValueError('Candidate differs from exact batch-read transformation')
    else:
        with target.open('xb') as f:
            f.write(result)
    with a.report.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2); f.write('\n')
    print(('PASS' if a.check is not None else 'Created'), 'batch-read HMI:', len(result), sha(result))
    print('Probe27124. Main/HAD/PLC preserved. Native Compile and live P1/P2/P3/BootAck checks remain.')


if __name__ == '__main__':
    main()
