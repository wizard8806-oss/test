#!/usr/bin/env python3
"""Adverse metadata checks; these do not simulate native SCADA or its archive."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from review_oshsky_scada_r3 import expected_bindings, public_source_findings, review


def main():
    expected = expected_bindings()
    assert len(expected) == 74
    assert [expected[f'current_{i}']['pduAddress'] for i in range(1, 5)] == [2504, 2505, 2506, 2507]
    assert [expected[f'minutes_hi_{i}']['pduAddress'] for i in range(1, 5)] == [2201, 2203, 2205, 2207]
    assert expected['cascade_add3']['pduAddress'] == 2884 and expected['cascade_add4']['pduAddress'] == 2885
    assert expected['cascade_alive']['pduAddress'] == 3125
    assert [k for k, r in expected.items() if r['access'] != 'ReadOnly'] == ['sp_command']
    valid = dict(schemaVersion=1, bindings=list(expected.values()))
    assert review(valid)['metadataMatchesSuppliedInventory']
    cases = 1
    for key in ('current_1', 'current_4', 'minutes_hi_4', 'sp_command', 'cascade_alive', 'map'):
        for field, value in (('pduAddress', 2806), ('access', 'WriteOnly'), ('region', 'COILS'),
                ('deviceType', 'int16'), ('serverType', 'int16'), ('decimalOffset', -1),
                ('scalingEnabled', True), ('useBit', 0), ('scadaExternal', False), ('pduAddress', '2504')):
            bad = copy.deepcopy(valid)
            next(row for row in bad['bindings'] if row['logicalId'] == key)[field] = value
            assert not review(bad)['metadataMatchesSuppliedInventory'], (key, field)
            cases += 1
    for index in range(len(valid['bindings'])):
        bad = copy.deepcopy(valid); bad['bindings'].pop(index)
        assert any(row['problem'] == 'missing' for row in review(bad)['issues'])
        cases += 1
    bad = copy.deepcopy(valid); bad['bindings'].append(dict(expected['map']))
    assert any(row['problem'] == 'duplicate' for row in review(bad)['issues'])
    cases += 1
    secret = 'SYNTHETIC_PRIVATE_ENDPOINT_DO_NOT_PUBLISH'
    bad['bindings'][0]['pduAddress'] = secret
    assert secret not in json.dumps(review(bad))
    findings = public_source_findings()
    assert findings['legacyVfd1CurrentRawPdu'] == 2806
    assert not findings['currentFeatureAliasPresent'] and not findings['cascadeFeatureAliasPresent']
    assert findings['nativeScadaVerified'] is False
    with tempfile.TemporaryDirectory(prefix='oshsky-scada-review-') as folder:
        p = Path(folder); source = p / 'bindings.json'; target = p / 'report.json'
        source.write_text(json.dumps(valid))
        original = source.read_bytes()
        command = [sys.executable, '-B', str(Path(__file__).with_name('review_oshsky_scada_r3.py')),
                   '--bindings', str(source), '--report', str(target)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        assert json.loads(target.read_text())['nativeScadaVerified'] is False
        before = target.read_bytes()
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        assert result.returncode != 0 and target.read_bytes() == before and source.read_bytes() == original
        cases += 2
    print(f'Oshsky SCADA r3 review: {cases} metadata cases PASS; no native/runtime/archive verification')


if __name__ == '__main__':
    main()
