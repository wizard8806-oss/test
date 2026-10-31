"""Portable resource/tool locations; credentials are never configured here."""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCADA_SEED = ROOT / 'source/scada-seed-2.6.15'
PLC = ROOT / 'source/plc'
PWSH = os.environ.get('CODEX_PWSH') or shutil.which('pwsh') or str(ROOT / '.local-tools/pwsh/pwsh')


def fpc():
    value = os.environ.get('CODEX_FPC') or shutil.which('ppcx64') or shutil.which('fpc')
    if not value:
        raise RuntimeError('Install fp-compiler or set CODEX_FPC to ppcx64.')
    return Path(value).resolve()


def fpc_units(compiler):
    configured = os.environ.get('CODEX_FPC_UNITS')
    folder = Path(configured) if configured else compiler.parent / 'units/x86_64-linux'
    return [d for d in folder.iterdir() if d.is_dir()] if folder.is_dir() else []


def page_bindings(root, used):
    if os.environ.get('CODEX_PAGE_LOADER') != '1':
        return dict(skipped=True, reason='Optional vendor Editor 2.6.15 loader disabled; use --vendor-pages.',
                    existingPageObjects=None, referencedControls=len(used), nativeGUIF9=False)
    from verify_scada_native_loader_01 import read_pages
    names = {x['name'] for x in read_pages(root / 'artifacts/station-process-display-01/Pages.spg')['objects']}
    assert used <= names, used - names
    return dict(skipped=False, existingPageObjects=len(names), referencedControls=len(used), nativeGUIF9=False)
