#!/usr/bin/env python3
"""Exercise the read-only probe with reviewed profiles and rejected inputs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from _runtime import ROOT, SCADA_SEED, PWSH


def check():
    source = SCADA_SEED / 'Servers.ssr'
    before = source.read_bytes()
    enabled = bytearray(before)
    enabled[236] = 0
    changed = bytearray(before)
    changed[20] ^= 1
    invalid = bytearray(before)
    invalid[236] = 2
    private = bytearray(before)
    marker = b'PRIVATE_FIXTURE_DO_NOT_PRINT'
    private[24:24+len(marker)] = marker
    cases = [('read_only', before, True), ('write_enabled', enabled, False),
             ('unreviewed', changed, None), ('truncated', before[:-1], None),
             ('trailing', before+b'X', None), ('invalid_flag', invalid, None),
             ('private_unknown', private, None), ('missing', None, None)]
    results = []
    for name, raw, expected in cases:
        with tempfile.TemporaryDirectory(prefix='opc-write-gate-') as folder:
            p = Path(folder)
            target = p / 'Servers.ssr'
            if raw is not None:
                target.write_bytes(raw)
            env = dict(os.environ, XDG_CACHE_HOME=str(p/'cache'),
                       XDG_CONFIG_HOME=str(p/'config'), XDG_DATA_HOME=str(p/'data'))
            proc = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-NonInteractive',
                                   '-File', str(ROOT/'tools/Read-ScadaOpcWriteGate.ps1'),
                                   '-Path', str(target)], capture_output=True, text=True,
                                  env=env, timeout=20)
            assert marker.decode() not in proc.stdout + proc.stderr
            if expected is None:
                assert proc.returncode != 0 and not proc.stdout.strip(), (name, proc.stdout, proc.stderr)
                assert 'SCADA_OPC_WRITE_GATE_READ_FAILED' in proc.stderr
            else:
                assert proc.returncode == 0 and not proc.stderr, (name, proc.stdout, proc.stderr)
                data = json.loads(proc.stdout)
                assert data['connectionReadOnly'] is expected
                assert data['sourceUnchanged'] and not data['hardwareWriteTested']
                assert not data['activeRuntimeSettingEstablished']
                assert data['fileSHA256'] == hashlib.sha256(raw).hexdigest()
            assert (target.read_bytes() == raw) if raw is not None else not target.exists()
            results.append(dict(case=name, passed=True))
    assert source.read_bytes() == before
    return results


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
