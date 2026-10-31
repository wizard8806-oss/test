#!/usr/bin/env python3
"""Prepare seven native-editor feedback mirrors; never patch a PDW or PLC."""
from _runtime import PLC
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

from check_native_drive_edit_02 import unpack

ROOT = Path(__file__).resolve().parents[1]
SOURCE = PLC / 'station_MC_CM55_900G_04.pdw'
EXPECTED = 'a25f9b5d2fe006bcb039896bae3989569b08e1b1adc4b503a755bfd5e3b22993'
OUT = ROOT / 'artifacts/station-setpoint-feedback-01'
ANCHOR = '95.W032 | WORD_STATUS_VERSION'


def networks():
    rows = [
        ('SP_FEEDBACK_VERSION', '1', 'R2850', 'SpFeedbackVersion'),
        ('SP_CONFIRMED_DRIVE', 'D672', 'R2851', 'SpConfirmedDrive'),
        ('SP_CONFIRMED_PRESSURE', 'D673', 'R2852', 'SpConfirmed_x100'),
        ('SP_APPLY_PHASE', 'D670', 'R2853', 'SpApplyPhase'),
        ('SP_APPLY_ERROR', 'D676', 'R2854', 'SpApplyError'),
        ('SP_APPLY_DETAIL', 'D677', 'R2855', 'SpApplyDetail'),
        ('SP_APPLY_FLAGS', 'WM968', 'R2856', 'SpApplyFlags'),
    ]
    result = []
    for number, (name, source, destination, tag) in enumerate(rows, 1):
        if source.isdecimal():
            op, value = 0xf5ac, int(source)
        elif source.startswith('D'):
            op, value = 0xf4ac, 0x4000 + 2 * int(source[1:])
        else:
            assert source == 'WM968'
            # Independently decoded as WM968 by the original vendor formatter.
            op, value = 0xf4ac, 0x097b
        code = struct.pack('>4H', 0x4fe8, op, value, 0x0a00 + 2 * int(destination[1:]))
        result.append(dict(label=f'95.SP{number:03d} | {name}', source=source, destination=destination,
                           function=8, Pulse=False, bits32=False, enable='Unconditional',
                           expectedCodeHex=code.hex(), tagName=tag))
    return result


def memory_review(old, cache):
    if cache['sourceSHA256'] != EXPECTED or cache['failures']:
        raise ValueError('Incomplete or wrong-source vendor mnemonic cache')
    rows = cache['networks']
    if [(r['pc'], r['label']) for r in rows] != old['rungs']:
        raise ValueError('Native mnemonic sequence differs from source')
    for i, row in enumerate(rows):
        end = old['rungs'][i + 1][0] if i + 1 < len(rows) else row['pc'] + 16
        if old['image'][row['pc']:end].hex() != row['codeHex']:
            raise ValueError('Mnemonic-cache code differs from source')
    references = [r['label'] for r in rows if re.search(r'\bR28(?:4[89]|5[0-9])\b', r['mnemonics'])]
    if references:
        raise ValueError('Feedback range or immediate neighbor referenced: ' + repr(references))
    indirect = [(r['label'], line.strip()) for r in rows for line in r['mnemonics'].splitlines()
                if re.search(r':\s*(?:P[0-9]|V\b|Z\b)|:\s*(?:R|D|WM|WS|WX|WY)\d+\s*[+\[PVZ]', line)]
    if indirect:
        raise ValueError('Indirect operands require manual allocation review: ' + repr(indirect[:5]))
    transfers = []
    for row in rows:
        for part in row['mnemonics'].split('FUN   103 _.BT_M')[1:]:
            source = re.search(r'Ts:\s+([A-Z]+)(\d+)', part)
            target = re.search(r'Td:\s+([A-Z]+)(\d+)', part)
            length = re.search(r'L :\s+(\d+)', part)
            if not (source and target and length):
                raise ValueError('Unresolved block-transfer operands')
            count = int(length[1])
            for match in (source, target):
                if match[1] == 'R' and max(2850, int(match[2])) < min(2857, int(match[2]) + count):
                    raise ValueError('Block-transfer overlaps feedback range')
            transfers.append(dict(label=row['label'], source=source[0], target=target[0], words=count))
    tables = []
    for register, table in old['tables'].items():
        if max(2850, int(register[1:])) < min(2857, int(register[1:]) + 1 + 7 * len(table['rows'])):
            raise ValueError('Table image overlaps feedback range')
        for number, row in enumerate(table['rows']):
            if row[3] == 12 and max(2850, row[4]) < min(2857, row[4] + row[2]):
                raise ValueError('Existing Modbus local R buffer overlaps feedback range')
        tables.append(register)
    return dict(sourceNetworksVendorFormatted=len(rows), directOrNeighborReferences=references,
                blockTransfersChecked=transfers, indirectOperandsFound=indirect,
                masterTablesChecked=tables, candidateRange='R2850..R2856',
                existingExternalHMIMapIndependentlyAudited=False,
                scope='All supplied program network mnemonics, explicit block extents and nine supplied Modbus tables; separate external HMI files were not supplied')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vendor-dll', type=Path, required=True)
    parser.add_argument('--network-cache', type=Path, required=True)
    args = parser.parse_args()
    before = SOURCE.read_bytes()
    if hashlib.sha256(before).hexdigest() != EXPECTED:
        raise ValueError('Different native source; review before proposing exports')
    old = unpack(SOURCE)
    memory = memory_review(old, json.loads(args.network_cache.read_text()))
    from render_fatek_network_01 import render, VENDOR_SHA256
    plan = networks()
    for row in plan:
        row['vendorMnemonics'] = render(bytes.fromhex(row['expectedCodeHex']), args.vendor_dll)
        text = re.sub(r'\s+', ' ', row['vendorMnemonics'])
        for expected in ('ORG SHORT', 'FUN 08 _.MOV', 'S : ' + row['source'], 'D : ' + row['destination']):
            if expected not in text:
                raise ValueError('Vendor formatter disagrees with proposed MOV: ' + repr(row))
    report = dict(date='2026-10-31', sourceFile=SOURCE.name, sourceSHA256=EXPECTED,
                  proposedCopy='station_MC_CM55_900G_05.pdw', programBlock='95_HMI_STATUS',
                  insertImmediatelyBefore=ANCHOR, mapVersionRemains=32, addedNetworks=plan,
                  addedProgramBytes=sum(len(bytes.fromhex(r['expectedCodeHex'])) for r in plan),
                  existingTablesAndWorkerQueueMustRemainUnchanged=True, newDrivePollRequests=0,
                  scalarSetpointWriteInput='R2100, no new write binding enabled by this proposal',
                  feedbackMeaning='Current coordinator state and its verified leading-drive cache, not a PLC request-ID acknowledgment',
                  flags=dict(source='WM968', bit0='M968: setpoint-application failure latch',
                             bit1='M969: current leading drive and current setpoint are verified',
                             rawWordPreserved=True, bothSuccessAndFailureMustBeRejected=True,
                             otherBits='M970..M983; do not decode without their individual contract'),
                  memoryReview=memory, formatterSHA256=VENDOR_SHA256,
                  PLCModified=False, sourceFileChanged=False, nativeEditorF8Observed=False,
                  nextStep='Native Save As05; add seven unconditional16bit/nonpulse MOV networks; F8/save/upload for comparison before the bench program update')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'native-edit-proposal.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    tags = [dict(name=r['tagName'], pduAddress=int(r['destination'][1:]), region='HOLDING_REGISTERS',
                 deviceType='uint16', serverType='uint32', access='ReadOnly', scalingEnabled=False) for r in plan]
    (OUT / 'masteropc-feedback-tags.json').write_text(json.dumps(tags, ensure_ascii=False, indent=2) + '\n')
    assert SOURCE.read_bytes() == before
    print('Prepared seven native-verified MOV mirrors;1834 existing networks/11 block copies/9 tables reviewed; no PDW or PLC changes.')


if __name__ == '__main__':
    main()
