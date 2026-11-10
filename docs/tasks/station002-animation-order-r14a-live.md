# Срочно: проверить R-before-W HMI по живому смещению канала3в1

Стенд доступен примерно до07:04МСК10.11. Пользователь уже показал реальную
панель с работающим толькоПЧ3/25Гц. DirectPLC/RX корректны; macroвходы чужие:

| ПЧ | FPLC | QPLC | Fмакр | Qмакр | Кадр | Статус | RXF |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 1 | 250 | 2 | 4 | 2 | 0 |
| 2 | 0 | 1 | 0 | 9 | 0 | 0 | 0 |
| 3 | 250 | 2 | 0 | 5 | 0 | 0 | 250 |

MapPLC=Mapmacro=32, alarmwords0/0, link1, probe27119, sample406.
На главной шкала3/25Гц правильная, «Работа»/ротор1 ошибочны. Это локализует
дефект в actual PLC→native macro input, до анимационных outputs/виджетов.
Соответствует смещению блока на2WORD; точный native ABI ещё надо подтвердить.

1. Получить `artifacts/station002-animation-order-r14a/delivery-manifest.json`
   из того же pinned-коммита, что задание; по rawBase скачать files[] и
   проверить bytes/SHA. Только2 Pythonstdlibhelpers, без новых установок.
   Новая папка:
   `C:\Users\user\CodexProjects\pump-station\.worktrees\station002-animation-order-local-14a\`.
2. Source — последняя переданная пользователем база со сдвинутыми подписями:
   `...\.worktrees\station002-animation-probe-local-13\pump_station_3p_animation_probe_r13.skm`,
   1273731байт/SHA256
   `1ea6cece228acbb1dd5d99750a44399bfc9a3a36fa261403649b0297d251bfc2`.
   Сохранить текущие активные/nativeправки отдельно. Если фактический новый
   HMI отличается — не откатывать его к старому и не убирать guard вслепую:
   строго адаптировать такой же reorder к проверенному source, сохранив всё
   остальное, либо взять exactcopy если новых функций в ней ещё не было.
3. Создать отдельный SKM, затем проверить его:

```text
python -S -B tools/reorder_animation_macro_r14a.py --source "ПОЛНЫЙ_ПУТЬ_К_ПОЛЬЗОВАТЕЛЬСКОМУ_R13.skm" --out pump_station_3p_animation_order_r14a.skm --report animation-order-build.json
python -S -B tools/reorder_animation_macro_r14a.py --source "ПОЛНЫЙ_ПУТЬ_К_ПОЛЬЗОВАТЕЛЬСКОМУ_R13.skm" --check pump_station_3p_animation_order_r14a.skm --report animation-order-validation.json
```

   Expected1273731байт/SHA256
   `b56648e47a41cdd4eef981060da7a20a0a12cb062f6af9a4c1cf9faf69523323`.
4. Меняются **только два сериализованных списка Variable settings**:

```text
AlarmWords          R  R2550  Batch16  10bytes
MapVersion          R  R2554  UInt16
PumpAnimTelemetry   R  R2500  Batch16  26bytes
PumpAnimRoles       R  R2320  Batch16  14bytes
PumpAnimManual      R  R2380  Batch16   6bytes
PumpAnimLeader      R  R2304  UInt16
BootAck             W  R2553  UInt16
```

   Раньше BootAck стоял третьим, перед PumpAnimTelemetry. ВсеR теперь передW.
   Сохранены7имён/типов/адресов/размеров/режимов, весь C, всеmain/Scene9HAD/
   probe/другиеэкраны иbytesвнеэтих2таблиц. PLC не меняется. Это **отдельный
   проверяемый ABI-кандидат**, не доказанное исправление и не законченная HMI
   nativefault-r14. Не корректировать индексычастот вC и адресаPLC по догадке.
5. Открыть новый файл именночерез File→Open, штатный Compile. Сверить generated
   aliases с новым порядком ифактическим inputlayout; использовать имена,
   не hardcodedpVar. Новый image/date/hash отэтогоSKM, не стараяprjCompiled.
   Если GUI снова не виден излокальногосеанса, **всёравно создать/проверитьSKM**
   и дать оператору полныйпуть+одиншагFile→Open/Compile. Не ограничиваться
   отчётом об отсутствующемокне, не повторятьTips/установки/массовыйkill.
6. Оператор загружает новый HMIimage на стенд и повторяет **толькоПЧ3/25Гц**.
   ПК не занимает общийPort0 одновременно сHMI. Signature27119 не менялась:
   это не доказательство именноновогоimage; сверить путь/date/hash/новыйCompile.
   Критерий: Fмакр[1,2,3]=[0,0,250], Qмакр совпадаютсPLC[1,1,2],
   LW922=250/LW925=2, вращение/«Работа» только3. Затем только1 и только2.
   Если ничего не изменилось — сразу измерить native offsets/размеры/смещения
   batch reader, а не увеличивать тайм-ауты и не рисовать по командеRUN.
7. Отдельно проверить прежний BootAck/bootlog handshake и сохранность работы
   звука/ручногоавтоперехода: переменнаязаписи перемещена, не удалена.
   Прежние защиты/PLCтаймеры/каскадпараметры не изменять ради этой правки.
8. Записать результаты толькофактическивыполненныхCompile/live/P1/P2/P3,
   пути/SHA/image/nativealiases. Быстроопубликовать краткуюсводкувhandoffветку.
   WholeSKM/vendorC/H/rawфото/секреты не публиковать. Дальше продолжить оставшиеся
   проверки часа: faultA52/качество/журнал/звук, restartтаймеры/AUTOкаскад.

Облачная статическаяприёмка подтверждает узостьпатча и сохранность исходника,
но без native Compile/живогоповтора **не подтверждает исправлениеABI**.
