#!/usr/bin/env python3
"""Add a guarded read-only station-mode display to the working freshness card."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

from build_radio_display_01 import bootstrap

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/station-freshness-03/scripts/StationDiagnostics.txt'
OUT = ROOT / 'artifacts/station-mode-display-01'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def module():
    text = BASE.read_text()

    def once(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('Unexpected source context: ' + old[:60])
        text = text.replace(old, new)

    once('interface\nprocedure StationProcessUpdate;\n', 'interface\nprocedure StationProcessUpdate;\nfunction StationModeName(Code: Int64): string;\nfunction StationModeNote(Code: Int64): string;\n')
    once('function DriveFaultText(Code: Int64): string;', '''function StationModeName(Code: Int64): string;
begin
  Result := 'НЕИЗВЕСТЕН (код ' + IntToStr(Code) + ')';
  case Code of
    0: Result := 'СТОП';
    10, 11, 12: Result := 'АВТО';
    20, 21, 22: Result := 'РУЧНОЙ';
    90: Result := 'ОШИБКА СЕЛЕКТОРА';
  end;
end;
function StationModeNote(Code: Int64): string;
begin
  Result := 'Неизвестный код режима от ПЛК: ' + IntToStr(Code) + '.';
  case Code of
    0: Result := 'Выбран СТОП. Состояние ПЧ показано отдельно.';
    10: Result := 'Выбран автоматический режим; разрешение работы ещё не подтверждено.';
    11: Result := 'Подготовка автоматического режима.';
    12: Result := 'Автоматическое управление разрешено ПЛК.';
    20: Result := 'Выбран ручной режим; разрешение работы ещё не подтверждено.';
    21: Result := 'Ручное управление разрешено ПЛК.';
    22: Result := 'В ручном режиме выдана команда работы.';
    90: Result := 'ПЛК обнаружил недопустимое сочетание сигналов селектора.';
  end;
end;

function DriveFaultText(Code: Int64): string;''')
    once('  DriveState, CurrentRaw, FaultRaw, AliveCounter: Int64;',
         '  DriveState, CurrentRaw, FaultRaw, AliveCounter, ModeRaw: Int64;')
    once('  Status, Detail, RouteText, RouteReason: string;',
         '  Status, Detail, RouteText, RouteReason, ModeText, ModeNote: string;\n  ModeGood: Boolean;')
    once('  ProcessStatus.Text := Status;', '''  ModeRaw := 0;
  ModeGood := False;
  ModeText := 'НЕТ ДАННЫХ';
  ModeNote := 'Нет подтверждённых данных режима от ПЛК.';
  if DriveMap and RouteLive then
    ModeGood := ProcessWord('StationMode', ModeRaw);
  if ModeGood then
  begin
    ModeText := StationModeName(ModeRaw);
    ModeNote := StationModeNote(ModeRaw);
  end;
  ProcessTitle.Text := 'НАСОСНАЯ СТАНЦИЯ · СТЕНД | РЕЖИМ: ' + ModeText;
  ProcessStatus.Text := Status;''')
    once('  ProcessDetail.Text := Detail;', "  ProcessDetail.Text := 'Режим: ' + ModeText + '. ' + ModeNote + #13#10 + Detail;")
    once("  else ProcessMap.Text := 'Версия карты ПЛК: не подтверждена';", "  else ProcessMap.Text := 'Версия карты ПЛК: не подтверждена';\n  ProcessMap.Text := ProcessMap.Text + ' | Режим: ' + ModeText;")
    return text


def main():
    (OUT / 'scripts').mkdir(parents=True, exist_ok=True)
    code = module()
    (OUT / 'scripts/StationDiagnostics.txt').write_text(code)
    template = (ROOT / 'tools/drive_display_install_template.ps1').read_text()
    template = template.replace('codex_diag_04', 'codex_diag_06').replace('codex_diag_03', 'codex_diag_05')
    before = "    $processSource=(Get-Item -LiteralPath $processSource).FullName.TrimEnd([char[]]'\\/')"
    after = before + '''
    if(-not (Test-Path -LiteralPath (Join-Path $processSource 'Project.spr') -PathType Leaf)){
        $child=Join-Path $processSource 'codex_diag_05'
        if(Test-Path -LiteralPath (Join-Path $child 'Project.spr') -PathType Leaf){$processSource=$child}
        else{throw 'Choose the codex_diag_05 project folder containing Project.spr, Pages.spg and Scripts.'}
    }'''
    assert template.count(before) == 1
    template = template.replace(before, after)
    template = template.replace('Import3 new ReadOnly OPC tags', 'Import the new ReadOnly StationMode tag')
    template = template.replace('Current PLC may stay map31 for this check.', 'Existing map32 PLC already exports R2300; no PLC program change is needed.')
    template = template.replace('Read-only drive display', 'Read-only station mode display')
    packed = base64.b64encode(gzip.compress(code.encode(), mtime=0)).decode()
    installer = template.replace('__MODULE_GZIP__', packed).replace('__MODULE_SHA__', sha(code.encode()))
    installer = installer.replace('__OLD_CORE_SHA__', sha(BASE.read_text().strip().encode()))
    (OUT / 'Install-Station-Mode-01.ps1').write_text(installer)
    paste = bootstrap(installer).replace('$radio', '$mode')
    (OUT / 'Paste-Station-Mode-01.ps1').write_text(paste)
    report = dict(date='2026-10-30', sourceProject='codex_diag_05', targetProject='Desktop/codex_diag_06',
                  modeSource='Existing R2300, interpreted from native vendor-formatted source networks',
                  newOPCItem=dict(name='StationMode', address=2300, region='HOLDING_REGISTERS', deviceType='uint16',
                                  serverType='uint32', access='ReadOnly', scalingEnabled=False),
                  knownCodes={'0': 'STOP selector', '10/11/12': 'AUTO', '20/21/22': 'MANUAL', '90': 'invalid selector'},
                  readRequiresMap32=True, readRequiresConfirmedCounterProgress=True,
                  unknownCodePreserved=True, badMissingOrStaleNeverMeansStop=True,
                  changes=['StationDiagnostics module only in a new project copy'],
                  existingPagesPreserved=True, radioAndTimerRecordsPreserved=True,
                  PLCProgramChanged=False, writesOrControlCommandsAdded=False,
                  sourceCoreSHA256=sha(BASE.read_text().strip().encode()),
                  moduleSHA256=sha(code.encode()), installerSHA256=sha(installer.encode()), inlineCharacters=len(paste),
                  nativeF9Observed=False, nativeModeDisplayObserved=False)
    (OUT / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Built read-only mode copy06:', len(code.splitlines()), 'lines,', len(paste), 'inline characters')


if __name__ == '__main__':
    main()
