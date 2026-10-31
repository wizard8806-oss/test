#!/usr/bin/env python3
"""Read-only source audit and native one-rung heartbeat edit specification."""
from _runtime import PLC
import hashlib
import json
import struct
from pathlib import Path

from check_native_drive_edit_02 import unpack

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/station-freshness-03'
SOURCE = PLC / 'station_MC_CM55_900G_03.pdw'
EXPECTED = '0c2c847b946f17c39290a056518235b2940a5a29dcc8813e3eadc33de6a4f69d'


def main():
    r = unpack(SOURCE)
    if hashlib.sha256(r['bytes']).hexdigest() != EXPECTED:
        raise ValueError('Unexpected map32 source')
    where = {name: pc for pc, name in r['rungs']}
    pc = where['95.161 | HMI_HEARTBEAT_ONE']
    if r['image'][pc:pc+2] != bytes.fromhex('4f92'):
        raise ValueError('Existing1s relay evidence changed')
    address = 0x0a00 + 2840 * 2
    hits = [offset for offset in range(0, len(r['image']) - 1, 2)
            if struct.unpack_from('>H', r['image'], offset)[0] == address]
    if hits:
        raise ValueError('Candidate heartbeat register already has encoded references')
    overlaps = []
    for table, spec in r['tables'].items():
        for i, row in enumerate(spec['rows']):
            if row[3] == 12 and row[4] <= 2840 < row[4] + row[2]:
                overlaps.append(dict(table=table, seq=i))
    if overlaps:
        raise ValueError('Heartbeat candidate overlaps a table receive buffer')
    report = dict(
        source=SOURCE.name, sourceSHA256=EXPECTED,
        nextCopyName='station_MC_CM55_900G_04.pdw',
        nativeProgramBlock='95_HMI_STATUS',
        insertBeforeNetwork='95.W032 | WORD_STATUS_VERSION',
        newNetwork='95.A100 | PLC_ALIVE_COUNTER',
        condition=dict(device='M1922', kind='Normally open', periodSeconds=1),
        function=dict(number=15, name='(+1)', pulse=True, doubleword=False,
                      D='R2840', auxiliaryOutputsConnected=False),
        mapVersionStays=32, counterWidth=16, readAsUnsigned=True,
        initialValue='Any word value is acceptable; no per-scan reset or extra reset rung',
        existingToggleR2328Preserved=True, CL50SIndependent=True,
        sourceEncodedR2840Matches=hits, tableRangeOverlaps=overlaps,
        sourceClockOperand='4f92',
        memoryEvidenceLimit='Direct encoded references and table ranges checked; no full external HMI/indirect-address audit is claimed',
        manuals=[
            dict(url='https://www.esea.cz/support/fatek/FBs_Manual/Manual_1/instruction/Chapter_2.pdf',
                 printedPage='2-4', evidence='M1922 is1s clock; R2840 is within general retentiveR0..R2999',
                 sha256='8384c1127dbccb08a8f3ef4b55dabd0d4b736435a55a5a51731893da4aa73535'),
            dict(url='https://www.esea.cz/support/fatek/FBs_Manual/Manual_1/instruction/Chapter_6.pdf',
                 printedPage='6-32', evidence='FUN15 (+1), Pulse0->1 execution and signed overflow wrapping; read raw word asuint16',
                 sha256='a6e44e7c6642e8ba92f37e47683b8f072493ad6ed1e356ec13cd74d376033c03'),
            dict(url='https://file.fatek.com/en/PLC/Software/Manual/WinProladder_Manual_en.pdf',
                 printedPage='2-4', evidence='Function Name accepts numeric function code; Pulse/32bits checkboxes, Alt+P/Alt+D')],
        ordinaryVFDPollRows=18, extraVFDPollRequests=0,
        extraOPCItem=dict(name='PlcAliveCounter', pduAddress=2840, access='ReadOnly', deviceType='uint16', serverType='uint32'),
        nativeEditObserved=False, nativeF8Observed=False, PLCWritePerformed=False,
        PDWPatchGenerated=False, deployable=False,
        nextUserStep='Edit saved copy only: insert one network before95.W032 with M1922->FUN15/Pulse/D=R2840/32bitsOFF, keep version32; F8,save,upload before any download')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'plc-counter-edit-spec.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Prepared1Hz native counter specification; source/table ranges checked; no PLC/file patch.')


if __name__ == '__main__':
    main()
