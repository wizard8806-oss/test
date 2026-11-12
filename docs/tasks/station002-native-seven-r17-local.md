# r17: продолжить сохранение и проверку открытого проекта

**12.11: AlarmSound [ID:0] успешно скомпилирован.** На снимке Script Editor
полного candidate-файла: HMI и local по 0 ошибок и 0 предупреждений,
Compile success. Эту проверку скрипта не повторять без новой причины.
Сборка всего проекта, Offline Simulator, native SaveAs и логотип ещё не
подтверждены. Штатно сохранить и закрыть Script Editor; продолжить шаги
ниже в уже открытом проекте, без повторной генерации или Open.

**Полный Open PASS подтверждён снимком оператора:** заголовок полного r17,
загруженное дерево16экранов/Screen1. Теперь выполнять только PASS-шаги
ниже из УЖЕ ОТКРЫТОГО проекта: отдельный nativeSaveAs/settings/Compile/
Simulator. Сначала прочитать фактические путь/размер/SHA Windows-файла;
новый локальный hash-report ещё не получен. При отличии сохранить более
новую копию и описать её, не перезаписывать. Build/Open не повторять,
fallback/ExportB01/native7 заново не нужны. Остальные исходы ещё pending.

Получен и переоткрыт пользователем native7-эталон. Теперь основой служит
**C_native_7groups.skm**, без реконструкции definitions/catalog2→7.
Сохраняются его7групп, все headers/names/IDs/flags/protocol/addresses/keys,
catalog и opaque-settings0..21, включая обновлённую native-секцию16.
Из прежнего r15f копируются только6message-vectors. Full также применяет
подготовленные nav/counter/logo-правки; messages-only — диагностический fallback.
Полный native Open и компиляция AlarmSound подтверждены снимками.
SaveAs/settings/общая Compile/Simulator ещё не подтверждены.
Старые пробы/native7 повторно не создавать.

## Справка о выполненной подготовке — повторно не выполнять

Взять `artifacts/station002-native-seven-r17/delivery-manifest.json` из
того же коммита, что это задание. Код закреплён на
`82a155976ff4a587dfecadc52c2d3d0e275ccd3a`. Скачать все семь files[] по
rawBase, сверить bytes/SHA, сохранить tools в `native-seven-r17`
существующей worktree15. Только Python stdlib. Группы/закрытыеsettings
не нормализовать и не перенумеровывать; всё уже создано самим редактором.

Рабочая папка:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15
```

Точные входы, оба сохранить:

- **C_native_7groups.skm**,1463855байт/SHA
  `1c48a69e9c63e1f2787d78fb286d04ea3ae04a7b75f304504d75609c28367b8b`.
  Уже сохранён/переоткрыт и прикреплён пользователем. Не подменять source2
  C_native_code_pages506 или более ранним7groups другогоSHA. Проверить путь
  самому в worktree15/15b, не просить пользователя вспоминать его.
- **pump_station_3p_fault_reset_r15f.skm**,1480015байт/SHA
  `2fe47083c0fbbb2fc9d31342c1ab76d3b220c81afa0f60c61d1ea4eed2c9676e`.
  Это только донор готовых текстов; никакой другой его metadata не копируется.

```text
python -S -B native-seven-r17/tools/build_native_seven_r17.py --source C_native_7groups.skm --donor pump_station_3p_fault_reset_r15f.skm --out pump_station_3p_native7_r17_candidate.skm --report r17-build.json
python -S -B native-seven-r17/tools/build_native_seven_r17.py --source C_native_7groups.skm --donor pump_station_3p_fault_reset_r15f.skm --check pump_station_3p_native7_r17_candidate.skm --report r17-check.json
python -S -B native-seven-r17/tools/build_native_seven_r17.py --source C_native_7groups.skm --donor pump_station_3p_fault_reset_r15f.skm --messages-only --out OPEN_NATIVE7_MESSAGES_ONLY.skm --report r17-messages-build.json
python -S -B native-seven-r17/tools/build_native_seven_r17.py --source C_native_7groups.skm --donor pump_station_3p_fault_reset_r15f.skm --messages-only --check OPEN_NATIVE7_MESSAGES_ONLY.skm --report r17-messages-check.json
```

| Выход | Байты | SHA256 |
| --- | ---: | --- |
| pump_station_3p_native7_r17_candidate.skm | 1479937 | 757d792f75a95ed31971dd2819942e88d703f738c9524ba309320699644c88b3 |
| OPEN_NATIVE7_MESSAGES_ONLY.skm | 1479965 | 4bdab6282d838b4a16527ad31a994b7897aacec4ddc8c8ac57c0fabda9c6b4d5 |

Выходы/отчёты новые; если точный файл уже существует, достаточно --check
в новый отчёт. Оригиналы/старыефайлы/оригинальныйJPEG не перезаписывать.
Проверить наличие и выдать оператору сначала **один полный реальный путь**:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15\pump_station_3p_native7_r17_candidate.skm
```

Если рабочая папка отличается, дать настоящий путь. Fallback используется
лишь при отказе полного Open. Internal имена Digital Alarm Login1..6
сохранены нативными; тексты операторского журнала содержат номерПЧ/код/описание.

## Продолжение после успешного Open полного r17

Оператор уже открыл полный кандидат: заголовок файла, дерево16экранов
и Screen1 видны на снимке. Повторный File→Open не нужен. В текущем окне
проверить доступ Screen9/15/16 и семь Alarm Login-групп.

**При PASS:**

1. Штатный SaveAs **pump_station_3p_native7_r17_native.skm** отдельно.
2. Проверить Main «Диагностика»→13, «КодыПЧ»→15, history16 иfooter-ссылки.
   В full согласованы4числовыхполя кнопок, counter→R3077.
3. Проверить Screen14 с оригинальным JPEG
   `C:\Users\user\Documents\HMI\Samkoon\Automatika визитка print.jpg`.
   Сохранить пропорции, не перерисовывать картинку. Если оригинал недоступен,
   записать реальный путь существующей копии/что не проверено.
4. В native-копии штатно HMI parameters→HMI Start Setting: рабочаяScreen1,
   If Load Screen→Screen14 (около3с, если поддерживается), Screensaver→
   Screen14/60с; проверить возврат. Сохранить остальные настройки/модель/
   адреса/макрос. Это ранее запрошенная пользователем загрузка/заставка.
5. Save→Compile **всего проекта** SKTool7.1→Offline Simulator. Успешный
   Compile AlarmSound в Script Editor уже подтверждён 12.11 и не заменяет
   эту общую сборку. Отдельно записать ошибки/
   предупреждения, логотип/навигацию/Screen9/15/16. Новые MacroInit/alias
   должны сохранить allReads Batch16, requestW12 и BootAck scalarWlast;
   старый _prjcompiled не выдавать за свежую сборку. Offline0/нетверсии PLC
   не являются физической приёмкой. PLC/hardware не подключать ради этого.
6. Дать реальный путь native-файла/размер/SHA для приватного прикрепления.
   NativeSave пересериализует проект, егоSHA записывается отдельно от generated.

**Архивный сценарий отказа; после подтверждённого Open не выполнять:** один File→Open
**OPEN_NATIVE7_MESSAGES_ONLY.skm** в той же папке.

- PASS: отдельный nativeSaveAs **C_native7_filled_messages.skm**, путь для
  приватного прикрепления. В нём только заполненные нативные сообщения,
  весь UI/nav/logo каквисходном native7. Это отделяет UI-правки.
- FAIL обоих: сохранить точные имя/SHA/ошибку. Новые guessedr18 и ещёодин
  native7 не создавать. Для следующего шага из рабочего source7 штатно
  экспортировать B01 (R3056/80) через его EXCEL/Export в предлагаемый
  редактором формат. Не переименовывать расширение. Выдать путь/размер/SHA
  этого шаблона для приватного прикрепления — тексты можно будет заполнить
  для штатного импорта, а не вводить240сообщений вручную. Source7 сохранить.

Если GUI агенту не виден, закончить build/check и дать оператору точный
путь полного r17; не застревать на Tips/скрытых процессах. Исходы NativeOpen/
Save/Compile не подменять host-проверками. Core/runtimeC не менялся,
целевые merge-проверки прошли; общие57повторять вместо этого не нужно.

PLC/reset-guard/main не менять. Шкаф отдан: Download/Force/RUN/hardware
здесь не выполнять. NativeSKM/PDW/JPG/vendor/закрытые данные в Git не
публиковать. В handoff-отчёте раздельно подготовка, nativeOpen/SaveAs,
StartSetting/logo, Compile/Simulator, fallback/export-if-needed и пути.
