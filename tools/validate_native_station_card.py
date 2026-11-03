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
from validate_native_operator_console_01 import runtime
from validate_native_overview_panel import EXTRA as OVERVIEW_EXTRA
from native_overview_panel import overview_module, station_card_module

CARD_EXTRA = r'''
 Check(UiOverviewMetric3Note.Text='Нет свежего подтверждения ПЛК','no fresh counter note');
 V[0,0].ComputerName:='localhost';V[1,0].OriginalAsInt:=32;
 Tick(1060,30003,142);Tick(1061,30004,143);
 Check(UiOverviewMetric3Note.Text='У всех станций есть свежее обновление','fresh note agrees with zero missing');
 Check(UiOverviewPumpStatus0.Text='Ошибка ПЧ: 7','confirmed fault displayed');
 Check(Pos('7.',UiCardEventText.Text)>0,'event summary uses current fault');
 Check(Pos('0 с назад',UiCardConnectionText.Text)>0,'connection summary uses PLC progress');
 Check(UiOverviewPumpStatus1.Text='Нет данных','pump2 stays unknown');
 Check(UiOverviewPumpStatus2.Text='Нет данных','pump3 stays unknown');
 Check(UiOverviewPumpStatus3.Text='Нет данных','pump4 stays unknown');
 Check(UiPumpState0.Text='Рабочий статус: нет данных','fault code is not motor state');
 V[0,6].IsGoodQuality:=False;OperatorUiUpdate;
 Check(UiOverviewPumpStatus0.Text='Нет данных','unknown fault cannot remain old confirmed fault');
 Check(Pos('нет данных',UiCardEventText.Text)>0,'bad fault quality resets summary');
 Tick(1065,30004,147);
 Check(Pos('4 с назад',UiCardConnectionText.Text)>0,'connection age is not refresh time');
 Tick(1070,30004,152);Tick(1076,30004,158);
 Check(UiOverviewMetric3Note.Text='Есть станции без свежих данных','partial freshness note');
 Check(Pos('Нет свежего подтверждения',UiCardConnectionText.Text)>0,'stale link does not look live');
 Check(V[0,5].OriginalAsInt=400,'card never writes setpoint');
'''


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
        rect=lambda name:struct.unpack_from('<4f',overview[name]['body'],8)
        columns=[rect(n) for n in ('UiRow0Name','UiRow0Mode','UiRow0Pressure','UiRow0Setpoint',
                 'UiOverviewPumpHeader','UiRow0Status','UiOverviewUpdatedHeader','UiRow0Open')]
        assert all(a[0]+a[2]<=b[0] for a,b in zip(columns,columns[1:])), 'table columns overlap'
        for i in range(4):
            for name in (f'UiOverviewPumpMarker{i}', f'UiOverviewPumpStatus{i}'):
                x,y,w,h=rect(name)
                assert columns[4][0]<=x and x+w<=columns[4][0]+columns[4][2]

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

        pascal=root/'pascal';pascal.mkdir()
        print(runtime(pascal,lambda text:station_card_module(overview_module(text)),OVERVIEW_EXTRA+CARD_EXTRA))

        print('PASS native station card: overview stale-note branches, four named pumps, unknown pump2-4, read-only event/connection summaries, 169 Text, 15 bindings, source/resource preservation')


if __name__ == '__main__':
    main()
