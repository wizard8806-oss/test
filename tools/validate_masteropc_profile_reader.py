#!/usr/bin/env python3
"""Offline fixtures: preserve repeated members, omit secrets, change no input."""
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

from _runtime import PWSH, ROOT
from review_masteropc_process_tags_01 import review


def main():
    # Repeated Node/Teg and Access members are intentional, as in native MBP.
    source = r'''{"NameInTree":"Сервер","Password":"SYNTHETIC_PRIVATE_FIELD",
"Script":"SYNTHETIC_SCRIPT_BODY",
"Node":{"NameInTree":"codex","Node":{"NameInTree":"Device1",
"Teg":{"Category":"Teg","NameInTree":"PressureSP_Command","Address":2100,"Region":"HOLDING_REGISTERS","Type":"uint32","TypeInDevice":"uint16","Access":"ReadWrite","Enabled":true,"TegCalculation":false,"KoffA":1,"KoffB":0,"Password":"SYNTHETIC_PRIVATE_FIELD"},
"Teg":{"Category":"Teg","NameInTree":"PressureSP_x100","Address":2360,"Access":"ReadOnly","KoffA":1,"KoffB":0},
"Teg":{"Category":"Teg","NameInTree":"PressureSP_Command","Address":9999,"Access":"ReadOnly","Access":"ReadWrite"},
"Teg":{"Category":"Teg","NameInTree":"Unrelated","Address":1234,"Password":"SYNTHETIC_PRIVATE_FIELD"}}},
"Node":{"NameInTree":"private-station-name","Teg":{"Category":"Teg","NameInTree":"PressureSP_Command","Address":777}}}'''
    expected_ids = ['codex.Device1.PressureSP_Command', 'codex.Device1.PressureSP_x100', 'codex.Device1.PressureSP_Command']
    cases = ['utf8', 'utf8_bom', 'cp1251', 'no_match', 'malformed', 'truncated_outer', 'trailing_comma', 'invalid_number', 'multiple_mbc', 'oversized', 'nested_field', 'calculation_body', 'ambiguous_node', 'not_zip', 'empty_archive']
    for case in cases:
        with tempfile.TemporaryDirectory(prefix='opc-profile-read-') as folder:
            root = Path(folder); path = root/'fixture.mbp'
            text = source
            if case == 'no_match': text = source.replace('"codex"', '"other"')
            if case == 'malformed': text = '{"Password":"SYNTHETIC_PRIVATE_FIELD",'
            if case == 'truncated_outer': text = source[:-1]
            if case == 'trailing_comma': text = source[:-1]+',}'
            if case == 'invalid_number': text = source.replace('"Address":2100', '"Address":02100')
            if case == 'nested_field': text = source.replace('"Address":2100', '"Address":{"Password":"SYNTHETIC_NESTED_FIELD"}')
            if case == 'calculation_body': text = source.replace('"TegCalculation":false', '"TegCalculation":"SYNTHETIC_CALCULATION_BODY"')
            if case == 'ambiguous_node': text = source.replace('"NameInTree":"Device1"', '"NameInTree":"Device1","NameInTree":"Other"')
            body = text.encode('cp1251' if case == 'cp1251' else 'utf-8')
            if case == 'utf8_bom': body = b'\xef\xbb\xbf'+body
            if case == 'oversized': body = b' ' * (4194304+1)
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
                if case != 'empty_archive': archive.writestr('fixture.mbc', body)
                if case == 'multiple_mbc': archive.writestr('other.mbc', b'{}')
            if case == 'not_zip': path.write_bytes(b'SYNTHETIC_PRIVATE_FIELD is not an archive')
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            env = dict(os.environ, XDG_CACHE_HOME=str(root/'cache'), XDG_CONFIG_HOME=str(root/'config'), XDG_DATA_HOME=str(root/'data'))
            p = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(ROOT/'tools/Read-MasterOpcProfile.ps1'), '-Path', str(path)], env=env, capture_output=True, text=True, timeout=20)
            assert hashlib.sha256(path.read_bytes()).hexdigest() == before
            assert not any(marker in p.stdout+p.stderr for marker in ['SYNTHETIC_PRIVATE_FIELD', 'SYNTHETIC_SCRIPT_BODY', 'SYNTHETIC_NESTED_FIELD', 'SYNTHETIC_CALCULATION_BODY', 'private-station-name']), (case, p.stdout, p.stderr)
            if case in ['malformed', 'truncated_outer', 'trailing_comma', 'invalid_number', 'multiple_mbc', 'oversized', 'ambiguous_node', 'not_zip', 'empty_archive']:
                assert p.returncode != 0 and not p.stdout.strip() and 'MASTEROPC_PROFILE_READ_FAILED' in p.stderr, (case, p.stdout, p.stderr)
                expected_stage = ('READ_FIELDS' if case == 'ambiguous_node' else
                                  'SELECT_MBC' if case in ['multiple_mbc','oversized','empty_archive'] else
                                  'OPEN_ARCHIVE' if case == 'not_zip' else 'VALIDATE_JSON')
                assert 'reader=2' in p.stderr and ('stage='+expected_stage) in p.stderr
                assert ' exception=' in p.stderr and ' hresult=0x' in p.stderr
            else:
                assert p.returncode == 0 and not p.stderr, (case, p.stdout, p.stderr)
                result = json.loads(p.stdout)
                assert result['sourceSHA256'] == before
                assert result['readerVersion'] == 2 and result['powerShellVersion']
                assert result['scope'] == 'OFFLINE_CANDIDATE_METADATA_ONLY'
                assert result['activeConfigurationEstablished'] is False
                assert result['liveOPCReadPerformed'] is False and result['hardwareCommandsSent'] is False
                tags = result['tags']
                if case == 'no_match': assert tags == []
                else:
                    assert [t['itemID'] for t in tags] == expected_ids
                    assert tags[2]['fields']['Access'] == ['ReadOnly', 'ReadWrite']
                    assert any(t['issue'] == 'REPEATED_TAG_NOT_COLLAPSED' for t in result['issues'])
                    if case == 'nested_field':
                        assert 'Address' not in tags[0]['fields']
                        assert any(t['issue'] == 'NON_SCALAR_OR_OVERLONG_FIELD_OMITTED' for t in result['issues'])
                    elif case == 'calculation_body':
                        assert 'TegCalculation' not in tags[0]['fields']
                        assert any(t['issue'] == 'NON_FLAG_CALCULATION_OMITTED' for t in result['issues'])
                    else:
                        # Cross-check with the existing independent Python MBP reader.
                        reference = [t for t in review(path)['codex_tags']
                                     if any(t['path'].endswith('.'+item) for item in expected_ids)]
                        for actual, prior in zip(tags, reference, strict=True):
                            for key, value in actual['fields'].items():
                                expected = prior[key]
                                if isinstance(expected, bool): expected = str(expected).lower()
                                elif isinstance(expected, list): expected = [str(x) for x in expected]
                                else: expected = str(expected)
                                assert value == expected, (case, key, value, expected)
            print('PASS offline profile reader', case, flush=True)
    print('PASS fifteen PowerShell/Linux fixture cases; safe stage/type/HRESULT diagnostics, no input changed or secret output; Windows5.1 v2 and actual bindings unverified')


if __name__ == '__main__':
    main()
