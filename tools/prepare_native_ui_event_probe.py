#!/usr/bin/env python3
"""Create a private, disk-derived SCADA11 probe; never open Editor or equipment.

The current unsaved Editor model is NOT included. Preserve it separately before
opening this candidate. Native Compile/load/visual checks remain mandatory;
event diagnostics additionally require their actual BOOT/ENTER markers.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import tempfile
from pathlib import Path

# -I deliberately removes the script directory from sys.path. Load only our
# adjacent reviewed parser, without accepting packages from the environment.
_spec = importlib.util.spec_from_file_location(
    '_native_event_probe_audit', Path(__file__).resolve().with_name('audit_native_ui_navigation.py'))
_audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_audit)
Reader, audit, scripts = _audit.Reader, _audit.audit, _audit.scripts

PINS = {
    'Pages.spg': '9826694fa750e9dc4be4db7f0d62d3e2d27affb54300dba65a83ae313964d169',
    'Scripts/Scripts.ssc': 'bc200efeb4d147a366aea3d6b5e134e9c1f7bbb70dbd001295424a89d861270d',
}
SHA = lambda data: hashlib.sha256(data).hexdigest()
ACL_SCRIPT = r'''$ErrorActionPreference='Stop'
$path=[Console]::In.ReadLine()
$acl=[Security.AccessControl.DirectorySecurity]::new()
$acl.SetAccessRuleProtection($true,$false)
$inherit=[Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
foreach($sid in @([Security.Principal.WindowsIdentity]::GetCurrent().User,
 [Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
 $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
  $sid,'FullControl',$inherit,'None','Allow'))
}
Set-Acl -LiteralPath $path -AclObject $acl
'''


def _replace_once(pattern, replacement, text):
    result, count = re.subn(pattern, replacement, text, flags=re.I | re.M)
    if count != 1:
        raise ValueError('Unexpected diagnostic injection site; original preserved')
    return result


def probe_event(probe_id):
    return f'''var aClient: string;
begin
  Log_Add('[{probe_id}] ENTER UiOverview0Nav1', True);
  UiOverview0Heading.Text := 'UI probe: handler entered';
  aClient := GetClientName;
  if aClient = '' then
  begin
    Log_Add('[{probe_id}] CLIENT_EMPTY', True);
    Exit;
  end;
  Log_Add('[{probe_id}] CLIENT_PRESENT', True);
  if GetPageByName('PageUiAlarms') = nil then
  begin
    Log_Add('[{probe_id}] TARGET_MISSING', True);
    Exit;
  end;
  try
    Log_Add('[{probe_id}] BEFORE_HELPER', True);
    UiGoPage('PageUiAlarms', aClient);
    Log_Add('[{probe_id}] AFTER_HELPER', True);
  except
    Log_Add('[{probe_id}] EXCEPTION', True);
  end;
end.'''


def patch_scripts(raw, probe_id):
    if not re.fullmatch(r'UINAV11-[A-Z0-9]{8,32}', probe_id):
        raise ValueError('Expected an injection-safe, unique UINAV11 identifier')
    reviewed = scripts(raw)  # bounded parser, duplicate/trailing-data checks
    if len(reviewed) != 48:
        raise ValueError('Expected the reviewed 48-script candidate')
    reader = Reader(raw)
    reader.number('q'); reader.take(reader.count(1024))
    if reader.number('I') != 0:
        raise ValueError('Unsupported script folders')
    count = reader.count(2048)
    parts, changed = [raw[:reader.pos]], []
    for _ in range(count):
        start = reader.pos
        id_, name = reader.number('q'), reader.text(True)
        reader.take(17)
        text_start = reader.pos
        lines = [reader.text(True) for _ in range(reader.count(8192))]
        if name not in ['OperatorConsole', 'UiOverview0Nav1_OnClick']:
            parts.append(raw[start:reader.pos])
            continue
        body = '\n'.join(lines)
        if 'UiProbeBootSent' in body or 'UINAV11-' in body:
            raise ValueError('Existing diagnostic code requires review')
        if name == 'OperatorConsole':
            if id_ != 7:
                raise ValueError('Unexpected global-module ID')
            body = _replace_once(r'^var[ \t]*\n(?=[ \t]*UiHasSample\b)',
                                 'var\n  UiProbeBootSent: Boolean;\n', body)
            pattern = (r'^procedure[ \t]+OperatorUiUpdate[ \t]*;[ \t]*\n'
                       r'var[ \t]+Index[ \t]*:[ \t]*Integer[ \t]*;[ \t]*\n'
                       r'begin[ \t]*(?=\n)')
            injection = (f"\n  if not UiProbeBootSent then\n  begin\n"
                         f"    Log_Add('[{probe_id}] BOOT', True);\n"
                         "    UiProbeBootSent := True;\n  end;")
            body = _replace_once(pattern, lambda match: match[0] + injection, body)
        else:
            pattern = (r"(?is)\A(?P<unit>unit\s+UiOverview0Nav1_OnClick\s*;\s*)?"
                       r"begin\s+UiGoPage\('PageUiAlarms',\s*GetClientName\);\s*end\.\s*\Z")
            match = re.fullmatch(pattern, body)
            if id_ != 19 or match is None:
                raise ValueError('Unexpected target event body/ID; review instead of overwriting')
            body = (match['unit'] or '') + probe_event(probe_id)
        encoded = [line.encode('utf-16le') for line in body.split('\n')]
        parts.append(raw[start:text_start] + struct.pack('<I', len(encoded)) + b''.join(
            struct.pack('<I', len(line)//2) + line for line in encoded))
        changed.append(name)
    reader.done()
    if set(changed) != {'OperatorConsole', 'UiOverview0Nav1_OnClick'}:
        raise ValueError('Expected exactly the two diagnostic targets')
    result = b''.join(parts)
    after = scripts(result)
    for id_, row in reviewed.items():
        updated = after[id_]
        if row['name'] not in changed and row != updated:
            raise ValueError('Untargeted script changed')
        if row['meta'] != updated['meta'] or row['name'] != updated['name']:
            raise ValueError('Script identity/metadata changed')
    return result


def _ordinary(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
        raise ValueError('Symlinks/reparse points are not accepted')
    return info


def inventory(root):
    result, total = {}, 0
    for path in sorted(root.rglob('*')):
        info = _ordinary(path)
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16*1024*1024:
            raise ValueError('Unexpected native project entry/size')
        total += info.st_size
        if len(result) >= 256 or total > 64*1024*1024:
            raise ValueError('Native project exceeds probe-copy limits')
        result[path.relative_to(root).as_posix()] = SHA(path.read_bytes())
    return result


def _private_directory(path):
    if os.name == 'nt':
        executable = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        task = subprocess.run([str(executable), '-NoLogo', '-NoProfile', '-NonInteractive',
                               '-Command', ACL_SCRIPT], input=str(path)+'\n', text=True,
                              capture_output=True, timeout=30)
        if task.returncode:
            raise ValueError('Cannot protect private probe directory; no source files copied')
    else:
        path.chmod(0o700)


def _git_checkout(path):
    marker = path/'.git'
    if marker.is_dir():
        return (marker/'HEAD').is_file()
    if marker.is_file():
        with marker.open('rb') as stream:
            return stream.read(8) == b'gitdir: '
    return False


def prepare(project, out, probe_id):
    return _prepare_copy(project, out, lambda raw: patch_scripts(raw, probe_id),
                         r'codex_diag_11_probe_[a-z0-9_-]{8,80}',
                         dict(probeId=probe_id, purpose='event-diagnostics', runtimeBootObserved=False))


def pressure_display_scripts(raw):
    spec = importlib.util.spec_from_file_location(
        '_pressure_display_builder', Path(__file__).resolve().with_name('build_native_operator_console_01.py'))
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    before = scripts(raw)
    if len(before) != 48 or before.get(0, {}).get('name') != 'StationDiagnostics' or before.get(7, {}).get('name') != 'OperatorConsole':
        raise ValueError('Expected the reviewed native display modules')
    reader = Reader(raw)
    reader.number('q'); reader.take(reader.count(1024))
    if reader.number('I') != 0:
        raise ValueError('Unsupported script folders')
    count = reader.count(2048)
    parts = [raw[:reader.pos]]
    for _ in range(count):
        start = reader.pos
        reader.number('q'); name = reader.text(True); reader.take(17)
        text_start = reader.pos
        lines = [reader.text(True) for _ in range(reader.count(8192))]
        if name not in ['StationDiagnostics', 'OperatorConsole']:
            parts.append(raw[start:reader.pos])
            continue
        body = builder.pressure_display_module('\n'.join(lines), name)
        encoded = [line.encode('utf-16le') for line in body.split('\n')]
        parts.append(raw[start:text_start] + struct.pack('<I', len(encoded)) + b''.join(
            struct.pack('<I', len(line)//2) + line for line in encoded))
    reader.done()
    result = b''.join(parts)
    after = scripts(result)
    for id_, row in before.items():
        updated = after[id_]
        if row['name'] not in ['StationDiagnostics', 'OperatorConsole'] and row != updated:
            raise ValueError('Untargeted script changed')
        if row['meta'] != updated['meta'] or row['name'] != updated['name']:
            raise ValueError('Script identity/metadata changed')
    return result


def prepare_pressure_display(project, out):
    return _prepare_copy(project, out, pressure_display_scripts,
                         r'codex_diag_11_display_[a-z0-9_-]{8,80}',
                         dict(purpose='pressure-display-1-decimal', pressureDecimals=1,
                              rawPressureDivisor=100, commandPrecisionUnchanged=True))


def prepare_visual_layout(project, out, project_width, project_height,
                          client_width=1366, client_height=768,
                          header_pixels=64, footer_pixels=24):
    spec = importlib.util.spec_from_file_location(
        '_visual_layout_builder', Path(__file__).resolve().with_name('build_native_operator_console_01.py'))
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    def reflow(raw):
        return builder.visual_layout_pages(raw, project_width, project_height,
            client_width, client_height, header_pixels, footer_pixels)
    return _prepare_copy(project, out, pressure_display_scripts,
        r'codex_diag_11_layout_[a-z0-9_-]{8,80}',
        dict(purpose='visual-layout-first-pass', pressureDecimals=1,
             projectDimensionsProvided=[project_width,project_height],
             referenceClientDimensions=[client_width,client_height],
             headerPixelsReserved=header_pixels, footerPixelsReserved=footer_pixels,
             dimensionsMeasuredByHelper=False, visualAcceptancePassed=False,
             commandPrecisionUnchanged=True), page_transform=reflow)


def prepare_layout_review(project, out, expected_pages_sha, expected_scripts_sha,
                          probe_id=None, native_navigation=False):
    # Current deployed candidate is identified by the operator's Server image.
    # Digests come from its preserved native manifest/audit, never from a guess.
    if not re.fullmatch(r'codex_diag_11_(?:layout_20261103t000000z|review_[a-z0-9_-]{8,80})',Path(project).name):
        raise ValueError('Choose the operator-confirmed layout candidate')
    if not all(re.fullmatch(r'[0-9a-f]{64}',v or '') for v in (expected_pages_sha,expected_scripts_sha)):
        raise ValueError('Explicit reviewed Pages/Scripts digests are required')
    if native_navigation and probe_id:
        raise ValueError('Do not probe a sidebar button removed by native navigation')
    spec=importlib.util.spec_from_file_location(
        '_layout_review_builder',Path(__file__).resolve().with_name('build_native_operator_console_01.py'))
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    def transform(raw):
        if probe_id:
            controls=[o['name'] for p in builder.parse_pages((Path(project)/'Pages.spg').read_bytes()) for o in p['objects']]
            if 'UiOverview0Nav1' not in controls:
                raise ValueError('The sidebar probe target has already been removed')
            return patch_scripts(raw,probe_id)
        if native_navigation and any('UiProbeBootSent' in row['body'] or 'UINAV11-' in row['body']
                                    for row in scripts(raw).values()):
            raise ValueError('Remove the diagnostic probe before final navigation')
        return pressure_display_scripts(raw) if native_navigation else raw
    return _prepare_copy(project,out,
        transform,
        r'codex_diag_11_review_[a-z0-9_-]{8,80}',
        dict(purpose='layout-navigation-review',correctedFontOrdinal=16,
             nativeTabsVisible=native_navigation,duplicateSidebarRemoved=native_navigation,probeId=probe_id,
             pressureDecimals=1 if native_navigation else None,
             geometryStrategy='semantic-grid-1920x1080-v1' if native_navigation else 'unchanged',
             geometryUnchanged=not native_navigation,controlLogicUnchanged=True,
             visualAcceptancePassed=False),
        page_transform=lambda raw:(builder.native_navigation_grid_pages(
            builder.repair_visual_page_style(raw,True),1920,1080) if native_navigation else
            builder.repair_visual_page_style(raw,False)),
        pins={'Pages.spg':expected_pages_sha,'Scripts/Scripts.ssc':expected_scripts_sha},
        expected_button_counts=(44,15))


def prepare_tab_clearance(project, out, expected_pages_sha, expected_scripts_sha):
    """Create a separate candidate that moves only page backgrounds below tabs."""
    if Path(project).name != 'codex_diag_11_review_grid_20261103t1030z':
        raise ValueError('Use the operator-confirmed saved grid candidate')
    if not all(re.fullmatch(r'[0-9a-f]{64}',v or '') for v in
               (expected_pages_sha,expected_scripts_sha)):
        raise ValueError('Explicit reviewed Pages/Scripts digests are required')
    spec=importlib.util.spec_from_file_location(
        '_tab_clearance_builder',Path(__file__).resolve().with_name('build_native_operator_console_01.py'))
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    return _prepare_copy(project,out,lambda raw:raw,
        r'codex_diag_11_review_tabs_[a-z0-9_-]{8,80}',
        dict(purpose='native-page-tab-clearance',backgroundTop=64,backgroundBottom=1080,
             changedScripts=[],controlLogicUnchanged=True,sourceUnchanged=True,
             runtimeNavigationVerified=False,hardwareCommands=0),
        page_transform=builder.native_tab_clearance_pages,
        pins={'Pages.spg':expected_pages_sha,'Scripts/Scripts.ssc':expected_scripts_sha},
        expected_button_counts=(15,))


def prepare_overview_panel(project, out, expected_pages_sha, expected_scripts_sha):
    """Add real-data overview cards in a separate saved native-console copy."""
    if not re.fullmatch(r'codex_diag_11_review_[a-z0-9_-]{8,80}',Path(project).name):
        raise ValueError('Use the saved native-navigation review candidate')
    if not all(re.fullmatch(r'[0-9a-f]{64}',v or '') for v in
               (expected_pages_sha,expected_scripts_sha)):
        raise ValueError('Explicit reviewed Pages/Scripts digests are required')
    spec=importlib.util.spec_from_file_location(
        '_overview_panel',Path(__file__).resolve().with_name('native_overview_panel.py'))
    panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
    def transform(raw):
        before=scripts(raw)
        if len(before)!=48 or before[7]['name']!='OperatorConsole':
            raise ValueError('Expected the saved 48-script operator console')
        if any('UiProbeBootSent' in r['body'] or 'UINAV11-' in r['body'] for r in before.values()):
            raise ValueError('Remove event diagnostics before the overview candidate')
        reader=Reader(raw);reader.number('q');reader.take(reader.count(1024))
        if reader.number('I')!=0:raise ValueError('Unsupported script folders')
        count=reader.count(2048);parts=[raw[:reader.pos]]
        for _ in range(count):
            start=reader.pos;id_=reader.number('q');reader.text(True);reader.take(17)
            text_start=reader.pos
            lines=[reader.text(True) for _ in range(reader.count(8192))]
            if id_!=7:parts.append(raw[start:reader.pos]);continue
            body=panel.overview_module('\n'.join(lines))
            encoded=[line.encode('utf-16le') for line in body.split('\n')]
            parts.append(raw[start:text_start]+struct.pack('<I',len(encoded))+b''.join(
                struct.pack('<I',len(line)//2)+line for line in encoded))
        reader.done();result=b''.join(parts);after=scripts(result)
        for id_,old in before.items():
            if old['name']!=after[id_]['name'] or old['meta']!=after[id_]['meta']:
                raise ValueError('Script identity or metadata changed')
            if id_!=7 and old!=after[id_]:raise ValueError('Untargeted script changed')
        return result
    return _prepare_copy(project,out,transform,
        r'codex_diag_11_review_overview_[a-z0-9_-]{8,80}',
        dict(purpose='native-overview-components-v1',nativeTabsVisible=True,
             actualStations=1,simulatedStationRows=0,controllerBindingsUnchanged=True,
             visualAcceptancePassed=False,WindowsCompileObserved=False),
        page_transform=panel.overview_pages,
        pins={'Pages.spg':expected_pages_sha,'Scripts/Scripts.ssc':expected_scripts_sha},
        expected_button_counts=(15,))


def prepare_station_card(project, out, expected_pages_sha, expected_scripts_sha):
    """Create a separate card copy from the saved native overview candidate."""
    if not re.fullmatch(r'codex_diag_11_review_overview_[a-z0-9_-]{8,80}', Path(project).name):
        raise ValueError('Use the saved native overview review candidate')
    if not all(re.fullmatch(r'[0-9a-f]{64}', v or '') for v in
               (expected_pages_sha, expected_scripts_sha)):
        raise ValueError('Explicit reviewed Pages/Scripts digests are required')
    panel_spec = importlib.util.spec_from_file_location(
        '_station_card_overview', Path(__file__).resolve().with_name('native_overview_panel.py'))
    panel = importlib.util.module_from_spec(panel_spec)
    panel_spec.loader.exec_module(panel)
    card_spec = importlib.util.spec_from_file_location(
        '_station_card_pages', Path(__file__).resolve().with_name('native_station_card.py'))
    card = importlib.util.module_from_spec(card_spec)
    card_spec.loader.exec_module(card)

    def transform(raw):
        before = scripts(raw)
        if len(before) != 48 or before[7]['name'] != 'OperatorConsole':
            raise ValueError('Expected saved 48-script operator console')
        if any('UiCardEventText' in row['body'] or 'UiPumpState0' in row['body']
               for row in before.values()):
            raise ValueError('Station-card script already exists')
        reader = Reader(raw)
        reader.number('q')
        reader.take(reader.count(1024))
        if reader.number('I') != 0:
            raise ValueError('Unsupported script folders')
        count = reader.count(2048)
        parts = [raw[:reader.pos]]
        for _ in range(count):
            start = reader.pos
            id_ = reader.number('q')
            reader.text(True)
            reader.take(17)
            text_start = reader.pos
            lines = [reader.text(True) for _ in range(reader.count(8192))]
            if id_ != 7:
                parts.append(raw[start:reader.pos])
                continue
            body = panel.station_card_module('\n'.join(lines))
            encoded = [line.encode('utf-16le') for line in body.split('\n')]
            parts.append(raw[start:text_start] + struct.pack('<I', len(encoded)) + b''.join(
                struct.pack('<I', len(line)//2) + line for line in encoded))
        reader.done()
        result = b''.join(parts)
        after = scripts(result)
        for id_, old in before.items():
            if old['name'] != after[id_]['name'] or old['meta'] != after[id_]['meta']:
                raise ValueError('Script identity or metadata changed')
            if id_ != 7 and old != after[id_]:
                raise ValueError('Untargeted script changed')
        return result

    return _prepare_copy(project, out, transform,
        r'codex_diag_11_review_station_card_[a-z0-9_-]{8,80}',
        dict(purpose='native-station-card-v1', nativeTabsVisible=True,
             unknownPumpStatesPreserved=True, eventHistorySource='PageUiAlarms',
             connectionFreshnessSource='PlcAliveCounter', radioHealthInferred=False,
             controllerBindingsUnchanged=True, visualAcceptancePassed=False,
             WindowsCompileObserved=False),
        page_transform=card.station_card_pages,
        pins={'Pages.spg': expected_pages_sha, 'Scripts/Scripts.ssc': expected_scripts_sha},
        expected_button_counts=(15,))


def _prepare_copy(project, out, transform, output_pattern, details, page_transform=None, pins=None,
                  expected_button_counts=(44,)):
    project, out = Path(project).absolute(), Path(out).absolute()
    if any('\n' in str(p) or '\r' in str(p) for p in [project, out]):
        raise ValueError('Unsupported path characters')
    for path in [project, *project.parents, out, *out.parents]:
        if path.exists() or path.is_symlink():
            _ordinary(path)
    project, out = project.resolve(strict=True), out.resolve()
    if (out == project or out.is_relative_to(project) or project.is_relative_to(out)
            or any(_git_checkout(p) for p in [out, *out.parents])):
        raise ValueError('Use a separate private destination outside source and Git')
    if out.exists():
        raise ValueError('Destination already exists; preserved')
    if not re.fullmatch(output_pattern, out.name):
        raise ValueError('Use a clearly named new directory for the chosen candidate type')
    if not out.parent.is_dir():
        raise ValueError('Create the private destination parent first')
    before = inventory(project)
    for name, expected in (PINS if pins is None else pins).items():
        if before.get(name) != expected:
            raise ValueError('Saved SCADA11 differs from the reviewed file: ' + name)
    header = (project/'Project.spr').read_bytes()
    if len(header) < 16 or struct.unpack_from('<4H', header, 8) != (2, 6, 15, 0):
        raise ValueError('Expected Simple-Scada2.6.15.0')
    verified = audit(project)
    if verified['findings'] or verified['buttons'] not in expected_button_counts:
        raise ValueError('Saved native bindings need review')
    source_scripts = (project/'Scripts/Scripts.ssc').read_bytes()
    patched = transform(source_scripts)
    patched_pages = None if page_transform is None else page_transform((project/'Pages.spg').read_bytes())
    old_records, new_records = scripts(source_scripts), scripts(patched)
    changed = [row['name'] for id_,row in old_records.items() if row != new_records[id_]]
    excluded = [n for n in before if n.lower().startswith('scripts/compiled/') or
                Path(n).suffix.lower() == '.exs']
    replaced_manifests=[n for n in before if n=='CodexProbeManifest.json']
    stage = Path(tempfile.mkdtemp(prefix='.event-probe-', dir=out.parent))
    try:
        _private_directory(stage)  # before copying any private native data
        for name in before:
            if name in excluded or name in replaced_manifests:
                continue
            dest = stage/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project/name, dest)
        (stage/'Scripts/Compiled').mkdir(parents=True, exist_ok=True)
        (stage/'Scripts/Scripts.ssc').write_bytes(patched)
        if patched_pages is not None:
            (stage/'Pages.spg').write_bytes(patched_pages)
        copied = inventory(stage)
        allowed = {'Scripts/Scripts.ssc'} | ({'Pages.spg'} if patched_pages is not None else set())
        for name, expected in before.items():
            if name not in excluded and name not in replaced_manifests and name not in allowed and copied.get(name) != expected:
                raise ValueError('Candidate preservation check failed')
        verified = audit(stage)
        if verified['findings'] or inventory(project) != before:
            raise ValueError('Source changed during preparation or candidate bindings differ')
        manifest = dict(schemaVersion=1, diskDerived=True,
                        unsavedEditorModelIncluded=False, sourceSHA256=before,
                        candidateSHA256=copied, changedScripts=changed,
                        excludedCompiledFiles=excluded, sourceUnchanged=True,
                        replacedPreparationManifests=replaced_manifests,
                        WindowsCompileObserved=False,
                        runtimeNavigationVerified=False, hardwareCommands=0)
        manifest.update(details)
        (stage/'CodexProbeManifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf8')
        if out.exists():
            raise ValueError('Destination appeared during preparation; preserved')
        stage.rename(out)
        stage = None
        return manifest
    finally:
        if stage is not None:
            shutil.rmtree(stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--mode', choices=['event', 'pressure-display', 'visual-layout', 'layout-review', 'tab-clearance', 'overview-panel', 'station-card'], default='event')
    parser.add_argument('--probe-id')
    parser.add_argument('--project-width', type=int)
    parser.add_argument('--project-height', type=int)
    parser.add_argument('--client-width', type=int, default=1366)
    parser.add_argument('--client-height', type=int, default=768)
    parser.add_argument('--header-pixels', type=int, default=64)
    parser.add_argument('--footer-pixels', type=int, default=24)
    parser.add_argument('--expected-pages-sha')
    parser.add_argument('--expected-scripts-sha')
    parser.add_argument('--native-navigation', action='store_true')
    args = parser.parse_args()
    if args.mode not in ('layout-review','tab-clearance','overview-panel','station-card') and (args.expected_pages_sha or args.expected_scripts_sha or args.native_navigation):
        parser.error('Reviewed digests are only valid in layout-review/tab-clearance/overview-panel modes')
    if args.mode in ('tab-clearance','overview-panel','station-card') and args.native_navigation:
        parser.error('Native navigation is already required for this candidate')
    if args.mode != 'visual-layout' and (args.project_width is not None or args.project_height is not None):
        parser.error('Project dimensions are only valid in visual-layout mode')
    if args.mode == 'event':
        if not args.probe_id: parser.error('--probe-id is required in event mode')
        prepare(args.project, args.out, args.probe_id)
        print('PREPARED: private disk-derived probe; unsaved Editor model excluded. Native compile/load/BOOT not yet tested.')
    elif args.mode == 'pressure-display':
        if args.probe_id: parser.error('--probe-id is only valid in event mode')
        prepare_pressure_display(args.project, args.out)
        print('PREPARED: private display candidate; one decimal, raw precision unchanged. Native compile/load not yet tested.')
    elif args.mode == 'visual-layout':
        if args.probe_id or args.project_width is None or args.project_height is None:
            parser.error('visual-layout requires both native project dimensions and no probe-id')
        prepare_visual_layout(args.project, args.out, args.project_width, args.project_height,
            args.client_width, args.client_height, args.header_pixels, args.footer_pixels)
        print('PREPARED: private layout candidate; native dimensions supplied by caller. Compile/load/visual acceptance not yet tested.')
    elif args.mode == 'layout-review':
        if not args.expected_pages_sha or not args.expected_scripts_sha:
            parser.error('layout-review requires both reviewed digests')
        prepare_layout_review(args.project,args.out,args.expected_pages_sha,args.expected_scripts_sha,
                              args.probe_id,args.native_navigation)
        print('PREPARED: private layout review; native font ordinal corrected. Windows navigation/visual acceptance not yet tested.')
    elif args.mode == 'tab-clearance':
        if args.probe_id or not args.expected_pages_sha or not args.expected_scripts_sha:
            parser.error('tab-clearance requires reviewed Pages/Scripts digests and no probe-id')
        prepare_tab_clearance(args.project,args.out,args.expected_pages_sha,args.expected_scripts_sha)
        print('PREPARED: separate candidate changes only page-background top clearance; compile/load/Client review still required.')
    elif args.mode == 'overview-panel':
        if args.probe_id or not args.expected_pages_sha or not args.expected_scripts_sha:
            parser.error('overview-panel requires reviewed Pages/Scripts digests and no probe-id')
        prepare_overview_panel(args.project,args.out,args.expected_pages_sha,args.expected_scripts_sha)
        print('PREPARED: separate real-data overview candidate. Native compile/load/visual acceptance not yet tested.')
    else:
        if args.probe_id or not args.expected_pages_sha or not args.expected_scripts_sha:
            parser.error('station-card requires reviewed Pages/Scripts digests and no probe-id')
        prepare_station_card(args.project,args.out,args.expected_pages_sha,args.expected_scripts_sha)
        print('PREPARED: separate station-card candidate; native Compile/Save and Client review still required.')
