#!/usr/bin/env python3
"""Prepare a reviewed, read-only PLC05 workpack for configurable 2/3/4 pumps.

Produces native-editor implementation inputs, not a modified PLC or HMI.
Only the exact baseline05 is accepted. No external packages or vendor DLL
are required. Physical addresses remain proposals until native cross-reference,
retention settings and the current external bindings have been reviewed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_setpoint_feedback_pdw_01 import layout
from check_native_drive_edit_02 import unpack


SOURCE_SHA = '6aba2a67d07596e4a479c462412859565186de86b410a3cd44476a81f20ffe81'
COUNT_RANGE = range(2860, 2880)
REGISTER_PROPOSAL = {
    'InstalledPumpCount': 2860,
    'ConfigurationMarker': 2861,
    'PumpCountDraft': 2862,
    'PumpCountStatus': 2863,
    'InstalledPumpMask': 2864,
    'PumpCountValid': 2865,
    'PumpCountRevision': 2866,
    'PumpPictureIndex': 2867,
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def schedules(rows):
    """Filter the *whole* stable table; never truncate its interleaved prefix."""
    if not rows or any(len(row) != 7 or type(row[0]) is not int or
                       not 1 <= row[0] <= 4 for row in rows):
        raise ValueError('Expected seven-field rows addressed to drives 1..4')
    return {
        str(count): [dict(sourceRowOneBased=i + 1, fields=list(row))
                     for i, row in enumerate(rows) if row[0] <= count]
        for count in (2, 3, 4)
    }


def inspect(source):
    source = Path(source)
    original = source.read_bytes()
    if sha(original) != SOURCE_SHA:
        raise ValueError('Expected exact recovered PLC05; review other baselines separately')
    frames = layout(original)
    obj = unpack(source)
    if obj['bytes'] != original or obj['image'] != frames['image']:
        raise ValueError('Source changed or independent image decoders disagree')
    if len(obj['rungs']) != 1841 or len(obj['tables']) != 9:
        raise ValueError('Different baseline inventory')
    normal = obj['tables']['R5000']['rows']
    plans = schedules(normal)
    if [len(plans[str(n)]) for n in (2, 3, 4)] != [11, 14, 18]:
        raise ValueError('Different normal poll distribution')
    image = obj['image']
    end = int.from_bytes(image[270:272], 'little')
    # This scan deliberately overcounts possible references: an equal immediate
    # or opcode is a hit too. It is only evidence for this operand encoding.
    raw_hits = {
        'R' + str(reg): [pc for pc in range(512, end, 2)
                         if image[pc:pc + 2] == struct.pack('>H', 0x0a00 + 2 * reg)]
        for reg in COUNT_RANGE
    }
    if any(raw_hits.values()):
        raise ValueError('Proposed register block has possible compiled operand references')
    overlaps = []
    for address, table in obj['tables'].items():
        start = int(address[1:])
        # Conservative extent, including spare header words.
        stop = start + 4 + 8 * len(table['rows'])
        if max(start, COUNT_RANGE.start) < min(stop, COUNT_RANGE.stop):
            overlaps.append(dict(table=address, start=start, stopExclusive=stop))
        for i, row in enumerate(table['rows']):
            if row[3] == 12 and max(row[4], COUNT_RANGE.start) < min(row[4] + row[2], COUNT_RANGE.stop):
                overlaps.append(dict(table=address, rowOneBased=i + 1,
                                     localBuffer='R' + str(row[4]), words=row[2]))
    if overlaps:
        raise ValueError('Proposed register block overlaps a master table or R buffer')
    if source.read_bytes() != original:
        raise ValueError('Source changed during inspection')
    return dict(
        schemaVersion=1, sourceSHA256=SOURCE_SHA, sourceBytes=len(original),
        mapVersion=32, sourceUnchanged=True, nativeCompileObserved=False,
        nativePumpCountImplemented=False, physicalAddressesAllocated=False,
        candidateRegisters={name: 'R' + str(reg) for name, reg in REGISTER_PROPOSAL.items()},
        candidateBlock='R2860..R2879', rawEvenWordPossibleReferences=raw_hits,
        tableOrBufferOverlaps=overlaps,
        requirements={
            'allowedCounts': [2, 3, 4],
            'newStationDesiredCount': 3,
            'fourAddressSlotsPreserved': True,
            'autoMembershipIsSeparate': True,
            'unconfiguredBoot': 'count invalid; block run until commissioned in STOP',
            'acceptedConfigurationBoot': 'retain count; do not generate apply or run request',
            'change': 'explicit STOP transaction; all RUN outputs off, queues idle, no start on commit',
            'unknownOrStaleConfiguration': 'show unknown; do not infer four installed pumps',
            'imageIndex': '0 for 2, 1 for 3, 2 for 4; valid configuration required',
        },
        normalPollSchedules=plans,
        oneShotTables=[dict(address=reg, name=table['name'], rows=table['rows'],
                            rule='validate immutable job target 1..N before admission and dispatch; match reply to that job')
                       for reg, table in sorted(obj['tables'].items()) if reg != 'R5000'],
        existingSettings={
            'begin': 'M1460', 'apply': 'M1461', 'cancel': 'M1462',
            'session': 'M1463', 'inputAllowed': 'M1464', 'stopAllowed': 'M1465',
            'status': 'R2166', 'revision': 'R2168',
            'autoDraft': ['R2170', 'R2171', 'R2172', 'R2173'],
            'autoInstalledMembership': ['R720', 'R721', 'R722', 'R723'],
            'occupiedManualFrequencyInputs': ['R2180', 'R2181', 'R2182', 'R2183'],
        },
        changeAnchors={
            'settingsValidation': ['95.S007', '95.S037', '95.S038', '95.S050', '95.S053'],
            'normalPoll': ['65.00'],
            'availabilityAndRotation': ['50.04', '50.08', '50.AI21', '60.07'],
            'pressureSelection': ['65.14', '65.15', '65.16', '65.17'],
            'manualQueue': ['65.M048', '65.M052', '65.M096', '65.M097'],
            'modeQueue': ['60.137', '65.36B', '65.36C'],
            'frequencyQueue': ['65.F15', '65.F16'],
            'pressureParameterQueue': ['65.K32', '65.K38'],
            'stopProbe': ['65.S32', '65.S33'],
            'physicalRunOutputs': ['90.02', '90.03', '90.04', '90.05'],
        },
        openNativeChecks=[
            'Current native CPU/retentive ranges, full cross-reference including indirect and multiword extents',
            'Current HMI/SCADA external read/write bindings and scripts',
            'Comment span can contain several networks: one successful formatter call is not complete coverage',
            'Native Modbus table format, worker state and safe runtime schedule switch',
            'Apply STOP checks, fresh stopped feedback for installed drives, and idle owners/queues',
            'Native compile and 2/3/4 behavior in isolated copies; no equipment download in this workpack',
        ])


def prepare(source, output):
    source, output = Path(source), Path(output)
    # Exclusive output also refuses symlinks/hardlinks, including an input alias.
    if output.exists() or output.is_symlink() or output.resolve() == source.resolve():
        raise ValueError('Output must be a new file, different from the source')
    report = inspect(source)
    with output.open('x', encoding='utf8') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plc', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    report = prepare(args.plc, args.out)
    print('PLC05 workpack prepared; normal poll rows for N=2/3/4: 11/14/18.')
    print('Register block is a proposal, not allocated; native PLC/HMI unchanged.')


if __name__ == '__main__':
    main()
