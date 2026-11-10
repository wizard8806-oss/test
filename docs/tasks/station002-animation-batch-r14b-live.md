# r14b: убрать оставшееся смещение входов макроса на одно слово

Стенд доступен примерно до07:04МСК10.11. После загрузки r14a пользователь
прислал два новых снимка: только3 даёт directF[0,0,250]/Q[1,1,2], но
macroF[0,250,0]/Q[1,2,9]; только2 даёт directF[0,250,0]/Q[1,2,1], но
macroF[250,0,0]/Q[2,1,9]. Значит, r14a изменила раскладку, однако полного
исправления нет. Оставшееся+1WORD начинается после scalar MapVersion.
Не считать это проблемой адресаSlave/ПЧ/датчика давления или очередным
неправильным рисунком. Нужен новый native Compile и живой повтор.

1. Получить `artifacts/station002-animation-batch-r14b/delivery-manifest.json`
   из того же pinned-коммита, что задание. По rawBase скачать3 files[],
   проверить bytes/SHA. Это Pythonstdlib, без новых установок.
   Новая папка:
   `C:\Users\user\CodexProjects\pump-station\.worktrees\station002-animation-batch-local-14b\`.
2. Source — exact r14a из предыдущей папки
   `...\.worktrees\station002-animation-order-local-14a\pump_station_3p_animation_order_r14a.skm`,
   1273731байт, SHA256
   `b56648e47a41cdd4eef981060da7a20a0a12cb062f6af9a4c1cf9faf69523323`.
   Также принимается исходный пользовательский r13 SHA1ea6…bfc2, с ним
   результат идентичен. Более новые native-правки сохранить, guard не
   убирать вслепую; нужна строгая адаптация с сохранением прочих изменений.
3. Собрать и проверить новую копию:

```text
python -S -B tools/build_animation_batch_r14b.py --source "ПОЛНЫЙ_ПУТЬ_К_R14A.skm" --out pump_station_3p_animation_batch_r14b.skm --report animation-batch-build.json
python -S -B tools/build_animation_batch_r14b.py --source "ПОЛНЫЙ_ПУТЬ_К_R14A.skm" --check pump_station_3p_animation_batch_r14b.skm --report animation-batch-check.json
```

   Expected1273871байт, SHA256
   `476138a71d10b284da088b145cf38b14bf31d75cfce22f6bce559642bb740b7f`.
4. Все Rinputs теперь Batch16: AlarmWords10байт, MapVersion2,
   Telemetry26, Roles14, Manual6, Leader2. BootAck остаётся scalarW R2553
   последним. Адреса не меняются. В обоих C-mirror лишь чтение Leader
   через `PumpAnimLeader[0]`, сведения о типах и signatureLW930=**27124**.
   MapVersion по-прежнему используется как AlarmWords[4]. Probe caption
   обновлён на27124 во всех7языковых/cacheзаписях. Main/надписи/новыйHAD/
   другие виджеты, PLC/защиты/таймеры/каскад сохранены. Полная инверсия
   перечисленных полей/релокации возвращает exactsource.
5. Через File→Open открыть именно r14b, штатный Compile. Изменён C, поэтому
   нужен новый compiled image, не старая prjCompiled. Проверить generated
   aliases: MapVersion и Leader являются one-WORD Batch16, telemetry стартует
   после10+2байт Rinputs; никаких hardcodedpVar/ручного сдвига частот.
   Проверять фактическую native структуру, не выдавать hostheader за неё.
   При отсутствии GUI всё равно создать/check SKM и дать полный путь
   оператору для File→Open/Compile. Не останавливаться на поиске окна.
6. Оператор загружает новый HMIimage; PLC сохраняется. На настоящей панели
   должно быть **27124**. Сначала только3/25Гц: macroF[0,0,250], Q[1,1,2],
   вращение/«Работа» только3. Через10–15с фото probe/main. Потом отдельно2,
   затем1, сверить direct/macro/индикатор. Неправильное значение27119
   означает, что новый C ещё не подтверждён на устройстве.
7. Проверить Leader/AUTO и прежний BootAck/bootlog/mute handshake. В облаке
   256hostсценариев/2304tick подтвердили сохранение всех логических выходов,
   входов/BootAck иbits, кроме signature27119→27124.7package/sourceguard
   проверок PASS; сборка изuser-r13/r14a одинакова. Это **не nativeABI**.
   Если смещение сохранилось, немедленно снять actual generated aliases/
   byteoffsets/типы/размеры именно этого образа, не менять PLC/таймауты.
8. Пользователь дал **действующий путь к оригиналу AUTOMATIKA KG**:

```text
C:\Users\user\Documents\HMI\Samkoon\Automatika визитка print.jpg
```

   Найти/прочитать именно его, сохранить оригинал и скопировать bytes без
   перерисовки в `assets\automatikakg.jpg` новой папки14b. Проверить картинку
   и зафиксировать размер/SHA; старый отсутствующий Desktop-путь не блокер.
   В SKTool для Screen14 штатно выбрать скопированный JPEG как фон/рисунок,
   сохранив пропорции и фирменную надпись. HMI parameters → HMI Start Setting:
   рабочая страницаScreen1, If Load Screen включить сScreen14 (около3с,
   если есть выдержка); ScreensaverScreen14/60с, касание возвращает прежний
   экран без команды насосам. Сохранить отдельный *_native.skm и сделать
   Compile с уже исправленными Batch inputs. Не угадывать opaque SysParame
   поля скриптом. Если GUI недоступен локальному, он всё равно создаёт r14b,
   копирует asset и даёт оператору полный путь/точные оставшиеся GUI-шаги.
   Native-save с картинкой/Generalsettings будет иметь другой SHA, чем
   golden r14b до этих настроек: source-checker применять ДО native-правок,
   потом отдельно проверить сохранение Batch inputs и signature27124.
   Один правильный путь к файлу ещё не доказывает включение loading/saver.
9. Сохранить native/image пути/SHA и реальные результаты3/2/1/Leader/BootAck
   в локальном отчёте/HANDOFF, краткую сводку опубликовать в handoff-ветку.
   Затем продолжить доступные faultA52/звук/журнал/перезапуски/каскад.
   Port0 общий сHMI: второгоmaster не добавлять; raw/native/vendor/секреты
   публично не выкладывать. Публикация нового SKM не доказывает его загрузку.
