#!/usr/bin/env python3
"""Run actual PowerShell copy/guard checks without native GUI or PLC access."""
from _runtime import PWSH as PWSH_RUNTIME
import base64
import gzip
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from prepare_setpoint_feedback_01 import SOURCE, OUT

PWSH = PWSH_RUNTIME


def main():
    source = SOURCE.read_bytes()
    expected = (OUT / 'station_MC_CM55_900G_05.pdw').read_bytes()
    installer = (OUT / 'Create-Setpoint-Feedback-Copy-01.ps1').read_text()
    metadata = json.loads((OUT / 'offline-file-generation.json').read_text())
    reports = []
    cases = ['normal', 'unicode_space_quote_path', 'changed_source', 'same_target_exists',
             'different_target_exists', 'target_is_source', 'corrupt_patch', 'wrong_output_hash',
             'missing_source', 'read_only_source']
    for case in cases:
        with tempfile.TemporaryDirectory(prefix='sp-pdw-copy-') as name:
            root = Path(name)
            source_dir = root / ("Станция user's files" if case == 'unicode_space_quote_path' else 'Original project')
            source_dir.mkdir()
            original = source_dir / 'station_MC_CM55_900G_04.pdw'
            original.write_bytes(source)
            destination = root / 'Desktop/codex_plc_sp_feedback_01'
            target = destination / 'station_MC_CM55_900G_05.pdw'
            before = source
            code = installer
            if case == 'changed_source':
                before = b'X' + source[1:]
                original.write_bytes(before)
            elif case == 'same_target_exists':
                destination.mkdir(parents=True)
                target.write_bytes(expected)
            elif case == 'different_target_exists':
                destination.mkdir(parents=True)
                target.write_bytes(b'preserve this edited native project')
            elif case == 'target_is_source':
                renamed = source_dir / 'station_MC_CM55_900G_05.pdw'
                original.rename(renamed)
                original = renamed
                destination = source_dir
                target = original
            elif case == 'corrupt_patch':
                packed = base64.b64encode((OUT / 'native-file.patch.gz').read_bytes()).decode()
                code = code.replace(packed, 'AAAA' + packed[4:])
            elif case == 'wrong_output_hash':
                code = code.replace(metadata['targetSHA256'], '0' * 64)
            elif case == 'missing_source':
                original.unlink()
            elif case == 'read_only_source':
                original.chmod(0o444)
            script = root / 'copy.ps1'
            script.write_text(code)
            env = os.environ | {k: str(root / folder) for k, folder in
                                [('XDG_CACHE_HOME', 'cache'), ('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data')]}
            run = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(script),
                                  '-SourcePath', str(original), '-OutputDirectory', str(destination)],
                                 env=env, capture_output=True, text=True, timeout=25)
            assert run.returncode == 0 and not run.stderr, (case, run.stdout, run.stderr)
            if case != 'missing_source':
                assert original.read_bytes() == before, (case, 'source altered')
            else:
                assert not original.exists()
            success = case in ['normal', 'unicode_space_quote_path', 'same_target_exists', 'different_target_exists', 'read_only_source']
            if success:
                assert 'SAVED:' in run.stdout and 'ERROR:' not in run.stdout, (case, run.stdout)
                if case == 'different_target_exists':
                    assert target.read_bytes() == b'preserve this edited native project'
                    actual = Path(str(destination) + '_2') / target.name
                else:
                    actual = target
                assert actual.read_bytes() == expected, (case, 'output differs')
            else:
                assert 'ERROR:' in run.stdout and 'SAVED:' not in run.stdout, (case, run.stdout)
                if case != 'target_is_source':
                    assert not target.exists(), (case, 'unexpected output')
            assert not list(root.rglob('*.tmp-*')), (case, 'temporary file left')
            reports.append(dict(case=case, passed=True))
            print('PASS PowerShell', case, flush=True)
    paste = (OUT / 'Paste-Setpoint-Feedback-Copy-01.ps1').read_text()
    packed = paste.split("$spCopyPacked=@'\n", 1)[1].split("\n'@", 1)[0]
    decoded = gzip.decompress(base64.b64decode(packed))
    assert decoded == installer.encode()
    assert hashlib.sha256(decoded).hexdigest() == metadata['installerSHA256']
    (OUT / 'powershell-copy-validation.json').write_text(json.dumps(dict(
        date='2026-10-31', cases=reports, inlinePayloadExactlyVerified=True,
        nativeWindowsFilePickerTested=False, nativeF8Tested=False, actualPLCUpdatePerformed=False,
        method='Actual PowerShell7/Linux with explicit paths; Windows-only file chooser bypassed in tests'),
        ensure_ascii=False, indent=2) + '\n')
    print('All ten PowerShell cases and exact inline payload passed; native F8/save still required.')


if __name__ == '__main__':
    main()
