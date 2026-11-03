"""Approved station-card composition based on the saved native overview copy."""
import importlib.util
import struct
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    '_station_card_overview_builder', Path(__file__).with_name('native_overview_panel.py'))
overview = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(overview)
builder = overview._builder


def _set_rect(obj, rect):
    body = bytearray(obj['body'])
    struct.pack_into('<4f', body, 8, *rect)
    obj['body'] = body
    prefix = 6 + len(obj['name'].encode('utf8'))
    obj['record'] = obj['record'][:prefix] + body + obj['record'][prefix + 141:]


def _set_caption(obj, caption):
    prefix = 6 + len(obj['name'].encode('utf8'))
    obj['record'] = obj['record'][:prefix + 141] + builder.string(caption, True) + bytes.fromhex('000000ffffff00ff06')
    obj['caption'] = caption


def station_card_pages(raw):
    pages = builder.parse_pages(raw)
    if len(pages) != 6 or sum(len(p['objects']) for p in pages) != 137:
        raise ValueError('Expected the saved 137-Text overview candidate')
    page_by_name = {p['name']: p for p in pages}
    overview_page = page_by_name.get('PageUiOverview')
    card = page_by_name.get('PageProcess')
    if overview_page is None or card is None:
        raise ValueError('Expected overview and station-card pages')
    names = {o['name'] for p in pages for o in p['objects']}
    if any(name.startswith('UiPumpState') or name.startswith('UiCardEvent') for name in names):
        raise ValueError('Station-card components already exist')

    ov = {o['name']: o for o in overview_page['objects']}
    for name in ['UiOverviewPumpHeader', 'UiOverviewPumpInfo',
                 'UiOverviewMetric3Note'] + [f'UiOverviewPumpMarker{i}' for i in range(4)]:
        if name not in ov:
            raise ValueError('Unexpected saved overview controls: ' + name)
    _set_caption(ov['UiOverviewPumpHeader'], 'СТАТУС НАСОСОВ')
    _set_rect(ov['UiOverviewPumpHeader'], (1030, 482, 440, 32))
    _set_caption(ov['UiOverviewPumpInfo'], 'Насосы 2–4: данных нет')
    _set_rect(ov['UiOverviewPumpInfo'], (1030, 626, 440, 24))
    # Allocate all columns together; widening pumps cannot cover status/age.
    for suffix, header, x, width in [
        ('Mode', '540', 620, 100), ('Pressure', '678', 730, 140),
        ('Setpoint', '846', 880, 140), ('Status', '1004', 1480, 180),
        ('Open', None, 1800, 70),
    ]:
        _set_rect(ov['UiRow0' + suffix], (x, 530, width, 80))
        if header:
            _set_rect(ov['UiOverviewHeader0' + header], (x, 482, width, 32))
    _set_rect(ov['UiOverviewUpdatedHeader'], (1670, 482, 120, 32))
    _set_rect(ov['UiOverviewUpdated'], (1670, 538, 120, 70))
    for i in range(4):
        obj = ov[f'UiOverviewPumpMarker{i}']
        _set_caption(obj, f'НАСОС {i + 1}')
        _set_rect(obj, (1030 + 110 * i, 538, 100, 30))

    uid = max(struct.unpack_from('<I', o['body'], 107)[0]
              for p in pages for o in p['objects'])
    proto = next(o['body'] for o in card['objects'] if o['name'] == 'UiMainHeading')
    back, front = [], []

    def add(name, caption, rect, scale=.78, bg=builder.PANEL,
            fg=builder.TEXT, layer=front):
        nonlocal uid
        uid += 4
        body = bytearray(proto)
        struct.pack_into('<4f', body, 8, *rect)
        body[31] = builder.FONT_REGULAR18
        struct.pack_into('<f', body, 32, scale)
        struct.pack_into('<I', body, 40, fg)
        struct.pack_into('<I', body, 45, bg)
        struct.pack_into('<q', body, 75, -1)
        struct.pack_into('<I', body, 107, uid)
        return struct.pack('<H', 4) + builder.string(name) + body + builder.string(caption, True) + bytes.fromhex('000000ffffff00ff06')

    # Four explicit per-pump work-state labels. A fault code is not a run-state.
    for i in range(4):
        x = 280 + 399 * i
        front.append(add(f'UiPumpState{i}', 'Рабочий статус: нет данных',
                         (x + 18, 490, 347, 22), .72, bg=0x1A293A, fg=builder.MUTED))

    controls = {o['name']: o for o in card['objects']}
    for name in ['ProcessDriveTitle', 'ProcessFrequencyLabel', 'ProcessCurrentLabel',
                 'ProcessFrequency', 'ProcessCurrent', 'ProcessFaultLabel', 'ProcessFault',
                 'UiPumpUnknown1', 'UiPumpUnknown2', 'UiPumpUnknown3']:
        if name not in controls:
            raise ValueError('Unexpected station card control: ' + name)

    for i in range(4):
        x = 280 + 399 * i
        if i == 0:
            _set_rect(controls['ProcessDriveTitle'], (x + 18, 456, 347, 32))
            _set_rect(controls['ProcessFrequencyLabel'], (x + 18, 516, 158, 20))
            _set_rect(controls['ProcessCurrentLabel'], (x + 194, 516, 171, 20))
            _set_rect(controls['ProcessFrequency'], (x + 18, 539, 158, 38))
            _set_rect(controls['ProcessCurrent'], (x + 194, 539, 171, 38))
            _set_rect(controls['ProcessFaultLabel'], (x + 18, 584, 130, 26))
            _set_rect(controls['ProcessFault'], (x + 154, 582, 211, 30))
            continue
        title = controls[f'UiPumpUnknown{i}']
        _set_caption(title, f'НАСОС {i + 1}')
        _set_rect(title, (x + 18, 456, 347, 32))
        for metric, label, value in [
            ('Frequency', 'ЧАСТОТА', 'Нет данных'),
            ('Current', 'ТОК', 'Нет данных'),
            ('Fault', 'КОД ОШИБКИ ПЧ', 'Нет данных'),
        ]:
            if metric == 'Frequency':
                label_rect, value_rect = (x + 18, 516, 158, 20), (x + 18, 539, 158, 38)
            elif metric == 'Current':
                label_rect, value_rect = (x + 194, 516, 171, 20), (x + 194, 539, 171, 38)
            else:
                label_rect, value_rect = (x + 18, 584, 136, 26), (x + 154, 582, 211, 30)
            front.append(add(f'UiPump{metric}Label{i}', label, label_rect, .68, fg=builder.MUTED))
            front.append(add(f'UiPump{metric}Value{i}', value, value_rect, .82))

    # These read-only summaries report the available view, with links by name to
    # the existing alarms and diagnostics pages. They do not claim radio health.
    back.append(add('UiCardEventPanel', '', (280, 916, 780, 116), .8,
                    bg=0x2A3B4E, layer=back))
    back.append(add('UiCardConnectionPanel', '', (1076, 916, 804, 116), .8,
                    bg=0x2A3B4E, layer=back))
    front.extend([
        add('UiCardEventHeading', 'СОБЫТИЯ · ТЕКУЩИЙ КОД ПЧ 1',
            (300, 928, 740, 24), .7, fg=builder.MUTED),
        add('UiCardEventText', 'Текущий код ПЧ 1: нет данных. История — вкладка «Аварии».',
            (300, 958, 740, 58), .72),
        add('UiCardConnectionHeading', 'СВЯЗЬ',
            (1096, 928, 764, 24), .7, fg=builder.MUTED),
        add('UiCardConnectionText', 'Нет свежего подтверждения ПЛК. Подробности — вкладка «Диагностика».',
            (1096, 958, 764, 58), .72),
    ])

    # Keep every original UID/control/event. Add lower panel backgrounds before
    # their text, then reassign page-local z-order consistently.
    rewritten = []
    for obj in card['objects']:
        name = obj['name']
        body = bytearray(obj['body'])
        if name == 'ProcessFaultNote':
            struct.pack_into('<4f', body, 8, 280, 672, 1600, 40)
        rewritten.append(obj['record'][:6 + len(name.encode('utf8'))] + body +
                         obj['record'][6 + len(name.encode('utf8')) + 141:])
    card_records = rewritten[:3] + back + rewritten[3:] + front
    overview_status_records = []
    result_pages = []
    for page in pages:
        page_records = []
        for obj in page['objects']:
            if page is overview_page and obj['name'].startswith('UiOverviewPumpStatus'):
                raise ValueError('Overview already has pump status rows')
            page_records.append(obj['record'])
        if page is overview_page:
            for i in range(4):
                overview_status_records.append(add(f'UiOverviewPumpStatus{i}', 'Нет данных',
                    (1030 + 110 * i, 574, 100, 44), .68, fg=builder.MUTED))
            page_records = []
            for obj in page['objects']:
                name = obj['name']
                body = bytearray(obj['body'])
                struct.pack_into('<I', body, 54, len(page_records))
                record = obj['record'][:6 + len(name.encode('utf8'))] + body + obj['record'][6 + len(name.encode('utf8')) + 141:]
                page_records.append(record)
            page_records.extend(overview_status_records)
        elif page is card:
            page_records = card_records
        normalized = []
        for z, record in enumerate(page_records):
            b = bytearray(record)
            start = 6 + struct.unpack_from('<I', b, 2)[0]
            struct.pack_into('<I', b, start + 54, z)
            normalized.append(bytes(b))
        result_pages.extend([page['header'], builder.U32(len(normalized)), b''.join(normalized)])
    return raw[:12] + b''.join(result_pages)
