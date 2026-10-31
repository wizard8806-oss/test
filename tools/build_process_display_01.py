#!/usr/bin/env python3
"""Build a read-only native 2.6.15 process-card copy, without modifying OPC vars."""
from _runtime import SCADA_SEED
import base64, hashlib, io, json, struct, textwrap, zipfile
from pathlib import Path
from build_radio_display_01 import bootstrap
from rebuild_scada_inline_delivery_01 import ansi, wide, num

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/station-process-display-01'
SOURCE = SCADA_SEED

def sha(b): return hashlib.sha256(b).hexdigest()

def build_pages():
    seed_pages = (SOURCE / 'Pages.spg').read_bytes()
    common_seed = seed_pages[209:350]
    assert len(common_seed) == 141
    assert struct.unpack_from('<I', common_seed, 107)[0] == 9164
    prefix_seed = seed_pages[12:193]
    objects = []
    def text(page, name, caption, rect, scale=1.0, color=0x646464):
        body = bytearray(common_seed)
        struct.pack_into('<I', body, 4, 0)
        struct.pack_into('<4f', body, 8, *rect)
        body[24] = 255; body[29:31] = b'\x01\x01'; body[31] = 4
        struct.pack_into('<ff', body, 32, scale, 0)
        struct.pack_into('<I', body, 40, 0xFFFFFF); body[44] = 255
        struct.pack_into('<I', body, 45, color)
        struct.pack_into('<I', body, 54, sum(x['page'] == page for x in objects))
        uid = 64100 + len(objects) * 4
        struct.pack_into('<I', body, 107, uid)
        struct.pack_into('<q', body, 111, -1)
        objects.append(dict(page=page, name=name, uid=uid, rect=rect, scale=scale, caption=caption))
        return struct.pack('<H', 4) + ansi(name) + body + wide(caption) + bytes.fromhex('000000ffffff00ff06')
    first = [
        text(0, 'ProcessTitle', 'НАСОСНАЯ СТАНЦИЯ · СТЕНД', (32, 64, 1376, 46), 1.3),
        text(0, 'ProcessStatus', 'Ожидание данных станции', (32, 126, 1376, 48), 1.05),
        text(0, 'ProcessDetail', 'Показания и достоверность источника передаются контроллером.', (32, 184, 1376, 68), .78),
        text(0, 'ProcessPressureLabel', 'ДАВЛЕНИЕ', (32, 276, 650, 36), .9),
        text(0, 'ProcessSetpointLabel', 'УСТАВКА ДАВЛЕНИЯ', (724, 276, 684, 36), .9),
        text(0, 'ProcessPressure', 'Нет данных', (32, 322, 650, 76), 1.55),
        text(0, 'ProcessSetpoint', 'Нет данных', (724, 322, 684, 76), 1.9),
        text(0, 'ProcessPressureNote', 'Ожидание значения и признака достоверности.', (32, 410, 650, 70), .72),
        text(0, 'ProcessSetpointNote', 'Действующая уставка ПЛК · только чтение', (724, 410, 684, 70), .75),
        text(0, 'ProcessDriveTitle', 'НАСОС 1 · ПЧ 900G', (32, 508, 1376, 36), .95),
        text(0, 'ProcessFrequencyLabel', 'ФАКТИЧЕСКАЯ ЧАСТОТА', (32, 562, 428, 36), .75),
        text(0, 'ProcessCurrentLabel', 'ВЫХОДНОЙ ТОК', (504, 562, 428, 36), .75),
        text(0, 'ProcessFaultLabel', 'ОШИБКА ПЧ', (976, 562, 432, 36), .75),
        text(0, 'ProcessFrequency', 'Нет данных', (32, 608, 428, 66), 1.65),
        text(0, 'ProcessCurrent', 'Не подключён', (504, 608, 428, 66), 1.05),
        text(0, 'ProcessFault', 'Не подключён', (976, 608, 432, 66), 1.05),
        text(0, 'ProcessFrequencyNote', 'Ожидание состояния частоты.', (32, 688, 428, 86), .68),
        text(0, 'ProcessCurrentNote', 'Чтение выходного тока ПЧ ещё не добавлено.', (504, 688, 428, 86), .68),
        text(0, 'ProcessFaultNote', 'Собственный код ошибки ПЧ ещё не подключён.', (976, 688, 432, 86), .68),
        text(0, 'ProcessMainScope', 'Первое подключение: мониторинг. Кнопки управления добавляются после проверки команд и подтверждений ПЛК.', (32, 798, 1376, 58), .72),
    ]
    second = [
        text(1, 'ProcessDiagTitle', 'ДИАГНОСТИКА СТАНЦИИ', (32, 64, 1376, 46), 1.3),
        text(1, 'ProcessOPC', 'MasterOPC: ожидание переменных', (32, 130, 1376, 44), .85),
        text(1, 'ProcessMap', 'Версия карты ПЛК: не подтверждена', (32, 186, 1376, 36), .8),
        text(1, 'ProcessValidity', 'Давление: достоверность неизвестна', (32, 236, 1376, 44), .85),
        text(1, 'ProcessFreshness', 'Свежесть данных станции ещё не подтверждается автоматически.', (32, 294, 1376, 56), .78),
        text(1, 'ProcessAlarmWords', 'Слова состояния ПЛК: нет данных', (32, 368, 1376, 36), .8),
        text(1, 'ProcessAlarmNote', 'Расшифровка слов состояния ещё проверяется. Они не являются собственным кодом ошибки ПЧ.', (32, 414, 1376, 62), .74),
        text(1, 'DiagRadioTitle', 'TELEOFIS · НЕЗАВИСИМАЯ ДИАГНОСТИКА МОДЕМА', (32, 506, 1376, 36), .9),
        text(1, 'DiagRadio', 'Сигнал: нет данных | Режим сети: нет данных | Питание: нет данных', (32, 556, 1376, 44), .8),
        text(1, 'DiagRadioNote', 'Ожидание сборщика радиодиагностики.', (32, 612, 1376, 68), .75),
        text(1, 'ProcessChecks', 'При потере показаний: MasterOPC и Gateway → интернет и M2M24 → модем → ПЛК и RS485.\r\nКаждый участок требует отдельного подтверждения.', (32, 712, 1376, 82), .75),
        text(1, 'ProcessScope', 'CL50S не участвует в оценке этой карточки. Установившееся давление не означает остановку обмена.', (32, 812, 1376, 52), .72),
    ]
    def header(page):
        body = bytearray(prefix_seed)
        struct.pack_into('<q', body, 33, page)
        body = bytes(body)
        for a, b in [(ansi('Page1'), ansi(['PageProcess', 'PageDiagnostics'][page])),
                     (wide('Страница 1'), wide(['Станция', 'Диагностика'][page])),
                     (ansi('Subpage1'), ansi(['SubpageProcess', 'SubpageDiagnostics'][page])),
                     (wide('Подстраница 1'), wide(['Станция', 'Диагностика'][page])),
                     (num(9156), num(64000 + page * 8)), (num(9160), num(64004 + page * 8))]:
            assert body.count(a) == 1
            body = body.replace(a, b, 1)
        return body
    pages = struct.pack('<qI', 2, 2) + header(0) + num(len(first)) + b''.join(first)
    pages += header(1) + num(len(second)) + b''.join(second)
    assert len({x['name'] for x in objects}) == len(objects)
    return pages, objects

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pages, objects = build_pages()
    (OUT / 'Pages.spg').write_bytes(pages)
    core = (OUT / 'scripts/StationDiagnostics.txt').read_bytes()
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, body in [('Pages.spg', pages), ('ProcessModule.txt', core)]:
            item = zipfile.ZipInfo(name, (2026, 10, 30, 0, 0, 0)); item.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(item, body)
    bundle = payload.getvalue(); (OUT / 'bundle.zip').write_bytes(bundle)
    installer = (ROOT / 'tools/process_display_install_template.ps1').read_text()
    installer = installer.replace('__BUNDLE__', '\n'.join(textwrap.wrap(base64.b64encode(bundle).decode(), 120)))
    installer = installer.replace('__BUNDLE_SHA__', sha(bundle))
    for key, path in [('CORE', ROOT / 'artifacts/simple-scada-diagnostics-01/scripts/StationDiagnostics.txt'),
                      ('RADIO', ROOT / 'artifacts/teleofis-radio-display-01/scripts/StationRadioDiagnostics.txt')]:
        installer = installer.replace('__' + key + '_SHA__', sha(path.read_text().strip().encode()))
    (OUT / 'Install-Process-Display-01.ps1').write_text(installer)
    paste = bootstrap(installer)
    # Keep the generic integrity-checked delivery helper; only rename its local variables for this task.
    paste = paste.replace('$radio', '$process')
    (OUT / 'Paste-Process-Display-01.ps1').write_text(paste)
    manifest = dict(date='2026-10-30', source='Current codex_diag_02', target='Desktop/codex_diag_03',
        version='2.6.15.0', source_preserved=True, variables_and_OPC_servers_preserved=True,
        process_tags_import_required=True, lookup='OPC item address plus exact server/host check; no variable-name dependency',
        CL50S_health_dependency=False, process_writes=False, current_or_native_fault_export_added=False,
        radio_module_preserved=True, freshness='Explicitly unconfirmed; no fake success based on GOOD or constant PV',
        alarm_decoding='Deferred pending packing verification; raw words only',
        pressure_validity='Use controller R2303; valid zero is displayed, invalid source hides pressure',
        frequency_factor_reference=0.1, frequency_nonzero_live_scale_verified=False,
        objects=objects, bundle_sha256=sha(bundle), installer_sha256=sha(installer.encode()),
        inline_characters=len(paste), native_GUI_F9_passed=False)
    observation = OUT / 'native-observation-2026-10-30.json'
    if observation.exists():
        native = json.loads(observation.read_text())
        manifest.update(native_GUI_F9_passed=None,
            native_pages_opened=native['newPagesOpened'],
            native_process_execution_observed=native['newProcessScriptExecutionObserved'],
            native_radio_module_execution_observed=native['interpretation']['radioModuleExecutionConfirmedAfterCopy'],
            native_observation=observation.name,
            native_F9_note='Exact F9 command not separately reported; new pages and process/radio script execution observed in native client.')
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('Built process card:', len(objects), 'texts;', len(paste), 'inline characters')

if __name__ == '__main__': main()
