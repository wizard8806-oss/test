# Main r20: материалы готовы, native файл ожидается от local

Пользователь утвердил реализацию тёмного макета №1 и убрал название
«Насосная станция». Уставка крупнее, частота ведомых меньше. Local ещё
делает r19 и постоянно ждёт согласия по сообщению пользователя. Native
r19/его SHA облаку не передан; remote-отчёта пока нет.

Code **6deb50e75448ab2df2116f42f13f76d68da51a82** подготовил настоящий
статический фон без живых значений/статусов/кнопок/названия,49nativeобластей
и CMainOverview только LW970..979. PNG1620×971/1605688байт/SHA
`3d5bef84bd14820e1626ea8f005c8d2c917bded2a9f2f569c389f74be23fb46e`;
в SKTool fit0,0,800,480. Визуальная проверка и OCR подтверждают отсутствие
рисованных readouts; остаются fixedlabels/pumpnumbers/scale ticks.

Сводка: подтверждённый RUN-count, link/map и ротация из настоящих
R2140/R2150/R2151 и ModeR2300. Нужны2новых READ ONLY nativeBatch aliases
R2300/2bytes иR2140/24bytes доBootAckW. Данные не читаются по догаданным
pVar: отсутствующие aliases вызывают явный Compile-error. Helper экспортирует
полный C с обратным восстановлением прежнегоUTF16, SKM/таблицы не патчит.

Actualr17aпроверка обнаружила **ND3014/NE5002R2100 иND3018/NE5004R2110**:
оба поля имеют показ+ввод. Старый запрет Main-ввода в task был ошибкой,
исправлен. Сохранить их guards/scale/limits, AUTO-reason/restart pause,
AlarmDisplay,17pages/7groups/RKF/ручное окно/звук/переходы/STOPreset.

Проверки: тест сначала RED на пустом сервисе, actualC **38/38PASS**;
unknown/связь/фазы/режим/переполнение/границы, отсутствие своего таймера
и любых записей вне LW970..979. Export/inverse, отказ старому/изменённому
источнику,17pageproductiongate/nooverwritePASS на privateancestorfixture.
Изолированная доставка14pinnedфайлов воспроизводит экспорт/38кейсов.
**58/58** общих build/checkгруппPASS, source tree не изменён.
После этого readonlyrotation-вход сужен с40до24байт: используются только
12слов доR2151. Повторены38Cкейсов и изолированный экспорт/доставка с
финальным24byteвходом; вычислительная логика не менялась.

Actualnative r19/новыйMain/SKToolCompile/GUI/RS485 не проверялись. Старый
16pagefixture не является рабочей основой. Ни sourceSKM/PDW, ни оборудование
не менялись. Задание docs/tasks/station002-main-modern-r20-local.md и
manifest artifacts/station002-main-modern-r20/delivery-manifest.json:
закончить r19, затем r20 в том же localсеансе, дать реальные Windows-пути.

Для CLI проверены официальные slash/reference docs: `/permissions` и
существующий fullaccesslauncher `resume --last`. Разрешение сохраняется;
облако не меняло Windows-профиль/globalconfig/UAC. Готовый SKM pending.
