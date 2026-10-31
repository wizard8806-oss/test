#!/usr/bin/env python3
"""Build a guarded native-editor proposal; no PDW bytes or PLC are modified."""
from _runtime import PLC
import hashlib
import json
import struct
from pathlib import Path

from review_fatek_process_map_01 import review, u16

ROOT = Path(__file__).resolve().parents[1]
SOURCE = PLC / 'station_MC_CM55_CL50S_02.pdw'
OUT = ROOT / 'artifacts/fatek-drive-telemetry-02'
EXPECTED = '41e0788134b7cbd4fa6e0f8ab1b6515a9a396c5fdcef0b40b871d460e38f3dff'


def main():
    before = SOURCE.read_bytes()
    if hashlib.sha256(before).hexdigest() != EXPECTED:
        raise ValueError('Unexpected source: native edit proposal requires fresh review')
    r = review(SOURCE)
    table = next(t for t in r['master_tables'] if t['register'] == 'R5000')
    first = 0x106 + u16(before, 0x102)
    cipher = before[first + 4:first + 4 + u16(before, first + 2)]
    key = bytes(x ^ 255 for x in cipher[-1280:])
    image = bytes(x ^ key[i % 1280] for i, x in enumerate(cipher))
    words = [struct.unpack_from('>H', image, i)[0] for i in range(0, len(image), 2)]
    if any(0x0a00 + address * 2 in words for address in range(2800, 2832)):
        raise ValueError('Candidate R range has encoded matches; review before proposing')
    changes = []
    for drive in r['drive_frequency_exports']:
        number = drive['drive']
        old = table['rows'][drive['normal_poll_row'] - 1]
        expected = [number, 1, 1, 13, 200 + (number - 1) * 3, 4, 4100]
        if old != expected:
            raise ValueError('Existing frequency row changed')
        old_buffer = 0x4000 + old[4] * 2
        if words.count(old_buffer) != 1:
            raise ValueError('Frequency-buffer consumers require a new review')
        start = 2800 + (number - 1) * 8
        changes.append(dict(
            drive=number,
            nativeRowOneBased=drive['normal_poll_row'],
            nativeSeqZeroBased=drive['normal_poll_row'] - 1,
            beforeSerializedRow=old,
            beforeUI=dict(command='Read', slave=number, masterData='D' + str(old[4]),
                          dataSize=1, slaveHoldingPDU=4099,
                          slaveHoldingReference6Digit=404100),
            proposedUI=dict(command='Read', slave=number,
                            masterData='R' + str(start), dataSize=7,
                            slaveHoldingPDU=4096, slaveHoldingReference6Digit=404097),
            allocated=False,
            frequencyMOV=dict(
                label=next(x['label'] for x in r['mov_evidence']
                           if dict(source='D' + str(old[4]), destination='R' + str(drive['frequency_register'])) in x['moves']),
                oldSource='D' + str(old[4]),
                proposedSource='R' + str(start + 3),
                unchangedDestination='R' + str(drive['frequency_register'])),
            existingFrequencyStateRegister=drive['frequency_state_register'],
            proposedPayloadWords={
                'nativeState': start,
                'nativeFaultCode': start + 1,
                'frequencySetpointRaw': start + 2,
                'actualFrequencyRaw': start + 3,
                'speedRaw': start + 4,
                'outputVoltageRaw': start + 5,
                'outputCurrentRaw': start + 6},
            reservedUnusedWord=start + 7))
    report = dict(
        status='Native-editor proposal; memory allocation and user-native table form still pending',
        sourcePDWSHA256=EXPECTED,
        suggestedCopyName='station_MC_CM55_900G_03.pdw',
        tableName=table['name'], tableRegister=table['register'],
        commandRowsBefore=18, commandRowsProposed=18,
        normalPollRequestsAdded=0,
        candidateReceiveRange='R2800..R2831', candidateAllocated=False,
        changes=changes,
        proposedMapVersion=dict(register=2554, old=31, new=32,
                               label='95.W032 | WORD_STATUS_VERSION'),
        compatibility=[
            'Existing pressure registers and R2500..R2503/R2510..R2513 remain unchanged',
            'A future SCADA copy must accept32 and gate new fields on32; old map31 must never expose zero-filled candidates as valid current/no-fault',
            'Current SCADA03 expects31; do not download a new32 PLC revision before the compatible SCADA copy and native checks are ready',
            'R2510..R2513 are frequency display states, not independent generic telemetry-quality registers; confirm their recovery/range-filter behavior before treating them as common validity'
        ],
        newRungsRequiredByThisProposal=False,
        rationale='Receive the complete native block directly into candidate R words; retarget only the four existing MOV frequency sources, preserving their conditions and request order',
        unresolved=[
            'Verify candidate receive range against indirect/block access and the actual external HMI/OPC map',
            'Inspect actual native Edit dialog: command, Master Data R support, reference-address input format and count',
            'Verify full-response acceptance and stale/restart invalidation in native execution',
            'Complete map32-compatible SCADA display and ReadOnly item import after native address confirmation',
            'Native save/validation plus bench read/recovery before operation'
        ],
        nextUserStep='Offline Save As to a copy; open M900G_TEST/R5000; Edit first frequency-read row (currently D200/count1) and show dialog without changing or downloading',
        nativeTableFormObserved=False,
        PLCModified=False, PDWPatchGenerated=False, deployable=False)
    OUT.mkdir(parents=True, exist_ok=True)
    observation = OUT / 'native-dialog-observation-2026-10-30.json'
    if observation.exists():
        native = json.loads(observation.read_text())
        assert native['commandItemDialog'] == {
            'Slave Station': 1, 'Command': 'Read', 'Data Size': 1,
            'Master Data Start Address': 'D200', 'Slave Data Start Address': 404100}
        report.update(
            nativeTableFormObserved=True, nativeDialogObservation=observation.name,
            status='Native dialog and reference format confirmed; offline copy edit/review next; allocation still pending',
            nextUserStep='In saved copy only, change Seq0/3/16/17 to seven-word reads at404097 into candidate R2800/2808/2816/2824; retarget four MOV frequency sources and map32; save and upload copy for comparison before any PLC download')
    (OUT / 'native-edit-proposal.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    if SOURCE.read_bytes() != before:
        raise ValueError('Source unexpectedly changed')
    print('Prepared4 native row/MOV proposals;18 requests retained; source unchanged; no allocations or PLC download.')


if __name__ == '__main__':
    main()
