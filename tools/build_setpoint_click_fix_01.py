#!/usr/bin/env python3
"""Build SCADA09: capture caller context in OnClick, preserve native08 pages."""
import base64
import hashlib
import json
from pathlib import Path

from build_radio_display_01 import bootstrap

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/station-setpoint-control-01/scripts/StationDiagnostics.txt'
SOURCE = ROOT / 'source/scada-native-08'
OUT = ROOT / 'artifacts/station-setpoint-click-fix-01'
SOURCE_PAGES_SHA = '7ac3a4647f7a49b0d5c50d88dd024ab38e92ee427e59101dd929c3ebcc1e631b'
EVENTS = [
    ('ProcessSpMinus', 'StationSpAdjust(-10, GetClientName, GetUserName, GetUserID);'),
    ('ProcessSpPlus', 'StationSpAdjust(10, GetClientName, GetUserName, GetUserID);'),
    ('ProcessSpApply', 'StationSpApply(GetClientName, GetUserName, GetUserID);'),
    ('ProcessSpCancel', 'StationSpCancel(GetClientName, GetUserName, GetUserID);'),
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build_module():
    text = BASE.read_text().strip()
    changes = []

    def change(old, new, count=1):
        nonlocal text
        assert text.count(old) == count, (count, old[:100])
        changes.append(dict(old=old, new=new, count=count))
        text = text.replace(old, new)

    change('procedure StationSpAdjust(Delta: Integer);',
           'procedure StationSpAdjust(Delta: Integer; const Client, UserLabel: string; UserID: Int64);', 2)
    change('procedure StationSpApply;',
           'procedure StationSpApply(const Client, UserLabel: string; UserID: Int64);', 2)
    change('procedure StationSpCancel;',
           'procedure StationSpCancel(const Client, UserLabel: string; UserID: Int64);', 2)
    change('''function SpControlActor(var Client, UserLabel: string; var UserID: Int64): Boolean;
begin
  Client := GetClientName;
  UserID := GetUserID;
  UserLabel := GetUserName;
  Result := (Client <> '') and (UserID >= 0);
end;''', '''function SpControlActor(const Client: string; UserID: Int64; var Reason: string): Boolean;
begin
  Reason := '';
  if Client = '' then
    Reason := 'Не удалось определить клиент SCADA для этого нажатия.'
  else if UserID < 0 then
    Reason := 'Войдите в клиент SCADA для управления.';
  Result := Reason = '';
end;''')
    change('''  if Client <> '' then
    ShowMessageClient(Client, 'Уставка давления', MessageText);''', '''  SpControlText := MessageText;
  ProcessMainScope.Text := MessageText;
  ProcessMainScope.Color := RGB(165, 100, 0);
  if Client <> '' then
  begin
    try ShowMessageClient(Client, 'Уставка давления', MessageText);
    except end;
  end;''')
    change('''  Client, UserLabel, Reason: string;
  UserID, Working, Counter, Readback, Candidate: Int64;''', '''  Reason: string;
  Working, Counter, Readback, Candidate: Int64;''')
    change('''  Client, UserLabel, Reason: string;
  UserID, Working, Counter, Readback: Int64;''', '''  Reason: string;
  Working, Counter, Readback: Int64;''')
    change('var Client, UserLabel: string; UserID: Int64;', 'var Reason: string;')
    change('''  if not SpControlActor(Client, UserLabel, UserID) then
  begin SpControlNotice(Client, 'Войдите в клиент SCADA для управления.'); Exit; end;''', '''  if not SpControlActor(Client, UserID, Reason) then
  begin SpControlNotice(Client, Reason); Exit; end;''', 2)
    change('  if not SpControlActor(Client, UserLabel, UserID) then Exit;',
           '  if not SpControlActor(Client, UserID, Reason) then\n  begin SpControlNotice(Client, Reason); Exit; end;')
    assert not any(name in text for name in ['GetClientName', 'GetUserName', 'GetUserID'])
    assert text.count('Command.Value := Integer(SpControlTarget);') == 1
    return text, changes


def main():
    (OUT / 'scripts').mkdir(parents=True, exist_ok=True)
    assert sha((SOURCE / 'Pages.spg').read_bytes()) == SOURCE_PAGES_SHA
    module, changes = build_module()
    (OUT / 'scripts/StationDiagnostics.txt').write_text(module + '\n')
    old_events = {}
    new_events = {}
    for name, call in EVENTS:
        event = name + '_OnClick'
        old_events[event] = (ROOT / 'artifacts/station-setpoint-control-01/scripts' / (event + '.txt')).read_text().strip()
        new_events[event] = 'begin\n  ' + call + '\nend.'
        (OUT / 'scripts' / (event + '.txt')).write_text(new_events[event] + '\n')
    catalog = dict(changes=changes, oldEvents=old_events, newEvents=new_events)
    packed = base64.b64encode(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')).encode()).decode()
    code = (ROOT / 'tools/setpoint_click_fix_install_template.ps1').read_text()
    values = dict(CATALOG=packed, CATALOG_SHA=sha(base64.b64decode(packed)),
                  OLD_CORE_SHA=sha(BASE.read_text().strip().encode()),
                  NEW_CORE_SHA=sha(module.encode()), PAGES_SHA=SOURCE_PAGES_SHA)
    for key, value in values.items():
        code = code.replace('__' + key + '__', value)
    assert '__' not in code
    (OUT / 'Install-Setpoint-Click-Fix-01.ps1').write_text(code)
    paste = bootstrap(code).replace('$radio', '$click')
    (OUT / 'Paste-Setpoint-Click-Fix-01.ps1').write_text(paste)
    report = dict(date='2026-10-31', sourceProject='codex_diag_08', targetProject='codex_diag_09',
                  sourcePagesSHA256=SOURCE_PAGES_SHA, pagesPreservedByteForByte=True,
                  oldCoreSHA256=values['OLD_CORE_SHA'], newCoreSHA256=values['NEW_CORE_SHA'],
                  installerSHA256=sha(code.encode()), inlineCharacters=len(paste),
                  contextCapture='GetClientName/GetUserName/GetUserID evaluated in each native OnClick before entering the global module',
                  native09Observed=False, noAutomaticOrRepeatedWrites=True,
                  permissionsChanged=False, PLCOrHMIChanged=False)
    (OUT / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Built context fix:', len(paste), 'inline characters;', len(module.encode()), 'module bytes')


if __name__ == '__main__':
    main()
