#!/usr/bin/env python3
"""Build an additive map32 heartbeat consumer and reversible SCADA copy05."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

from build_radio_display_01 import bootstrap

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/station-drive-display-02/scripts/StationDiagnostics.txt'
OUT = ROOT / 'artifacts/station-freshness-03'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def module():
    text = BASE.read_text()
    def once(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('Unexpected drive-module context')
        text = text.replace(old, new)
    once('procedure StationProcessUpdate;\nimplementation',
         'procedure StationProcessUpdate;\nprocedure RouteFreshReset;\nprocedure RouteFreshStep(CounterGood: Boolean; CounterValue: Int64;\n  SecondsNow: Double; var State, AgeSeconds: Integer);\nimplementation')
    once('function ProcessWord(const Item:', '''  RouteStaleSeconds = 15;
  RouteClockGapSeconds = 10;
  RouteMaxForwardDelta = 60;
var
  RouteHasTick, RouteHasSample, RouteHasProgress: Boolean;
  RouteLastTick, RouteLastProgress: Double;
  RouteLastCounter: Int64;
''' + (OUT / 'route-core.txt').read_text() + '\nfunction ProcessWord(const Item:')
    once('  DriveState, CurrentRaw, FaultRaw: Int64;', '  DriveState, CurrentRaw, FaultRaw, AliveCounter: Int64;')
    once('    LoGood, HiGood, MapMatches, DriveMap, NativeGood, CurrentGood, FaultGood, FrequencyUsable, DriveUsable: Boolean;',
         '    LoGood, HiGood, MapMatches, DriveMap, NativeGood, CurrentGood, FaultGood, FrequencyUsable, DriveUsable, AliveGood, RouteLive: Boolean;')
    once('  Count, DriveCount, StatusColor: Integer;',
         '  Count, DriveCount, StatusColor, RouteState, RouteAge, RouteColor: Integer;')
    once('  Status, Detail: string;', '  Status, Detail, RouteText, RouteReason: string;')
    once('  NativeGood := False; CurrentGood := False; FaultGood := False;', '''  AliveGood := False;
  AliveCounter := 0;
  if DriveMap then AliveGood := ProcessWord('PlcAliveCounter', AliveCounter);
  RouteFreshStep(DriveMap and AliveGood, AliveCounter, Now * 86400.0, RouteState, RouteAge);
  RouteLive := RouteState = 1;
  NativeGood := False; CurrentGood := False; FaultGood := False;''')
    once('  ProcessStatus.Text := Status;', '''  if DriveMap then
  begin
    RouteText := 'Ожидание первого изменения общего счётчика ПЛК.';
    RouteReason := 'Дождитесь подтверждения обновления данных ПЛК.';
    RouteColor := RGB(165, 100, 0);
    if RouteState = 1 then
    begin
      RouteText := 'Обновление ПЛК подтверждено. Счётчик: ' + IntToStr(AliveCounter) +
        '. Без изменения: ' + IntToStr(RouteAge) + ' с.';
      RouteColor := RGB(40, 140, 90);
    end
    else if RouteState = 2 then
    begin
      RouteText := 'Нет доступного общего счётчика ПЛК или его качества OPC.';
      RouteReason := 'Проверить общий счётчик, MasterOPC и соединение со станцией.';
    end
    else if RouteState = 3 then
    begin
      RouteText := 'Неверный диапазон общего счётчика ПЛК.';
      RouteReason := 'Проверить адрес и тип общего счётчика в профиле станции.';
    end
    else if RouteState = 4 then
    begin
      RouteText := 'Нет изменения общего счётчика ПЛК более 15 с.';
      RouteReason := 'Обновление показаний не подтверждено. Проверить опрос, Gateway, сеть и RUN ПЛК.';
      RouteColor := RGB(165, 50, 50);
    end
    else if RouteState = 6 then
    begin
      RouteText := 'Контроль обновления возобновляется после паузы или изменения часов.';
      RouteReason := 'Ожидается новое изменение общего счётчика ПЛК.';
    end
    else if RouteState = 7 then
    begin
      RouteText := 'Общий счётчик ПЛК изменился скачком. Ожидается следующее изменение.';
      RouteReason := 'Подтверждение обновления выполняется заново.';
    end;
    ProcessFreshness.Text := RouteText;
    ProcessFreshness.Color := RouteColor;
    if not RouteLive then
    begin
      ProcessPressure.Text := 'Нет достоверных данных';
      ProcessPressureNote.Text := RouteReason;
      ProcessSetpoint.Text := 'Нет данных';
      ProcessFrequency.Text := 'Нет данных';
      ProcessFrequencyNote.Text := RouteReason;
      ProcessCurrent.Text := 'Нет данных';
      ProcessCurrentNote.Text := RouteReason;
      ProcessFault.Text := 'Нет данных';
      ProcessFaultNote.Text := RouteReason;
      ProcessFault.Color := RGB(105, 105, 105);
      ProcessValidity.Text := 'Достоверность давления не подтверждена';
      ProcessValidity.Color := RGB(105, 105, 105);
      ProcessAlarmWords.Text := 'Слова состояния ПЛК: нет подтверждённых данных';
      Status := 'Нет подтверждения обновления показаний ПЛК';
      Detail := RouteReason;
      StatusColor := RouteColor;
    end;
  end;
  ProcessStatus.Text := Status;''')
    return text


def main():
    (OUT / 'scripts').mkdir(parents=True, exist_ok=True)
    code = module()
    (OUT / 'scripts/StationDiagnostics.txt').write_text(code)
    template = (ROOT / 'tools/drive_display_install_template.ps1').read_text()
    template = template.replace('codex_diag_04', 'codex_diag_05').replace('codex_diag_03', 'codex_diag_04')
    template = template.replace('Import3 new ReadOnly OPC tags', 'Import the new ReadOnly PlcAliveCounter tag')
    template = template.replace('Current PLC may stay map31 for this check.', 'General heartbeat is required on map32; no PLC operation is triggered.')
    template = template.replace('Read-only drive display', 'Read-only station freshness display')
    packed = base64.b64encode(gzip.compress(code.encode(), mtime=0)).decode()
    installer = template.replace('__MODULE_GZIP__', packed).replace('__MODULE_SHA__', sha(code.encode()))
    installer = installer.replace('__OLD_CORE_SHA__', sha(BASE.read_text().strip().encode()))
    (OUT / 'Install-Station-Freshness-03.ps1').write_text(installer)
    paste = bootstrap(installer).replace('$radio', '$fresh')
    (OUT / 'Paste-Station-Freshness-03.ps1').write_text(paste)
    manifest = dict(date='2026-10-30', sourceProject='codex_diag_04', targetProject='Desktop/codex_diag_05',
                    map32Additive=True, noNewMapVersionRequired=True,
                    newOPCItem=dict(name='PlcAliveCounter', address=2840, region='HOLDING_REGISTERS',
                                    deviceType='uint16', serverType='uint32', access='ReadOnly', scalingEnabled=False),
                    heartbeatPeriodSeconds=1, staleSeconds=15, clockGapSeconds=10,
                    maxAcceptedForwardDelta=60, unsignedWrap=65536,
                    firstChangeRequired=True, staleProcessPayloadsHidden=True,
                    radioRecordPreserved=True, radioCollectorChanged=False, pagesPreserved=True,
                    generalHeartbeatRequiresNewPLCRung=True, commandsAdded=False,
                    installerSHA256=sha(installer.encode()), moduleSHA256=sha(code.encode()),
                    sourceCoreSHA256=sha(BASE.read_text().strip().encode()), inlineCharacters=len(paste),
                    nativeF9Observed=False, nativeCounterProgressObserved=False,
                    nativeStopRecoveryTestObserved=False,
                    limits=['Bench1Hz/15s timing; future station profiles need measured periods',
                            'A changing heartbeat confirms PLC program/data-path progress, not every sensor/drive condition',
                            'No coherent multi-item snapshot or command acknowledgements added'])
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('Built general freshness copy:', len(code.splitlines()), 'lines,', len(paste), 'paste characters; no live changes')


if __name__ == '__main__':
    main()
