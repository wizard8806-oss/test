# r15e: исправить шесть номеров групп, открыть полный HMI и Compile

Нативный R80-эталон уже получен. Повторять его создание, TEST, старые
CONTROL/A/B/C, три новые диагностические пробы или Open r15c/r15d не нужно.

Найдено рассогласование: семь определений r15d имели номер0, тогда как
каталог называл их B00..B06. В обоих нативных образцах SKTool7.1 номера
исходной/второй групп равны0/1. Наш сборщик ошибочно копировал этот байт
исходной группы. r15e назначает номера0..6; это **ровно шесть байтов**,
длина, указатели и все прочие данные остаются прежними. Успешный Open
полной r15e ещё требуется; статический PASS не заменяет его.

## Создание файла без зависимости от GUI

Взять `artifacts/station002-alarm-group-ids-r15e/delivery-manifest.json`
из того же коммита, что это задание. Код закреплён на
`aaf01a3ebb29d6188b7eb9cc5db8fb2bcdea2d03`. По rawBase скачать 5 files[],
проверить размеры/SHA и сохранить структуру tools в подпапку `repair-r15e`
существующего пакета15. Python stdlib, без установки зависимостей.

Источник — полный файл, уже созданный по отчёту af1c121:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15\pump_station_3p_fault_reset_r15d.skm
```

1480005 байт, SHA256
`9a482900380d56f3bb86a625664ad09b10885fe6d9fd58b15262ef974c9bd8bb`.
Если путь другой — найти полный файл по этому SHA. Не подставлять native
SaveAs или частичную диагностическую копию, исходник сохранить.

Из папки `station002-fault-reset-local-15`:

```text
python -S -B repair-r15e/tools/validate_skm_alarm_catalog.py
python -S -B repair-r15e/tools/repair_alarm_group_ids_r15e.py --source pump_station_3p_fault_reset_r15d.skm --out pump_station_3p_fault_reset_r15e.skm --report r15e-build.json
python -S -B repair-r15e/tools/repair_alarm_group_ids_r15e.py --source pump_station_3p_fault_reset_r15d.skm --check pump_station_3p_fault_reset_r15e.skm --report r15e-check.json
```

Ожидается **1480005 байт**, SHA256
`2198325315f9b9a6918f483f07f164f855ef454fb3454d7363fe73b6e3fb171d`.
Размер тот же, что у источника: обязательно сверить SHA и ровно шесть
изменений из report. Источник до/после должен совпасть. Существующий
выход не перезаписывать, проверить его либо создать отдельную новую копию.

Дать оператору полный путь:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15\pump_station_3p_fault_reset_r15e.skm
```

Невидимость окна SKTool агенту не блокирует этот файловый этап. В обеих
облачных сборках quickrepair и rebuild получился один SHA, указанный выше.

## Открытие и нативная сборка

Закрыть прежний Warning и через File→Open открыть **полный r15e**.
Проверить загрузку дерева проекта, семь групп B00..B06 в Alarm Login,
доступность Screen1,9,13,15,16. Одно имя Screen16 в combobox не является
успешным Open. При отказе зафиксировать точный путь/SHA/текст; новые
предположения не объявлять готовым ремонтом.

После успешного Open выполнить штатный Compile. Проверить generated aliases:
все 8 R-входов Batch16, затем W DriveResetRequest/12 байт и BootAck scalarW
последним; префикс216 байт. C в этом ремонте не меняется, но его native
Compile ещё не подтверждён. Новый образ/папку сборки сверить по пути/дате/SHA;
старый prjCompiled не выдавать за результат. Затем Offline Simulator и
навигация; нули без PLC не подтверждают реальную связь или сброс ПЧ.

Если GUI доступен — выполнить Open/Compile на ПК, при необходимости в
отдельном штатном экземпляре SKTool7.1 для этого файла, сохраняя другие
открытые проекты. Если агентскому сеансу GUI недоступен — дать оператору
один полный путь и конкретный шаг, без циклов Tips/CtrlO и без ложного PASS.

После успешного открытия отдельным *_native.skm завершить HMI Start Setting:
loading14/saver14 с уже скопированным оригиналом AUTOMATIKA KG в assets.
Проверить Screen14 и учесть новый SHA после нативного SaveAs. Прежняя
ссылка на картинку сохраняется, её наличие не означает работающую заставку.

## Сохранность и резервная сборка

Все остальные байты r15d сохранены: UI, пользовательская раскладка, HAD,
кнопки, оба C, обе Batch-таблицы, коды/тексты, поля сканирования/типа,
все указатели и ссылка на логотип. Все 268 привязок битов/сообщений
сохранены независимо от исправляемого номера группы. ПЛК, адреса и
условия сброса этим контейнерным ремонтом не меняются.

Если full r15d отсутствует, manifest содержит 15 fullRebuildFiles[] с
исправленным producer/validator. Скачать из того же закреплённого кода.
Источник — рабочий «бабанов байтик.skm»1273673 байта/SHA
`359906cfd85975b9d2955f6b03b8f996761a7612fcbf37a23b95c8e5ee6c0b4c`:

```text
python -S -B tools/build_fault_reset_hmi_r15.py --source "ПУТЬ_К_accepted.skm" --out pump_station_3p_fault_reset_r15e.skm --report full-build.json
python -S -B tools/validate_fault_reset_hmi_r15.py --source "ПУТЬ_К_accepted.skm" --candidate pump_station_3p_fault_reset_r15e.skm --report full-check.json
```

Итог должен совпасть с quickrepair. Сохранить в прежнем пакете15, чтобы
путь assets/automatikakg.jpg оставался верным. Нативный R80-образец не
использовать как новую базу рабочего экрана.

Обновить HANDOFF и компактный отчёт в handoff-ветке: source/candidate/native/
image SHA, реальные Open/Compile/Simulator исходы и оставшиеся ограничения.
Шкаф отдан: аппаратных действий/Download/Force/RUN/reset здесь нет.
Main, native SKM/PDW/JPG/vendor не публиковать. До native Open/Compile r15e
остаётся подготовленным кандидатом.
