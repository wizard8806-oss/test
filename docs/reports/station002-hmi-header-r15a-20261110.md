# HMI r15 OpenFAIL/0x0: исправление заголовка r15a, 10.11.2026

> **Обновление: пользователь подтвердил OpenFAIL новой r15a.**
> Этот ремонт заголовка не закрыл открытие. Следующий шаг: [изоляция r15b](../tasks/station002-hmi-open-isolation-r15b-local.md), а не повторная выдача r15a.


Пользователь сообщил, что последняя версия не открывается, и показал
SKTool Missing Model Replacement/Size7.0/Resolution0x0. Затем подтвердил
конкретный путь `station002-fault-reset-local-15/pump_station_3p_fault_reset_r15.skm`.
Локальный6e5fa03 подтвердил изготовление exactpinned пары и копирование
JPEG; нативных проверок в том отчёте ещё не было. Эта последующая реальная
попытка оператора — **OpenFAIL**, она не отменяется прежними staticPASS.

## Установленная ошибка

Ошибка в нашем builder. После двух QString version/model поток хранит
число страниц и по паре32-bit integer sceneCommonData для каждой страницы.
За ними начинается первый QSamDrawScene/QRectF. В r15 число14 заменено16,
но14служебных пар не расширены. Native reader потребляет16байт начала
Scene1 как ещё две пары, и читает его геометрию со смещением.

На exact accepted source: count14@56, пары60..171, QRectF@172 равен
0,0,800,480. На rejectedr15: count16, тот же прежний блок14пар и QRectF@172;
последовательный reader ждёт QRectF@188. Первый modelQString SK-070HE
сохранён, но это не делает поток корректным. Подмена модели не нужна.

Схема подтверждена также чтением символизированного runtime: readStreamData
читает sceneCommonData по два int за итерацию, а QSamDrawScene reader
начинает с прямоугольника. Это разбор сериализации, не запуск редактора.
Предыдущая проверка QString anchors/directory/full-inverse не проверяла
этот инвариант и пропустила дефект. За ошибку отвечает облачный генератор.

## Исправление

`tools/repair_fault_reset_hmi_r15a.py` принимает только точный отклонённый
r15, добавляет две default пары(0,-1) поoffset172 и релокирует24directory
entries/locator на16байт. Создаёт новый файл, source не перезаписывает.
Исправлен также `build_fault_reset_hmi_r15.py`, чтобы полноценная
пересборка из user3599 сразу включала16пар. Оба пути дают **одинаковый SKM**.

| Файл | Байты | SHA256 |
|---|---:|---|
| Rejected r15 |1480325|f410a9c1e0fb9198c092f18b9b54b62207ff6d1d44d821f64564906fc6913a31|
| Fixed r15a |1480341|d08b5ec1358e84bdc640acdda30ed164038d57c6d3be39a1ad08d68e81176551|

Модель SK-070HE,16пар, геометрия0,0,800,480. Все другие bytes, кроме25
релокированных указателей, сохранены. Полная обратная операция возвращает
exactrejectedsource. C/Batch16/BootAck/HAD/раскладка/кнопки/лого-reference
не меняются. PLC не менялся. Вопрос «почему reset только STOP» обсуждался,
но изменение условий пользователь не поручал; этот ремонт их сохраняет.

## Проверки

Новый `skm_project_header.py` читает префикс последовательно, а не ищет
произвольные имена экранов. Actual rejectedr15 теперь отклоняется. Добавлено
12публичных регрессий: правильные1/14/16страниц, недостаток/избыток пар,
нулевая/NaN/дробная геометрия, усечение/неверныйcount и точный16-byte repair.
Проверка внесена в основной run_checks.

На неизменяемом worktree f90d30e выполнен `tools/run_checks.py`:
**55build/check groups PASS**, включая новую регрессию; исходное дерево
не изменилось. Это облачная проверка, нативные Windows/PLC проверки отдельно.

Реальная пара source/fixed: quickrepair==fullrebuild, directory/header,
полнаяинверсия, неизменныйC, tamper/nooverwrite/source-preservation PASS.
Полный HMIvalidator: HAD/геометрия/Batch,64C89differential/576ticks и21новый
protocol/C+PLC случай PASS. Они не подтверждают nativeOpen/Compile.

4закреплённых quickrepairфайла скачаны поHTTP с bytes/SHA. В новой папке
Python-S-B без sitepackages выполняет regression/build/check и получает
goldenr15a. Также14fullRebuildFiles[] независимо скачаны с bytes/SHA;
stdlibbuild/check из accepted3599 повторяет тот же goldenr15a.
Пакет не содержит nativeSKM/PDW/vendor/JPG. Private артефакты:
`/workspace/shared/station002-header-r15a-20261110/`.

## Доставка и оставшаяся приёмка

Код закреплён на `f90d30e426f03b0acdb09d0162ecc4a7d4a8234c`.
Действующее короткое задание: `docs/tasks/station002-hmi-header-r15a-local.md`;
manifest `artifacts/station002-fault-reset-r15a/delivery-manifest.json`.
Для ремонта только4files[], для полной пересборки14fullRebuildFiles[].
Прежняя r15-доставка помечена withdrawn, старое задание содержит предупреждение.

На ПК: Cancel в MissingModel, новыйr15a рядом с прежнимSKM, File→Open,
Screen1/9/13/15/16, затем Compile/OfflineSimulator. JPG уже найден/скопирован;
native loading/saver остаются отдельной настройкой General и не являются
причиной дефекта заголовка. Открытие/Compile новойr15a здесь **ещё не
наблюдались**. WindowsGUI недоступен облаку, шкаф отдан, аппаратных действий0.
Без этого результата не объявлять nativeприёмку пройденной.
