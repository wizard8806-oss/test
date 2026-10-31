#!/usr/bin/env bash
# Install a pinned, checksum-checked PowerShell locally; no hardware connections.
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
task_tools="$task_root/.local-tools"
task_pwsh_version=7.5.4
task_archive="powershell-$task_pwsh_version-linux-x64.tar.gz"
task_release="https://github.com/PowerShell/PowerShell/releases/download/v$task_pwsh_version"
mkdir -p "$task_tools/pwsh"
if [[ ! -x "$task_tools/pwsh/pwsh" ]]; then
  task_download="$(mktemp -d)"
  trap 'rm -rf -- "$task_download"' EXIT
  curl -fLsS "$task_release/$task_archive" -o "$task_download/$task_archive"
  curl -fLsS "$task_release/hashes.sha256" -o "$task_download/hashes.sha256"
  python3 - "$task_download" "$task_archive" <<'PY'
import hashlib, re, sys
from pathlib import Path
p, name = Path(sys.argv[1]), sys.argv[2]
raw = (p/'hashes.sha256').read_bytes()
text = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
matches = [line for line in text.splitlines() if line.strip().endswith(name)]
if len(matches) != 1:
    raise SystemExit('Release checksum entry is missing or ambiguous')
expected = re.match(r'([a-fA-F0-9]{64})\s', matches[0])
if not expected or hashlib.sha256((p/name).read_bytes()).hexdigest() != expected[1].lower():
    raise SystemExit('PowerShell release checksum mismatch')
PY
  tar -xzf "$task_download/$task_archive" -C "$task_tools/pwsh"
  chmod +x "$task_tools/pwsh/pwsh"
fi
printf '%s\n' 'PowerShell installed under .local-tools/pwsh (ignored by Git).'
printf '%s\n' 'For Pascal checks install fp-compiler, or set CODEX_FPC/CODEX_FPC_UNITS.'
