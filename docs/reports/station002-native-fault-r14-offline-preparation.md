# Подготовка native fault r14, 09.11.2026

Пользователь сообщил, что панели сейчас нет. Подготовлен source-locked PLC
builder и передача локальному для завершения HMI/нативных проверок без стенда.
Новая HMI-база — пользовательский r13 со сдвинутыми надписями:
1273731байт, SHA256
`1ea6cece228acbb1dd5d99750a44399bfc9a3a36fa261403649b0297d251bfc2`.
Файл сохранён приватно, main80объектов/HAD1794244624/два одинаковых C mirror
подтверждены. Фирменный AUTOMATIKA KG дан пользователем; Screen14 уже содержит
ссылку на automatikakg.jpg. Включение loading/saver ещё требует native settings.

## Сделано в облаке

- `build_vfd_fault_export_r14.py` строит отдельный PDW из точного r10:
  source187549байт/b5de31e3…192a8b, candidate201327байт/
  `718a004b098f32493829db4cd42475eb842669a157511c90066883e5d9ea84cf`.
- Добавлены384сети/7186байт перед95.W032. Все прежние program bytes,
  data/poll tables и непрограммная metadata сохранены. Контрольные суммы
  и изменённые PC metadata проверены. Новые аппаратные команды0.
- Публикация кодов3ПЧ по уже существующим accepted pulses/cache; READY не
  требуется. Raw/quality/sequence/lastnonzero, отдельныйcontract27120,
  native fault-event flags1..80/unknown и display countR3077. R2363 иR2840
  не изменяются. Retained signatures/коды восстанавливают активное событие
  после рестарта, свежий0 снимает его, timeout не подтверждает восстановление.
- Validator исполнил **258**сценариев на фактических добавленных инструкциях:
  все240комбинацийПЧ×код1..80,8масок3ПЧ,unknown81/255/32768/65535,
  repeated/stale/reboot/fresh0/unqualified/sequencewrap. PASS.
- **384**добавленных сети приняты изолированным vendor Prolad18 node converter.
  Это не штатный F8/WinProLadder Simulation.
- Собственный каталог37коротких подписей по ранее выбранному руководству
  900G/900M, PDFстр56–59. A52/Err52=нехватка воды; raw52 на конкретном
  ASDA AC900 и остальные соответствия прошивки пока живьём не подтверждены.
- Проверен отдельный дефект SB6010: target-name Screen13 с тремяcached
  index3. Это основание для исправления навигации, не доказанная причина
  перекрёстной анимации. Проверка упаковки R/W inputs остаётся native-задачей.

## Что ещё нужно сделать локальному

Новый HMI-r14 **не создан**. Нужно завершить native fault page/журнал/звук,
сохранить пользовательский main и новый HAD, исправить routing, проверить
generated macro aliases, включить loading/saver Screen14 и прогнать отдельную
OFFLINE_TEST копию. Подробное задание:
`docs/tasks/station002-native-fault-r14-local-offline.md`.

Native memory/retain/косвенные ссылки, F8, Compile, нативные alarm groups и
аппаратные timing/retention/звук/анимация пока не приняты. Перед загрузкой
проверить R3040..3079 иR2832..2837/R2844..2848 не только direct operands:
явные ссылки отсутствуют, но это не вся карта распределения памяти.
ПК к оборудованию не подключался; Download/Force/RUN/reset не выполнялись.
