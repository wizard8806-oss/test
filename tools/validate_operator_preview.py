#!/usr/bin/env python3
"""Exercise the offline UI in Chromium using an ephemeral loopback-only server.

Optional development dependencies: playwright and Chromium. No vendor projects,
PLC, OPC, archive or other servers are opened. Only the generated HTML directory
is served. Browser traffic outside that loopback origin is blocked and reported.
"""
import argparse
import csv
import io
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from build_operator_preview import DEFAULT, build


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def validate(browser_path, screenshots=None):
    from playwright.sync_api import sync_playwright, expect

    output = build()
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(output.parent)))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    checks, errors, external = [], [], []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=browser_path, headless=True, args=['--no-sandbox'])
            context = browser.new_context(viewport={'width':1536, 'height':1050}, accept_downloads=True)

            def traffic(route):
                if route.request.url.startswith(origin + '/'):
                    route.continue_()
                else:
                    external.append(route.request.url)
                    route.abort()

            context.route('**/*', traffic)
            def observe(page):
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('console', lambda message: errors.append(message.text) if message.type=='error' else None)

            context.on('page', observe)
            page = context.new_page()
            page.goto(origin + '/' + DEFAULT.name)
            expect(page.locator('[data-testid="fleet-table"] tbody tr')).to_have_count(4)
            expect(page.locator('.preview-strip')).to_contain_text('оборудование не подключено')
            stale = page.locator('tr[data-station-id="station-004"]')
            expect(stale).to_contain_text('НЕТ ДАННЫХ')
            assert '4,00' not in stale.inner_text()
            page.locator('#fleet-group').select_option('north')
            expect(page.locator('[data-testid="fleet-table"] tbody tr')).to_have_count(2)
            page.locator('#fleet-group').select_option('all')
            page.locator('#fleet-search').fill('station-001')
            expect(page.locator('[data-testid="fleet-table"] tbody tr')).to_have_count(1)
            page.locator('#fleet-search').fill('')
            checks.append('fleet: filters, missing pressure and stale values')

            page.locator('tr[data-station-id="station-001"] .station-link').click()
            expect(page.locator('[data-testid="station-pressure"]')).to_have_text('Нет достоверных данных')
            expect(page.locator('[data-testid="station-setpoint"]')).to_contain_text('4,00')
            expect(page.locator('.pump-card')).to_have_count(4)
            expect(page.locator('.pump-card').nth(1)).to_contain_text('Нет данных')
            page.locator('[data-action="draft-plus"]').click()
            expect(page.locator('.draft-value')).to_contain_text('4,1')
            expect(page.locator('[data-testid="station-setpoint"]')).to_contain_text('4,00')
            page.locator('[data-action="draft-cancel"]').click()
            expect(page.locator('.draft-value')).to_contain_text('4,0')
            with page.expect_popup() as opened:
                page.locator('[data-action="open-window"]').click()
            popup = opened.value
            expect(popup.locator('body')).to_have_class('standalone')
            expect(popup.locator('.preview-strip')).to_be_visible()
            # A remote model update cancels another window's pending draft.
            popup.locator('[data-action="draft-plus"]').click()
            page.locator('[data-action="draft-plus"]').click()
            page.locator('[data-action="confirm-apply"]').click()
            expect(page.get_by_role('dialog')).to_contain_text('только в модели браузера')
            page.locator('[data-action="apply-model"]').click()
            expect(page.locator('[data-testid="station-setpoint"]')).to_contain_text('4,10')
            expect(popup.locator('[data-testid="station-setpoint"]')).to_contain_text('4,10')
            expect(popup.locator('[data-action="draft-cancel"]')).to_be_disabled()
            checks.append('setpoint: draft/cancel, mock confirmation, separate-window sync')

            page.locator('#role-select').select_option('viewer')
            expect(page.locator('[data-action="draft-plus"]')).to_be_disabled()
            page.evaluate("location.hash='#alarms'")
            expect(page.locator('[data-action="ack-alarm"]').first).to_be_disabled()
            page.locator('#role-select').select_option('operator')
            page.locator('[data-action="ack-alarm"][data-id="a-drive"]').click()
            row = page.locator('tr[data-alarm-id="a-drive"]')
            expect(row).to_contain_text('Активно')
            expect(row).to_contain_text('Подтверждено')
            popup.evaluate("location.hash='#station/station-003/alarms'")
            expect(popup.locator('tr[data-alarm-id="a-drive"]')).to_contain_text('Подтверждено')
            page.locator('#alarm-filter').select_option('unack')
            expect(page.locator('tr[data-alarm-id="a-drive"]')).to_have_count(0)
            checks.append('alarms: viewer, acknowledgement preserves active cause and syncs')

            page.evaluate("location.hash='#charts'")
            expect(page.locator('svg[data-chart="pressure"]')).to_be_visible()
            page.locator('#chart-station').select_option('station-002')
            page.locator('#chart-extras').check()
            expect(page.locator('svg[data-chart]')).to_have_count(3)
            page.locator('svg[data-chart="pressure"]').focus()
            page.keyboard.press('ArrowRight')
            expect(page.locator('#chart-tooltip')).to_be_visible()
            page.locator('[data-action="chart-range"][data-hours="24"]').click()
            with page.expect_download() as downloaded:
                page.locator('[data-action="export-csv"]').click()
            rows = list(csv.reader(io.StringIO(Path(downloaded.value.path()).read_text(encoding='utf-8-sig')), delimiter=';'))
            invalid = [r for r in rows[1:] if r[-1]=='bad']
            assert invalid and all(r[4:8]==['','','',''] for r in invalid)
            page.locator('#chart-station').select_option('station-001')
            expect(page.locator('.chart-no-data').first).to_contain_text('История ещё не подключена')
            expect(page.locator('[data-action="export-csv"]')).to_be_disabled()
            checks.append('trends: periods, separate units, keyboard tooltip, gaps, CSV, no fabricated bench history')

            page.locator('#role-select').select_option('engineer')
            page.evaluate("location.hash='#settings'")
            page.locator('[data-action="add-station"]').click()
            page.locator('#new-station [name="name"]').fill('НС-05 · новая')
            page.locator('#new-station [name="pumpCount"]').fill('2')
            page.locator('#new-station [type="submit"]').click()
            expect(page.locator('[data-testid="catalog-table"] tbody tr')).to_have_count(5)
            page.locator('a.station-link', has_text='НС-05').click()
            expect(page.locator('#setting-id')).to_have_value('station-005')
            page.locator('a[href="#station/station-005/observation"]').click()
            expect(page.locator('.pump-card')).to_have_count(2)
            expect(page.locator('[data-testid="station-setpoint"]')).to_contain_text('—')
            expect(page.locator('[data-action="draft-plus"]')).to_be_disabled()
            page.locator('a[href="#station/station-005/settings"]').click()
            page.locator('#setting-prefix').fill('codex.Device1')
            page.locator('#station-settings [type="submit"]').click()
            expect(page.locator('#settings-error')).to_contain_text('одни и те же адреса')
            page.locator('#setting-prefix').fill('codex.Device5')
            page.locator('#station-settings [type="submit"]').click()
            # Same ID with a new route must not inherit old telemetry/alarms/history.
            page.evaluate("location.hash='#station/station-001/settings'")
            page.locator('#setting-prefix').fill('codex.Other')
            page.locator('#station-settings [type="submit"]').click()
            page.locator('a[href="#station/station-001/observation"]').click()
            expect(page.locator('[data-testid="station-setpoint"]')).to_contain_text('—')
            page.reload()
            expect(page.locator('[data-testid="station-setpoint"]')).to_contain_text('—')
            checks.append('catalog: add station, variable pump count, duplicate-route rejection, rebinding clears old data, reload')

            page.locator('#role-select').select_option('engineer')
            page.evaluate("location.hash='#settings'")
            with page.expect_download() as downloaded:
                page.locator('[data-action="export-catalog"]').click()
            exported = json.loads(Path(downloaded.value.path()).read_text(encoding='utf-8'))
            assert len(exported['stations'])==5 and 'snapshots' not in exported
            exported['password']='PRIVATE_FIXTURE'
            page.locator('#catalog-file').set_input_files({'name':'invalid.json','mimeType':'application/json','buffer':json.dumps(exported).encode()})
            expect(page.locator('#toast')).to_contain_text('Импорт отклонён')
            expect(page.locator('[data-testid="catalog-table"] tbody tr')).to_have_count(5)
            checks.append('catalog export/import: configuration only, unknown/secret fields rejected atomically')

            popup.close()
            # Clean fixture view for review screenshots, not the test's modified model.
            page.evaluate('localStorage.clear()')
            page.reload()
            page.locator('#role-select').select_option('engineer')
            if screenshots:
                screenshots.mkdir(parents=True, exist_ok=True)
                for name, hash_value in [('overview','overview'),('station','station/station-001/observation'),('alarms','alarms'),('charts','charts'),('settings','settings')]:
                    page.evaluate('(hash)=>{location.hash=hash}', '#'+hash_value)
                    page.locator('#view h1').wait_for()
                    page.evaluate('window.scrollTo(0,0)')
                    page.screenshot(path=str(screenshots/(name+'.png')), full_page=True)
            page.locator('[data-action="theme"]').click()
            expect(page.locator('html')).to_have_attribute('data-theme','light')
            page.set_viewport_size({'width':768,'height':1024})
            page.evaluate("location.hash='#station/station-001/observation'")
            expect(page.locator('.pump-card')).to_have_count(4)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            if screenshots:
                page.evaluate('window.scrollTo(0,0)')
                page.screenshot(path=str(screenshots/'station-tablet-light.png'), full_page=True)
            checks.append('desktop/tablet, light theme, responsive width, explicit model marker')
            assert not errors, errors
            assert not external, external
            result = {'status':'PASS','checks':checks,'browser':browser.version,'javascriptErrors':errors,'externalRequests':external,'transport':'ephemeral loopback HTTP; file:// blocked by managed Chromium policy','html':str(output)}
            browser.close()
            return result
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', default='/usr/bin/chromium')
    parser.add_argument('--screenshots', type=Path)
    parser.add_argument('--report', type=Path, help='Optional JSON result outside the native project')
    args=parser.parse_args()
    result=json.dumps(validate(args.browser,args.screenshots), ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(result+'\n', encoding='utf-8')
    print(result)
