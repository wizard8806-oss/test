# r15c: исправить каталог групп аварий и проверить полный HMI

Оператор уже проверил nativeOpen: CONTROL/A/C открываются, B даёт
«Illegal opening of configuration file!». Дополнительные изоляционные
файлы/старую r15a повторно проверять не нужно. D у оператора не найден;
это не препятствие данному ремонту.

Пользователь прислал образец, сохранённый в SKTool 7.1:
`C_native_alarm_sample.skm` (1298542 байта, SHA0ecac7…7c3f). В нём два
определения групп, два имени B00/B01 в отдельном каталоге и две пустые
сопутствующие записи по 4 байта. Исходная группа R2550, C и обе таблицы
Batch сохранены. В нашем r15a было 13 определений, но только одно имя B00
и одна сопутствующая запись. Сборщик теперь заполняет каталог всех групп.

## Быстрый ремонт существующего полного r15a

Получить `artifacts/station002-alarm-directory-r15c/delivery-manifest.json`
из того же коммита, что задание. Код закреплён на
`2399113fbc0e4af178d39efac404870d30967b97`.
По rawBase скачать 5 файлов из files[], проверить каждый размер/SHA и сохранить
структуру tools в отдельной подпапке `repair-r15c` прежнего локального
пакета. Python stdlib, без установок и без зависимости от GUI.

Источник — **полный** файл:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15\pump_station_3p_fault_reset_r15a.skm
```

Ожидаемый размер — 1480341 байт, SHA256:
`d08b5ec1358e84bdc640acdda30ed164038d57c6d3be39a1ad08d68e81176551`.
Если фактический путь отличается, найти уже созданную localr15a по этому
SHA; не подставлять частичный A/B/C или новый TEST-образец. Исходник сохранить.

Из папки `station002-fault-reset-local-15`:

```text
python -S -B repair-r15c/tools/validate_skm_alarm_catalog.py
python -S -B repair-r15c/tools/repair_alarm_directory_r15c.py --source pump_station_3p_fault_reset_r15a.skm --out pump_station_3p_fault_reset_r15c.skm --report r15c-build.json
python -S -B repair-r15c/tools/repair_alarm_directory_r15c.py --source pump_station_3p_fault_reset_r15a.skm --check pump_station_3p_fault_reset_r15c.skm --report r15c-check.json
```

Новый **pump_station_3p_fault_reset_r15c.skm**: **1480911 байт**, SHA256
`0141fa91f028144ad9fea5d256c464682860515d4d4c4eab0d80f658ae1ff930`.
Дать оператору полный путь этого единственного полного файла. Не останавливаться
на поиске окна SKTool: файловый ремонт/check GUI не требует.

Изменение относительно r15a: добавлено 570 байт имён и пустых сопутствующих
записей; смещены 24 указателя разделов и указатель их таблицы. Все 13
определений групп сохранены побайтно. C, Batch, BootAck, кнопки, раскладка,
HAD и ссылка на логотип сохранены. ПЛК не меняется. Диагностическая группа
TEST не включается. Новая проверка отклоняет известные r15a/B именно на
отсутствующем имени B01.

## Реальное открытие и сборка

Закрыть прежний Warning, File→Open **именно r15c**. Проверить загрузку
всего проекта и наличие 13 групп в Alarm Login; затем Screen1,9,13,15,16.
Screen9 должен сохранить рабочую таблицу, Screen15 — коды и три reset-кнопки,
Screen16 — bootlog; probe13 остаётся27124. Не объявлять одно наличие имени
в combobox успешным открытием. При ошибке сохранить точный путь/SHA/текст;
не заменять модель и не выдавать PythonPASS за nativePASS.

После успешного Open выполнить штатный Compile, проверить generatedaliases:
все8R-входов Batch16, затем W DriveResetRequest12bytes и BootAck scalarW
последний, размер префикса 216 байт. C в этом ремонте не менялся, но его nativeCompile
до этого не подтверждён. Новый образ/каталог сборки сверять по пути/дате/SHA,
не использовать старый prjCompiled. Затем OfflineSimulator с навигацией и
страницами. Без PLC нули/несовместимость профиля ожидаемы; это не проверка
физического сброса.

Скопированный originalAUTOMATIKA KG JPG уже есть в прежних assets. Не
повторять поиск Desktopоригинала. Проверить Screen14. Native HMI Start Setting
loading14/saver14 ещё pending: выполнить отдельным *_native.skm после
успешного открытия r15c, сохранить рабочуюScreen1/касание без команд насосам.
НативныйSaveAs изменитSHA, его сохранить отдельно от goldenr15c.

При недоступности GUI локальному дать оператору один полный путь r15c
для Open и конкретный оставшийся Compile/StartSetting шаг, без Tips/CtrlO
циклов. Шкаф отдан; никаких Download/Force/RUN/reset/второго Modbus master.

## Полная пересборка, если источник r15a отсутствует

В manifest есть 15 файлов fullRebuildFiles[] с исправленным сборщиком,
валидатором, C, каталогом и зависимостями. Скачать их из того же коммита.
Источник — уже найденный рабочий «бабанов байтик.skm», 1273673 байта/SHA359906…b4c,
не TEST-образец. В отдельной папке:

```text
python -S -B tools/build_fault_reset_hmi_r15.py --source "ПУТЬ_К_accepted.skm" --out pump_station_3p_fault_reset_r15c.skm --report full-build.json
python -S -B tools/validate_fault_reset_hmi_r15.py --source "ПУТЬ_К_accepted.skm" --candidate pump_station_3p_fault_reset_r15c.skm --report full-check.json
```

Результат обязан совпасть с quickrepair по размеру/SHA выше. Исходный
логотипный путь в пакете15 сохраняется; не переносить картинку в другую
папку без штатного relink. Исторический r15b-generator использовал старую
несогласованную схему: не генерировать его cases через новый producer.

Сохранить exactsource/candidate/native/imageSHA и настоящие Open/Compile/
Simulator результаты, обновить HANDOFF и опубликовать компактный отчёт в
handoff-ветку. Main/nativeSKM/PDW/JPG/vendor не публиковать. До nativeOpen/
Compile это подготовленный кандидат, после них аппаратная приёмка отдельно.
