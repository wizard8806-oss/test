# SCADA11: сводка и таблица обзора в отдельной копии

База16d7284 уже объединена в handoff-ветку. Верхние вкладки работают;
Save As/tab-clearance не повторять. Два парных кадра обзора/станции получены.
Сначала новый обзор, затем компоненты карточки. Полная UI-приёмка открыта.

1. Проверить branch/HEAD/status/index/untracked и прочитать AGENTS/HANDOFF.
   Сохранить местные изменения; не reset/clean/stash. Fetch с явной веткой:
   `git fetch origin refs/heads/codex/project-handoff-2026-10-31:refs/remotes/origin/codex/project-handoff-2026-10-31`.
   Чистый worktree16d обновить `git merge --ff-only origin/codex/project-handoff-2026-10-31`.
   При изменениях/расхождении создать новый worktree от fetched ref. Основную
   грязную папку ноутбука на5e3cbae не переключать/не перезаписывать.
2. Сохранённый источник:
   `C:\Users\user\Documents\Simple-Scada 2\Projects\codex_diag_11_review_tabs_20261103t1500z`.
   Прочитать текущие Pages/Scripts/SHA/manifest, сверить6 страниц/102 Text/
   48 скриптов/15 связок/фоны `[0,64,1920,1016]`, отсутствие probe и сохранность
   ресурсов/ArcSystem.sar. Старый SHA grid не использовать. Новые несохранённые
   правки Editor сначала сохранить отдельно; backup1019z не перезаписывать.
3. Установленным Python3.13.17 подготовить новую приватную копию. Переменные
   ниже Codex заполняет сам после сверки шага2, не просит у пользователя хеши:

   ```powershell
   $overviewOut = Join-Path $env:LOCALAPPDATA ('CodexCandidates\SCADA11\codex_diag_11_review_overview_' + [Guid]::NewGuid().ToString('N'))
   & "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -I -B .\tools\prepare_native_ui_event_probe.py --mode overview-panel --project $overviewSource --out $overviewOut --expected-pages-sha $overviewPagesSha --expected-scripts-sha $overviewScriptsSha
   if ($LASTEXITCODE -ne 0) { throw 'Overview copy not prepared; source preserved' }
   ```

4. Проверить manifest/audit: sourceUnchanged=true; changedScripts только
   OperatorConsole;137 Text/48 IDs/15 bindings/0 findings;5 страниц/47 скриптов,
   Variables/Servers/Windows/Trends/профили сохранены побайтно, compiled исключён.
   При отказе выяснить конкретное отличие, не обходить guards переименованием.
5. Открыть новую копию в Editor, Compile All/Save; сверить журнал и фактически
   сохранённый путь/Pages/Scripts SHA. Пропущенный Save As ресурс восстановить
   только неизменённой проверенной копией после сравнения. Сохранить источник.
6. Штатно показать новый Client с учётом двух экранов/границ/DPI, без двух
   одновременно управляющих проектов. Один кадр «Все станции»: сравнить
   четыре блока/таблицу/насосы/обновление/шрифты/отступы, проверить действие
   отдельного окна и верхние вкладки. Apply/пуски ради UI не нужны. При GUI-
   препятствии попросить открыть конкретное окно/сделать этот кадр в чате или
   через существующий Telegram-notifier; бота заново не настраивать.
7. Проверить реальные данные: одна станция, PV/SP с одним знаком, unknown/
   stale не становятся «здоровой станцией», насосы2–4 остаются н/д; возраст —
   прогресс счётчика. Свежий counter не доказывает достоверность датчика.
8. Самостоятельно записать версию кода/путь и SHA кандидата, результаты и
   непроверенное в новый отчёт/HANDOFF; опубликовать согласованное в handoff.
   Если вид ещё расходится — исправлять source без нового общего согласия.
   При незавершённой приёмке оставить/вернуть проверенную конфигурацию,
   указав имя. Затем продолжить карточку: показатели, реальные статусы
   насосов, нижние события/связь. Поиск/фильтры и остальные окна ещё впереди.

Command contracts SCADA/ПЛК/HMI и радио02 не менять. Пароли/частные проекты/
архивные данные в Git не добавлять. Облачные42 PASS не заменяют Windows-вид.
