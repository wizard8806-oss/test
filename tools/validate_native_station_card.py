#!/usr/bin/env python3
"""Station-card structure, unknown-state, read-only logic and copy guards."""
import re
import struct
import tempfile
from pathlib import Path

import prepare_native_ui_event_probe as candidate
from build_native_operator_console_01 import native_navigation_grid_pages, parse_pages, repair_visual_page_style
from native_station_card import station_card_pages
from validate_native_ui_event_probe import fixture


def main():
    with tempfile.TemporaryDirectory(prefix='native-station-card-') as tmp:
        # The fixture contains synthetic public data; the production helper's
        # Windows-private ACL is tested separately by its existing checks.
        candidate._private_directory = lambda path: None
        root = Path(tmp)
        source = root / 'codex_diag_11_review_tabs_test0001'
        fixture(source)
        pages = native_navigation_grid_pages(
            repair_visual_page_style((source / 'Pages.spg').read_bytes(), True))
        (source / 'Pages.spg').write_bytes(pages)
        (source / 'Scripts/Scripts.ssc').write_bytes(
            candidate.pressure_display_scripts((source / 'Scripts/Scripts.ssc').read_bytes()))
        before = candidate.inventory(source)
        overview_out = root / 'codex_diag_11_review_overview_test0001'
        overview_report = candidate.prepare_overview_panel(
            source, overview_out, before['Pages.spg'], before['Scripts/Scripts.ssc'])
        assert overview_report['changedScripts'] == ['OperatorConsole']
        source_sha = candidate.inventory(overview_out)
        out = root / 'codex_diag_11_review_station_card_test0001'
        report = candidate.prepare_station_card(
            overview_out, out, source_sha['Pages.spg'], source_sha['Scripts/Scripts.ssc'])
        assert report['changedScripts'] == ['OperatorConsole']
        assert report['unknownPumpStatesPreserved'] and report['radioHealthInferred'] is False
        assert report['hardwareCommands'] == 0 and not report['WindowsCompileObserved']
        assert candidate.inventory(overview_out) == source_sha
        for name, digest in source_sha.items():
            if name in ('Pages.spg', 'Scripts/Scripts.ssc', 'CodexProbeManifest.json') or name.startswith('Scripts/Compiled/'):
                continue
            assert candidate.SHA((out / name).read_bytes()) == digest, name

        old_pages = parse_pages((overview_out / 'Pages.spg').read_bytes())
        new_pages = parse_pages((out / 'Pages.spg').read_bytes())
        assert sum(len(page['objects']) for page in new_pages) == 169
        old = {p['name']: p for p in old_pages}
        new = {p['name']: p for p in new_pages}
        for name in ['PageDiagnostics', 'PageUiAlarms', 'PageUiCharts', 'PageUiSettings']:
            assert old[name]['header'] == new[name]['header']
            assert old[name]['objects'] == new[name]['objects']
        overview = {o['name']: o for o in new['PageUiOverview']['objects']}
        for i in range(4):
            assert overview[f'UiOverviewPumpMarker{i}']['caption'] == f'НАСОС {i + 1}'
            assert overview[f'UiOverviewPumpStatus{i}']['caption'] == 'Нет данных'
        assert overview['UiOverviewPumpInfo']['caption'] == 'Насосы 2–4: данных нет'
        assert new['PageUiOverview']['objects'][0]['body']

        card = {o['name']: o for o in new['PageProcess']['objects']}
        for i in range(4):
            assert card[f'UiPumpState{i}']['caption'] == 'Рабочий статус: нет данных'
        for i in range(1, 4):
            assert card[f'UiPumpUnknown{i}']['caption'] == f'НАСОС {i + 1}'
            for metric in ['Frequency', 'Current', 'Fault']:
                assert card[f'UiPump{metric}Value{i}']['caption'] == 'Нет данных'
        assert card['UiCardEventText']['caption'].endswith('вкладка «Аварии».')
        assert card['UiCardConnectionText']['caption'].endswith('вкладка «Диагностика».')
        for name in ['UiCardEventPanel', 'UiCardConnectionPanel']:
            x, y, w, h = struct.unpack_from('<4f', card[name]['body'], 8)
            assert y >= 902 and y + h <= 1080

        audit = candidate.audit(out)
        assert audit['buttons'] == 15 and not audit['findings']
        scripts = candidate.scripts((out / 'Scripts/Scripts.ssc').read_bytes())
        assert len(scripts) == 48
        body = scripts[7]['body']
        assert 'UiStationCount = 0' in body and 'Нет станций в обзоре' in body
        assert 'FreshCount = UiStationCount' in body and 'У всех станций есть свежее обновление' in body
        assert 'UiCardConnectionText.Text' in body and 'PlcAliveCounter' in body
        assert 'UiDashboardFaultCode[0]' in body
        assert not re.search(r'\.Value\s*:=|SetVariableValue|AddActionMessage', body)
        assert all(scripts[i]['name'] == candidate.scripts((overview_out / 'Scripts/Scripts.ssc').read_bytes())[i]['name']
                   for i in scripts)

        print('PASS native station card: overview stale-note branches, four named pumps, unknown pump2-4, read-only event/connection summaries, 169 Text, 15 bindings, source/resource preservation')


if __name__ == '__main__':
    main()
