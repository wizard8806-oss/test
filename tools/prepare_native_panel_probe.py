#!/usr/bin/env python3
"""Instrument two current R2 panel buttons in a private, pinned project copy.

This does not activate SCADA, change page/user rights, configure archives or send
equipment commands. Log markers distinguish dispatch from a returned API call;
neither proves that a panel was displayed. Native Compile/Save is still required.
"""
import argparse
import importlib.util
import re
import struct
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    '_panel_copy', Path(__file__).resolve().with_name('prepare_native_ui_event_probe.py'))
copy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(copy)

TARGETS = {
    'UiMessages2_OnClick': (32, "GoToMessagesGroupClient(GetClientName, -1)"),
    'UiTrendsAll1_OnClick': (39, "GoToTrendsClient(GetClientName, Now - 1/24.0, Now)"),
}


def event_body(name, call):
    return f'''var PanelClient: string;
begin
  UiPanelProbeLog('ENTER {name}');
  PanelClient := GetClientName;
  if PanelClient = '' then
  begin
    UiPanelProbeLog('CLIENT_EMPTY {name}');
    Exit;
  end;
  UiPanelProbeLog('CLIENT_PRESENT {name}');
  UiPanelProbeLog('BEFORE_API {name}');
  {call.replace('GetClientName', 'PanelClient')};
  UiPanelProbeLog('AFTER_API {name}');
end.'''


def patch_scripts(raw, probe_id):
    if not re.fullmatch(r'UIPANEL11-[A-Z0-9]{8,32}', probe_id):
        raise ValueError('Expected a unique, injection-safe UIPANEL11 identifier')
    before = copy.scripts(raw)
    if len(before) != 48 or before.get(7, {}).get('name') != 'OperatorConsole':
        raise ValueError('Expected the reviewed 48-script R2 project')
    reader = copy.Reader(raw)
    reader.number('q'); reader.take(reader.count(1024))
    if reader.number('I') != 0:
        raise ValueError('Script folders need separate review')
    count = reader.count(2048)
    parts, changed = [raw[:reader.pos]], set()
    for _ in range(count):
        start = reader.pos
        id_, name = reader.number('q'), reader.text(True)
        reader.take(17)
        text_start = reader.pos
        lines = [reader.text(True) for _ in range(reader.count(8192))]
        if name != 'OperatorConsole' and name not in TARGETS:
            parts.append(raw[start:reader.pos])
            continue
        body = '\n'.join(lines)
        if re.search(r'UiPanelProbe|UIPANEL11-|UINAV11-', body, re.I):
            raise ValueError('Existing diagnostic code requires review')
        if name == 'OperatorConsole':
            if 'UiCardConnectionText.Text' not in body or 'UiCardEventText.Text' not in body:
                raise ValueError('Expected the current station-card module')
            body = copy._replace_once(
                r'^interface[ \t]*$',
                'interface\nprocedure UiPanelProbeLog(const Stage: string);', body)
            body = copy._replace_once(
                r'^var[ \t]*\n(?=[ \t]*UiHasSample\b)',
                'var\n  UiPanelProbeBootSent: Boolean;\n', body)
            log = f'''procedure UiPanelProbeLog(const Stage: string);
begin
  try
    Log_Add('[{probe_id}] ' + Stage, True);
  except
  end;
end;

'''
            pattern = (r'^procedure OperatorUiUpdate;\n'
                       r'var Index, FreshCount, FaultCount, KnownCount: Integer;\n'
                       r'begin(?=\n)')
            boot = '''
  if not UiPanelProbeBootSent then
  begin
    UiPanelProbeBootSent := True;
    UiPanelProbeLog('BOOT');
  end;'''
            body = copy._replace_once(pattern, lambda m: log + m[0] + boot, body)
        else:
            expected_id, call = TARGETS[name]
            # Whitespace from a native Save is immaterial; the actual statement
            # sequence must still match, rather than replacing an unknown handler.
            original = before[id_]['body']
            expected = "begin if GetClientName <> '' then " + call + '; end.'
            compact = lambda text: re.sub(r'\s+', '', text).lower()
            if id_ != expected_id or compact(original) != compact(expected):
                raise ValueError('Unexpected target handler; original preserved')
            unit = re.match(r'(?is)\Aunit\s+' + re.escape(name) + r'\s*;\s*', body)
            body = (unit[0] if unit else '') + event_body(name, call)
        encoded = [line.encode('utf-16le') for line in body.split('\n')]
        parts.append(raw[start:text_start] + struct.pack('<I', len(encoded)) + b''.join(
            struct.pack('<I', len(line)//2) + line for line in encoded))
        changed.add(name)
    reader.done()
    if changed != {'OperatorConsole', *TARGETS}:
        raise ValueError('Expected exactly three diagnostic script bodies')
    result = b''.join(parts)
    after = copy.scripts(result)
    for id_, row in before.items():
        if (row['name'] != after[id_]['name'] or row['meta'] != after[id_]['meta'] or
                (row['name'] not in changed and row != after[id_])):
            raise ValueError('Untargeted script or metadata changed')
    return result


def prepare(project, out, probe_id, pages_sha, scripts_sha):
    project = Path(project)
    if not re.fullmatch(r'codex_diag_11_review_station_card_[a-z0-9_-]{8,80}', project.name):
        raise ValueError('Use the saved station-card project, not an earlier probe')
    checked = copy.audit(project)
    if (checked['pageCount'], checked['textObjects'], checked['buttons']) != (6, 169, 15):
        raise ValueError('Expected the current six-page R2 layout')
    return copy._prepare_copy(
        project, out, lambda raw: patch_scripts(raw, probe_id),
        r'codex_diag_11_panel_probe_[a-z0-9_-]{8,80}',
        dict(purpose='native-panel-dispatch-probe', probeID=probe_id,
             pagesUnchanged=True, callerNamesLogged=False,
             apiReturnDoesNotProveVisiblePanel=True,
             requiresBootBeforeInterpretingMissingEntry=True),
        pins={'Pages.spg': pages_sha, 'Scripts/Scripts.ssc': scripts_sha},
        expected_button_counts=(15,))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--probe-id', required=True)
    parser.add_argument('--expected-pages-sha', required=True)
    parser.add_argument('--expected-scripts-sha', required=True)
    args = parser.parse_args()
    prepare(args.project, args.out, args.probe_id, args.expected_pages_sha, args.expected_scripts_sha)
    print('PREPARED: private copy; only three diagnostic script bodies changed. Native dispatch and panel visibility unverified.')
