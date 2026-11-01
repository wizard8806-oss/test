(function (root, factory) {
  const model = factory();
  if (typeof module === 'object' && module.exports) module.exports = model;
  else root.OperatorModel = model;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const profiles = {
    'fatek-900g': {name: 'FATEK · 900G', maxPumps: 4, minRaw: 10, maxRaw: 1190, stepRaw: 10},
    'generic-monitor': {name: 'Мониторинг · общий профиль', maxPumps: 16}
  };
  const clone = value => JSON.parse(JSON.stringify(value));
  const nonempty = (value, max = 120) => typeof value === 'string' && value.trim().length > 0 && value.length <= max;
  const slug = value => typeof value === 'string' && /^[a-z][a-z0-9-]{1,47}$/.test(value);
  function shape(value, fields, label) {
    if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(k => !fields.includes(k))) throw new Error(label + ': неподдерживаемые поля. Пароли и ключи не входят в каталог.');
  }
  function validateCatalog(value) {
    shape(value, ['schemaVersion', 'timezone', 'groups', 'connections', 'stations'], 'Каталог');
    if (value.schemaVersion !== 1 || value.timezone !== 'Europe/Moscow') throw new Error('Ожидается каталог версии 1, время Europe/Moscow.');
    for (const field of ['groups', 'connections', 'stations']) if (!Array.isArray(value[field]) || value[field].length < 1 || value[field].length > 1000) throw new Error('Проверьте список: ' + field);
    function unique(rows, field, label) {
      const seen = new Set();
      for (const row of rows) {
        if (!slug(row[field]) || seen.has(row[field])) throw new Error(label + ': ID должен быть уникальным, латиница/цифры/дефис.');
        seen.add(row[field]);
      }
    }
    unique(value.groups, 'id', 'Группы'); unique(value.connections, 'id', 'Подключения'); unique(value.stations, 'id', 'Станции');
    for (const row of value.groups) {
      shape(row, ['id', 'name'], 'Группа'); if (!nonempty(row.name)) throw new Error('Укажите название группы.');
    }
    const endpoints = new Set();
    for (const row of value.connections) {
      shape(row, ['id', 'name', 'type', 'computer', 'server'], 'Подключение');
      if (!nonempty(row.name) || !['opc-da', 'demo'].includes(row.type) || typeof row.computer !== 'string' || typeof row.server !== 'string') throw new Error('Неверный профиль подключения.');
      if (row.type === 'opc-da' && (!nonempty(row.computer) || !nonempty(row.server))) throw new Error('Укажите компьютер и имя OPC-сервера.');
      if (row.type === 'opc-da') {
        if (!/^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$/.test(row.computer) || !/^[A-Za-z_]\w*(\.\w+)+$/.test(row.server)) throw new Error('Укажите имя компьютера и ProgID, без URL, логина и пароля.');
        const endpoint = row.computer.toLowerCase() + '|' + row.server.toLowerCase();
        if (endpoints.has(endpoint)) throw new Error('Это подключение уже есть: используйте существующий профиль.');
        endpoints.add(endpoint);
      }
    }
    const bindings = new Set();
    for (const row of value.stations) {
      shape(row, ['id', 'name', 'location', 'groupId', 'profileId', 'pumpCount', 'connectionId', 'itemPrefix', 'enabled', 'controlEnabled', 'limits'], 'Станция');
      if (!nonempty(row.name) || typeof row.location !== 'string' || row.location.length > 180) throw new Error('Проверьте название и адрес станции.');
      if (!value.groups.some(g => g.id === row.groupId) || !value.connections.some(c => c.id === row.connectionId)) throw new Error('У станции неизвестная группа или подключение.');
      const profile = profiles[row.profileId];
      if (!profile || !Number.isInteger(row.pumpCount) || row.pumpCount < 1 || row.pumpCount > profile.maxPumps) throw new Error('Количество насосов не соответствует профилю.');
      if (typeof row.enabled !== 'boolean' || typeof row.controlEnabled !== 'boolean' || (row.controlEnabled && !profile.stepRaw)) throw new Error('Для этого профиля доступен только мониторинг.');
      if (!/^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$/.test(row.itemPrefix || '') || row.itemPrefix.length > 140) throw new Error('Укажите префикс адресов, например codex.Device2.');
      const key = row.connectionId + '|' + row.itemPrefix.toLowerCase();
      if (bindings.has(key)) throw new Error('Две станции ссылаются на одни и те же адреса.');
      bindings.add(key);
      shape(row.limits, ['pressureLow', 'pressureHigh', 'staleSeconds'], 'Пороги');
      if (![row.limits.pressureLow, row.limits.pressureHigh, row.limits.staleSeconds].every(Number.isFinite) || row.limits.pressureLow < 0 || row.limits.pressureHigh <= row.limits.pressureLow || row.limits.pressureHigh > 100 || row.limits.staleSeconds < 5 || row.limits.staleSeconds > 300) throw new Error('Проверьте пороги давления и время устаревания.');
    }
    return clone(value);
  }
  function readPressure(station, snapshot, now) {
    if (!station.enabled) return {value: null, state: 'disabled', reason: 'Станция отключена в каталоге'};
    if (!snapshot || !Number.isFinite(snapshot.receivedAt)) return {value: null, state: 'unknown', reason: 'Нет данных станции'};
    if (now - snapshot.receivedAt > station.limits.staleSeconds * 1000 || now < snapshot.receivedAt) return {value: null, state: 'stale', reason: 'Нет свежих данных'};
    if (snapshot.quality !== 'good') return {value: null, state: 'bad', reason: 'Нет достоверных данных станции'};
    if (!snapshot.routeFresh) return {value: null, state: 'unknown', reason: 'Обновление ПЛК не подтверждено'};
    const p = snapshot.pressure;
    if (!p || p.quality !== 'good' || !snapshot.sourceValid || !Number.isFinite(p.value)) return {value: null, state: 'invalid', reason: p?.reason || 'ПЛК не подтвердил источник давления'};
    return {value: p.value, state: 'good', reason: 'Достоверные данные'};
  }
  const bindingKey = station => [station.connectionId, station.itemPrefix, station.profileId].join('|');
  const fixtureBindings = {
    'station-001': 'local-masteropc|codex.Device1|fatek-900g',
    'station-002': 'demo|demo.Station2|fatek-900g',
    'station-003': 'demo|demo.Station3|fatek-900g',
    'station-004': 'demo|demo.Station4|generic-monitor'
  };
  function hasFixture(station, catalog) {
    if (fixtureBindings[station.id] !== bindingKey(station)) return false;
    const connection = catalog.connections.find(c => c.id === station.connectionId);
    return station.connectionId === 'local-masteropc'
      ? connection?.type === 'opc-da' && connection.computer === 'localhost' && connection.server === 'InSAT.ModbusOPCServer.DA'
      : connection?.type === 'demo' && connection.computer === '' && connection.server === '';
  }
  function writeReason(station, snapshot, role, now) {
    const p = profiles[station.profileId];
    if (!['operator', 'engineer'].includes(role) || !station.enabled || !station.controlEnabled || !p?.stepRaw) return 'Недостаточно прав или профиль не поддерживает команду.';
    if (!snapshot || !Number.isFinite(snapshot.receivedAt) || snapshot.quality !== 'good' || !snapshot.routeFresh || now < snapshot.receivedAt || now - snapshot.receivedAt > station.limits.staleSeconds * 1000) return 'Нет свежих данных станции.';
    if (snapshot.mapVersion !== 32 || snapshot.feedbackVersion !== 1 || !['stop','auto','manual'].includes(snapshot.mode)) return 'Нет совместимой карты или подтверждённого режима ПЛК.';
    if (!snapshot.bindingReady || !snapshot.connectionWriteEnabled || snapshot.commandRaw !== snapshot.spRaw) return 'Привязка записи или её readback не подтверждены.';
    if (!Number.isInteger(snapshot.spRaw) || snapshot.spRaw < p.minRaw || snapshot.spRaw > p.maxRaw || snapshot.spRaw % p.stepRaw) return 'Текущая уставка вне допустимого профиля.';
    return null;
  }
  function makeDraft(station, snapshot, actor = 'preview') {
    if (!station.controlEnabled || !profiles[station.profileId].stepRaw || !Number.isInteger(snapshot?.spRaw)) throw new Error('Изменение уставки недоступно.');
    return {stationId: station.id, binding: bindingKey(station), baseRaw: snapshot.spRaw, raw: snapshot.spRaw, actor};
  }
  function adjustDraft(station, draft, delta) {
    const p = profiles[station.profileId];
    if (draft.stationId !== station.id || ![-p.stepRaw, p.stepRaw].includes(delta)) throw new Error('Черновик относится к другой станции или неверный шаг.');
    return {...draft, raw: Math.min(p.maxRaw, Math.max(p.minRaw, draft.raw + delta))};
  }
  function simulateApply(station, snapshot, draft, actor, role, now) {
    const p = profiles[station.profileId];
    const reason = writeReason(station, snapshot, role, now);
    if (reason) throw new Error(reason);
    if (draft.stationId !== station.id || draft.binding !== bindingKey(station) || draft.actor !== actor) throw new Error('Изменилась станция или владелец черновика.');
    if (snapshot.spRaw !== draft.baseRaw) throw new Error('Уставка уже изменилась. Повторите ввод.');
    if (!Number.isInteger(draft.raw) || draft.raw < p.minRaw || draft.raw > p.maxRaw || draft.raw % p.stepRaw || draft.raw === draft.baseRaw) throw new Error('Выберите новую допустимую уставку.');
    return {...clone(snapshot), spRaw: draft.raw, commandRaw: draft.raw, receivedAt: now, counter: (snapshot.counter + 2) % 65536, driveConfirmed: false};
  }
  function ackAlarm(alarm, actor, now) {
    if (alarm.acknowledged) return clone(alarm);
    return {...clone(alarm), acknowledged: true, acknowledgedBy: actor, acknowledgedAt: now};
  }
  function segments(points, from, to, maxGap = 360000) {
    const result = []; let current = [], previous = null;
    for (const point of points) {
      if (point.ts < from || point.ts > to) continue;
      if (point.quality !== 'good' || !Number.isFinite(point.value)) {if (current.length) result.push(current); current = []; previous = null; continue;}
      if (previous !== null && (point.ts - previous > maxGap || point.ts <= previous)) {if (current.length) result.push(current); current = [];}
      current.push(point); previous = point.ts;
    }
    if (current.length) result.push(current);
    return result;
  }
  function csvCell(value) {
    let text = String(value ?? '');
    if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  }
  function createFixtures(catalog, now) {
    const signal = (value, quality = 'good') => ({value, quality});
    const snapshots = {};
    for (const station of catalog.stations) {
      let snapshot = {receivedAt: null, quality: 'unknown', sourceValid: false, pressure: signal(null, 'unknown'), spRaw: null, mode: 'unknown', counter: 0, driveConfirmed: false, pumps: [], radio: 'Нет данных'};
      if (hasFixture(station, catalog)) {
        const bench = station.id === 'station-001', fault = station.id === 'station-003', stale = station.id === 'station-004';
        snapshot = {receivedAt: now - (stale ? 183000 : 3000), quality: 'good', routeFresh: !stale, sourceValid: !bench && !stale, pressure: {...signal(bench ? null : fault ? 3.62 : 4.16, bench ? 'bad' : 'good'), reason: bench ? 'Датчик отсутствует на стенде' : ''}, spRaw: 400, commandRaw: 400, mapVersion: 32, feedbackVersion: 1, bindingReady: true, connectionWriteEnabled: true, mode: bench ? 'stop' : 'auto', counter: 48487, driveConfirmed: !bench && !fault, radio: bench || stale ? 'Нет данных' : '4G · сигнал 26'};
        snapshot.pumps = Array.from({length: station.pumpCount}, (_, i) => ({id: i + 1, state: bench ? (i ? 'unknown' : 'stop') : fault && i === 1 ? 'fault' : i === 0 ? 'run' : 'reserve', frequency: signal(bench ? (i ? null : 0) : i === 0 ? 38.4 : 0, bench && i ? 'unknown' : 'good'), current: signal(bench ? (i ? null : 0) : i === 0 ? 7.8 : 0, bench && i ? 'unknown' : 'good'), fault: signal(fault && i === 1 ? 20 : bench && i ? null : 0, bench && i ? 'unknown' : 'good')}));
        const knownCount = {'station-001':4, 'station-002':3, 'station-003':2, 'station-004':4}[station.id];
        snapshot.pumps = snapshot.pumps.map((pump, i) => i < knownCount ? pump : {id:i+1, state:'unknown', frequency:signal(null,'unknown'), current:signal(null,'unknown'), fault:signal(null,'unknown')});
      }
      snapshots[station.id] = snapshot;
    }
    const alarms = [
      {id: 'a-drive', stationId: 'station-003', severity: 'critical', category: 'drive', text: 'Насос 2 · ошибка ПЧ, код 20 (пример)', active: true, acknowledged: false, at: now - 102000, code: 'Err20'},
      {id: 'a-link', stationId: 'station-004', severity: 'warning', category: 'communication', text: 'Нет свежих данных станции', active: true, acknowledged: false, at: now - 183000, code: 'Связь'},
      {id: 'a-source', stationId: 'station-001', severity: 'info', category: 'quality', text: 'Датчик давления не подключён на стенде', active: true, acknowledged: false, at: now - 720000, code: 'Данные'},
      {id: 'a-history', stationId: 'station-002', severity: 'warning', category: 'process', text: 'Давление ниже предупредительного порога', active: false, acknowledged: true, at: now - 6480000, clearedAt: now - 6300000, code: 'Давление'}
    ].filter(a => catalog.stations.some(s => s.id === a.stationId && hasFixture(s, catalog)));
    return {snapshots, alarms};
  }
  function history(stationId, now) {
    if (!['station-002', 'station-003', 'station-004'].includes(stationId)) return [];
    return Array.from({length: 289}, (_, i) => {
      const ts = now - (288 - i) * 300000, offset = stationId === 'station-003' ? -0.35 : stationId === 'station-004' ? 0.45 : 0;
      const bad = stationId === 'station-004' ? i > 284 : stationId === 'station-002' && i > 234 && i < 239;
      return {ts, pressure: 4 + offset + 0.16 * Math.sin(i / 9) + 0.055 * Math.cos(i / 2.8), setpoint: i < 165 ? 3.8 : 4, frequency: 37 + 3 * Math.sin(i / 12), current: 7.2 + 0.65 * Math.sin(i / 12), quality: bad ? 'bad' : 'good'};
    });
  }
  return {profiles, clone, validateCatalog, readPressure, bindingKey, hasFixture, writeReason, makeDraft, adjustDraft, simulateApply, ackAlarm, segments, csvCell, createFixtures, history};
});
