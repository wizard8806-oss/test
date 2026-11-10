# r15f: расширить обе служебные таблицы экранов и проверить полный проект

**Завершён этап Open с отказом:** local54992be подтвердил exact1480015/SHA2fe470…9676e,
оператор ответил «При открытии — Illegal opening». Полная r15f не принята.
Не повторять её Open/Compile. Следующее задание —
`docs/tasks/station002-native16-code-pages-local.md`: один контроль UI на native16.

Получен C_native_16pages.skm1299291/SHA671ce4309579da4e2d5109c6910b35a08f2baaf7b702dbaca800f373e910c738.
Пользователь подтвердил его повторное Open без ошибки. Прямое сравнение с
native14 R80 установило ещё две таблицы, зависящие от числа экранов:
section1:14→16байт; section21:48+14×4→48+16×4. В нашей r15e они оставались
на14, хотя заголовок/карта уже16. Исправление добавляет **2+8байт** и
пересчитывает24указателя/locator. Все остальные payload сохранены.
Это конкретный пропуск формата. Успех Open полной r15f ещё не подтверждён.

## Создать один полный кандидат

Взять `artifacts/station002-page-storage-r15f/delivery-manifest.json` из
того же коммита, что это задание. Код закреплён на
`ce767cf5300e794aac561ef59b20210729f82e2a`. Скачать пять files[] по rawBase,
проверить bytes/SHA и сохранить структуру tools в `repair-page-storage`
существующей worktree15. Только Python stdlib. Отсутствие GUI не блокирует
создание и проверку файла.

Рабочая папка:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15
```

Источник — существующая **полная pump_station_3p_fault_reset_r15e.skm**,
1480005байт/SHA
`2198325315f9b9a6918f483f07f164f855ef454fb3454d7363fe73b6e3fb171d`.
Не подменять источник A/C/CONTROL/native16 или nativeSave. Они нужны только
как эталоны диагностики. Исходники сохранить, выходы/отчёты новые:

```text
python -S -B repair-page-storage/tools/repair_page_storage_r15f.py --source pump_station_3p_fault_reset_r15e.skm --out pump_station_3p_fault_reset_r15f.skm --report r15f-build.json
python -S -B repair-page-storage/tools/repair_page_storage_r15f.py --source pump_station_3p_fault_reset_r15e.skm --check pump_station_3p_fault_reset_r15f.skm --report r15f-check.json
```

Результат **1480015байт**, SHA256
`2fe47083c0fbbb2fc9d31342c1ab76d3b220c81afa0f60c61d1ea4eed2c9676e`.
Если выход уже существует и совпадает — не пересоздавать; проверку писать
в новый отчёт. Этот полный файл сохраняет16страниц, семь групп аварий,
оба C/Batch, коды/сброс, HAD, пользовательскую раскладку и путь лого.

Проверить существование и дать оператору **полный реальный путь**:

```text
C:\Users\user\CodexProjects\pump-station\.worktrees\station002-fault-reset-local-15\pump_station_3p_fault_reset_r15f.skm
```

При другой фактической папке дать настоящий путь. Старые A/контроли,
создание native16 и общий run_checks ради этого шага не повторять.

## Один native Open, затем SaveAs/Compile

Через File→Open открыть именно полный r15f. Успех — загрузилось дерево16
экранов и доступны Screen1/9/15/16 без Illegal opening. Имя Screen16 в
combobox при пустом дереве успехом не считать. Другие открытые проекты
сохранить; модель/редактор не менять, процессы массово не завершать.

При успехе штатный SaveAs **pump_station_3p_fault_reset_r15f_native.skm**,
затем Compile SKTool7.1 и Offline Simulator. Записать результаты отдельно,
сохранить точный текст ошибок/предупреждений. В Simulator проверить открытие
главной/аварий/кодов со сбросом/истории запусков и навигацию. Нулевые PLC-данные
в offline сами по себе не означают ошибку телеметрии.

Сохранить новый native-файл, его путь/размер/SHA для приватного прикрепления.
Проверка --check выше относится к исходному generated r15f; native SaveAs
имеет собственный SHA после пересериализации редактором. Открытие/Compile
не доказывают аппаратную работу сброса или настройки loading/saver; эти
приёмки пока раздельны. Если полный Open опять отказал — точные имя/SHA/ошибка,
файл сохранить, новый guessed r15g не создавать.

Если GUI агенту недоступен, закончить build/check/выдачу точного пути, затем
оператор открывает этот один файл. Не застревать на Tips/скрытых процессах.
ПЛК/runtime/reset-guard/main не менять. No Download/Force/RUN/оборудование;
шкаф отдан. SKM/PDW/JPG/vendor/сырые закрытые данные в Git не публиковать.

Обновить HANDOFF и компактный отчёт handoff-ветки: exact source/candidate,
nativeOpen, nativeSaveAs, Compile, Simulator и полный путь результата.
Сборка файла и host-проверки не заменяют эти нативные исходы.
