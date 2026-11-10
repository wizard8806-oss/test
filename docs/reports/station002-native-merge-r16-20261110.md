# Полный журнал и навигация на native-saved основе, r16

10.11.2026 получен C_native_code_pages.skm1461830/SHA
`506dec71f62efadca3cc6660707306d2076c4122a83f24b1568c908a95c29b4a`.
Источник сохранён штатно самим пользователем из operator-OpenPASS контроля
OPEN_NATIVE16_CODE_PAGES/SHA b9fe40…b58b9. Отдельный reopen именно506 пока
не сообщён; SaveAs не выдаётся за Compile/hardware. Private
`/workspace/shared/station002-native-merge-r16-20261110/user_native_code_pages.skm`.

Сверка с контролем:16экранов/обе page-arrays16/две alarm-группы; обе C-копии,
оба Batch-списка и opaque-секции0..21 побайтно прежние. Новые34/43виджета
сохранены без изменения содержимого; Page16 записана в ином порядке.
Размер уменьшился на27байт за счёт UI/первичнойmetadata; указатели обновлены.
Это рабочая нативная основа, а не повтор сборки из старого accepted3599.

## Управляемое объединение

`build_native_merge_r16.py` фиксируетSHA обоих источников. Из fullr15f2fe
заимствуются **только**7определений Alarm Login и companion-catalog.
Исходная station-группа побайтно равна donor; все268word/bit mappings,
флаги/языки/тексты нового журнала совпадают с подготовленным r15f.

Полный режим дополнительно исправляет:

- Main «Диагностика»→Screen13; кнопка бывших «ЗапусковПЛК» на авариях→
  «КодыПЧ»/Screen15. История запусков остаётся доступна с новой страницы.
- Все7новыхfooter-кнопок: согласованы четыре числовых поля48/49/57/60
  с ScreenName56. Проверка93исходныхnative-кнопок подтвердила этот шаблон;
  прежний producer оставлял60=12 у новых ссылок на другие экраны.
- Active-counter ND8278: все3зеркала R2363→R3077, включая packed-поле;
  равная UTF16-длина сохраняет внутренние размеры строк.
- Background Screen14: ссылка на **оригинальный пользовательский JPEG**
  `C:/Users/user/Documents/HMI/Samkoon/Automatika визитка print.jpg`.
  Исходное изображение не менялось/не встраивалось. Native loading/saver
  ещё нужно назначить штатно в SKTool после успешного Open.

Вся остальная нативная сериализация/раскладка/sceneheaders/HAD/макрос/
обаBatch/таблицы16 сохранены;24указателя/locator пересчитаны. Полная
инверсия восстанавливает native-источник побайтно. Отдельный режим
--alarms-only меняет исключительно два alarm-блока и указатели, сохраняя
даже весь UI до первичных alarm-definitions в точности. Это fallback,
если полный кандидат снова не откроется; полную прошивку он не заменяет.

| Выход | Байты | SHA256 |
| --- | ---: | --- |
| pump_station_3p_native_merge_r16_candidate.skm | 1479661 | 84797b73846e5266894812e4bcd7bd7aa8a977baa962934b8eea479aa58420e6 |
| OPEN_R16_ALARMS_ONLY.skm | 1479689 | 9e45309a2595462a705e2654f4c82a98b85425fef9c57c6559b8ec7a07ba886b |

## Проверки и следующий шаг

Cloud Linux: оба режима прошли проверку opaque0..21 и хвоста, C обоих
источников, packed/nativeBatch count10, BootAckWlast/Batch16-представления,
обе16page-arrays,268maps, первичногоUI fallback, HAD. Все77виджетов
инвентаризированы, геометрия сохранена; у новыхSB только целевые поля
навигации изменены, все остальные их property-поля прежние. CLI build/check
обоих режимов, nooverwrite/tamper/input preservation PASS.

RuntimeC и ПЛК не изменялись; прежние57coregroups/hostC-проверки не
повторялись. Они не подменяют nativeOpen нового r16. **NativeOpen,
SaveAs_native, Compile, Simulator и logo-start/saver ещё pending.**
Физический reset/новая прошивка оборудования не проверены; шкаф отдан.
Main/STOP-reset неизменны, никаких Download/Force/RUN не выполнялось.

Задание `docs/tasks/station002-native-merge-r16-local.md`: полный файл
сначала; приPASS отдельный nativeSave, loading/saver14 и Compile/Simulator.
ПриFAIL один alarms-only fallback отделит журнал от nav/logo. Source-файлы
и оригинальный JPEG сохранить. Native SKM/PDW/JPG/vendor не публиковать.
