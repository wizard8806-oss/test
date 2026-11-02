(function () {
  'use strict';
  const M = window.OperatorModel;
  const initial = M.validateCatalog(JSON.parse(document.getElementById('initial-catalog').textContent));
  const storageKey = 'pump-operator-preview:catalog:v1';
  const runtimeKey = 'pump-operator-preview:model:v1';
  let catalog;
  try {catalog = M.validateCatalog(JSON.parse(localStorage.getItem(storageKey)) || initial);} catch (_) {catalog = M.clone(initial);}
  const now = Math.floor(Date.now() / 60000) * 60000;
  let {snapshots, alarms} = M.createFixtures(catalog, now);
  const state = {role: 'operator', group: 'all', search: '', status: 'all', page: 0,
    alarmFilter: 'active', alarmSeverity: 'all', alarmStation: 'all',
    chartStation: 'all', hours: 6, zoom: 100, showSetpoint: true, showExtras: false,
    draft: null, modal: null, modalReturnFocus: null, selectedStation: 'station-001'};
  const view = document.getElementById('view');
  const charts = new Map();
  const h = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = (value, digits = 1) => Number.isFinite(value) ? new Intl.NumberFormat('ru-RU', {minimumFractionDigits: digits, maximumFractionDigits: digits}).format(value) : '—';
  const time = (ts, seconds = false) => new Intl.DateTimeFormat('ru-RU', {timeZone: catalog.timezone, hour: '2-digit', minute: '2-digit', ...(seconds ? {second:'2-digit'} : {})}).format(new Date(ts));
  const day = ts => new Intl.DateTimeFormat('ru-RU', {timeZone: catalog.timezone, day: '2-digit', month: 'long'}).format(new Date(ts));
  const dateTime = ts => day(ts) + ', ' + time(ts, true);
  const stationById = id => catalog.stations.find(s => s.id === id);
  const groupName = id => catalog.groups.find(g => g.id === id)?.name || 'Без группы';
  const actor = () => 'preview-' + state.role;
  const canOperate = () => ['operator', 'engineer'].includes(state.role);
  const canConfigure = () => state.role === 'engineer';
  const historyFor = station => M.hasFixture(station, catalog) ? M.history(station.id, now) : [];
  function readOverlay() {
    try {
      const value = JSON.parse(localStorage.getItem(runtimeKey));
      if (value?.version === 1 && value.commands && typeof value.commands === 'object' && Array.isArray(value.acknowledged)) return value;
    } catch (_) {}
    return {version:1, commands:{}, acknowledged:[]};
  }
  function restoreModel() {
    ({snapshots, alarms} = M.createFixtures(catalog, now));
    const overlay = readOverlay();
    for (const station of catalog.stations) {
      const saved = overlay.commands[station.id], profile = M.profiles[station.profileId];
      if (M.hasFixture(station, catalog) && saved?.binding === M.bindingKey(station) && profile.stepRaw && Number.isInteger(saved.raw) && saved.raw >= profile.minRaw && saved.raw <= profile.maxRaw && saved.raw % profile.stepRaw === 0) {
        Object.assign(snapshots[station.id], {spRaw:saved.raw, commandRaw:saved.raw, driveConfirmed:false});
      }
    }
    alarms = alarms.map(a => overlay.acknowledged.includes(a.id) ? M.ackAlarm(a,'preview-operator',now) : a);
  }
  function storeModel(change) {
    const overlay = readOverlay(); change(overlay);
    try {localStorage.setItem(runtimeKey, JSON.stringify(overlay));}
    catch (_) {toast('Модель изменена только в этом окне: хранилище браузера недоступно.');}
  }
  const colors = ['var(--accent)', 'var(--blue)', 'var(--amber)', 'var(--violet)'];
  const paths = {
    grid:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
    alarm:'M12 3 2 21h20L12 3Zm0 6v5m0 3h.01',
    chart:'M3 3v18h18M6 15l4-5 4 3 6-8',
    settings:'m9 3-1 3-3 1-2 3 2 2-1 3 2 3 3-1 3 1 3-1 3 1 2-3-1-3 2-2-2-3-3-1-1-3H9Zm3 6a3 3 0 1 1 0 6 3 3 0 0 1 0-6Z',
    station:'M3 20V9l9-6 9 6v11H3Zm5-8v8m8-8v8M3 9h18',
    water:'M12 2C9 7 5 10 5 15a7 7 0 0 0 14 0c0-5-4-8-7-13Zm-3 13a3 3 0 0 0 3 3',
    check:'m5 12 4 4L19 6', plus:'M12 5v14M5 12h14',
    link:'m8 12 4-4 4 4-4 4-4-4Zm-4 4a7 7 0 0 1 0-8m16 0a7 7 0 0 1 0 8',
    open:'M14 3h7v7M21 3 10 14M10 3H3v18h18v-7',
    download:'M12 3v12m-5-5 5 5 5-5M3 16v5h18v-5',
    upload:'M12 16V4m-5 5 5-5 5 5M3 16v5h18v-5',
    sun:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 1v3m0 16v3M1 12h3m16 0h3M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2',
    info:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 7v7m0-10h.01',
    close:'m6 6 12 12M6 18 18 6', clock:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v6l4 2'
  };
  const icon = (name, cls = '') => `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.info}"/></svg>`;
  const badge = (text, style = '', dot = false) => `<span class="badge ${style}">${dot ? '<span class="badge-dot"></span>' : ''}${h(text)}</span>`;
  const empty = (title, text, name = 'chart') => `<div class="empty-state">${icon(name)}<h3>${h(title)}</h3><p>${h(text)}</p></div>`;
  const modeName = s => ({auto:'АВТО',stop:'СТОП',manual:'РУЧНОЙ',unknown:'НЕТ ДАННЫХ'}[s?.mode] || 'НЕТ ДАННЫХ');
  const stationHref = (id, tab = 'observation') => '#station/' + encodeURIComponent(id) + '/' + tab;
  function route() {
    const parts = location.hash.slice(1).split('/');
    if (parts[0] === 'station') {
      let id; try {id = decodeURIComponent(parts[1] || '');} catch (_) {id = '';}
      return {page:'station', id, tab:['observation','alarms','charts','settings'].includes(parts[2]) ? parts[2] : 'observation'};
    }
    return {page:['overview','alarms','charts','settings'].includes(parts[0]) ? parts[0] : 'overview'};
  }
  function quality(station) {return M.readPressure(station, snapshots[station.id], now);}
  function stationStatus(station) {
    if (!station.enabled) return {kind:'', text:'Не наблюдается'};
    if (alarms.some(a => a.stationId === station.id && a.active && a.severity === 'critical')) return {kind:'critical', text:'Авария ПЧ'};
    const q = quality(station);
    if (q.state === 'stale') return {kind:'warning', text:'Нет связи'};
    if (q.state === 'unknown') return {kind:'', text:'Ожидает подключения'};
    if (q.state !== 'good') return {kind:'warning', text:'Нет достоверного давления'};
    return {kind:'good', text:'Норма'};
  }
  function freshness(station) {
    const s = snapshots[station.id];
    if (!s?.receivedAt) return 'Нет данных';
    const age = Math.max(0, Math.floor((now - s.receivedAt) / 1000));
    return age < 60 ? age + ' с назад' : Math.floor(age / 60) + ' мин назад';
  }
  function persist() {
    try {localStorage.setItem(storageKey, JSON.stringify(catalog));}
    catch (_) {toast('Изменения сохранены только в этом окне. Экспортируйте каталог в JSON.');}
  }
  let toastTimer;
  function toast(text) {
    const t = document.getElementById('toast'); t.textContent = text; t.classList.add('visible');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('visible'), 6500);
  }
  function renderKeepFocus() {
    const current = document.activeElement, id = current?.id;
    const start = current?.selectionStart, end = current?.selectionEnd;
    render();
    const next = id && document.getElementById(id);
    if (next) {next.focus(); if (typeof start === 'number' && next.setSelectionRange) next.setSelectionRange(start,end);}
  }
  function renderNavigation(r) {
    const count = alarms.filter(a => a.active && !a.acknowledged).length;
    const items = [['overview','grid','Обзор станций'],['alarms','alarm','Аварии и события'],['charts','chart','Графики'],['settings','settings','Настройки']];
    document.getElementById('navigation').innerHTML = items.map(([id, glyph, title]) => `<a href="#${id}" class="${r.page === id || (r.page === 'station' && id === 'overview') ? 'active' : ''}" aria-label="${title}" ${r.page === id ? 'aria-current="page"' : ''}>${icon(glyph)}<span class="nav-label">${title}</span>${id === 'alarms' && count ? `<span class="nav-count">${count}</span>` : ''}</a>`).join('');
    const names = {overview:'Все станции',alarms:'Аварии и события',charts:'Графики',settings:'Настройки'};
    document.getElementById('breadcrumbs').innerHTML = `<div class="breadcrumbs"><span>Диспетчерская</span><span class="chevron">/</span>${r.page === 'station' ? `<a href="#overview">Все станции</a><span class="chevron">/</span><strong>${h(stationById(r.id)?.name || 'Станция не найдена')}</strong>` : `<strong>${names[r.page]}</strong>`}</div>`;
    document.getElementById('theme-toggle').innerHTML = icon('sun');
  }
  function stats(stations) {
    const count = kind => stations.filter(s => stationStatus(s).kind === kind).length;
    const rows = [[stations.length,'Станций в обзоре','station',''],[count('good'),'Без замечаний','check','good'],[count('critical'),'С авариями','alarm','critical'],[stations.filter(s => ['stale','unknown'].includes(quality(s).state)).length,'Без свежих данных','link','warning']];
    return `<div class="kpi-grid">${rows.map(([value,label,glyph,color]) => `<div class="kpi ${color}"><div><div class="eyebrow">${label}</div><div class="kpi-number">${value}</div></div><span class="kpi-icon">${icon(glyph)}</span></div>`).join('')}</div>`;
  }
  function filteredStations() {
    return catalog.stations.filter(s => state.group === 'all' || s.groupId === state.group).filter(s => !state.search || (s.name + ' ' + s.location + ' ' + s.id).toLowerCase().includes(state.search.toLowerCase())).filter(s => state.status === 'all' || (state.status === 'critical' ? stationStatus(s).kind === 'critical' : state.status === 'unavailable' ? ['stale','unknown'].includes(quality(s).state) : stationStatus(s).kind === 'good'));
  }
  function renderOverview() {
    const grouped = catalog.stations.filter(s => state.group === 'all' || s.groupId === state.group);
    const filtered = filteredStations(); state.page = Math.min(state.page, Math.max(0, Math.ceil(filtered.length / 25) - 1));
    const rows = filtered.slice(state.page * 25, state.page * 25 + 25);
    return `<div class="page-heading"><div><h1>Обзор насосных станций</h1><p class="subtitle">Давление, насосы и связь — на одном экране</p></div><div class="actions"><button data-action="go-settings">${icon('settings')}Каталог станций</button><button class="primary" data-action="add-station" ${!canConfigure() ? 'disabled title="Добавление доступно наладчику; смените роль в макете"' : ''}>${icon('plus')}Добавить станцию</button></div></div>
    ${stats(grouped)}<section class="panel"><div class="panel-header"><h2>Станции <span class="subtle">· ${filtered.length}</span></h2><small>Примеры состояний для проверки интерфейса</small></div><div class="toolbar"><input class="search" id="fleet-search" type="search" placeholder="Найти станцию, адрес или ID" aria-label="Поиск станции" value="${h(state.search)}"><select id="fleet-group" aria-label="Группа станций"><option value="all">Все группы</option>${catalog.groups.map(g => `<option value="${h(g.id)}" ${state.group === g.id ? 'selected' : ''}>${h(g.name)}</option>`).join('')}</select><select id="fleet-status" aria-label="Состояние станции">${[['all','Все состояния'],['critical','С авариями'],['unavailable','Без свежих данных'],['good','Без замечаний']].map(([v,t]) => `<option value="${v}" ${state.status === v ? 'selected' : ''}>${t}</option>`).join('')}</select></div><div class="table-wrap"><table data-testid="fleet-table"><thead><tr><th>СТАНЦИЯ</th><th>РЕЖИМ</th><th>ДАВЛЕНИЕ</th><th>УСТАВКА</th><th>НАСОСЫ</th><th>СОСТОЯНИЕ</th><th>ОБНОВЛЕНИЕ</th><th></th></tr></thead><tbody>${rows.map(s => {
      const q = quality(s), snap = snapshots[s.id], status = stationStatus(s);
      const fresh = !['stale','unknown','disabled','bad'].includes(q.state);
      const allPumpsKnown = fresh && snap?.pumps?.length === s.pumpCount && snap.pumps.every(p => p.state !== 'unknown');
      return `<tr data-station-id="${h(s.id)}"><td><div class="station-cell"><span class="station-symbol">${icon('station')}</span><div><a class="station-link" href="${stationHref(s.id)}">${h(s.name)}</a><small>${h(s.location)} · ${h(groupName(s.groupId))}</small></div></div></td><td>${badge(fresh ? modeName(snap) : 'НЕТ ДАННЫХ',fresh && snap?.mode === 'auto' ? 'blue' : '')}</td><td><span class="pressure-value ${q.value === null ? 'invalid' : ''}">${num(q.value)} ${q.value === null ? '' : '<small style="display:inline">бар</small>'}</span><small>${h(q.value === null ? q.reason : 'Источник подтверждён')}</small></td><td>${num(!fresh || snap?.spRaw == null ? null : snap.spRaw / 100)} <span class="subtle">бар</span></td><td><div class="small-pumps" aria-label="${s.pumpCount} насосов">${Array.from({length:s.pumpCount},(_,i) => `<span class="small-pump ${h(fresh ? snap?.pumps?.[i]?.state || 'unknown' : 'unknown')}" title="Насос ${i+1}"></span>`).join('')}</div><small>${allPumpsKnown ? snap.pumps.filter(p => p.state === 'run').length + ' работают / ' + s.pumpCount : 'Нет полных данных'}</small></td><td>${badge(status.text,status.kind,true)}</td><td>${h(freshness(s))}</td><td><button class="icon-button" data-action="open-window" data-id="${h(s.id)}" aria-label="Открыть ${h(s.name)} в отдельном окне">${icon('open')}</button></td></tr>`;
    }).join('') || '<tr><td colspan="8">'+empty('Станции не найдены','Измените фильтр или добавьте станцию в каталоге.','station')+'</td></tr>'}</tbody></table></div><div class="table-footer"><span>Показано ${rows.length} из ${filtered.length} · данные макета</span><div class="actions"><button class="small" data-action="previous-page" ${state.page === 0 ? 'disabled' : ''}>Назад</button><span>${state.page + 1} / ${Math.max(1,Math.ceil(filtered.length/25))}</span><button class="small" data-action="next-page" ${(state.page+1)*25 >= filtered.length ? 'disabled' : ''}>Далее</button></div></div></section>
    <div class="notice info below-note">${icon('info')}<span>Каждая станция открывается в своей карточке или отдельном окне. Аварии и графики доступны как по всему списку, так и по выбранной станции.</span></div>`;
  }
  function stationHeader(station, tab) {
    const snap = snapshots[station.id], status = stationStatus(station), fresh = !['stale','unknown','disabled','bad'].includes(quality(station).state);
    return `<div class="page-heading"><div class="station-banner"><span class="station-symbol">${icon('station')}</span><div><h1>${h(station.name)}</h1><p class="subtitle">${h(station.location)} · ${h(groupName(station.groupId))} · ${h(station.id)}</p><div class="status-strip">${badge(status.text,status.kind,true)}${badge(fresh ? modeName(snap) : 'НЕТ ДАННЫХ',fresh && snap?.mode === 'auto' ? 'blue' : '')}</div></div></div><button data-action="open-window" data-id="${h(station.id)}">${icon('open')}Отдельное окно</button></div><nav class="tabs" aria-label="Разделы станции">${[['observation','Наблюдение'],['alarms','Аварии и события'],['charts','Графики'],['settings','Настройки станции']].map(([id,t]) => `<a href="${stationHref(station.id,id)}" class="${tab === id ? 'active' : ''}" ${tab === id ? 'aria-current="page"' : ''}>${t}</a>`).join('')}</nav>`;
  }
  const pumpGlyph = `<svg class="pump-glyph" viewBox="0 0 64 54" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M2 38h12V20h10V9h18v11h9v18h11M19 45h29M25 45v-7m17 7v-7"/><circle cx="33" cy="28" r="12"/><path d="m27 22 12 12m0-12L27 34"/></svg>`;
  function renderObservation(station) {
    const snap = snapshots[station.id], q = quality(station), fresh = !['stale','unknown','disabled','bad'].includes(q.state);
    const currentSp = fresh && Number.isInteger(snap?.spRaw) ? snap.spRaw / 100 : null;
    const canEdit = !M.writeReason(station, snap, state.role, now);
    const draft = state.draft?.stationId === station.id ? state.draft : null;
    const draftRaw = draft?.raw ?? snap?.spRaw;
    const activeAlarms = alarms.filter(a => a.stationId === station.id && a.active);
    const pumps = Array.from({length:station.pumpCount},(_,i) => snap?.pumps?.[i] || {id:i+1,state:'unknown',frequency:{value:null},current:{value:null},fault:{value:null}});
    return `<div class="station-stats"><article class="metric-card"><div class="metric-top"><span class="eyebrow">Давление</span>${icon('water')}</div><div class="metric-number ${q.value === null ? 'unavailable' : ''}" data-testid="station-pressure">${q.value === null ? 'Нет достоверных данных' : num(q.value)+' <span>бар</span>'}</div><div class="metric-note">${h(q.reason)}</div></article><article class="metric-card"><div class="metric-top"><span class="eyebrow">Общая уставка ПЛК</span>${badge(currentSp === null ? 'Нет данных' : 'Принято ПЛК',currentSp === null ? '' : 'good')}</div><div class="metric-number" data-testid="station-setpoint">${num(currentSp)} <span>бар</span></div><div class="metric-note">${snap?.driveConfirmed && fresh ? 'Подтверждена ведущим ПЧ' : 'Применение ведущим ПЧ не подтверждено'}</div></article><article class="metric-card"><div><div class="eyebrow">Режим станции</div><div class="mode-number">${h(fresh ? modeName(snap) : 'НЕТ ДАННЫХ')}</div></div><div class="metric-note">Физический селектор · состояние передано ПЛК<br>${snap?.mode === 'stop' ? 'Пусковые команды не выдаются' : 'Работа по условиям контроллера'}</div></article></div>
      ${q.value === null ? `<div class="notice warning">${icon('info')}<div>${h(q.reason)}. Недостоверное давление не заменяется нулём.${station.id === 'station-001' ? ' Проверка измерения отложена до подключения калибратора.' : ''}</div></div>` : ''}
      <div class="section-title"><h2>Насосная группа</h2><span class="subtle">${station.pumpCount} насосов · ${M.profiles[station.profileId].name}</span></div>
      <div class="pump-grid">${pumps.map(p => {
        const available = fresh && p.state !== 'unknown';
        const label = available ? ({run:'Работает',reserve:'Резерв',stop:'Остановлен',fault:'Авария'}[p.state] || 'Нет данных') : 'Нет данных';
        const kind = available ? ({run:'good',fault:'critical'}[p.state] || '') : '';
        return `<article class="pump-card ${fresh ? h(p.state) : 'unknown'}"><div class="pump-header"><h3>Насос ${p.id}</h3>${badge(label,kind)}</div>${pumpGlyph}<div class="pump-metrics"><div><small>ЧАСТОТА</small><strong>${num(available && p.frequency?.quality === 'good' ? p.frequency.value : null,1)}</strong> <em>Гц</em></div><div><small>ВЫХОДНОЙ ТОК</small><strong>${num(available && p.current?.quality === 'good' ? p.current.value : null,1)}</strong> <em>А</em></div></div><div class="pump-bottom">${!available || p.fault?.quality !== 'good' ? 'Код ошибки не получен' : p.fault.value === 0 ? 'ПЧ: код ошибки 0' : 'ПЧ: ошибка '+h(p.fault.value)}${p.fault?.value === 20 && available ? ' · пример кода; нужна расшифровка по руководству' : ''}</div></article>`;
      }).join('')}</div>
      <section class="panel" style="margin-top:20px"><div class="panel-body"><div class="control-row"><div><h3>Изменить общую уставку</h3><p class="subtitle">То же значение, которое задаётся с HMI · шаг 0,1 бар</p></div><div class="draft-controls"><button class="step" data-action="draft-minus" data-id="${h(station.id)}" aria-label="Уменьшить уставку" ${!canEdit ? 'disabled' : ''}>−</button><span class="draft-value" data-testid="draft-value">${num(draftRaw == null ? null : draftRaw/100,1)} <small>бар</small></span><button class="step" data-action="draft-plus" data-id="${h(station.id)}" aria-label="Увеличить уставку" ${!canEdit ? 'disabled' : ''}>+</button><button class="primary" data-action="confirm-apply" data-id="${h(station.id)}" ${!canEdit || !draft || draft.raw === draft.baseRaw ? 'disabled' : ''}>Применить</button><button data-action="draft-cancel" ${!draft ? 'disabled' : ''}>Отмена</button></div></div><div class="audit-model">Макет: подтверждение изменяет только модель в браузере. Команда в ПЛК не отправляется.</div></div></section>
      <div class="station-lower"><section class="panel"><div class="panel-header"><h2>События станции</h2><a href="${stationHref(station.id,'alarms')}">Все события →</a></div><div class="panel-body">${activeAlarms.map(a => `<div class="event-item"><time>${time(a.at)}</time><span class="severity-mark ${a.severity}">${icon(a.severity === 'info' ? 'info' : 'alarm')}</span><span>${h(a.text)}<br><small class="subtle">${a.acknowledged ? 'Подтверждено оператором' : 'Не подтверждено'}</small></span></div>`).join('') || '<div class="muted">Активных событий нет</div>'}</div></section><section class="panel"><div class="panel-header"><h2>Данные и связь</h2></div><div class="panel-body"><div class="dl-row"><span>Обновление ПЛК</span><strong>${h(freshness(station))}</strong></div><div class="dl-row"><span>Достоверность давления</span><strong>${q.state === 'good' ? 'Подтверждена' : 'Не подтверждена'}</strong></div><div class="dl-row"><span>Модем · отдельный канал</span><strong>${h(snap?.radio || 'Нет данных')}</strong></div><div class="dl-row"><span>История давления</span><a href="${stationHref(station.id,'charts')}">Открыть графики →</a></div></div></section></div>`;
  }
  function renderAlarms(station) {
    const selected = station?.id || state.alarmStation;
    const filtered = alarms.filter(a => selected === 'all' || a.stationId === selected).filter(a => state.alarmSeverity === 'all' || a.severity === state.alarmSeverity).filter(a => state.alarmFilter === 'all' || (state.alarmFilter === 'active' ? a.active : state.alarmFilter === 'unack' ? !a.acknowledged : !a.active));
    const head = station ? '' : `<div class="page-heading"><div><h1>Аварии и события</h1><p class="subtitle">Общая лента всех станций · подтверждение не устраняет причину аварии</p></div>${badge(alarms.filter(a=>a.active&&!a.acknowledged).length+' не подтверждено','warning')}</div>`;
    return `${head}<section class="panel"><div class="toolbar"><select id="alarm-filter" aria-label="Состояние события">${[['active','Активные'],['unack','Неподтверждённые'],['all','Все события'],['history','Снятые']].map(([v,t])=>`<option value="${v}" ${state.alarmFilter===v?'selected':''}>${t}</option>`).join('')}</select><select id="alarm-severity" aria-label="Важность события">${[['all','Любая важность'],['critical','Аварии'],['warning','Предупреждения'],['info','Информация']].map(([v,t])=>`<option value="${v}" ${state.alarmSeverity===v?'selected':''}>${t}</option>`).join('')}</select>${station ? '' : `<select id="alarm-station" aria-label="Станция событий"><option value="all">Все станции</option>${catalog.stations.map(s=>`<option value="${h(s.id)}" ${selected===s.id?'selected':''}>${h(s.name)}</option>`).join('')}</select>`}<span class="subtle" style="margin-left:auto;font-size:11px">${day(now)} · МСК</span></div><div class="table-wrap"><table data-testid="alarm-table"><thead><tr><th></th><th>ВРЕМЯ</th><th>СТАНЦИЯ</th><th>СОБЫТИЕ</th><th>СОСТОЯНИЕ</th><th>ПОДТВЕРЖДЕНИЕ</th></tr></thead><tbody>${filtered.map(a=>`<tr class="alarm-row ${a.acknowledged?'acknowledged':''} ${!a.active?'cleared':''}" data-alarm-id="${h(a.id)}"><td><span class="severity-mark ${a.severity}">${icon(a.severity==='info'?'info':'alarm')}</span></td><td>${time(a.at,true)}<small>${day(a.at)}</small></td><td><a href="${stationHref(a.stationId)}" class="station-link">${h(stationById(a.stationId)?.name||a.stationId)}</a></td><td class="alarm-text">${h(a.text)}<small>${h(a.code)} · ${h({drive:'Частотный преобразователь',communication:'Связь',quality:'Достоверность данных',process:'Процесс'}[a.category]||'Событие')}</small></td><td>${badge(a.active?'Активно':'Снято',a.active?a.severity==='critical'?'critical':a.severity==='warning'?'warning':'blue':'')}</td><td>${a.acknowledged?`<span class="muted">${icon('check')} Подтверждено</span>`:`<button class="small" data-action="ack-alarm" data-id="${h(a.id)}" ${!canOperate()?'disabled':''}>Подтвердить</button>`}</td></tr>`).join('')||'<tr><td colspan="6">'+empty('Подходящих событий нет','Измените фильтры или выберите другую станцию.','check')+'</td></tr>'}</tbody></table></div><div class="table-footer"><span>${filtered.length} событий · причины и подтверждения хранятся раздельно</span><span>Данные макета</span></div></section><div class="notice info below-note">${icon('info')}<span>Подтверждённая авария остаётся активной до снятия её причины. Потеря связи и недостоверное давление показываются отдельно от кодов ошибок ПЧ.</span></div>`;
  }
  function chartSvg(series, title, unit, id) {
    const from = now - state.hours * 3600000 * state.zoom / 100, to = now;
    const valid = series.flatMap(s=>s.points.filter(p=>p.ts>=from&&p.ts<=to&&p.quality==='good'&&Number.isFinite(p.value)).map(p=>p.value));
    if (!valid.length) return `<div class="chart-no-data">${empty('История ещё не подключена','Здесь появятся архивные значения выбранной станции. Отсутствующие и недостоверные точки не рисуются нулём.','chart')}</div>`;
    const min = Math.max(0,Math.floor((Math.min(...valid)-0.35)*2)/2), max = Math.max(min+1,Math.ceil((Math.max(...valid)+0.35)*2)/2);
    const W=1000,H=260,L=53,R=20,T=20,B=35,x=t=>L+(t-from)/(to-from)*(W-L-R),y=v=>T+(max-v)/(max-min)*(H-T-B);
    let body='';
    for(let n=0;n<=4;n++){const value=min+(max-min)*n/4,py=y(value);body+=`<path class="chart-grid" d="M${L} ${py}H${W-R}"/><text class="chart-axis" x="${L-10}" y="${py+4}" text-anchor="end">${h(num(value,1))}</text>`;}
    for(let n=0;n<=6;n++){const ts=from+(to-from)*n/6;body+=`<text class="chart-axis" x="${x(ts)}" y="${H-10}" text-anchor="middle">${time(ts)}</text>`;}
    body+=`<text class="chart-axis" x="${L}" y="12">${h(unit)}</text>`;
    for(const s of series){for(const part of M.segments(s.points,from,to)){const d=part.map((p,i)=>(i?'L':'M')+x(p.ts).toFixed(2)+' '+y(p.value).toFixed(2)).join(' ');body+=`<path class="chart-path" d="${d}" stroke="${s.color}" ${s.dashed?'stroke-dasharray="6 5"':''}/>`;}}
    charts.set(id,{series,from,to,title,unit});
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" data-chart="${id}" tabindex="0" role="img" aria-label="${h(title)}. Наведите курсор или используйте стрелки для просмотра значений.">${body}<path class="chart-cursor" d="M0 0v0" style="display:none"/></svg>`;
  }
  function chartContext(station) {
    const id=station?.id||state.chartStation;
    return {id,stations:id==='all'?catalog.stations.filter(s=>s.enabled):catalog.stations.filter(s=>s.id===id)};
  }
  function renderCharts(station) {
    const ctx=chartContext(station),series=[];
    ctx.stations.forEach((s,i)=>{
      const rows=historyFor(s);
      series.push({name:s.name,color:colors[i%colors.length],points:rows.map(r=>({ts:r.ts,value:r.pressure,quality:r.quality}))});
      if(ctx.id!=='all'&&state.showSetpoint) series.push({name:'Уставка',color:'var(--blue)',dashed:true,points:rows.map(r=>({ts:r.ts,value:r.setpoint,quality:r.quality}))});
    });
    const first=ctx.stations[0],rows=ctx.id!=='all'&&first?historyFor(first):[];
    return `${station?'':`<div class="page-heading"><div><h1>Графики</h1><p class="subtitle">Архив давления и параметров насосов · сравнение станций</p></div><button data-action="export-csv" ${!ctx.stations.some(s=>historyFor(s).length)?'disabled':''}>${icon('download')}Экспорт CSV</button></div>`}
      <section class="panel"><div class="panel-header"><div><h2>Давление${ctx.id==='all'?' · сравнение станций':''}</h2><p class="subtitle">${day(now)} · разрывы соответствуют отсутствию достоверных данных</p></div><div class="chart-toolbar">${station?'':`<select id="chart-station" aria-label="Станция графика"><option value="all">Все станции · сравнение</option>${catalog.stations.map(s=>`<option value="${h(s.id)}" ${ctx.id===s.id?'selected':''}>${h(s.name)}</option>`).join('')}</select>`}<div class="segmented" aria-label="Период графика">${[1,6,24].map(n=>`<button data-action="chart-range" data-hours="${n}" class="${state.hours===n?'active':''}">${n} ч</button>`).join('')}</div></div></div><div class="panel-body"><div class="chart-legend">${series.map(s=>`<span><i class="legend-line ${s.dashed?'dashed':''}" style="background:${s.dashed?'transparent':s.color}"></i>${h(s.name)}${!s.points.length?' · нет архива':''}</span>`).join('')}</div>${chartSvg(series,'Давление','бар','pressure')}<div class="chart-fine"><span>Архив макета · МСК</span><label>Масштаб времени <input type="range" class="zoom-range" id="chart-zoom" min="10" max="100" step="10" value="${state.zoom}" aria-label="Масштаб времени графика"></label></div>${ctx.id!=='all'?`<div class="chart-legend"><label><input type="checkbox" id="chart-setpoint" ${state.showSetpoint?'checked':''}> Уставка на графике</label><label><input type="checkbox" id="chart-extras" ${state.showExtras?'checked':''}> Частота и ток насоса 1</label></div>`:''}</div></section>
      ${ctx.id!=='all'&&state.showExtras?`<div class="chart-extra-grid">${[['frequency','Частота насоса 1','Гц','#51c8b2'],['current','Ток насоса 1','А','#c4a1ef']].map(([key,title,unit,color])=>`<section class="panel"><div class="panel-header"><h3>${title}</h3></div><div class="panel-body">${chartSvg([{name:title,color,points:rows.map(r=>({ts:r.ts,value:r[key],quality:r.quality}))}],title,unit,key)}</div></section>`).join('')}</div>`:''}
      <p class="chart-note">В макете архив заполнен только у станций-примеров. Для стенда реальное архивирование технологических значений ещё не подтверждено. Графики не восстанавливают отсутствующую историю.</p>`;
  }
  function stationFields(station, isNew) {
    const s=station||{id:nextId(),name:'',location:'',groupId:catalog.groups[0].id,profileId:'fatek-900g',pumpCount:1,connectionId:catalog.connections[0].id,itemPrefix:nextPrefix(),enabled:true,controlEnabled:false,limits:{pressureLow:2,pressureHigh:6,staleSeconds:15}};
    const disabled=!canConfigure()?'disabled':'';
    return `<div class="form-grid"><label>Название станции<input name="name" id="setting-name" required maxlength="120" value="${h(s.name)}" ${disabled}></label><label>Постоянный ID<input name="id" id="setting-id" required pattern="[a-z](?:[a-z0-9]|-){1,47}" value="${h(s.id)}" ${!isNew?'readonly':''} ${disabled}><small>ID не зависит от TCP-порта и названия.</small></label><label class="wide">Адрес / расположение<input name="location" maxlength="180" value="${h(s.location)}" ${disabled}></label><label>Группа<select name="groupId" ${disabled}>${catalog.groups.map(g=>`<option value="${h(g.id)}" ${g.id===s.groupId?'selected':''}>${h(g.name)}</option>`).join('')}</select></label><label>Профиль оборудования<select name="profileId" id="setting-profile" ${disabled}>${Object.entries(M.profiles).map(([id,p])=>`<option value="${id}" ${id===s.profileId?'selected':''}>${p.name}</option>`).join('')}</select></label><label>Количество насосов<input name="pumpCount" id="setting-pumps" type="number" min="1" max="${M.profiles[s.profileId].maxPumps}" value="${s.pumpCount}" required ${disabled}><small>Карточки строятся по составу станции.</small></label><label>Профиль подключения<select name="connectionId" ${disabled}>${catalog.connections.map(c=>`<option value="${h(c.id)}" ${c.id===s.connectionId?'selected':''}>${h(c.name)}</option>`).join('')}</select></label><label class="wide">Префикс адресов станции<input name="itemPrefix" id="setting-prefix" required maxlength="140" value="${h(s.itemPrefix)}" ${disabled}><small>Например codex.Device2. Добавление в каталог не создаёт OPC-теги автоматически.</small></label><label>Нижний порог давления, бар<input name="pressureLow" type="number" min="0" max="99" step="0.1" value="${s.limits.pressureLow}" required ${disabled}></label><label>Верхний порог давления, бар<input name="pressureHigh" type="number" min="0.1" max="100" step="0.1" value="${s.limits.pressureHigh}" required ${disabled}></label><label>Данные устарели через, с<input name="staleSeconds" type="number" min="5" max="300" step="1" value="${s.limits.staleSeconds}" required ${disabled}></label><div></div><label class="check-label"><input type="checkbox" name="enabled" ${s.enabled?'checked':''} ${disabled}> Включить в наблюдение</label><label class="check-label"><input type="checkbox" name="controlEnabled" ${s.controlEnabled?'checked':''} ${disabled}> Показывать ввод уставки</label><small class="wide">Пороги и каталог относятся к отображению. Эти настройки макета не изменяют параметры ПЛК, привода, БД и работающей SCADA.</small></div>`;
  }
  function renderSettings(station) {
    const readonly=!canConfigure();
    if(station) return `<div class="settings-layout"><section class="panel"><div class="panel-header"><h2>Параметры станции</h2>${badge(readonly?'Просмотр':'Наладчик',readonly?'':'blue')}</div><div class="panel-body"><form id="station-settings" data-id="${h(station.id)}">${stationFields(station,false)}<div class="form-error" id="settings-error" role="alert"></div><div class="form-actions"><button type="submit" class="primary" ${readonly?'disabled':''}>Сохранить настройки</button></div></form></div></section><aside class="panel settings-note"><h3>Один каталог — все окна</h3><p>Название, группа, состав насосов и привязки используются общей диспетчерской и отдельной карточкой.</p><p>Редактирование доступно наладчику. В этом макете роль выбирается в верхней панели и не является системой авторизации.</p><p>Пароли хранятся отдельно от каталога.</p></aside></div>`;
    return `<div class="page-heading"><div><h1>Настройки диспетчерской</h1><p class="subtitle">Каталог станций, группы и профили оборудования</p></div><div class="actions"><button data-action="export-catalog">${icon('download')}Экспорт каталога</button><button data-action="import-catalog" ${readonly?'disabled':''}>${icon('upload')}Импорт JSON</button><button class="primary" data-action="add-station" ${readonly?'disabled':''}>${icon('plus')}Добавить станцию</button></div></div>
      ${readonly?`<div class="notice info" style="margin-bottom:18px">${icon('info')}<span>Вы просматриваете настройки. Для изменения выберите роль <strong>«Наладчик»</strong> в верхней панели макета. Реальные пользователи SCADA не изменяются.</span></div>`:''}
      <section class="panel"><div class="panel-header"><h2>Каталог станций <span class="subtle">· ${catalog.stations.length}</span></h2><small>Новая станция появляется во всех списках без новой страницы</small></div><div class="table-wrap"><table data-testid="catalog-table"><thead><tr><th>СТАНЦИЯ / ID</th><th>ГРУППА</th><th>ОБОРУДОВАНИЕ</th><th>ПРИВЯЗКА</th><th></th></tr></thead><tbody>${catalog.stations.map(s=>`<tr><td><a href="${stationHref(s.id,'settings')}" class="station-link">${h(s.name)}</a><small class="mono">${h(s.id)}</small></td><td>${h(groupName(s.groupId))}</td><td>${M.profiles[s.profileId].name}<small>${s.pumpCount} насосов</small></td><td><span class="mono">${h(s.itemPrefix)}</span><small>${h(catalog.connections.find(c=>c.id===s.connectionId)?.name)}</small></td><td><a href="${stationHref(s.id,'settings')}">${readonly?'Просмотр':'Настроить'} →</a></td></tr>`).join('')}</tbody></table></div></section>
      <div class="station-lower"><section class="panel"><div class="panel-header"><h2>Группы</h2><button class="small" data-action="add-group" ${readonly?'disabled':''}>${icon('plus')}Добавить</button></div><div class="panel-body">${catalog.groups.map(g=>`<div class="dl-row"><strong>${h(g.name)}</strong><span>${catalog.stations.filter(s=>s.groupId===g.id).length} станций</span></div>`).join('')}</div></section><section class="panel"><div class="panel-header"><h2>Принцип добавления</h2></div><div class="panel-body"><div class="event-item"><strong>1</strong><span>Добавить ID, название и группу</span></div><div class="event-item"><strong>2</strong><span>Выбрать профиль, состав насосов и привязки</span></div><div class="event-item"><strong>3</strong><span>Проверить качество данных и команды перед вводом в работу</span></div></div></section></div><div class="notice info below-note">${icon('info')}<span>Каталог хранит параметры интерфейса. Ключи групп модемов, пароли операторов и БД в JSON не включаются. Новая станция сначала отображается как «Ожидает подключения».</span></div><input type="file" id="catalog-file" accept="application/json,.json" hidden>`;
  }
  function nextId() {let n=1;while(catalog.stations.some(s=>s.id==='station-'+String(n).padStart(3,'0')))n++;return 'station-'+String(n).padStart(3,'0');}
  function nextPrefix() {let n=1;while(catalog.stations.some(s=>s.connectionId===catalog.connections[0].id&&s.itemPrefix.toLowerCase()===('codex.Device'+n).toLowerCase()))n++;return 'codex.Device'+n;}
  function render() {
    charts.clear(); document.getElementById('chart-tooltip').style.display='none';
    const r=route();renderNavigation(r);
    if(r.page==='station'){
      const station=stationById(r.id);
      if(!station){view.innerHTML=empty('Станция не найдена','Вернитесь в общий обзор или проверьте каталог.','station');return;}
      state.selectedStation=station.id;
      view.innerHTML=stationHeader(station,r.tab)+({observation:()=>renderObservation(station),alarms:()=>renderAlarms(station),charts:()=>renderCharts(station),settings:()=>renderSettings(station)}[r.tab])();
    }else view.innerHTML=({overview:renderOverview,alarms:()=>renderAlarms(),charts:()=>renderCharts(),settings:()=>renderSettings()}[r.page])();
  }
  function closeModal() {document.getElementById('modal-root').innerHTML='';state.modal=null;state.modalReturnFocus?.focus();}
  function openModal(title,body,kind) {
    state.modalReturnFocus=document.activeElement;state.modal=kind;
    document.getElementById('modal-root').innerHTML=`<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true" aria-label="${h(title)}"><div class="modal-header"><h2>${h(title)}</h2><button class="icon-button" data-action="close-modal" aria-label="Закрыть">${icon('close')}</button></div><div class="modal-body">${body}</div></section></div>`;
    setTimeout(()=>(document.querySelector('.modal input:not([disabled])')||document.querySelector('.modal button'))?.focus(),0);
  }
  function saveStation(form,isNew) {
    const data=new FormData(form),existing=stationById(form.dataset.id);
    const s={id:String(data.get('id')).trim(),name:String(data.get('name')).trim(),location:String(data.get('location')).trim(),groupId:String(data.get('groupId')),profileId:String(data.get('profileId')),pumpCount:Number(data.get('pumpCount')),connectionId:String(data.get('connectionId')),itemPrefix:String(data.get('itemPrefix')).trim(),enabled:data.has('enabled'),controlEnabled:data.has('controlEnabled'),limits:{pressureLow:Number(data.get('pressureLow')),pressureHigh:Number(data.get('pressureHigh')),staleSeconds:Number(data.get('staleSeconds'))}};
    if(!canConfigure())throw new Error('Изменение доступно наладчику.');
    if(!isNew&&s.id!==existing?.id)throw new Error('Постоянный ID нельзя изменить.');
    const next=M.clone(catalog);
    if(isNew)next.stations.push(s);else next.stations[next.stations.findIndex(x=>x.id===s.id)]=s;
    catalog=M.validateCatalog(next);
    restoreModel();
    if(state.draft?.stationId===s.id){state.draft=null;}
    persist();closeModal();render();toast(isNew?'Станция добавлена в макет. До подключения данные остаются неизвестными.':'Настройки макета сохранены. Оборудование не изменялось.');
  }
  function download(name,body,type) {
    const url=URL.createObjectURL(new Blob([body],{type})),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function exportCsv() {
    const r=route(),ctx=chartContext(r.page==='station'?stationById(r.id):null),from=now-state.hours*3600000*state.zoom/100;
    const lines=[['source','station_id','station','time_utc','pressure_bar','setpoint_bar','frequency_hz','current_a','quality']];
    for(const s of ctx.stations)for(const p of historyFor(s).filter(p=>p.ts>=from))lines.push(['INTERFACE_PREVIEW',s.id,s.name,new Date(p.ts).toISOString(),...(p.quality==='good'?[p.pressure.toFixed(3),p.setpoint,p.frequency.toFixed(2),p.current.toFixed(2)]:['','','','']),p.quality]);
    download('model-trends.csv','\ufeff'+lines.map(row=>row.map(M.csvCell).join(';')).join('\r\n'),'text/csv;charset=utf-8');
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
    const action=button.dataset.action,station=stationById(button.dataset.id);
    try {
      if(action==='theme'){document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark';try{localStorage.setItem('pump-preview-theme',document.documentElement.dataset.theme);}catch(_){}return;}
      if(action==='go-settings'){location.hash='#settings';return;}
      if(action==='close-modal'){closeModal();return;}
      if(action==='open-window'){const u=new URL(location.href);u.searchParams.set('standalone','1');u.hash=stationHref(station.id);window.open(u.href,'pump_station_'+station.id);return;}
      if(action==='previous-page'||action==='next-page'){state.page+=action==='next-page'?1:-1;render();return;}
      if(action==='add-station'){if(!canConfigure())return;openModal('Добавить станцию',`<form id="new-station">${stationFields(null,true)}<div class="form-error" id="new-station-error" role="alert"></div><div class="form-actions"><button type="button" data-action="close-modal">Отмена</button><button type="submit" class="primary">Добавить в каталог</button></div></form>`,'new-station');return;}
      if(action==='add-group'){if(!canConfigure())return;openModal('Новая группа',`<form id="new-group"><div class="form-grid"><label>Название<input name="name" required maxlength="120"></label><label>ID группы<input name="id" required pattern="[a-z](?:[a-z0-9]|-){1,47}" placeholder="district-west"></label></div><div class="form-error" id="group-error" role="alert"></div><div class="form-actions"><button type="button" data-action="close-modal">Отмена</button><button type="submit" class="primary">Добавить группу</button></div></form>`,'new-group');return;}
      if(action==='draft-plus'||action==='draft-minus'){const s=snapshots[station.id];state.draft=M.adjustDraft(station,state.draft?.stationId===station.id?state.draft:M.makeDraft(station,s,actor()),action==='draft-plus'?10:-10);render();return;}
      if(action==='draft-cancel'){state.draft=null;render();return;}
      if(action==='confirm-apply'){if(!state.draft||!canOperate())return;openModal('Подтвердить уставку',`<p>${h(station.name)}</p><div class="confirm-value">${num(state.draft.baseRaw/100)}<span>→</span>${num(state.draft.raw/100)} бар</div><p>Будет изменена общая уставка выбранной станции. В этом макете действие выполняется только в модели браузера.</p><div class="form-actions"><button data-action="close-modal">Отмена</button><button class="primary" data-action="apply-model" data-id="${h(station.id)}">Подтвердить в макете</button></div>`,'apply');return;}
      if(action==='apply-model'){snapshots[station.id]=M.simulateApply(station,snapshots[station.id],state.draft,actor(),state.role,now);storeModel(o=>{o.commands[station.id]={binding:M.bindingKey(station),raw:snapshots[station.id].spRaw};});state.draft=null;closeModal();render();toast('Уставка изменена в модели макета. Команда оборудованию не отправлялась.');return;}
      if(action==='ack-alarm'){if(!canOperate())return;alarms=alarms.map(a=>a.id===button.dataset.id?M.ackAlarm(a,actor(),now):a);storeModel(o=>{if(!o.acknowledged.includes(button.dataset.id))o.acknowledged.push(button.dataset.id);});render();toast('Подтверждено в макете. Активная причина аварии не снимается.');return;}
      if(action==='chart-range'){state.hours=Number(button.dataset.hours);state.zoom=100;render();return;}
      if(action==='export-catalog'){download('station-catalog.json',JSON.stringify(catalog,null,2),'application/json');toast('Экспортирован каталог интерфейса. Демонстрационная телеметрия и пароли в него не входят.');return;}
      if(action==='import-catalog'){if(canConfigure())document.getElementById('catalog-file')?.click();return;}
      if(action==='export-csv'){exportCsv();return;}
    }catch(error){toast(error.message);}
  });
  document.addEventListener('submit',event=>{
    if(!['new-station','station-settings','new-group'].includes(event.target.getAttribute('id')))return;
    event.preventDefault();const form=event.target,formId=form.getAttribute('id');
    try {
      if(formId==='new-group'){
        if(!canConfigure())return;const data=new FormData(form),next=M.clone(catalog);next.groups.push({id:String(data.get('id')).trim(),name:String(data.get('name')).trim()});catalog=M.validateCatalog(next);persist();closeModal();render();toast('Группа добавлена в каталог макета.');
      }else saveStation(form,formId==='new-station');
    }catch(error){const id=formId==='new-station'?'new-station-error':formId==='new-group'?'group-error':'settings-error';document.getElementById(id).textContent=error.message;}
  });
  document.addEventListener('input',event=>{
    if(event.target.id==='fleet-search'){state.search=event.target.value;state.page=0;renderKeepFocus();}
    if(event.target.id==='chart-zoom'){state.zoom=Number(event.target.value);renderKeepFocus();}
  });
  document.addEventListener('change',async event=>{
    const el=event.target;
    if(el.id==='role-select'){state.role=el.value;state.draft=null;closeModal();render();return;}
    const fields={'fleet-group':'group','fleet-status':'status','alarm-filter':'alarmFilter','alarm-severity':'alarmSeverity','alarm-station':'alarmStation','chart-station':'chartStation'};
    if(fields[el.id]){state[fields[el.id]]=el.value;state.page=0;renderKeepFocus();return;}
    if(el.id==='chart-setpoint'||el.id==='chart-extras'){state[el.id==='chart-setpoint'?'showSetpoint':'showExtras']=el.checked;renderKeepFocus();return;}
    if(el.id==='setting-profile'){const p=M.profiles[el.value],input=el.form.elements.pumpCount;input.max=p.maxPumps;if(Number(input.value)>p.maxPumps)input.value=p.maxPumps;if(!p.stepRaw)el.form.elements.controlEnabled.checked=false;return;}
    if(el.id==='catalog-file'&&el.files[0]){
      try {
        if(!canConfigure())return;
        if(el.files[0].size>1048576)throw new Error('Каталог должен быть меньше 1 МБ.');
        const next=M.validateCatalog(JSON.parse(await el.files[0].text()));catalog=next;restoreModel();state.draft=null;state.group='all';state.search='';state.chartStation='all';state.alarmStation='all';persist();render();toast('Каталог импортирован в макет. Новые станции ожидают подключения.');
      }catch(error){toast('Импорт отклонён: '+error.message);el.value='';}
    }
  });
  function showChartTooltip(svg,fraction,clientX,clientY) {
    fraction=Math.max(0,Math.min(1,fraction));
    const context=charts.get(svg.dataset.chart);if(!context)return;
    const at=context.from+(context.to-context.from)*Math.max(0,Math.min(1,fraction));
    const t=document.getElementById('chart-tooltip');
    const rows=context.series.map(s=>{
      const points=s.points.filter(p=>p.ts>=context.from&&p.ts<=context.to);if(!points.length)return '';
      const p=points.reduce((best,p)=>Math.abs(p.ts-at)<Math.abs(best.ts-at)?p:best,points[0]);
      return `<div><span><i class="legend-line" style="background:${s.color};width:10px"></i>${h(s.name)}</span><b>${p.quality==='good'?num(p.value):'—'} ${h(context.unit)}</b></div>`;
    }).join('');
    t.innerHTML=`<strong>${h(dateTime(at))} · МСК</strong>${rows}<small class="subtle">Модельные архивные точки</small>`;t.style.display='block';t.style.left=Math.max(8,Math.min(innerWidth-t.offsetWidth-12,clientX+14))+'px';t.style.top=Math.max(36,Math.min(innerHeight-t.offsetHeight-12,clientY+16))+'px';
    const p=svg.querySelector('.chart-cursor'),x=53+(1000-53-20)*fraction;p.style.display='';p.setAttribute('d',`M${x} 20V225`);
  }
  document.addEventListener('pointermove',event=>{const svg=event.target.closest('svg[data-chart]');if(!svg)return;const r=svg.getBoundingClientRect();const fraction=((event.clientX-r.left)/r.width*1000-53)/(1000-53-20);showChartTooltip(svg,fraction,event.clientX,event.clientY);});
  document.addEventListener('pointerout',event=>{const svg=event.target.closest('svg[data-chart]');if(svg&&!svg.contains(event.relatedTarget)){document.getElementById('chart-tooltip').style.display='none';svg.querySelector('.chart-cursor')?.style.setProperty('display','none');}});
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&state.modal){closeModal();return;}
    if(state.modal&&event.key==='Tab'){
      const controls=[...document.querySelectorAll('.modal button:not([disabled]),.modal input:not([disabled]),.modal select:not([disabled])')].filter(x=>x.offsetParent!==null);
      if(controls.length&&event.shiftKey&&document.activeElement===controls[0]){event.preventDefault();controls.at(-1).focus();}
      else if(controls.length&&!event.shiftKey&&document.activeElement===controls.at(-1)){event.preventDefault();controls[0].focus();}
    }
    const svg=event.target.closest?.('svg[data-chart]');if(svg&&['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();const f=Math.max(0,Math.min(1,Number(svg.dataset.cursor||0.5)+(event.key==='ArrowRight'?0.04:-0.04)));svg.dataset.cursor=f;const r=svg.getBoundingClientRect();showChartTooltip(svg,f,r.left+r.width*f,r.top+r.height/2);}
  });
  window.addEventListener('hashchange',()=>{const r=route();if(state.draft&&(r.page!=='station'||r.id!==state.draft.stationId)){state.draft=null;toast('Черновик уставки отменён при смене станции. Записи не было.');}closeModal();render();window.scrollTo(0,0);view.focus({preventScroll:true});});
  window.addEventListener('storage',event=>{
    if (![storageKey,runtimeKey,null].includes(event.key)) return;
    try {catalog=M.validateCatalog(JSON.parse(localStorage.getItem(storageKey))||initial);} catch (_) {return;}
    restoreModel();
    if (state.draft) {state.draft=null;toast('Данные обновились в другом окне. Черновик отменён; выберите уставку заново.');}
    closeModal();render();
  });
  if(new URLSearchParams(location.search).get('standalone')==='1')document.body.classList.add('standalone');
  try{document.documentElement.dataset.theme=localStorage.getItem('pump-preview-theme')||'dark';}catch(_){}
  restoreModel();render();
})();
