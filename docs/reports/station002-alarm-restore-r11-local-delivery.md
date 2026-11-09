# HMI alarm restore r11 — краткий результат

Задание закреплено к `2d0b219826ccbc3747833afc718a2509221cc73d`. Из exact r10 создан отдельный r11 candidate: 1,287,916 байт, SHA256 `3e6d60e52d3177d786fe72e89cb4cb64c842e16867974c4f8ca5a5fb1065b0d7`.

Четыре pinned package-файла прошли size/SHA. Локальные restore/validator reports подтверждают восстановление всего HAD8288, его 135 native properties и сохранение остальных данных r10, включая восемь настроек каскада/макросы/аварии. PLC не менялся. Исходный candidate r10 сохранён.

Native SKTool Open/Compile/Offline Simulator, grid visibility and native fitting remain unverified. The restored object also has its original 976×360 bounds; no native-fit SKM or compiled panel image has been produced. Пользователь сообщил, что на r10 grid не отображался; причина не установлена. Оборудование не подключалось и не загружалось. Полный SKM и приватные журналы не опубликованы.
