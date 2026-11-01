const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const M = require('./model.js');
const catalog = JSON.parse(fs.readFileSync(path.join(__dirname, 'catalog.json'), 'utf8'));
const now = Date.UTC(2026,10,1,20);
const station = catalog.stations[0];
const fixture = () => M.createFixtures(catalog, now).snapshots[station.id];

test('catalog supports different pump counts and stable identities', () => {
  const result = M.validateCatalog(catalog);
  assert.deepEqual(result.stations.map(s => s.pumpCount), [4,3,2,4]);
  const changed = M.clone(catalog); changed.stations[0].name = 'Новое название';
  assert.equal(M.validateCatalog(changed).stations[0].id, 'station-001');
});
test('duplicate IDs, duplicate physical endpoints and duplicate bindings are rejected', () => {
  for (const mutate of [c=>c.stations[1].id=c.stations[0].id,
                        c=>c.connections.push({...c.connections[0],id:'alias'}),
                        c=>{c.stations[1].connectionId=c.stations[0].connectionId;c.stations[1].itemPrefix=c.stations[0].itemPrefix;}]) {
    const c=M.clone(catalog);mutate(c);assert.throws(()=>M.validateCatalog(c));
  }
});
test('secrets, unsupported profiles and invalid bounds fail before import', () => {
  for (const mutate of [c=>c.password='PRIVATE_FIXTURE',c=>c.stations[0].token='PRIVATE_FIXTURE',
                        c=>c.connections[0].computer='user:password@host',c=>c.stations[0].pumpCount=5,
                        c=>c.stations[0].limits.pressureHigh=1,c=>c.stations[0].limits.staleSeconds=0,
                        c=>c.stations[0].profileId='unknown']) {
    const c=M.clone(catalog);mutate(c);assert.throws(()=>M.validateCatalog(c));
  }
});
test('valid zero is visible; missing source, bad quality, unconfirmed freshness and stale values are not zero', () => {
  const snap=fixture();snap.sourceValid=true;snap.pressure={value:0,quality:'good'};
  assert.equal(M.readPressure(station,snap,now).value,0);
  for (const patch of [{sourceValid:false},{quality:'bad'},{routeFresh:false},{receivedAt:now-16000},{receivedAt:now+1000}]) {
    assert.equal(M.readPressure(station,{...snap,...patch},now).value,null);
  }
});
test('editing a draft changes neither setpoint nor another station', () => {
  const snap=fixture();const draft=M.adjustDraft(station,M.makeDraft(station,snap,'operator'),10);
  assert.equal(snap.spRaw,400);assert.equal(draft.raw,410);
  assert.throws(()=>M.simulateApply(catalog.stations[1],snap,draft,'operator','operator',now));
  assert.throws(()=>M.simulateApply({...station,itemPrefix:'codex.Other'},snap,draft,'operator','operator',now));
  assert.throws(()=>M.simulateApply(station,snap,draft,'other','operator',now));
});
test('stored setpoint can be adjusted in STOP without a pressure sensor; only the mock snapshot changes', () => {
  const snap=fixture();const draft=M.adjustDraft(station,M.makeDraft(station,snap,'operator'),10);
  const next=M.simulateApply(station,snap,draft,'operator','operator',now);
  assert.equal(next.spRaw,410);assert.equal(next.commandRaw,410);assert.equal(snap.spRaw,400);
  assert.equal(next.sourceValid,false);assert.equal(next.mode,'stop');assert.equal(next.driveConfirmed,false);
});
test('stale draft, readonly connection, missing map/feedback and viewer cannot apply', () => {
  const snap=fixture(),draft=M.adjustDraft(station,M.makeDraft(station,snap,'operator'),10);
  for (const patch of [{spRaw:420,commandRaw:420},{connectionWriteEnabled:false},{bindingReady:false},
                       {commandRaw:390},{mapVersion:31},{feedbackVersion:0},{routeFresh:false},
                       {quality:'bad'},{receivedAt:now-20000}]) {
    assert.throws(()=>M.simulateApply(station,{...snap,...patch},draft,'operator','operator',now));
  }
  assert.throws(()=>M.simulateApply(station,snap,draft,'operator','viewer',now));
});
test('out-of-range/unaligned values and unchanged target are rejected', () => {
  const snap=fixture(),draft=M.makeDraft(station,snap,'operator');
  for (const raw of [0,1200,405,400]) assert.throws(()=>M.simulateApply(station,snap,{...draft,raw},'operator','operator',now));
  assert.throws(()=>M.adjustDraft(station,draft,50));
});
test('new catalog entries have no invented telemetry', () => {
  const c=M.clone(catalog);c.stations.push({...M.clone(station),id:'station-005',name:'Новая',itemPrefix:'codex.Device5'});
  const valid=M.validateCatalog(c),snap=M.createFixtures(valid,now).snapshots['station-005'];
  assert.equal(snap.spRaw,null);assert.equal(M.readPressure(valid.stations.at(-1),snap,now).value,null);
});
test('rebinding a known ID discards fixture telemetry and alarms; extra pumps stay unknown', () => {
  for (const mutate of [c=>c.stations[0].itemPrefix='codex.Other',c=>c.connections[0].computer='other-host']) {
    const c=M.clone(catalog);mutate(c);const fixture=M.createFixtures(M.validateCatalog(c),now);
    assert.equal(fixture.snapshots['station-001'].spRaw,null);
    assert.equal(fixture.alarms.some(a=>a.stationId==='station-001'),false);
    assert.equal(M.hasFixture(c.stations[0],c),false);
  }
  const c=M.clone(catalog);c.stations[1].pumpCount=4;
  const pump=M.createFixtures(c,now).snapshots['station-002'].pumps[3];
  assert.equal(pump.state,'unknown');assert.equal(pump.frequency.value,null);
});
test('acknowledgement preserves an active condition', () => {
  const alarm=M.createFixtures(catalog,now).alarms[0];const ack=M.ackAlarm(alarm,'operator',now);
  assert.equal(ack.active,true);assert.equal(ack.acknowledged,true);assert.equal(alarm.acknowledged,false);
});
test('chart segments preserve real zero and break at invalid quality or missing intervals', () => {
  const points=[{ts:0,value:0,quality:'good'},{ts:1,value:2,quality:'bad'},
    {ts:2,value:3,quality:'good'},{ts:100,value:4,quality:'good'}];
  const parts=M.segments(points,0,100,5);
  assert.equal(parts.length,3);assert.equal(parts[0][0].value,0);
  assert.equal(parts.flat().some(p=>p.quality==='bad'),false);
});
test('catalog export round trip contains configuration, not fixture telemetry; CSV escapes formulas', () => {
  const next=M.validateCatalog(JSON.parse(JSON.stringify(catalog)));
  assert.equal(next.stations.length,4);assert.equal('snapshots' in next,false);
  assert.equal(M.csvCell('=1+1'),'"\'=1+1"');assert.equal(M.csvCell('А;Б'),'"А;Б"');
});
