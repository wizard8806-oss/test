# Station11: file probe prepared and compiled; runtime gate remains closed

02.11.2026, Windows, Simple-Scada Editor/Server/Client 2.6.15.0, Python
3.13.17. Branch `codex/project-handoff-2026-10-31`, verified base
`f1cf0f1ae03467087fe8676206d7e7084f2ac501`. Read current `AGENTS.md`,
`docs/HANDOFF.md` and `docs/tasks/station11-file-probe-resume.md`.

## Preparation and source preservation

The existing Editor RAM state was not saved over `codex_diag_11`. Using
Editor **Save project as**, it was saved under the distinct name
`codex_diag_11_UNVERIFIED-unsaved_20261102T1432Z` in the Simple-Scada project
catalog. Its DACL was restricted recursively to the current user and SYSTEM;
the private SHA256 manifest is
`%LOCALAPPDATA%\CodexBackups\SCADA11Preparation\UNVERIFIED-unsaved_20261102T1432Z\sha256-manifest.json`
(manifest SHA256 `0abcd34fea0922b23e0dfc998c379fa06f603187d06546105d3ad78ace70bb55`).
Save As omitted the small `ArcSystem.sar`; that unchanged file was copied from
disk11 into this separate snapshot. The snapshot has 14 files. Compared with
disk11, only the expected renamed `Project.spr` and compiled cache
`Scripts/Compiled/program.exs` differ; the remaining files match. This remains
an **UNVERIFIED** model snapshot, not a new accepted candidate.

The original disk11 stayed unchanged: `Pages.spg` SHA256
`9826694fa750e9dc4be4db7f0d62d3e2d27affb54300dba65a83ae313964d169` and
`Scripts/Scripts.ssc` SHA256
`bc200efeb4d147a366aea3d6b5e134e9c1f7bbb70dbd001295424a89d861270d` still
match the pinned files.

The read-only file helper prepared probe ID
`UINAV11-202611021729144FDC71` from disk11 at
`%LOCALAPPDATA%\CodexCandidates\SCADA11\codex_diag_11_probe_202611021729144fdc71`.
It reported `PREPARED`, source unchanged, and explicitly excluded the Editor
RAM snapshot. Because the Editor's Open Projects list cannot browse to AppData,
the prepared files were copied to the new catalog path
`%USERPROFILE%\Documents\Simple-Scada 2\Projects\codex_diag_11_probe_202611021729144fdc71`.
The 12 copied project files matched the AppData probe byte-for-byte before
native compile; the catalog copy's recursive DACL allows only the current user
and SYSTEM. Both probe copies are separate from disk11, working10 and Git.

## Native compile and preservation checks

The selected Editor title showed the exact probe ID. **Compile All** completed
with Editor status `Компиляция завершена!`; the project then showed
`Проект успешно сохранен!`. This proves native compile/save of the catalog
probe only, not Server load or execution.

After native Save/Compile, both source files still match the prepared probe's
pages/script bodies where expected: all 48 script names and IDs match; the 46
untouched scripts have 0 logical-body differences. Across all 48 scripts,
logical-body differences are 0 and ID differences are 0. Editor reserialized
metadata in 31 script records; this is recorded as a native metadata delta,
not assumed harmless or corrected. The 10 noncompiled project/settings files
compared between prepared and compiled probe have 0 hash differences.
The original disk11 was not used as the compile target.

Working10 is preserved by the existing private backup
`%LOCALAPPDATA%\CodexBackups\SCADA11Preparation\20261101T215836Z\disk-codex_diag_10`:
14/14 files currently match it exactly, no hash differences. Server still showed
`codex_diag_10` active, database working, 40 active tags. Client10 remained
open and visible: STOP, 4.10 bar, pressure unavailable, VFD confirmation not
received. No Apply was pressed and no field command was sent.

Before the attempted runtime switch, passive MasterOPC showed R2100=410 and
R2360=410, both GOOD. `SpApplyPhase` R2853=0, `SpApplyError` R2854=0,
`SpApplyDetail` R2855=0 and `SpApplyFlags` R2856=2052 were GOOD; no active
Apply phase was visible. One poll timeout briefly caused BAD quality in the
table; before this preflight was accepted all required rows returned to GOOD.
The timestamp column was truncated, so freshness beyond the live display is
not independently timestamp-verified.

## Runtime gate and current state

The probe was not activated. A click on the active10 Server stop control was
rejected by automatic action review: it was judged a possible stop of the
working Server and a conflict with the explicit instruction to preserve10.
The rejected action was not retried by another method. Server10 therefore
remains active; Client10 remains open. Probe BOOT was not observed, no Client
was switched to the probe, no navigation click was made, and ENTER/transition
were not tested. This is an authorization gate, not a negative runtime result.

To continue the remaining runtime part, explicit approval is needed for a
temporary software-only stop of active `codex_diag_10`, activation of exactly
this diagnostic probe, one navigation click after its unique BOOT, then
restoring10. No Apply, equipment command, start/stop/reset of the pump, or
setpoint write is part of that request. Until approved, leave10 active and the
compiled probe private and inactive. The Editor is currently on the compiled
probe; the saved UNVERIFIED model is separate. Original11 and working10 remain
unchanged on disk.
