# SCADA11: диагностика desktop-контекста и недоступности Client

02.11.2026, локальный Windows-сеанс. Проверяемая ветка перед публикацией
`codex/project-handoff-2026-10-31`, SHA `5727a43f4de416cee9e3de9c5aeeee5bf051e4b9`.
Основная локальная копия не обновлена: HEAD `5e3cbaec17ec2c78e248be5fea1b3483dbe6e934`,
изменён HANDOFF и присутствуют три ранее перечисленных untracked-файла. Они
сохранены. Локальный fetch не смог открыть `.git/FETCH_HEAD` (Access denied),
а созданная managed worktree имела старый HEAD 5e3cbae; основную папку не
переключали и не сбрасывали. Текст задания/контракта и helper прочитан из
указанного GitHub commit.

## Выполненный helper

`tools/Get-ScadaUiContext.ps1` из `5727a43` (blob SHA
`8e6686a6d113045048ed909b53cb4dd04410f748`) выполнен без изменений во
временном каталоге, тем же локальным исполнителем. Использовались Windows
PowerShell `5.1.19041.1682`, x64, FullLanguage. JSON сохранён вне Git под
`%TEMP%\scada-ui-context-run-<id>\context.json`; путь не перезаписывал
существующие результаты.

Результат: `status=measured`, `userInteractive=true`. Executor имеет
SessionId 1, window station `WinSta0`, desktop `CodexSandboxDesktop-<instance>`,
не повышенный уровень; активная консоль также SessionId 1. Server, Client,
Editor и `modbusopcserver` имеют тот же SessionId 1, но все отмечены
elevated=true и hasMainWindow=false. Для executor `EnumWindows=false`,
Win32 error 0, перечислено окон 0, ошибок чтения окон 0. Это не подтверждает,
что у приложений вообще нет окон на их desktop; оно подтверждает, что текущий
executor перечисление не получил. Измеренный отдельный desktop executor и
несовпадающий уровень elevation объясняют недоступность окон из данного
Codex-канала; другой Windows Session как причина не подтверждён.

В обеих registry views (32/64) `OPC.Automation.1` и `OPC.Automation`
не зарегистрированы; `InSAT.ModbusOPCServer.DA` зарегистрирован как
LocalServer. COM не активировался: `opcObjectsCreated=0`. Проверка не
доказывает отсутствие любых других OPC-клиентов или доступность live-тегов.
Скрипт зафиксировал `windowActionsInvoked=0`, `equipmentCommands=0`.

## Визуальная приёмка и следующий шаг

Реальные кадры Client11 не получены; путь/масштаб/viewport активного Client
этим результатом не установлен. Эталонный mockup и его контракт прочитаны,
но сравнение «кадр Client11 против макета» выполнить нельзя. Изображения
Editor/HTML не подменялись снимками Client. Изменения native/UI исходников не
вносились: без парного кадра это было бы предположительной правкой и не
исполняло бы установленный порядок приёмки. SCADA, проекты, настройки и
оборудование не менялись.

Следующий шаг — выполнить диагностику/захват из исполнителя, реально
находящегося на desktop с видимым Client, либо предоставить поддерживаемый
снимок экрана для этого executor. Нельзя отключать desktop/session isolation,
поднимать права или инъецировать ввод как обход. После получения приватных
кадров с Client11 и эталона при сопоставимом viewport можно завести реестр
конкретных расхождений и точечно исправить генератор/native-копию, затем
подтвердить парой кадров до/после. Работа по
`docs/tasks/station11-visual-parity.md` остаётся незавершённой.
