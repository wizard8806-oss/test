# Срочно: восстановить открытие HMI r15 → r15a

> **Обновление: пользователь подтвердил OpenFAIL новой r15a.**
> Этот ремонт заголовка не закрыл открытие. Следующий шаг: [изоляция r15b](../tasks/station002-hmi-open-isolation-r15b-local.md), а не повторная выдача r15a.


Пользователь открыл `pump_station_3p_fault_reset_r15.skm` в папке
`station002-fault-reset-local-15` и получил **Missing Model Replacement,
Resolution0x0**. Точный файл совпадает с прежней pinned-доставкой: локальный
6e5fa03 ранее подтвердил golden-сборку. Это реальный native OpenFAIL;
прежний staticPASS не является нативной приёмкой.

Причина в облачном builder: число страниц14→16 изменено, а таблица
sceneCommonData в начале осталась на14пар. Native-reader читает по два
32-bit integer на каждую страницу, поэтому потребляет ещё16байт первого
QRectF. Это наша ошибка генерации, модель **SK-070HE/800x480 сохраняется**.
Не выбирать Replace и не подбирать другую панель. В текущем диалоге Cancel.

## Быстрый точечный ремонт

Получить `artifacts/station002-fault-reset-r15a/delivery-manifest.json` из
того же коммита, что это задание. Код закреплён на
`f90d30e426f03b0acdb09d0162ecc4a7d4a8234c`.
По `rawBase` скачать только **4files[]**, сверить bytes/SHA. Сохранить
структуру `tools` в отдельной подпапке `repair-r15a` текущего локального
пакета. Не перезаписывать старый файл/локальные helpers/native-правки.
Python уже использовался в r15; новые установки не нужны.

Источник:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15\pump_station_3p_fault_reset_r15.skm
```

Его expected1480325байт/SHA256:
`f410a9c1e0fb9198c092f18b9b54b62207ff6d1d44d821f64564906fc6913a31`.
Исходник сохранить. Новый файл разместить **рядом**, в прежней папке15:
так сохраняется действующая ссылка на уже скопированный JPG в assets.

Из папки `station002-fault-reset-local-15`:

```text
python -S -B repair-r15a/tools/validate_skm_project_header.py
python -S -B repair-r15a/tools/repair_fault_reset_hmi_r15a.py --source pump_station_3p_fault_reset_r15.skm --out pump_station_3p_fault_reset_r15a.skm --report r15a-build.json
python -S -B repair-r15a/tools/repair_fault_reset_hmi_r15a.py --source pump_station_3p_fault_reset_r15.skm --check pump_station_3p_fault_reset_r15a.skm --report r15a-check.json
```

Expected **1480341байт**, SHA256:
`d08b5ec1358e84bdc640acdda30ed164038d57c6d3be39a1ad08d68e81176551`.
Helper создаёт только новый файл и принимает только точный rejectedr15.
Если есть другое native-save, сохранить его отдельно; guard не отключать.

Изменение строго16байт: две пары(0,-1) после14служебных записей поoffset172.
Затем24directorypointers иlocator смещены на16. Полная обратная операция
даёт exactстарыйSKM. C/VariableSettings/HAD/раскладка/кнопки/лого/reference
не меняются. ПЛК, reset-условия и аппаратура вообще не затрагиваются.

## Нативное открытие и доступные проверки

После Cancel открыть через File→Open именно
`pump_station_3p_fault_reset_r15a.skm`. Проверить модель SK-070HE/800x480,
затем Screen1,9,13,15,16. На9 прежний HAD, на15 коды/три reset-кнопки,
на16 история запусков. Нужен фактический успешный Open, не только повтор
наших bytes/SHA. После открытия — штатные Compile и Offline Simulator.

JPG уже найден/скопирован и SHA-проверен в локальном6e5fa03: не повторять
поиск старого Desktop-оригинала. Проверить существующую картинку Screen14.
Пока General Start Setting не настроен: отдельным Save As включить loading14
и screensaver14/60с, сохранить рабочую Screen1/касание без команд насосам.
Эти настройки не являются условием первичной проверки открытия.
Native-save оставить отдельным *_native.skm, его SHA будет другим.

Если снова появится MissingModel/0x0 либо ошибка чтения, Cancel, проверить
фактический открываемый путь/SHA и сохранить конкретное сообщение; не
нажимать Replace и не пересоздавать проект. Сообщить, на каком шаге и с
каким exactфайлом произошёл отказ. Не объявлять причиной версию Windows,
шрифты/логотип без новых доказательств.

Если GUI недоступен агенту, всё равно выполнить точечный ремонт/check и
дать оператору полный путь нового файла для File→Open. Не застревать в
Tips-циклах, массовом закрытии процессов или переустановке SKTool.
Пользователь уже показал реально доступное окно — не считать прежнюю
невидимость GUI доказательством отсутствия программы.

## Что уже проверено в облаке

Quickrepair совпал с исправленной пересборкой из exact acceptedHMI3599.
Последовательное чтение заголовка подтверждает16пар и QRectF0,0,800,480;
старыйr15 этот тест не проходит. 12новых synthetic регрессий плюс проверки
реального rejected/fixed, полной инверсии, исходника/nooverwrite, C/HAD/
Batch/геометрии,64hostdifferential/576ticks и21protocol случая PASS.
Это не native Open/Compile. Автор старого builder признал пропуск этого
инварианта; прежняя проверка ссылок/директории его не ловила.

Для полной пересборки, если понадобится, вmanifest есть отдельные
14 `fullRebuildFiles[]`, включая исправленный builder/header parser.
Источник остаётся accepted3599, а результат должен совпасть с r15a.
Для текущего rejected-файла достаточно быстрого ремонта выше.

Записать реальный результат Open/Compile/Simulator в локальный отчёт,
обновить HANDOFF и опубликовать компактную сводку в handoff-ветку, main не
менять. NativeSKM/PDW/JPG/vendor не публиковать. Никаких загрузок/Force/RUN/
reset или второго Modbus master: шкаф отдан. Обсуждение сброса только
выбранного остановленного ПЧ не является поручением менять PLC в этом
ремонте. Остальные доработки r15 сохранены.
