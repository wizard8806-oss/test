#!/usr/bin/env python3
"""Pinned geometry application/refusal tests using synthetic bytes only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

from apply_hmi_layout_recipe import prepare, qstring, transform


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture(equal_pairs=False):
    raw = bytearray(512)
    header = qstring('SKTOOL-V7.1.0.80') + qstring('SK-070HE')
    raw[:len(header)] = header
    frame, ident = 96, 316
    raw[frame:frame + 4] = bytes.fromhex('0001000f')
    old = dict(x=20., y=100., width=20. if equal_pairs else 60., height=100. if equal_pairs else 30.)
    new = dict(x=40., y=120., width=100., height=40.)
    struct.pack_into('>4d', raw, frame + 4, 0., 0., old['width'], old['height'])
    for offset in (frame + 20, frame + 140):
        struct.pack_into('>2d', raw, offset, old['width'], old['height'])
    for offset in (frame + 77, frame + 160):
        struct.pack_into('>2d', raw, offset, old['x'], old['y'])
    raw[ident:ident + len(qstring('Text1'))] = qstring('Text1')
    binding = qstring('R2100#1#6#1#2100#R#1#')
    raw[400:400 + len(binding)] = binding
    result = bytearray(raw)
    for offset in (frame + 20, frame + 140):
        struct.pack_into('>2d', result, offset, new['width'], new['height'])
    for offset in (frame + 77, frame + 160):
        struct.pack_into('>2d', result, offset, new['x'], new['y'])
    recipe = dict(schemaVersion=1, format='sktool-geometry-pinned-v1', sourceBytes=len(raw),
                  sourceSHA256=sha(raw), targetSHA256=sha(result), geometryRegion=[frame, 350],
                  objects=[dict(id='Text1', frameOffset=frame, graphicsEnd=ident, before=old, after=new,
                                sizeOffsets=[frame + 20, frame + 140],
                                positionOffsets=[frame + 77, frame + 160])])
    return bytes(raw), bytes(result), recipe


def refused(call, expected=ValueError):
    try:
        call()
    except expected:
        return
    raise AssertionError('Unsafe or inconsistent update was accepted')


def main():
    source, target, recipe = fixture()
    changed, pairs = transform(source, recipe)
    assert changed == target and pairs == 4 and changed[400:] == source[400:]
    count = 1
    mutations = [
        lambda r: r.update(schemaVersion=2),
        lambda r: r.update(sourceSHA256='0' * 64),
        lambda r: r.update(sourceBytes=len(source) - 1),
        lambda r: r.update(targetSHA256='0' * 64),
        lambda r: r.update(geometryRegion=[96, 5120]),
        lambda r: r['objects'].append(copy.deepcopy(r['objects'][0])),
        lambda r: r['objects'][0].update(graphicsEnd=300),
        lambda r: r['objects'][0].update(positionOffsets=[173, 400]),
        lambda r: r['objects'][0].update(sizeOffsets=[116, 116]),
        lambda r: r['objects'][0]['after'].update(x=790),
        lambda r: r['objects'][0]['after'].update(height=float('nan')),
    ]
    for mutate in mutations:
        bad = copy.deepcopy(recipe)
        mutate(bad)
        refused(lambda: transform(source, bad))
        count += 1
    stale = bytearray(source)
    stale[420] ^= 1
    refused(lambda: transform(bytes(stale), recipe))
    count += 1
    raw, _, overlap = fixture(equal_pairs=True)
    overlap['objects'][0]['sizeOffsets'][1] = overlap['objects'][0]['positionOffsets'][0]
    refused(lambda: transform(raw, overlap))
    count += 1
    with tempfile.TemporaryDirectory(prefix='hmi-layout-recipe-') as folder:
        root = Path(folder)
        src, data, out = root / 'original.skm', root / 'recipe.json', root / 'candidate.skm'
        src.write_bytes(source)
        data.write_text(json.dumps(recipe), encoding='utf8')
        report = prepare(src, data, out, root / 'report.json')
        assert src.read_bytes() == source and out.read_bytes() == target
        assert report['nativeOpenObserved'] is False and report['equipmentCommands'] == 0
        count += 1
        refused(lambda: prepare(src, data, src))
        refused(lambda: prepare(src, data, out))
        refused(lambda: prepare(src, data, data))
        count += 3
        # Report failures must remove only the newly created output.
        failed = root / 'rolled-back.skm'
        refused(lambda: prepare(src, data, failed, root / 'missing' / 'report.json'), FileNotFoundError)
        assert not failed.exists() and src.read_bytes() == source
        count += 1
        alias_cases = []
        for kind in ('hardlink', 'symlink'):
            alias = root / (kind + '.skm')
            try:
                if kind == 'hardlink':
                    os.link(src, alias)
                else:
                    alias.symlink_to(src)
            except (OSError, NotImplementedError):
                alias_cases.append(kind + ': unavailable')
                continue
            refused(lambda: prepare(src, data, alias))
            assert src.read_bytes() == source
            alias_cases.append(kind + ': refused')
            count += 1
        standalone = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).with_name('apply_hmi_layout_recipe.py')),
                                     '--source', str(src), '--recipe', str(data), '--out', str(root / 'standalone.skm')],
                                    text=True, capture_output=True, timeout=20)
        assert standalone.returncode == 0, standalone.stderr
        assert (root / 'standalone.skm').read_bytes() == target
        count += 1
    print('PASS', count, 'geometry recipe cases; synthetic inputs only;', ', '.join(alias_cases),
          '; no native SKTool or PLC execution.')


if __name__ == '__main__':
    main()
