# Калибратор и один знак давления в SCADA

02.11.2026 МСК. Пользователь включил калибратор и сообщил **2,9бар**, попросил
один знак после запятой. Свежая сверка PV/SourceOK/качества/счётчика ещё нужна.
База локального результата `5e3cbaec17ec2c78e248be5fea1b3483dbe6e934`,
[отчёт Windows](../reports/station11-file-probe-resume-20261102.md).

Работает10, исходная11 неизменна. RAM-модель уже сохранена отдельно в
UNVERIFIED-unsaved_20261102T1432Z; повторный Save As не нужен без новых
несохранённых изменений. Editor на сохранённой/скомпилированной probe
`codex_diag_11_probe_202611021729144fdc71`, ID
`UINAV11-202611021729144FDC71`. BOOT/ENTER/переход не испытаны.

**Локальный review отклонил Stop активной10**, сочтя его остановкой рабочего
Server/конфликтом сохранения10. Не повторять отклонённое действие другим
интерфейсом. До уточнённого разрешения на временное программное переключение
выполнять чтение/подготовку/компиляцию копии, оставляя10 активной. Apply,
пуск/останов насосов, режим и сброс для этой задачи не нужны.

1. Получить ветку, сохранив местные изменения/старые station09 JSONL; прочитать
   HANDOFF. Через уже работающий MasterOPC получить несколько согласованных
   наблюдений PressurePV_x100, PressureSourceOK, MapVersion, PlcAliveCounter,
   StationMode, R2100/R2360 с качеством и полным временем. Проверить прогресс
   счётчика/свежесть; GOOD с обрезанным временем недостаточно. Нового
   Modbus-клиента не подключать. Записать raw PV и PV/100, сравнить с2,9 **до
   округления**. Ориентир290 не подставлять; недостоверность не обходить.
   Ранее SP=410 GOOD — это уставка, не измерение; автоматически не возвращать4,00.
2. Создать чистую display-копию из исходной **дисковой11**, не из probe/
   UNVERIFIED. Helper проверяет pinned SHA Pages/Scripts/версию2.6.15/44 связки;
   несовпадение не обходить сменой pins. Из корня репозитория:

```powershell
$displayPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
$displaySource = Join-Path $env:USERPROFILE 'Documents\Simple-Scada 2\Projects\codex_diag_11'
$displayParent = Join-Path $env:LOCALAPPDATA 'CodexCandidates\SCADA11'
$null = New-Item -ItemType Directory -Path $displayParent -Force
$displayToken = (Get-Date -Format 'yyyyMMddHHmmss') + ([Guid]::NewGuid().ToString('N').Substring(0,6))
$displayTarget = Join-Path $displayParent ('codex_diag_11_display_' + $displayToken)
& $displayPython -I -B .\tools\prepare_native_ui_event_probe.py --mode pressure-display --project $displaySource --out $displayTarget
if ($LASTEXITCODE -ne 0) { throw 'Display copy failed; source preserved' }
```

В новой приватной копии user/SYSTEM меняются только10 масок FormatFloat в
StationDiagnostics/OperatorConsole.46 других записей, все ID/metadata,
Pages/Windows/Project/Variables/Trends/Servers/ArcSystem и архив сохраняются;
старый cache исключён. BOOT/ENTER не добавляются. Давление/уставка/обратная
связь/операторские сообщения показывают один знак, разделитель региональный.
Raw x100, шаг10raw=0,1бар, команды/сравнения, журнал команд/архив/экспорт
сохраняют точность. CodexProbeManifest.json остаётся приватным.

3. Повторить **найденный в последнем отчёте** способ открытия: скопировать
   AppData-копию в новый одноимённый каталог Projects с DACL user/SYSTEM,
   сверить файлы, открыть штатным списком Editor. Не пытаться снова искать
   AppData в списке, который не позволяет туда перейти. Проверить состояние
   Editor перед открытием; не терять новую несохранённую модель.
   Compile All/Save — только новой копии. Сверить имена/ID/тела и ресурсы/
   архив. Metadata31 скрипта прежней probe изменились: классифицировать
   позиции0–1(type),2–5(UID),6–8(flags),9–16(tail), не считать все дельты
   безвредными. Прогнать читающий audit. Если Save As пропустил ArcSystem,
   восстановить его из подготовленной копии только в новом каталоге.
4. Runtime после явного уточнённого разрешения: отсутствие pending →
   штатное переключение **выбранного программного проекта**, с возвратом10.
   Процессы Server/MasterOPC и оборудование не останавливать. Для probe —
   уникальный BOOT и один клик; для display-копии — реальные давление/уставка
   с одним знаком, обзор/окно и +/−/Отмена без Apply. Не смешивать две копии
   и не принимать компиляцию за загрузку. RAW-шкалы трендов остаются отдельной
   незакрытой задачей; PressurePV не подключать к архиву без исторической маски.

Codex сам сохраняет отчёт/HANDOFF: raw/качество калибратора, native-хеши/
метаданные, что подготовлено/скомпилировано/загружено, BOOT/ENTER, активный
путь и непройденное. Публиковать только согласованные исходники/документы.
Сохранять10/ПЛК/HMI/радио02/ServiceDiag9336/7000/БД/профили/старые JSONL.
