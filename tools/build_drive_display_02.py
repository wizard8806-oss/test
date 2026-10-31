#!/usr/bin/env python3
"""Prepare a map31/32 read-only SCADA copy; no live files or PLC writes."""
import gzip
import hashlib
import json
from pathlib import Path

from build_radio_display_01 import bootstrap

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/station-drive-display-02'
BASE = ROOT / 'artifacts/station-process-display-01/scripts/StationDiagnostics.txt'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def module():
    source = BASE.read_text()
    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError('Unexpected process source context')
        source = source.replace(old, new)
    replace('  ProcessMapVersion = 31;', '  ProcessBaseMapVersion = 31;\n  ProcessDriveMapVersion = 32;')
    replace('procedure StationProcessUpdate;\nvar', '''function DriveFaultText(Code: Int64): string;
begin
  Result := 'Ненулевой код ПЧ; расшифровка для этой версии неизвестна.';
  case Code of
    0: Result := 'ПЧ передал нулевой код неисправности.';
    1: Result := '900G: сработала защита ПЧ (Err01).';
    2: Result := '900G: перегрузка по току при разгоне (Err02).';
    3: Result := '900G: перегрузка по току при торможении (Err03).';
    4: Result := '900G: перегрузка по току при постоянной скорости (Err04).';
    5: Result := '900G: перенапряжение при разгоне (Err05).';
    6: Result := '900G: перенапряжение при торможении (Err06).';
    7: Result := '900G: перенапряжение при постоянной скорости (Err07).';
    8: Result := '900G: неисправность источника питания (Err08).';
    9: Result := '900G: пониженное напряжение (Err09).';
    10: Result := '900G: перегрузка преобразователя (Err10).';
    11: Result := '900G: перегрузка двигателя (Err11).';
    12: Result := '900G: потеря входной фазы (Err12).';
    13: Result := '900G: потеря выходной фазы (Err13).';
    14: Result := '900G: перегрев модуля (Err14).';
    15: Result := '900G: внешняя ошибка (Err15).';
    16: Result := '900G: ошибка связи, переданная самим ПЧ (Err16).';
    17: Result := '900G: ошибка контактора (Err17).';
    18: Result := '900G: ошибка измерения тока (Err18).';
    19: Result := '900G: ошибка автонастройки двигателя (Err19).';
    20: Result := '900G: обрыв датчика давления (Err20).';
    21: Result := '900G: ошибка EEPROM (Err21).';
    22: Result := '900G: аппаратная ошибка преобразователя (Err22).';
    23: Result := '900G: замыкание на землю (Err23).';
    26: Result := '900G: достигнуто суммарное время работы (Err26).';
    29: Result := '900G: достигнуто суммарное время включения (Err29).';
    30: Result := '900G: обрыв нагрузки (Err30).';
    40: Result := '900G: ограничение тока (Err40).';
    41: Result := '900G: переключение двигателя во время работы (Err41).';
    42: Result := '900G: чрезмерное отклонение скорости (Err42).';
    45: Result := '900G: сигнализация перегрева Pt100 (Err45).';
    52: Result := '900G: нехватка воды (Err52/A52).';
    53: Result := '900G: избыточное давление (Err53).';
    55: Result := '900G: ошибка, связанная с нехваткой воды (Err55; см. Err52).';
    56: Result := '900G: неисправность DI платы управления (Err56).';
  end;
end;
procedure StationProcessUpdate;
var''')
    replace('  Map, PV, SourceOK, SP, Freq, FreqState, AlarmLo, AlarmHi: Int64;',
            '  Map, PV, SourceOK, SP, Freq, FreqState, AlarmLo, AlarmHi: Int64;\n  DriveState, CurrentRaw, FaultRaw: Int64;')
    replace('    LoGood, HiGood, MapMatches: Boolean;',
            '    LoGood, HiGood, MapMatches, DriveMap, NativeGood, CurrentGood, FaultGood, FrequencyUsable, DriveUsable: Boolean;')
    replace('  Count, StatusColor: Integer;', '  Count, DriveCount, StatusColor: Integer;')
    replace('  MapMatches := MapGood and (Map = ProcessMapVersion);',
            '  MapMatches := MapGood and ((Map = ProcessBaseMapVersion) or (Map = ProcessDriveMapVersion));\n  DriveMap := MapGood and (Map = ProcessDriveMapVersion);\n  NativeGood := False; CurrentGood := False; FaultGood := False;\n  FrequencyUsable := False; DriveUsable := False; DriveCount := 0;')
    replace("    HiGood := ProcessWord('AlarmHi', AlarmHi);", """    HiGood := ProcessWord('AlarmHi', AlarmHi);
    if DriveMap then
    begin
      NativeGood := ProcessWord('Vfd1NativeState', DriveState);
      CurrentGood := ProcessWord('Vfd1CurrentRaw', CurrentRaw);
      FaultGood := ProcessWord('Vfd1FaultCode', FaultRaw);
      if NativeGood then DriveCount := DriveCount + 1;
      if CurrentGood then DriveCount := DriveCount + 1;
      if FaultGood then DriveCount := DriveCount + 1;
    end;""")
    replace("  ProcessFaultNote.Text := 'Собственный код ошибки ПЧ ещё не подключён.';", """  ProcessFaultNote.Text := 'Собственный код ошибки ПЧ ещё не подключён.';
  ProcessFault.Color := RGB(105, 105, 105);
  if DriveMap then
  begin
    ProcessCurrent.Text := 'Нет данных';
    ProcessFault.Text := 'Нет данных';
    ProcessCurrentNote.Text := 'Нет подтверждённых данных тока ПЧ.';
    ProcessFaultNote.Text := 'Нет подтверждённого кода неисправности ПЧ.';
  end;""")
    replace("    Detail := 'Ожидается карта 31. Показания этой карточки скрыты.';",
            "    Detail := 'Ожидается карта 31 или 32. Показания этой карточки скрыты.';")
    replace("    Detail := 'Карта ПЛК 31. Проверить импорт и качество недоступных тегов.';",
            "    Detail := 'Карта ПЛК ' + IntToStr(Map) + '. Проверить импорт и качество недоступных тегов.';")
    replace('      if ((FreqState = 1) and (Freq = 0)) or\n         ((FreqState = 2) and (Freq > 0) and (Freq <= 5999)) then',
            '      FrequencyUsable := ((FreqState = 1) and (Freq = 0)) or\n         ((FreqState = 2) and (Freq > 0) and (Freq <= 5999));\n      if FrequencyUsable then')
    replace('    if LoGood and HiGood then', """    if DriveMap then
    begin
      DriveUsable := FrequencyUsable and NativeGood and
        ((DriveState = 1) or (DriveState = 2) or (DriveState = 3));
      if not FrequencyUsable then
      begin
        ProcessCurrentNote.Text := 'ПЛК не подтверждает допустимое состояние частоты. Ток скрыт.';
        ProcessFaultNote.Text := 'ПЛК не подтверждает допустимое состояние частоты. Код ПЧ скрыт.';
      end
      else if NativeGood and (not DriveUsable) then
      begin
        ProcessCurrentNote.Text := 'Неизвестное слово состояния 900G: ' + IntToStr(DriveState);
        ProcessFaultNote.Text := 'Неизвестное слово состояния 900G: ' + IntToStr(DriveState);
      end;
      if DriveUsable then
      begin
        if DriveState = 1 then ProcessFrequencyNote.Text := '900G: слово состояния 1 (вперёд).'
        else if DriveState = 2 then ProcessFrequencyNote.Text := '900G: слово состояния 2 (назад).'
        else ProcessFrequencyNote.Text := '900G: слово состояния 3 (стоп).';
        if CurrentGood then
        begin
          ProcessCurrent.Text := FormatFloat('0.0', CurrentRaw / 10.0) + ' А';
          ProcessCurrentNote.Text := 'Выходной ток U0-06. Масштаб 0,1 А по руководству 900G.';
        end;
        if FaultGood then
        begin
          ProcessFault.Text := 'Код ' + IntToStr(FaultRaw);
          ProcessFaultNote.Text := DriveFaultText(FaultRaw);
          if FaultRaw <> 0 then
          begin
            ProcessFault.Color := RGB(165, 50, 50);
            Status := 'ПЧ 900G: код неисправности ' + IntToStr(FaultRaw);
            Detail := DriveFaultText(FaultRaw);
            StatusColor := RGB(165, 50, 50);
          end;
        end;
      end;
    end;
    if LoGood and HiGood then""")
    replace("  if MapMatches then ProcessMap.Text := 'Версия карты ПЛК: 31'", """  if DriveMap then
  begin
    ProcessOPC.Text := 'MasterOPC: базовые теги ' + IntToStr(Count) + ' из 7; теги ПЧ ' + IntToStr(DriveCount) + ' из 3';
    if (Count <> 7) or (DriveCount <> 3) then ProcessOPC.Color := RGB(165, 100, 0);
  end;
  if MapMatches then ProcessMap.Text := 'Версия карты ПЛК: ' + IntToStr(Map)""")
    return source


def main():
    (OUT / 'scripts').mkdir(parents=True, exist_ok=True)
    code = module()
    (OUT / 'scripts/StationDiagnostics.txt').write_text(code)
    template = (ROOT / 'tools/drive_display_install_template.ps1').read_text()
    import base64
    packed = gzip.compress(code.encode(), mtime=0)
    installer = template.replace('__MODULE_GZIP__', base64.b64encode(packed).decode())
    installer = installer.replace('__MODULE_SHA__', sha(code.encode()))
    installer = installer.replace('__OLD_CORE_SHA__', sha(BASE.read_text().strip().encode()))
    (OUT / 'Install-Drive-Display-02.ps1').write_text(installer)
    paste = bootstrap(installer).replace('$radio', '$drive')
    (OUT / 'Paste-Drive-Display-02.ps1').write_text(paste)
    tags = [dict(name=name, pdu_address=address, region='HOLDING_REGISTERS',
                 device_type='uint16', server_type='uint32', access='ReadOnly',
                 scalingEnabled=False, mapVersionRequired=32)
            for name, address in [('Vfd1NativeState', 2800), ('Vfd1FaultCode', 2801), ('Vfd1CurrentRaw', 2806)]]
    (OUT / 'masteropc-new-tags.json').write_text(json.dumps(tags, ensure_ascii=False, indent=2) + '\n')
    manifest = dict(date='2026-10-30', sourceProject='codex_diag_03', targetProject='Desktop/codex_diag_04',
                    supportedMapVersions=[31,32], newFieldsRequireMap=32, nativeScadaVersion='2.6.15.0',
                    currentFactor=0.1, faultDisplay='Raw native code; model900G text from manual',
                    oldSourcePreserved=True, pagesPreserved=True, radioRecordBytePreserved=True,
                    PLCWrites=False, newCurrentOrFaultPLCReadObserved=False, nativeF9Observed=False,
                    baseCoreSHA256=sha(BASE.read_text().strip().encode()), moduleSHA256=sha(code.encode()),
                    installerSHA256=sha(installer.encode()), inlineCharacters=len(paste),
                    limitations=['General end-to-end freshness remains explicitly unconfirmed',
                                 'Frequency state gates new fields conservatively; invalid frequency also hides fault/current',
                                 'No shared snapshot identity across separate OPC items',
                                 'Current factor/nonzero values and native fault encoding require bench comparison',
                                 'No PLC/drive command writes or physical operation are claimed'])
    observation = OUT / 'native-observation-2026-10-30.json'
    if observation.exists():
        native = json.loads(observation.read_text())
        manifest.update(nativeObservation=observation.name,
                        newFieldsInNativeScadaObserved=native['newProcessScriptExecutionObserved'],
                        map32BranchExecutionInferred=native['inferenceFromValidatedScript']['map32BranchExecuted'],
                        nativeZeroCurrentAndFaultDisplayObserved=True,
                        nativeF9Observed=None,
                        nativeEvidenceScope='New script execution and zero current/fault/native-state3 display observed; exact F9/PLC-download commands and wire freshness not separately observed')
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('Built read-only drive display:', len(code.splitlines()), 'lines,', len(paste), 'paste characters')


if __name__ == '__main__':
    main()
