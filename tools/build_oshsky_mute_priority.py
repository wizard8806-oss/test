"""Give one requested mute token its transfer cycle on the shared R2553 output."""
import argparse
import hashlib
import re
import struct
from pathlib import Path

from build_native_merge_r16 import macro_mirrors
from prepare_telemetry_hmi_r19 import replace_records

SOURCE_SHA = '67dd6fcc45d3d8aa9f145575b4ace0e31fc7ac99fbefd841434f66e065ec10c9'


def build(source):
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA:
        raise ValueError('Expected the saved Oshsky r3f HMI')
    first, second = macro_mirrors(data)
    assert first == second
    body = first[4:].decode('utf-16-be')
    old = '} else if (BootAck == 0u) {'
    assert body.count(old) == 1
    change = body.replace(old, '} else { /* Mute uses this cycle. Boot acknowledgement resumes on the next. */')
    encoded = change.encode('utf-16-be')
    new = struct.pack('>I', len(encoded)) + encoded
    offsets = [m.start() for m in re.finditer(re.escape(first), data)]
    assert len(offsets) == 2
    output = replace_records(data, [(pos, first, new) for pos in offsets])
    for before, after in [('R3f DIAG 26.11.2026', 'R3g DIAG 27.11.2026'), ('R3f · живые данные', 'R3g · живые данные')]:
        output = output.replace(before.encode('utf-16-be'), after.encode('utf-16-be'))
    # The two sound pages use the short native label.
    label = lambda text: struct.pack('>I', len(text) * 2) + text.encode('utf-16-be')
    return output.replace(label('R3f'), label('R3g'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = build(args.source)
    with args.output.open('xb') as file:
        file.write(data)
