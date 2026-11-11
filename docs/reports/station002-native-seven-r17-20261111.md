# Native7-пример и заполнение его существующих message-векторов, r17

11.11.2026 получен C_native_7groups.skm1463855/SHA
`1c48a69e9c63e1f2787d78fb286d04ea3ae04a7b75f304504d75609c28367b8b`.
Пользователь прямо сообщил, что сохранил/переоткрыл, и прислал загруженное
окно с7группами. Это **operator-reported native Open PASS** данного образца.
Compile/runtime этим не подтверждены. Private
`/workspace/shared/station002-native-seven-r17-20261111/user_native_7groups.skm`.

Фактические группы:25/R2550;80/R3056;1/R3071;80/R3061;1/R3072;80/R3066;1/R3073.
Native подтвердилIDs0..6, flags/typeWord/driver/keys и нужные vector-counts.
Имена Digital Alarm Login1..6 оставлены редактором, сообщения пустые.
Макрос e02de3…61e5 и оба Batch-списка совпали с предыдущей рабочей основой.

## Дополнительное различие с прежним merge

Кроме объявленных alarm-блоков, native7 обновил opaque-секцию16: одну
QString(index7) в структуре tag3/list16. Остальные opaque0..21 совпадают с
source2. В badr16 эта область оставалась от проекта с2группами. UI/имя
проекта также пересериализованы штатным Save. Точный смысл закрытой строки
не декодируется и не публикуется; её различие не объявляется единственной
доказанной причиной. Вывод для сборки: использовать native7 целиком,
сохранить его служебные параметры и не восстанавливать группы вручную.

## Новая сборка

`build_native_seven_r17.py` принимает exactnative7 и прежнийfullr15f2fe
**только как донор подготовленных сообщений**. В6существующих native-группах
заменяются языковые message-векторы. Все native group headers/names/IDs/
addresses/protocol/flags/use/OFF-vectors/languagekeys и catalog остаются
побайтно прежними, включая исходную station-группу. Приёмы renumber или
перестройка definitions2→7 здесь не используются.

Полный режим дополнительно использует ранее проверенные UI-правки:
mainДиагностика13, КодыПЧ15/история16/footer-ссылки, четыре target-поля
кнопок, counterR3077 и оригинальный JPEG из Documents/HMI/Samkoon.
Структура16сцен, раскладка/77виджетов/HAD/C/Batch и всеopaque0..21,
включая native16, сохранены. Режим --messages-only оставляет весь UI каквsource7.

| Выход | Байты | SHA256 |
| --- | ---: | --- |
| pump_station_3p_native7_r17_candidate.skm | 1479937 | 757d792f75a95ed31971dd2819942e88d703f738c9524ba309320699644c88b3 |
| OPEN_NATIVE7_MESSAGES_ONLY.skm | 1479965 | 4bdab6282d838b4a16527ad31a994b7897aacec4ddc8c8ac57c0fabda9c6b4d5 |

## Проверки

- ui_edits выделен из старогоr16-helper; оба исторических r16-результата
  сохранены побайтно, служебный интерфейс prepare не изменён.
- Все native group-поля до/после messages и каталог сохранились точно.
  Все268word/bit/flags/language/message mappings равны подготовленному донору.
- Все opaque0..21/хвост доиндекса, включая новый16-блок, равны native7.
  C обоих источников и оба Batch-списка count10/BootAckWlast сохранены.
- Обеpage-arrays16, первичныйUI messages-only,77widgetIDs/геометрия/content
  (уSB тольконавигационныеполя) и originalHAD сохранены. Полная инверсия PASS.
- Fresh stdlib CLI build/check обоих режимов, nooverwrite/tamper и источники PASS.

Core/runtimeC/PLC/reset-guard/main не менялись; общие57не повторялись.
**Новые nativeOpen/SaveAs/Compile/Simulator/loading/saver pending.**
Native7 пустогообразца OpenPASS не означает полного r17 OpenPASS.

Задание `docs/tasks/station002-native-seven-r17-local.md`: сначала fullr17,
приPASS NativeSaveAs/start+saver14/Compile/Simulator; приFAIL одинmessages-only.
ЕслиобаFAIL — нативный Export B01 для текстовогоимпорта, без guessedr18
или ещёодного создания7групп. Сохранить всеисточники/JPEG, native-файлы
и закрытые данные в Git не публиковать. Шкаф отдан; hardware/Download/
Force/RUN не выполнялись.
