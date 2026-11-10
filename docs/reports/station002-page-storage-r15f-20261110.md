# Нативный16-page образец выявил ещё два пропущенных страничных массива

Дата проверки10.11.2026, cloud Linux `/workspace/test`, handoff-ветка.
Код `ce767cf5300e794aac561ef59b20210729f82e2a`; Windows SKTool7.1
облако не запускало. Native-файлы/сырые данные остаются приватными.

Получен C_native_16pages.skm1299291/SHA
`671ce4309579da4e2d5109c6910b35a08f2baaf7b702dbaca800f373e910c738`.
Пользователь прямо подтвердил его повторный Open без ошибки и прислал
загруженное дерево16экранов. Принимается **operator-reported native Open PASS**.
Само предоставление файла не выдаётся за Compile/Simulator/hardware.

Модель SK-070HE/800×480,16commonpairs,16scene-map entries; Screen15/16 пустые.
Обе C-копии и оба expanded Batch-списка совпадают с ранее полученными
nativeC/R80. Две alarm-группы — исходнаяR2550/25 и R3056/80; файл основан
на нативном R80-образце, а не на полном generated r15e. Он не production-база.

## Установленное расхождение

Прямое сравнение native14 R80 SHA4574726a…17a и native16 показало:

| Область | Native14 | Native16 | Generated full r15e |
| --- | ---: | ---: | ---: |
| Root/common/scene-map count | 14 | 16 | 16 |
| Trailing section1 | 14байт | 16байт | **14байт** |
| Trailing section21 | 48+14×4=104байта | 48+16×4=112байт | **104байта** |

Native16 section1 побайтно равна native14 плюс2нуля; section21 — native14
плюс8нулей. Их точное назначение в UI не утверждается. Наблюдённая схема —
однобайтовые и четырёхбайтовые записи на экран; prefix48 сохранён.
Все прочие opaque spans, кроме штатно обновляемой metadata16 и абсолютного
индекса, у native14/16 одинаковы. Generated A/AC/fullr15e получили16сцен,
но эти две таблицы не расширяли. Это конкретный дефект согласованности;
его исключительность как причины OpenFAIL ещё не доказана.

## Исправление

`skm_page_storage.py` проверяет обе длины для reviewed SK-070HE. Полный
producer теперь добавляет обе записи при14→16, validator требует16/16/16.
`repair_page_storage_r15f.py` принимает только exactfullr15e1480005/SHA219832…171d,
делает две вставки2+8байт, пересчитывает24absoluteentries и locator.
Полная инверсия восстанавливает исходные байты. Отдельное сравнение всех
payload-секций подтвердило сохранность, включая C2 и prefix21; первичная
UI/алармы/C1/Batch до locator сохранены целиком.

Quickrepair == независимая полная пересборка из accepted3599:

```text
pump_station_3p_fault_reset_r15f.skm
1480015 bytes
SHA256 2fe47083c0fbbb2fc9d31342c1ab76d3b220c81afa0f60c61d1ea4eed2c9676e
```

Сохраняются16страниц с34/43объектами на новых15/16, оригинальный HAD,
пользовательская раскладка,7групп/ID0..6/268битов и тексты, коды/сброс,
оба C/Batch, BootAck scalarW last/aligned, путь лого. PLC и STOP-допуск
сброса не менялись. Настройка loading/saver и физический reset не проверены.

## Проверки

- 12синтетических регрессий: согласованные14/16, оба/один stale-массив,
  лишние записи, две вставки/все payload/указатели, idempotence, отказ
  shrink/рассогласованных таблиц/header. Без нативных/vendor-байтов в тестах.
- Реальные accepted/C/nativeLB/nativeR80/native16 PASS новой схемы;
  knownbadA/AC/fullr15e отклонены. Обратимость и совпадение всех payload,
  сохранность источника, stdlibCLI build/check/nooverwrite/tamper/symlink PASS.
- Полный HMI-validator PASS: геометрия/навигация/HAD/Batch,64C89cases,
  576тиков и21protocol/integration сценарий. Это host-проверки, не nativeABI.
- Изолированный run_checks **57групп PASS**, исходный код неизменен.
  Использованы существующие кэшированные FPC/PowerShell через CODEX_FPC/PWSH.
- HTTP5 pinned helpers/SHA/размеры PASS, два свежих Python -S -B запуска
  build/check из скачанных файлов дали точный итоговый SHA.

Manifest `artifacts/station002-page-storage-r15f/delivery-manifest.json`;
актуальное задание `docs/tasks/station002-page-storage-r15f-local.md`.
NativeOpen/SaveAs/Compile/Simulator **полного r15f ещё pending**. Нужен один
полный файл в прежней worktree15, не повтор старых A/контролей/native16.
Private output/reference/reports: `/workspace/shared/station002-page-storage-r15f-20261110/`.
В main изменений нет; hardware/Download/Force/RUN не выполнялись.
