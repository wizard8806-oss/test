# Один контроль новых экранов на открывающейся нативной основе

**Native SaveAs получен:** C_native_code_pages.skm1461830/SHA506dec71f62efadca3cc6660707306d2076c4122a83f24b1568c908a95c29b4a.
Повторные Open/SaveAs/build этого контроля не нужны. Следующее задание —
`docs/tasks/station002-native-merge-r16-local.md`: полный кандидат на этой основе.

**Open PASS подтверждён пользователем:** local21f618a сверил exact1461857/SHA
b9fe40…b58b9, затем пользователь прямо подтвердил открытие этого файла
и доступ Screen15/16. Не пересоздавать пакет и не повторять Open.
Сейчас выполнить только штатный **Save As → C_native_code_pages.skm** из
уже открытого контроля, сообщить полный путь для приватного прикрепления.
Если native-файл уже сохранён/передан — повтор не нужен. Исходный контроль
сохранить. Compile/полная HMI ещё не приняты.

Fullr15f exact1480015/SHA2fe470…9676e дал подтверждённый оператором
**Illegal opening при Open**, не Compile. Полная HMI не принята. Не
повторять r15f/старые пробы, не выпускать guessed production r15g.

Нужен один контроль: в уже открывающийся C_native_16pages перенести только
тела новых Screen15/16 из fullr15f. Нативные headers/массивы16/старые страницы/
C/Batch/две alarm-группы/путь лого сохраняются. Так проверяются77новых
виджетов отдельно от остальных правок полной сборки. Это Open-only диагностика.

## Подготовить один файл

Взять `artifacts/station002-native16-code-pages/delivery-manifest.json` из
того же коммита, что это задание. Код закреплён на
`2e371795ac34c7321c1cf1ea39a2d8d993cf701b`. Скачать шесть files[] по
rawBase, проверить bytes/SHA и положить с сохранением tools в `native16-ui`
существующей worktree15. Только Python stdlib.

Два существующих входа:

- Native: `C_native_16pages.skm`,1299291байт/SHA
  `671ce4309579da4e2d5109c6910b35a08f2baaf7b702dbaca800f373e910c738`.
  Пользователь уже подтвердил его reopenPASS. По присланному окну путь:
  `C:\Users\user\CodexProjects\pump-station\.worktrees\station002-open-isolation-local-15b\open-tests\C_native_16pages.skm`.
- Донор только новых page-блоков: `pump_station_3p_fault_reset_r15f.skm`,
  1480015байт/SHA`2fe47083c0fbbb2fc9d31342c1ab76d3b220c81afa0f60c61d1ea4eed2c9676e`.
  Уже создан в `station002-fault-reset-local-15` и сверён local54992be.

Пути проверить самому. Если отличаются — найти нужные имена в существующих
worktree15b/15, сверить SHA и использовать реальные пути; не просить
пользователя вспоминать путь. Оригиналы не пересохранять/не перезаписывать.

Из `C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15`:

```text
python -S -B native16-ui/tools/prepare_native16_code_pages.py --native "..\station002-open-isolation-local-15b\open-tests\C_native_16pages.skm" --donor pump_station_3p_fault_reset_r15f.skm --out OPEN_NATIVE16_CODE_PAGES.skm --report native16-ui-build.json
python -S -B native16-ui/tools/prepare_native16_code_pages.py --native "..\station002-open-isolation-local-15b\open-tests\C_native_16pages.skm" --donor pump_station_3p_fault_reset_r15f.skm --check OPEN_NATIVE16_CODE_PAGES.skm --report native16-ui-check.json
```

Ожидаемый результат **1461857байт**, SHA
`b9fe40ba0e65ac6a41712d6e5116a1f92103208678868f7233566c1c359b58b9`.
Выходы/отчёты новые. Если точный выход уже есть, не пересоздавать;
новый отчёт проверки писать отдельно.

Проверить существование и дать оператору **реальный полный путь**:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15\OPEN_NATIVE16_CODE_PAGES.skm
```

## Один новый Open

File→Open именно **OPEN_NATIVE16_CODE_PAGES.skm**. Успех: загружено дерево
16экранов, Screen15/16 открываются **через дерево редактора**. Старые кнопки
главной специально сохранены нативными, их маршруты не изменялись.
Не подменять загруженное дерево оставшимся Screen16 в combobox после Warning.

- **PASS:** отдельный штатный SaveAs **C_native_code_pages.skm** рядом с
  контролем. Записать путь/размер/SHA, выдать путь для приватного прикрепления
  в облачном чате. Это образец новых виджетов после native-save, не итоговая HMI.
- **FAIL:** точные имя/SHA/текст ошибки и исход. Новый отказ отделяет UI-блоки
  от новых alarm-групп, но ещё не устанавливает конкретный дефект виджета.
  Не создавать guessed r15g и не просить ещё один native16 или повтор r15f.

Если GUI доступен — завершить этот Open/SaveAs самому, сохраняя прочие
проекты. Если агенту GUI недоступен — всё равно закончить build/check и
дать оператору полный путь для одного Open. Не застревать на Tips/скрытых
процессах и не заменять необходимый Open повтором общих57hostпроверок.

Compile/Simulator/Download/оборудование этой диагностике не нужны.
ПЛК/runtime/reset-guard/main не менять. SKM/PDW/JPG/vendor/закрытые дампы
в Git не публиковать. Обновить HANDOFF и компактный отчёт handoff-ветки с
раздельными filePrepared/nativeOpen/nativeSaveAs и реальным путём результата.
