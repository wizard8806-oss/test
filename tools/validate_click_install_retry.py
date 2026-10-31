#!/usr/bin/env python3
"""Exercise the three pasteable recovery parts without reading real history."""
import base64
import gzip
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from _runtime import PWSH, SCADA_SEED
from build_radio_display_01 import bootstrap
from build_setpoint_click_fix_01 import OUT, SOURCE
from validate_radio_install_01 import hashes, parse_scripts

ROOT = Path(__file__).resolve().parents[1]
OLD_SHA = 'c0dd106e3fd82b338f561f9ab5322297a5b2b2d417118c98d3140c0d9239b3dc'
NEW_SHA = 'a176ed6d0a5fdcb6d3a8d7de61c3d0093190c10e2ad8e4b217e4022c658b60d7'


def main():
    helper = (ROOT / 'tools/retry_setpoint_click_install.ps1').read_text()
    one, two, three = re.split(r'^# PART [23]:[^\n]*\n', helper, flags=re.M)
    # Only synthetic in-memory Get-History entries; never read PSReadLine files.
    assert 'PSReadLine' not in helper and 'Get-History' in one
    fixed = (OUT / 'Install-Setpoint-Click-Fix-01.ps1').read_bytes()
    assert hashlib.sha256(fixed).hexdigest() == NEW_SHA
    old_line = re.search(r"\$old=@'\n(.*?)\n'@", two, re.S)[1]
    new_lines = re.search(r"\$new=@'\n(.*?)\n'@", two, re.S)[1]
    old = fixed.decode().replace(new_lines, old_line)
    assert hashlib.sha256(old.encode()).hexdigest() == OLD_SHA
    packet = bootstrap(old).replace('$radio', '$click')
    invalid = "$clickPacked=@'\n%invalid%\n'@"
    large = "$clickPacked=@'\n" + base64.b64encode(gzip.compress(b'A' * 20000)).decode() + "\n'@"
    cases = {
        'valid_lf': ([packet], '', True),
        'valid_crlf': ([packet.replace('\n', '\r\n')], '', True),
        'bad_newer_entries': ([packet, invalid, large, bootstrap(fixed.decode()).replace('$radio', '$click')], '', True),
        'empty_history': ([], '', False),
        'wrong_hash': ([bootstrap(old + '// changed').replace('$radio', '$click')], '', False),
        'malformed_only': ([invalid], '', False),
        'changed_after_recovery': ([packet], "$scadaRetryCode+='// changed'\n", False),
        'duplicate_patch_line': ([packet], "$scadaRetryCode+=$scadaRetryCode\n", False),
    }
    for case, (entries, mutate, expected) in cases.items():
        with tempfile.TemporaryDirectory(prefix='scada-retry-') as folder:
            root = Path(folder)
            prefix = "Clear-History\n"
            for index, entry in enumerate(entries):
                path = root / f'history-{index}.txt'
                path.write_bytes(entry.encode())
                prefix += ("Add-History -InputObject ([pscustomobject]@{CommandLine=[IO.File]::ReadAllText('" + str(path) + "');ExecutionStatus='Completed';StartExecutionTime=[DateTime]::Now;EndExecutionTime=[DateTime]::Now})\n")
            result_file = root / 'verified.ps1'
            probe = prefix + one + mutate + two
            probe += "\nif($scadaRetryReady){[IO.File]::WriteAllText('" + str(result_file) + "',$scadaRetryReady.ToString(),[Text.UTF8Encoding]::new($false))}\n"
            if not expected:
                probe += three
            runner = root / 'probe.ps1'
            runner.write_text(probe)
            env = dict(os.environ, XDG_CACHE_HOME=str(root/'cache'), XDG_CONFIG_HOME=str(root/'config'), XDG_DATA_HOME=str(root/'data'))
            proc = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(runner)], env=env, capture_output=True, text=True, timeout=20)
            assert proc.returncode == 0 and not proc.stderr, (case, proc.stdout, proc.stderr)
            assert result_file.exists() == expected, (case, proc.stdout)
            if expected:
                assert result_file.read_bytes() == fixed
                assert 'PART 1 OK' in proc.stdout and 'PART 2 OK' in proc.stdout
            else:
                assert 'STOP:' in proc.stdout and 'PART 2 OK' not in proc.stdout
            assert 'SAVED:' not in proc.stdout, 'Parts1/2 must not start the installer'
            if case == 'valid_lf':
                # Only after exact whole-installer hash verification, replace
                # Windows paths in a test copy and exercise the real installer.
                src = root / 'Current08'; dst = root / 'Desktop/codex_diag_09'
                shutil.copytree(SCADA_SEED, src); dst.parent.mkdir()
                (src/'Pages.spg').write_bytes((SOURCE/'Pages.spg').read_bytes())
                (src/'Scripts/Scripts.ssc').write_bytes((SOURCE/'Scripts.ssc').read_bytes())
                (src/'Users.fixture').write_text('synthetic preservation marker')
                before = hashes(src)
                code = result_file.read_text()
                code = re.sub(r'^\$clickTarget=.*$', lambda _: "$clickTarget='"+str(dst)+"'", code, count=1, flags=re.M)
                code = re.sub(r' \$candidates=@\(.*?\n \)', lambda _: " $candidates=@('"+str(src)+"')", code, count=1, flags=re.S)
                copy_runner = root/'copy.ps1'; copy_runner.write_text(code)
                proc = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(copy_runner)], env=env, capture_output=True, text=True, timeout=20)
                assert proc.returncode == 0 and not proc.stderr and 'SAVED:' in proc.stdout and 'ERROR:' not in proc.stdout, (proc.stdout, proc.stderr)
                assert hashes(src) == before
                new_rows = parse_scripts((dst/'Scripts/Scripts.ssc').read_bytes())
                old_rows = parse_scripts((src/'Scripts/Scripts.ssc').read_bytes())
                assert new_rows[1:3] == old_rows[1:3]
                assert new_rows[0][3] == (OUT/'scripts/StationDiagnostics.txt').read_text().splitlines()
                for name, digest in before.items():
                    if name == 'Scripts/Scripts.ssc' or name.startswith('Scripts/Compiled/'): continue
                    assert hashes(dst)[name] == digest
            print('PASS recovery', case, flush=True)
    print('PASS eight synthetic-history cases; verified installer copy preserves08; no hardware connections')


if __name__ == '__main__':
    main()
