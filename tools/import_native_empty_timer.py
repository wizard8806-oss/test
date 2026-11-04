#!/usr/bin/env python3
"""Copy a saved 2.6.15 project and fill one explicitly reviewed empty script.

The UTF-8 payload must be reviewed separately. This tool never runs it, opens
Editor, changes script metadata or parses/rebuilds Pages.spg. Native Compile/
Save and actual timer execution remain separate checks.
"""
import argparse
import importlib.util
import json
import re
import shutil
import struct
import tempfile
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    '_timer_copy', Path(__file__).resolve().with_name('prepare_native_ui_event_probe.py'))
copy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(copy)


def patch(raw, script_id, script_name, payload):
    before = copy.scripts(raw)
    target = before.get(script_id)
    if target is None or target['name'] != script_name:
        raise ValueError('Selected script ID/name does not match the saved model')
    if not re.fullmatch(r'begin\s+end\.', target['body'], re.I):
        raise ValueError('Target is not empty; existing code is preserved')
    body = payload.replace('\r\n', '\n').replace('\r', '\n').strip()
    if ('\x00' in body or len(body.encode('utf8')) > 65536 or len(body.splitlines()) > 8192
            or not re.match(r'(?i)\A(?:var|begin)\b', body)
            or not re.search(r'(?i)\bend\.\Z', body)
            or re.fullmatch(r'begin\s*end\.', body, re.I)):
        raise ValueError('Use a bounded, nonempty UTF-8 event body without a procedure/unit header')
    reader = copy.Reader(raw)
    reader.number('q'); reader.take(reader.count(1024))
    if reader.number('I') != 0:
        raise ValueError('Script folders require a separately reviewed importer')
    count = reader.count(2048)
    parts = [raw[:reader.pos]]
    for _ in range(count):
        start = reader.pos
        id_, name = reader.number('q'), reader.text(True)
        reader.take(17)
        text_start = reader.pos
        text = '\n'.join(reader.text(True) for _ in range(reader.count(8192)))
        if id_ != script_id:
            parts.append(raw[start:reader.pos])
            continue
        unit = re.match(r'(?is)\A\s*unit\s+' + re.escape(name) + r'\s*;\s*', text)
        lines = ((unit[0] if unit else '') + body).split('\n')
        encoded = [line.encode('utf-16le') for line in lines]
        parts.append(raw[start:text_start] + struct.pack('<I', len(lines)) + b''.join(
            struct.pack('<I', len(line)//2) + line for line in encoded))
    reader.done()
    result = b''.join(parts)
    after = copy.scripts(result)
    for id_, row in before.items():
        if id_ == script_id:
            if after[id_] != dict(row, body=body):
                raise ValueError('Target identity, metadata or imported body differs')
        elif after[id_] != row:
            raise ValueError('Untargeted script changed')
    return result


def prepare(project, out, payload_file, script_id, script_name, pages_sha, scripts_sha, payload_sha):
    project, out, payload_file = (Path(p).absolute() for p in (project, out, payload_file))
    for path in [project, *project.parents, out, *out.parents, payload_file, *payload_file.parents]:
        if '\n' in str(path) or '\r' in str(path):
            raise ValueError('Unsupported path characters')
        if path.exists() or path.is_symlink():
            copy._ordinary(path)
    project, out = project.resolve(strict=True), out.resolve()
    if (out == project or out.is_relative_to(project) or project.is_relative_to(out)
            or any(copy._git_checkout(p) for p in [out, *out.parents])):
        raise ValueError('Use a separate private destination outside source and Git')
    if out.exists() or not out.parent.is_dir():
        raise ValueError('Destination must be new with an existing private parent')
    if not re.fullmatch(r'codex_diag_11_trend_timer_[a-z0-9_-]{8,80}', out.name):
        raise ValueError('Use a clearly named new trend-timer copy')
    before = copy.inventory(project)
    if before.get('Pages.spg') != pages_sha or before.get('Scripts/Scripts.ssc') != scripts_sha:
        raise ValueError('Saved project differs from reviewed Pages/Scripts hashes')
    header = (project/'Project.spr').read_bytes()
    if len(header) < 16 or struct.unpack_from('<4H', header, 8) != (2, 6, 15, 0):
        raise ValueError('Expected Simple-Scada 2.6.15.0')
    if payload_file.stat().st_size > 65536:
        raise ValueError('Payload exceeds event-body limit')
    payload_raw = payload_file.read_bytes()
    if copy.SHA(payload_raw) != payload_sha:
        raise ValueError('Payload differs from separately reviewed code')
    patched = patch((project/'Scripts/Scripts.ssc').read_bytes(), script_id, script_name,
                    payload_raw.decode('utf-8-sig'))
    manifest_name = 'CodexTimerImportManifest.json'
    if manifest_name in before:
        raise ValueError('Existing import manifest requires review')
    excluded = [n for n in before if n.lower().startswith('scripts/compiled/') or Path(n).suffix.lower() == '.exs']
    stage = Path(tempfile.mkdtemp(prefix='.trend-timer-', dir=out.parent))
    try:
        copy._private_directory(stage)
        for name in before:
            if name in excluded:
                continue
            dest = stage/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project/name, dest)
        (stage/'Scripts/Compiled').mkdir(parents=True, exist_ok=True)
        (stage/'Scripts/Scripts.ssc').write_bytes(patched)
        copied = copy.inventory(stage)
        for name, digest in before.items():
            if name not in excluded and name != 'Scripts/Scripts.ssc' and copied.get(name) != digest:
                raise ValueError('Native resource preservation failed')
        if (copy.inventory(project) != before or payload_file.read_bytes() != payload_raw):
            raise ValueError('Source or reviewed payload changed during copy')
        manifest = dict(schemaVersion=1, purpose='reviewed-empty-timer-import',
                        sourceSHA256=before, candidateSHA256=copied,
                        changedScript=dict(id=script_id, name=script_name),
                        payloadSHA256=payload_sha, excludedCompiledFiles=excluded,
                        pagesOpaqueAndUnchanged=True, sourceUnchanged=True,
                        unsavedEditorModelIncluded=False, WindowsCompileObserved=False,
                        timerExecutionObserved=False, hardwareCommands=0)
        (stage/manifest_name).write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf8')
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
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--script-id', type=int, required=True)
    parser.add_argument('--script-name', required=True)
    parser.add_argument('--expected-pages-sha', required=True)
    parser.add_argument('--expected-scripts-sha', required=True)
    parser.add_argument('--expected-payload-sha', required=True)
    args = parser.parse_args()
    prepare(args.project, args.out, args.payload, args.script_id, args.script_name,
            args.expected_pages_sha, args.expected_scripts_sha, args.expected_payload_sha)
    print('PREPARED: private saved-model copy; one empty event body filled. Native compile and timer execution unverified.')
