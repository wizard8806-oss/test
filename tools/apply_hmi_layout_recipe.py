#!/usr/bin/env python3
"""Apply a reviewed, source-locked SKTool geometry recipe to a NEW file.

Only mirrored rectangle sizes and scene positions are changed. The recipe
pins the entire input and output; this does not replace native SKTool checks.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct


SHA = lambda raw: hashlib.sha256(raw).hexdigest()


def qstring(text):
    raw = text.encode('utf-16-be')
    return struct.pack('>I', len(raw)) + raw


def transform(raw, recipe):
    if recipe.get('schemaVersion') != 1 or recipe.get('format') != 'sktool-geometry-pinned-v1':
        raise ValueError('Unsupported geometry recipe')
    if len(raw) != recipe['sourceBytes'] or SHA(raw) != recipe['sourceSHA256']:
        raise ValueError('Source differs from the reviewed upload; original preserved')
    if not raw.startswith(qstring('SKTOOL-V7.1.0.80') + qstring('SK-070HE')):
        raise ValueError('Expected the reviewed SKTool version and SK-070HE model')
    objects = recipe['objects']
    if not objects or len(objects) > 1000:
        raise ValueError('Invalid object inventory')
    limit_start, limit_end = recipe['geometryRegion']
    if not 0 <= limit_start < limit_end <= len(raw):
        raise ValueError('Invalid geometry region')
    changes, names = [], set()
    for obj in objects:
        name = obj['id']
        if not re.fullmatch(r'[A-Za-z]+[0-9]+', name) or name in names:
            raise ValueError('Invalid or duplicate object ID')
        names.add(name)
        frame, graphic_end = obj['frameOffset'], obj['graphicsEnd']
        if not limit_start <= frame < graphic_end <= limit_end:
            raise ValueError('Object outside the reviewed first-screen region')
        if raw[frame:frame + 4] != bytes.fromhex('0001000f'):
            raise ValueError('Frame primitive differs: ' + name)
        if raw[graphic_end:graphic_end + len(qstring(name))] != qstring(name):
            raise ValueError('Object identity anchor differs: ' + name)
        old, new = obj['before'], obj['after']
        if set(old) != {'x', 'y', 'width', 'height'} or set(new) != set(old):
            raise ValueError('Expected only rectangle geometry')
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)
               for item in (old, new) for v in item.values()):
            raise ValueError('Invalid numeric geometry')
        if not (new['x'] >= 0 and new['y'] >= 0 and new['width'] > 0 and new['height'] > 0
                and new['x'] + new['width'] <= 800 + 1e-7
                and new['y'] + new['height'] <= 480 + 1e-7):
            raise ValueError('New object lies outside 800x480: ' + name)
        if struct.unpack_from('>4d', raw, frame + 4) != (0., 0., old['width'], old['height']):
            raise ValueError('Frame rectangle differs: ' + name)
        for slots, keys, first_offset in (
                ('sizeOffsets', ('width', 'height'), frame + 20),
                ('positionOffsets', ('x', 'y'), frame + 77)):
            offsets = obj[slots]
            if len(offsets) not in (2, 3) or len(set(offsets)) != len(offsets) or offsets[0] != first_offset:
                raise ValueError('Invalid geometry mirrors: ' + name)
            before = struct.pack('>2d', *(old[k] for k in keys))
            after = struct.pack('>2d', *(new[k] for k in keys))
            for offset in offsets:
                if not frame <= offset or offset + 16 > graphic_end:
                    raise ValueError('Patch would extend beyond graphic primitives')
                if raw[offset:offset + 16] != before:
                    raise ValueError('Geometry mirror differs: ' + name)
                if before != after:
                    changes.append((offset, before, after))
    changes.sort()
    for previous, following in zip(changes, changes[1:]):
        if previous[0] + len(previous[1]) > following[0]:
            raise ValueError('Overlapping geometry changes')
    if not changes:
        raise ValueError('Empty geometry update')
    output = bytearray(raw)
    for offset, _, replacement in changes:
        output[offset:offset + 16] = replacement
    result = bytes(output)
    if len(result) != len(raw) or SHA(result) != recipe['targetSHA256']:
        raise ValueError('Result differs from reviewed geometry candidate')
    return result, len(changes)


def prepare(source, recipe_path, output, report_path=None):
    source, recipe_path, output = Path(source), Path(recipe_path), Path(output)
    destinations = [output] + ([Path(report_path)] if report_path else [])
    if len({p.resolve() for p in destinations}) != len(destinations):
        raise ValueError('Output/report paths must differ')
    for path in destinations:
        if path.resolve() in (source.resolve(), recipe_path.resolve()) or path.exists() or path.is_symlink():
            raise ValueError('Destination already exists or aliases an input; preserved')
    raw = source.read_bytes()
    recipe = json.loads(recipe_path.read_text(encoding='utf-8-sig'))
    result, count = transform(raw, recipe)
    if source.read_bytes() != raw:
        raise ValueError('Source changed during preparation')
    report = dict(sourceName=source.name, sourceSHA256=SHA(raw), outputName=output.name,
                  targetSHA256=SHA(result), bytes=len(result), objects=len(recipe['objects']),
                  geometryPairsChanged=count, sourceUnchanged=True,
                  nativeOpenObserved=False, nativeCompilationObserved=False,
                  simulatorObserved=False, equipmentCommands=0)
    created = []
    try:
        for path, content in [(output, result)] + (
                [(Path(report_path), (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())]
                if report_path else []):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                created.append(path)
                stream.write(content)
        if source.read_bytes() != raw:
            raise ValueError('Source changed before completion')
    except BaseException:
        for path in created:
            path.unlink()
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--recipe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = prepare(args.source, args.recipe, args.out, args.report)
    print('Prepared NEW SK-070HE layout candidate:', report['objects'], 'objects;',
          report['geometryPairsChanged'], 'geometry pairs; source preserved.')
    print('Target SHA256:', report['targetSHA256'])
    print('Open the new file in SKTool, run native checks and Offline Simulator; no equipment action performed.')


if __name__ == '__main__':
    main()
