#!/usr/bin/env python3
"""Rebuild/test an isolated copy of the publishable tree. No field connections."""
import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _runtime import ROOT, PWSH, fpc

BUILDERS = [
    'rebuild_scada_inline_delivery_01.py', 'build_radio_display_01.py',
    'build_radio_service_delivery_01.py', 'build_service_group_split_02.py',
    'build_process_display_01.py', 'build_drive_display_02.py',
    'build_station_freshness_03.py', 'build_station_mode_display_01.py',
    'build_setpoint_feedback_pdw_01.py', 'build_setpoint_display_01.py',
    'build_setpoint_control_01.py',
    'build_setpoint_click_fix_01.py',
    'build_native_operator_console_01.py',
]
CHECKS = [
    'validate_scada_inline_01.py', 'validate_radio_install_01.py',
    'validate_teleofis_radio_usb_probe_04.py', 'validate_teleofis_auth_capture_03.py',
    'validate_radio_display_01.py', 'validate_radio_service_delivery_01.py',
    'validate_service_group_split_02.py', 'validate_process_display_01.py',
    'validate_drive_display_02.py', 'validate_station_freshness_03.py',
    'validate_station_mode_display_01.py', 'validate_setpoint_feedback_01.py',
    'validate_setpoint_feedback_copy_01.py',
    'validate_setpoint_display_01.py',
    'validate_setpoint_control_01.py',
    'validate_setpoint_click_fix_01.py',
    'validate_click_install_retry.py',
    'validate_scada_variable_metadata_reader.py',
    'validate_native_operator_console_01.py',
    'validate_project_python_setup.py',
    'validate_native_ui_navigation.py',
    'validate_native_ui_event_probe.py',
    'validate_pressure_display_01.py',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, help='Write a JSON result outside the isolated build tree')
    parser.add_argument('--vendor-pages', action='store_true', help='Require separately supplied Editor.exe/demo/dependencies')
    parser.add_argument('--framework48', action='store_true', help='Also require CODEX_FRAMEWORK48_REFS')
    args = parser.parse_args()
    compiler = fpc()
    env = dict(os.environ, CODEX_FPC=str(compiler), CODEX_PWSH=str(Path(shutil.which(PWSH) or PWSH).resolve()),
               CODEX_PAGE_LOADER='1' if args.vendor_pages else '0', PYTHONDONTWRITEBYTECODE='1')
    if shutil.which(PWSH) is None and not Path(PWSH).is_file():
        raise SystemExit('PowerShell unavailable: run bash tools/setup_dev.sh or set CODEX_PWSH.')
    files = sorted(set(subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT
    ).decode().split('\0')) - {''})
    before = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files if (ROOT/name).is_file()}
    results = []
    with tempfile.TemporaryDirectory(prefix='station-checks-') as name:
        work = Path(name)
        for path in before:
            target = work / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/path, target)
        # Git placeholders represent empty Windows project directories.
        # They are not runtime project files and must not enter preservation fixtures.
        for placeholder in (work/'source/scada-seed-2.6.15').rglob('.gitkeep'):
            placeholder.unlink()
        for path in work.glob('tools/*.py'):
            ast.parse(path.read_text(), filename=path.name)
        resources = json.loads((work/'source/resources.json').read_text())['resources']
        for entry in resources:
            assert hashlib.sha256((work/'source'/entry['path']).read_bytes()).hexdigest() == entry['sha256']

        def run(label, command):
            print('RUN', label, flush=True)
            task_env = dict(env, XDG_CACHE_HOME=str(work/'cache'), XDG_CONFIG_HOME=str(work/'config'), XDG_DATA_HOME=str(work/'data'))
            result = subprocess.run(command, cwd=work, env=task_env, text=True, capture_output=True, timeout=300)
            if result.returncode or result.stderr:
                print(result.stdout[-5000:], result.stderr[-5000:], flush=True)
                raise RuntimeError(label + ' failed')
            results.append(dict(check=label, passed=True, output=result.stdout.strip()))
            print('PASS', label, flush=True)

        for builder in BUILDERS:
            run(builder, [sys.executable, str(work/'tools'/builder)])
        # Parse every PowerShell source/template and rebuilt delivery without executing it.
        ps = work/'parse-all.ps1'
        ps.write_text("""$ErrorActionPreference='Stop'
$count=0
Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1' -File -Recurse | Where-Object { $_.Name -notlike '*_template.ps1' } | ForEach-Object {
 $tokens=$null;$errors=$null
 [void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$tokens,[ref]$errors)
 if($errors.Count -gt 0){throw ('PowerShell parse failed: '+$_.Name)}
 $count++
}
Write-Host ('Parsed PowerShell files: '+$count)
""")
        run('PowerShell syntax', [PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(ps)])
        for check in CHECKS:
            run(check, [sys.executable, str(work/'tools'/check)])
        # Check the candidate against the actual native source in addition to mutation fixtures.
        run('native PDW feedback comparison', [sys.executable, str(work/'tools/check_setpoint_feedback_01.py'),
            str(work/'artifacts/station-setpoint-feedback-01/station_MC_CM55_900G_05.pdw'), '--out', str(work/'native-check.json')])
        if args.framework48:
            run('Framework4.8 compatibility', [sys.executable, str(work/'tools/validate_service_xml_reference_01.py')])
        # Hash all shipped sources after rebuilding, including generated-but-retained modules.
        rebuilt = [n for n in before if n.endswith('.ps1') or '/scripts/' in n or n.endswith('route-core.txt')]
        for path in rebuilt:
            assert hashlib.sha256((work/path).read_bytes()).hexdigest() == before[path], ('Rebuilt source differs', path)
    for path, digest in before.items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == digest, ('Working source changed', path)
    report = dict(date='2026-10-31', passed=True, isolated=True, shippedFiles=len(before),
                  resourceHashesVerified=len(resources), sourceFilesUnchanged=True,
                  vendorPageLoader=args.vendor_pages, framework48=args.framework48,
                  noHardwareOrCloudSessionOpened=True, checks=results,
                  notTested=['Windows GUI/F8/F9', 'PLC download or physical outputs', 'Live setpoint feedback'])
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print('PASS:', len(results), 'build/check groups; source tree unchanged. Windows/PLC checks are separate.')


if __name__ == '__main__':
    main()
