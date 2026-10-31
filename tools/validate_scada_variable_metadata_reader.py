"""Read-only/safe-output and adverse-format tests for the offline PS reader."""
import hashlib
import json
import os
import struct
import subprocess
import tempfile
from pathlib import Path

from _runtime import ROOT, SCADA_SEED, PWSH
from verify_scada_variable_metadata_native import Layout

COMMAND = 'codex.Device1.PressureSP_Command'
MIRROR = 'codex.Device1.PressureSP_x100'
PRIVATE = 'SYNTHETIC_PRIVATE_METADATA_NOT_FOR_OUTPUT'


def text(value, wide=False):
    data = value.encode('utf-16le' if wide else 'utf8')
    return struct.pack('<I', len(data)//(2 if wide else 1))+data


def replace_text(raw, start, value, wide=False):
    count = struct.unpack_from('<I', raw, start)[0]
    end = start+4+count*(2 if wide else 1)
    return raw[:start]+text(value, wide)+raw[end:]


def fixture():
    raw = (SCADA_SEED/'Variables.svr').read_bytes()
    for index, address, name in [(-1, MIRROR, 'PressureMirror'), (-2, COMMAND, 'PressureCommand')]:
        record = Layout(raw).run().records[index]
        raw = replace_text(raw, record['address_position'], address, True)
        raw = replace_text(raw, record['start'], name)
    # Private fields exist in both a system variable and the selected command.
    for index in [-2, 0]:
        record = Layout(raw).run().records[index]
        raw = replace_text(raw, record['description_position'], PRIVATE, True)
    raw = raw.replace(text('InSAT.ModbusOPCServer.DA', True), text(PRIVATE, True))
    return raw


def main():
    valid = fixture()
    project = (SCADA_SEED/'Project.spr').read_bytes()
    cases = ['valid', 'offset_negative', 'offset_positive', 'use_scaling', 'use_bit',
             'internal_binding', 'duplicate_binding', 'missing_bindings', 'truncated',
             'trailing_bytes', 'overlong_string', 'unsupported_version', 'unsupported_ua',
             'duplicate_id', 'invalid_boolean', 'invalid_utf16', 'invalid_utf8',
             'group_limit', 'file_limit']
    failures = {'truncated', 'trailing_bytes', 'overlong_string', 'unsupported_version',
                'unsupported_ua', 'duplicate_id', 'invalid_boolean', 'invalid_utf16',
                'invalid_utf8', 'group_limit', 'file_limit'}
    for case in cases:
        raw, spr = bytearray(valid), bytearray(project)
        layout = Layout(raw).run(); command = layout.records[-2]
        if case == 'offset_negative': struct.pack_into('<b', raw, command['offset_position'], -2)
        if case == 'offset_positive': struct.pack_into('<b', raw, command['offset_position'], 1)
        if case == 'use_scaling': raw[command['offset_position']+1] = 1
        if case == 'use_bit': raw[command['address_position']+len(text(COMMAND, True))] = 3
        if case == 'internal_binding': raw[command['address_position']+len(text(COMMAND, True))+5] = 0
        if case == 'duplicate_binding': raw = replace_text(raw, layout.records[-1]['address_position'], COMMAND, True)
        if case == 'missing_bindings': raw = (SCADA_SEED/'Variables.svr').read_bytes()
        if case == 'truncated': del raw[-1:]
        if case == 'trailing_bytes': raw += b'\0'
        if case == 'overlong_string': struct.pack_into('<I', raw, 12, 0xffffffff)
        if case == 'unsupported_version': struct.pack_into('<H', spr, 12, 16)
        if case == 'unsupported_ua': raw[command['ua_position']] = 1
        if case == 'duplicate_id': struct.pack_into('<q', raw, layout.records[-1]['body']-8, command['id'])
        if case == 'invalid_boolean': raw[command['offset_position']+1] = 2
        if case == 'invalid_utf16': struct.pack_into('<H', raw, command['description_position']+4, 0xd800)
        if case == 'invalid_utf8': raw[command['start']+4] = 0xff
        if case == 'group_limit': struct.pack_into('<I', raw, 8, 1001)
        if case == 'file_limit': raw = bytes(8388609)
        with tempfile.TemporaryDirectory(prefix='scada-metadata-') as folder:
            root = Path(folder); candidate = root/'candidate'; candidate.mkdir()
            (candidate/'Variables.svr').write_bytes(raw); (candidate/'Project.spr').write_bytes(spr)
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in candidate.iterdir()}
            env = dict(os.environ, XDG_CACHE_HOME=str(root/'cache'),
                       XDG_CONFIG_HOME=str(root/'config'), XDG_DATA_HOME=str(root/'data'))
            result = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-File',
                                     str(ROOT/'tools/Read-ScadaVariableMetadata.ps1'),
                                     '-ProjectDirectory', str(candidate)],
                                    capture_output=True, text=True, timeout=25, env=env)
            assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in candidate.iterdir()} == before
            assert PRIVATE not in result.stdout+result.stderr
            assert 'InSAT.ModbusOPCServer.DA' not in result.stdout+result.stderr
            assert 'SysLicenseType' not in result.stdout+result.stderr
            if case in failures:
                assert result.returncode != 0 and not result.stdout.strip(), (case, result.stdout, result.stderr)
                assert 'SCADA_VARIABLE_METADATA_READ_FAILED reader=1 stage=' in result.stderr
                assert ' exception=' in result.stderr and ' hresult=0x' in result.stderr
            else:
                assert result.returncode == 0 and not result.stderr, (case, result.stdout, result.stderr)
                data = json.loads(result.stdout)
                assert data['scope'] == 'OFFLINE_CANDIDATE_METADATA_ONLY'
                assert data['activeProjectEstablished'] is False and data['hardwareCommandsSent'] is False
                assert data['liveOPCReadPerformed'] is False
                assert data['variablesSHA256'] == before['Variables.svr']
                assert data['projectSHA256'] == before['Project.spr']
                assert data['variablesParsed'] == 20 and data['groupsParsed'] == 2
                assert data['rawScalarScalingConfirmedInCandidate'] == (case == 'valid')
                if case == 'missing_bindings': assert data['tags'] == []
                else:
                    reference = [r for r in Layout(bytes(raw)).run().records if r['address'] in [COMMAND, MIRROR]]
                    for actual, expected in zip(data['tags'], reference, strict=True):
                        assert actual['itemID'] == expected['address']
                        assert actual['decimalOffset'] == expected['offset']
                        assert actual['decimalMultiplier'] == 10.0**expected['offset']
                        assert actual['decimalOffsetPosition'] == expected['offset_position']
                        assert actual['recordStart'] == expected['start'] and actual['recordEnd'] == expected['end']
            print('PASS offline SCADA variable reader', case, flush=True)
    print('PASS 19 PowerShell/Linux cases; sources unchanged, private fields omitted; Windows5.1/candidate09 not tested.')


if __name__ == '__main__':
    main()
