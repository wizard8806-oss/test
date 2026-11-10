# Два контроля оставшихся изменений после подтверждённого отказа full

Оператор подтвердил: **CONTROL_FULL_ORIGINAL_ALARMS.skm тоже не открывается**.
Exact файл 1461495 байт/SHA790f…700e уже создан (локальный e73b88c).
Его повторный Open, старые CONTROL/A/B/C/D и ещё один R80-образец не нужны.
Новые группы не единственная причина. Новую production r15f не собирать.

## Подготовить обе копии

Взять `artifacts/station002-remaining-open-controls/delivery-manifest.json`
из того же коммита, что это задание. Все пять files[] скачать по rawBase
с сохранением tools в `repair-remaining-open` прежней worktree15; проверить
размеры/SHA. Код закреплён на
`5c1a8fef1bca1fd1c1edb0a100ad75681a6c2b3c`. Только Python stdlib.

В папке `C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15`
выполнить:

```text
python -S -B repair-remaining-open/tools/prepare_remaining_open_controls.py --source CONTROL_FULL_ORIGINAL_ALARMS.skm --out-dir remaining-open-checks
```

Источник должен иметь SHA
`790f095467a359f1896938ab424bb4adb5365af2992ef68046e72d8a53d4700e`.
Никакие исходники/сохранённые оператором проекты не перезаписывать.
Папка выхода новая; если уже существует — проверить её файлы по manifest,
при совпадении повторную генерацию не делать. Проверить результаты:

| Файл | Байты | SHA256 |
| --- | ---: | --- |
| OPEN_OLD_LOGO.skm | 1461381 | c6ef59b8593f169db00a7f7b66f05f9578310a2c7ea2dcc7f993dbe335839e9b |
| OPEN_PAGES_AND_MACRO_ONLY.skm | 1461431 | 119155c0b1f4ed1e8cbcb69162722955d7773e61df7a254bf1fe0895f28fd00f |

В обоих 16 страниц/одна исходная группа аварий. Первый отменяет только
перепривязку лого; второй дополнительно возвращает три старых виджета,
оставляя точное объединение ранее открывшихся A+C. Отсутствие картинки по
старому пути допустимо для этого теста открытия; настройки заставки не менять.
Структура/инверсия/независимая композиция проверены в cloud. Реальное
Open этих двух новых файлов ещё не проверено.

Убедиться, что оба файла созданы, и выдать **полные реальные Windows-пути**:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15\remaining-open-checks\OPEN_OLD_LOGO.skm
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15\remaining-open-checks\OPEN_PAGES_AND_MACRO_ONLY.skm
```

Если фактическая папка отличается, дать настоящий путь. Недоступный GUI
не блокирует создание/проверку копий и выдачу путей оператору.

## Открывать строго по порядку

1. Через File→Open открыть **OPEN_OLD_LOGO.skm**. Нужны загрузка дерева и
   доступ к страницам; оставшееся имя Screen16 не означает успешный Open.
   При успехе сохранить отдельный **C_native_old_logo.skm** в той же папке,
   дать путь для приватного прикрепления. Второй тест пока не нужен.
2. Только если первый дал ошибку, открыть **OPEN_PAGES_AND_MACRO_ONLY.skm**.
   При успехе отдельный SaveAs **C_native_pages_macro.skm**, выдать путь.
3. Если оба отказали, записать оба фактических исхода/имени/SHA/текст ошибки.
   Это уже сужает сбой до совместного изменения страниц и макроса; не
   объявлять новый путь лого единственной причиной и не делать r15f наугад.

Если GUI доступен — выполнить локально в SKTool7.1, сохраняя другие открытые
проекты. Если недоступен — передать оператору сначала только первый Open
с точным путём. Не заменять его очередным run_checks или поиском Tips.
При PASS приватный native SaveAs нужен для следующего сравнения; raw SKM,
PDW/JPG/vendor в Git не публиковать. Это диагностические копии, не прошивки.

Обновить HANDOFF и компактный отчёт в handoff-ветке с раздельными полями
filePrepared/nativeOpen/nativeSaveAs. ПЛК/runtime/reset-guard/main не менять.
Compile/Simulator/Download/аппаратные действия этим заданием не нужны.
