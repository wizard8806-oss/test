# Полный r16 на сохранённой пользователем рабочей native-основе

Получен C_native_code_pages.skm1461830/SHA506dec71f62efadca3cc6660707306d2076c4122a83f24b1568c908a95c29b4a.
Его исходный контроль с34/43новыми виджетами пользователь открыл без ошибки,
затем выполнил SaveAs. Старые пробы/nativeSave этого же файла не повторять.
Теперь из этой основы подготовлены полный r16 и fallback только с журналом.
Весь C/Batch/раскладка/sceneheaders/16pagearrays сохранены. Из fullr15f
берутся только7alarm-definitions/catalog; старый полный файл как основу
не использовать. Full дополнительно исправляет nav/counter/путьJPEG.

## Создать/проверить файлы

Взять `artifacts/station002-native-merge-r16/delivery-manifest.json` из
того же коммита, что это задание. Код закреплён на
`f76914ef5401420815e6e1d3cdee801625d4afba`. Скачать шесть files[] по rawBase,
сверить bytes/SHA и положить с сохранением tools в `native-merge-r16`
существующей worktree15. Только Python stdlib; GUI для подготовки не нужен.

Рабочая папка:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15
```

Входы, оба сохранить:

- **C_native_code_pages.skm**1461830/SHA
  `506dec71f62efadca3cc6660707306d2076c4122a83f24b1568c908a95c29b4a`.
  Ожидается рядом с OPEN_NATIVE16_CODE_PAGES после последнего SaveAs.
  Локальный сам проверяет фактический путь/хеш в worktree15/15b, не просит
  пользователя вспоминать путь. Не подменять старым C_native_16pages671.
- **pump_station_3p_fault_reset_r15f.skm**1480015/SHA
  `2fe47083c0fbbb2fc9d31342c1ab76d3b220c81afa0f60c61d1ea4eed2c9676e`.
  Уже создан и сверён local54992be; сейчас это только донор alarm-блоков.

```text
python -S -B native-merge-r16/tools/build_native_merge_r16.py --source C_native_code_pages.skm --donor pump_station_3p_fault_reset_r15f.skm --out pump_station_3p_native_merge_r16_candidate.skm --report r16-build.json
python -S -B native-merge-r16/tools/build_native_merge_r16.py --source C_native_code_pages.skm --donor pump_station_3p_fault_reset_r15f.skm --check pump_station_3p_native_merge_r16_candidate.skm --report r16-check.json
python -S -B native-merge-r16/tools/build_native_merge_r16.py --source C_native_code_pages.skm --donor pump_station_3p_fault_reset_r15f.skm --alarms-only --out OPEN_R16_ALARMS_ONLY.skm --report r16-alarms-build.json
python -S -B native-merge-r16/tools/build_native_merge_r16.py --source C_native_code_pages.skm --donor pump_station_3p_fault_reset_r15f.skm --alarms-only --check OPEN_R16_ALARMS_ONLY.skm --report r16-alarms-check.json
```

| Выход | Байты | SHA256 |
| --- | ---: | --- |
| pump_station_3p_native_merge_r16_candidate.skm | 1479661 | 84797b73846e5266894812e4bcd7bd7aa8a977baa962934b8eea479aa58420e6 |
| OPEN_R16_ALARMS_ONLY.skm | 1479689 | 9e45309a2595462a705e2654f4c82a98b85425fef9c57c6559b8ec7a07ba886b |

Существующие источники/выходы/отчёты не перезаписывать. Если точный выход уже
есть, достаточно --check в новый отчёт. Сначала выдать оператору **один
проверенный полный путь к полному кандидату**:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15\pump_station_3p_native_merge_r16_candidate.skm
```

Если фактическая папка другая — дать реальный путь. Fallback подготовлен
на случай отказа; при успешном полном Open его открывать не требуется.

## Штатный Open полного кандидата

File→Open именно полный r16. Нужны загруженное дерево16экранов и доступ
Screen1/9/15/16 без Illegal opening. Имя Screen16 после Warning не успех.

**При полном Open PASS:**

1. Штатный SaveAs отдельный **pump_station_3p_native_merge_r16_native.skm**.
   Источник506 и generated-кандидат сохранить. Дальнейшие GUI-правки в native.
2. Проверить7групп Alarm Login и Screen9/HAD, Code/Reset Screen15, History16.
   Main «Диагностика»→13, «КодыПЧ»→15, footer-переходы новых экранов
   проверяются по назначению. У full согласованы все4числовых поля кнопок;
   это исправляет остатки старого target12 в cloned-footer.
3. Проверить оригинальный JPEG по **указанному пользователем** пути
   `C:\Users\user\Documents\HMI\Samkoon\Automatika визитка print.jpg`.
   Full background-reference уже указывает туда. Изображение не перерисовывать;
   сохранить пропорции при показе Screen14. Если оригинал недоступен, найти
   существующую копию/записать реальный путь, не объявлять логотип проверенным.
4. Штатно HMI parameters→HMI Start Setting: рабочая Screen1; If Load Screen→
   Screen14 (около3с, если выдержка поддерживается); Screensaver→Screen14/60с.
   Сохранить прочие параметры/макрос/адреса/модель. Проверить штатный возврат
   с заставки. Это ранее запрошенные пользователем загрузка и заставка.
   Если GUI/поля недоступны — явно записать, что native-конфигурация не выполнена.
5. Save, Compile SKTool7.1, Offline Simulator. Раздельно записать ошибки/
   предупреждения, отображение логотипа, переходы и открытие Screen9/15/16.
   Свежие generated MacroInit/alias должны сохранить allReads Batch16,
   requestW12 и BootAck scalarW last; не брать старый _prjcompiled за новую
   успешную сборку. Offline нули/нетверсии PLC не являются физической приёмкой.
6. Дать реальный полный путь native-файла и его размер/SHA для приватного
   прикрепления в облачный чат. Его SHA после Save может отличаться от generated.

**Только при полном Open FAIL:** открыть один подготовленный
**OPEN_R16_ALARMS_ONLY.skm** из той же папки. В нём только журнал, весь
UI/навигация/картинка точные как в source506.

- Fallback PASS: отдельный SaveAs **C_native_full_alarms.skm** и путь для
  приватного прикрепления. Это отделяет nav/logo-правки полного кандидата.
- Fallback FAIL: точные имя/SHA/текст обоих отказов; журнал добавляет сбой
  на этой основе. Не объявлять очередной padding-патч готовым ремонтом.

Не выпускать guessed r17, не повторять старые C/A/r15f/native16 вместо этих
исходов. Если GUI агенту не виден, всё равно закончить build/check и выдать
реальный полный путь к одному полному файлу; оператор выполняет Open.
Не застревать на Tips/скрытых процессах и не заменять нативный исход
повтором57coreпроверок: runtimeC не менялся, целевые проверки merge прошли.

PLC/reset-guard/main не менять. Шкаф отдан: Download/Force/RUN/оборудование
здесь не выполнять. NativeSKM/PDW/JPG/vendor/сырые закрытые данные в Git
не публиковать. В handoff-отчёте раздельно filePrepared/nativeOpen/SaveAs,
StartSetting/logo, Compile, Simulator, fallback-if-used и пути результатов.
