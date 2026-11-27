"""Check the native Oshsky alarm page for overlapping actions and the original mute binding."""
import argparse
import struct
from itertools import combinations
from pathlib import Path

from build_animation_probe_hmi import qs
from build_native_merge_r16 import GROUP
from build_oshsky_sound_transfer import transfer_record
from skm_project_header import read_project_header


ACTIONS = {
    'SB24002': 'Запуски ПЛК',
    'BB18004': 'Отключить звук',
    'SB63010': 'История ПЧ',
    'BB8286': 'Сохранить журнал',
}
CAPTIONS = {'Text18002': 'BB18004', 'Text8284': 'BB8286'}


def read_toolbar(data):
    pages = read_project_header(data)['pageCount']
    markers = [qs(f'Screen{i}') + b'\xff' * 4 for i in range(1, pages + 1)]
    start = data.index(markers[8])
    stop = min((p for m in markers if (p := data.index(m)) > start), default=len(data))
    count_at = start + len(markers[8])
    count = struct.unpack_from('>I', data, count_at)[0]
    # Ungrouped drawing items also contribute to the SKTool scene count.
    starts = [m.start() for m in GROUP.finditer(data, count_at + 4, stop)]
    if not starts or starts[0] != count_at + 4 or len(starts) > count:
        raise ValueError('Invalid grouped widget boundaries on the alarm page')
    result = {}
    for a, b in zip(starts, starts[1:] + [stop]):
        widget = data[a:b]
        for name in (*ACTIONS, *CAPTIONS):
            if qs(name) not in widget:
                continue
            if name in result:
                raise ValueError(f'Duplicate widget {name}')
            at = widget.index(bytes.fromhex('0001000f')) + 4
            width, height = struct.unpack_from('>2d', widget, at + 16)
            x, y = struct.unpack_from('>2d', widget, at + 73)
            if not (width > 0 and height > 0 and x >= 0 and y >= 0 and x + width <= 1024 and y + height <= 600):
                raise ValueError(f'Invalid bounds for {name}')
            if name in ACTIONS and qs(ACTIONS[name]) not in widget:
                raise ValueError(f'Action label changed for {name}')
            if name == 'BB18004' and qs('LB800') not in widget:
                raise ValueError('Missing panel mute request LB800')
            result[name] = (x, y, x + width, y + height)
    if result.keys() != ACTIONS.keys() | CAPTIONS.keys():
        raise ValueError('Missing alarm toolbar objects')
    return result


def validate(data):
    bounds = read_toolbar(data)
    for caption, action in CAPTIONS.items():
        if bounds[caption] != bounds[action]:
            raise ValueError(f'Detached caption for {action}')
    for a, b in combinations(ACTIONS, 2):
        x1, y1, x2, y2 = bounds[a]
        u1, v1, u2, v2 = bounds[b]
        if max(x1, u1) < min(x2, u2) and max(y1, v1) < min(y2, v2):
            raise ValueError(f'Overlapping active buttons {a} and {b}')
    if data.count(transfer_record()) != 1:
        raise ValueError('Expected one native mute transfer to R2553')
    return bounds


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    args = parser.parse_args()
    for name, box in validate(args.project.read_bytes()).items():
        print(name, box)
