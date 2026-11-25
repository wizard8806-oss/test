#!/usr/bin/env python3
"""Check a sanitized binding inventory against the Oshsky r3 contract.

No OPC/Modbus connection, native project change, or secret/endpoint output.
A matching supplied export is metadata evidence, not runtime verification.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'docs/interfaces/oshsky-scada-r3-registers.csv'


def expected_bindings():
    rows = list(csv.DictReader(CONTRACT.open(encoding='utf8', newline='')))
    result = {}
    for row in rows:
        key = row['logicalId']
        if key in result:
            raise ValueError('Duplicate logical contract item')
        result[key] = dict(logicalId=key, pduAddress=int(row['pduAddress']),
            region='HOLDING_REGISTERS', deviceType='uint16', serverType='uint32',
            access=row['access'], scadaExternal=True, decimalOffset=0,
            scalingEnabled=False, useBit=-1)
    return result


def review(document):
    expected = expected_bindings()
    if not isinstance(document, dict) or document.get('schemaVersion') != 1:
        raise ValueError('Expected sanitized schemaVersion1 inventory')
    rows = document.get('bindings')
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('Invalid binding inventory')
    selected, unrelated, issues = {}, 0, []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid inventory row')
        key = row.get('logicalId')
        if not isinstance(key, str) or key not in expected:
            unrelated += 1
            continue
        if key in selected:
            issues.append(dict(logicalId=key, problem='duplicate'))
        selected[key] = row
    for key, wanted in expected.items():
        actual = selected.get(key)
        if actual is None:
            issues.append(dict(logicalId=key, problem='missing'))
            continue
        for field, value in wanted.items():
            # Reject ambiguous JSON booleans and numeric/string coercions.
            if type(actual.get(field)) is not type(value) or actual[field] != value:
                issues.append(dict(logicalId=key, problem='mismatch', field=field))
    return dict(schemaVersion=1, expectedBindings=len(expected), suppliedRequiredBindings=len(selected),
        unrelatedRows=unrelated, metadataMatchesSuppliedInventory=not issues, issues=issues,
        nativeScadaVerified=False, nativeOpcVerified=False, liveTagQualityVerified=False,
        plcProgramInCabinetVerified=False, writesPerformed=0,
        limits=['Only supplied metadata; no verification of export provenance or runtime',
                'Binding types/offsets/access do not prove freshness, scaling in scripts, or archive gaps'])


def public_source_findings():
    tags = json.loads((ROOT / 'artifacts/station-drive-display-02/masteropc-new-tags.json').read_text())
    script = (ROOT / 'artifacts/station-setpoint-click-fix-01/scripts/StationDiagnostics.txt').read_text()
    ui = (ROOT / 'ui/native-console/OperatorConsole.txt').read_text()
    return dict(scope='Published source only; actual Windows SCADA11 may differ',
        legacyVfd1CurrentRawPdu=next(x['pdu_address'] for x in tags if x['name'] == 'Vfd1CurrentRaw'),
        expectedR3CurrentPdu=[2504, 2505, 2506, 2507],
        publishedDiagnosticReadsVfd1CurrentRaw="ProcessWord('Vfd1CurrentRaw', CurrentRaw)" in script,
        currentFeatureAliasPresent='CurrentExportVersion' in script,
        cascadeFeatureAliasPresent='CascadeExportVersion' in script,
        publishedOverviewMentionsVfd4='Vfd4' in ui,
        nativeScadaVerified=False, writesPerformed=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bindings', type=Path, help='Private sanitized metadata inventory')
    parser.add_argument('--report', type=Path, help='New report path, never overwrites an input')
    args = parser.parse_args()
    if args.report and (args.report.exists() or args.report.is_symlink() or
                        (args.bindings and args.report.resolve() == args.bindings.resolve())):
        parser.error('Report must be a NEW regular file, distinct from the input')
    if args.bindings:
        data = args.bindings.read_bytes()
        if len(data) > 8 * 1024 * 1024:
            parser.error('Binding inventory exceeds8MiB')
        result = review(json.loads(data))
        if args.bindings.read_bytes() != data:
            raise ValueError('Input changed during read-only review')
        result['inventorySHA256'] = hashlib.sha256(data).hexdigest()
    else:
        result = public_source_findings()
        result['expectedBindings'] = len(expected_bindings())
    output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        with args.report.open('x', encoding='utf8') as stream:
            stream.write(output)
    print(output, end='')
    return 2 if result.get('metadataMatchesSuppliedInventory') is False else 0


if __name__ == '__main__':
    raise SystemExit(main())
