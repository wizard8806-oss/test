# r17: успешная компиляция AlarmSound в SKTool7.1

12.11.2026 оператор прислал снимок **Script Editor**. В заголовке открыт
`pump_station_3p_native7_r17_candidate.skm` из локальной worktree
`station002-fault-reset-local-15`. В списке Success выбран
**AlarmSound [ID:0]**.

В Compile information output видны:

- Compiling(AlarmSound).
- HMI compiling output: 0 error(s), 0 warning(s).
- Local compiling output: 0 error(s), 0 warning(s).
- Compile success!

Это подтверждает нативную компиляцию данного скрипта для HMI и локального
симулятора по снимку оператора. Полное открытие r17 подтверждено отдельным
снимком 11.11.2026. Общая компиляция проекта, запуск Offline Simulator,
native SaveAs, логотип при загрузке и заставке этим снимком не подтверждены.
Свежие Windows размер/SHA и локальный отчёт ещё не получены; известный SHA
generated-файла не выдаётся за SHA текущего сохранённого проекта.

Продолжение: штатно сохранить и закрыть Script Editor, из текущего проекта
сохранить отдельный `pump_station_3p_native7_r17_native.skm`, проверить
Screen14 и HMI Start Setting по действующему заданию, сохранить, выполнить
общую Compile, затем Offline Simulator. Зафиксировать каждый результат
отдельно. Уже пройденные Open и сборку скрипта без новой причины не повторять;
новый кандидат, fallback и изменения макроса не нужны.

Задание: `docs/tasks/station002-native-seven-r17-local.md`.
В этой итерации изменены только инструкции и отчёт. Нативные исходники,
PLC, reset guard и main не менялись; аппаратная проверка не выполнялась.
