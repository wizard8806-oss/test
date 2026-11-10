# r15d: семь групп аварий, затем открытие полной HMI

Оператор подтвердил: **r15c не открывается**, «Illegal opening of
configuration file!». Локальный отчёт afff23e подтверждает подготовку exact
r15c; прежнее отсутствие GUI у агента не отменяет результат оператора.
Повторять r15c, CONTROL/A/B/C и создание нативного образца не нужно.

В разделе Digital alarm login английской справки из кешированного комплекта
SKTool7.0 (2022) указано: «Number of digital alarm is up to 10 for SK series
HMI.» Наши 13 групп превышали документированную ёмкость. r15d объединяет
их в 7, сохраняя все сообщения и привязки битов. Точное исполнение
считывателя SKTool7.1 здесь не наблюдалось: успешное открытие ещё требуется.

## Создать полный файл до проверки GUI

Получить `artifacts/station002-alarm-group-limit-r15d/delivery-manifest.json`
из того же коммита, что это задание. В нём закреплён код
`b2b71cd07a60547dc2cf113470d3ce4331f599a4`. По rawBase скачать все 5 files[],
проверить размеры/SHA и положить с сохранением структуры tools в отдельную
папку `repair-r15d` существующего локального пакета15. Нужен только Python
со стандартной библиотекой, устанавливать зависимости не требуется.

Исходник — уже созданная полная r15c:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15\pump_station_3p_fault_reset_r15c.skm
```

1480911 байт, SHA256
`0141fa91f028144ad9fea5d256c464682860515d4d4c4eab0d80f658ae1ff930`.
Исходник сохраняется. При другом фактическом пути найти файл по этому SHA,
а не подставлять произвольную пересохранённую копию.

Из папки `station002-fault-reset-local-15` выполнить:

```text
python -S -B repair-r15d/tools/validate_skm_alarm_catalog.py
python -S -B repair-r15d/tools/repair_alarm_group_limit_r15d.py --source pump_station_3p_fault_reset_r15c.skm --out pump_station_3p_fault_reset_r15d.skm --report r15d-build.json
python -S -B repair-r15d/tools/repair_alarm_group_limit_r15d.py --source pump_station_3p_fault_reset_r15c.skm --check pump_station_3p_fault_reset_r15d.skm --report r15d-check.json
```

Ожидается **1480005 байт**, SHA256
`9a482900380d56f3bb86a625664ad09b10885fe6d9fd58b15262ef974c9bd8bb`.
Отдельный новый полный результат:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15\pump_station_3p_fault_reset_r15d.skm
```

Сверить источник до/после и итоговый SHA. При существующем выходе проверить
его; перезапись запрещена. Дать оператору полный путь. Недоступность окна
SKTool агенту не блокирует создание файла и выдачу пути.

## Что меняется

Сохраняется группа B00 «События станции». Для каждого ПЧ три диапазона
32+32+16 битов объединяются в один диапазон 80 битов; отдельная группа
неизвестного кода остаётся. Получается 1+3×2=7 групп и столько же записей
каталога. R3056..3060, R3061..3065, R3066..3070 и R3071..3073 не меняются.
Все 268 привязок битов, флаги, языки и сообщения побайтно/семантически
сверены. ПЛК, оба C, обе Batch-таблицы, BootAck, UI, пользовательская
раскладка, HAD, кодовые/reset-страницы и ссылка на логотип сохранены.

## Нативная проверка

1. Закрыть Warning и через File→Open открыть **полный r15d** по пути выше.
   Убедиться, что загрузилось дерево проекта, Alarm Login содержит 7 групп,
   и доступны Screen1,9,13,15,16. Screen9 сохраняет таблицу, Screen15 —
   коды и три кнопки сброса. Имя Screen16 в combobox само по себе не PASS.
2. При успешном открытии выполнить Compile. Проверить generated aliases:
   все 8 входов R — Batch16, затем W DriveResetRequest/12 байт и BootAck
   scalar W последним; префикс 216 байт. Сверить свежий образ по пути/дате/
   SHA; старый prjCompiled не является результатом новой сборки.
3. Выполнить Offline Simulator и навигацию. Нули без ПЛК не подтверждают
   аппаратный обмен или сброс. Если агенту GUI недоступен — дать оператору
   один полный путь и оставшийся конкретный шаг, без циклов Tips/CtrlO.
4. После успешного открытия отдельно завершить штатный HMI Start Setting:
   loading14/saver14 с уже скопированным оригиналом AUTOMATIKA KG в assets.
   Сохранить как отдельный *_native.skm и учесть новый SHA. Пока эти
   настройки не проверены, заставка не считается принятой.

При ошибке открытия зафиксировать точный путь/SHA и текст. Не объявлять
Python PASS успешным Open, не менять модель панели и не выдавать ещё одну
ревизию с предположением, что отказ устранён. Шкаф уже отдан: аппаратных
действий, Download/Force/RUN/reset в этом задании нет. Условия сброса ПЧ
в PLC остаются прежними.

## Если полной r15c нет

Manifest содержит 15 fullRebuildFiles[] с обновлённым сборщиком/валидатором.
Скачать их из того же закреплённого кода и использовать рабочий исходник
«бабанов байтик.skm», 1273673 байта/SHA
`359906cfd85975b9d2955f6b03b8f996761a7612fcbf37a23b95c8e5ee6c0b4c`.
Он уже был найден в предыдущем локальном задании.

```text
python -S -B tools/build_fault_reset_hmi_r15.py --source "ПУТЬ_К_accepted.skm" --out pump_station_3p_fault_reset_r15d.skm --report full-build.json
python -S -B tools/validate_fault_reset_hmi_r15.py --source "ПУТЬ_К_accepted.skm" --candidate pump_station_3p_fault_reset_r15d.skm --report full-check.json
```

Результат должен совпасть с быстрым ремонтом. Сохранить в прежнем пакете15,
чтобы ссылка на assets/automatikakg.jpg оставалась верной.

Опубликовать компактный отчёт и обновить HANDOFF в handoff-ветке: источник/
итоговый/native/image SHA и реальные Open/Compile/Simulator результаты.
Main, нативные файлы, оригинальный JPG и vendor не публиковать. До реального
Open/Compile r15d остаётся подготовленным кандидатом.
