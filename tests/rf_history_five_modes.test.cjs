"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path");
const root=path.join(__dirname,"../tihulu_flight_radar/web");
const mod=require(path.join(root,"rf_history_models.js"));
const t=Date.UTC(2026,10,9,20);
const row=(hex,lat,lon,radiusKm,at=t)=>({
 hex,lat,lon,radiusKm,capturedAtMs:at,recorded_rf:true,
 altitudeFeet:35000
});
const base=[
 row("a00001",50.6,6.8,270),
 row("a00002",51.2,6.9,270),
 row("a00003",50.9,7.5,270),
 row("a00004",50.8,6.3,270)
];
test("exact five distinct model modes are wired to real shared UI",()=>{
 assert.deepEqual([...mod.MODES],["live10","liveX","best","history","historyBest"]);
 const html=fs.readFileSync(path.join(root,"index.html"),"utf8");
 const app=fs.readFileSync(path.join(root,"app.js"),"utf8");
 const ui=fs.readFileSync(path.join(root,"rf_history_ui.js"),"utf8");
 for(const id of ["rfMode","rfHours","rfHistorySpeed","rfRecorderToggle",
  "rfNewSession","rfRecalculate","rfModeSpread","rfArchiveStatus"])
  assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/rf_history_ui\.js/);
 assert.match(app,/TihuluRFV2\?\.display/);
 assert.match(app,/TihuluRFV2\?\.ingest/);
 assert.match(ui,/client\.calculate/);
});
test("only valid, genuinely RF-tagged input is accepted as historical evidence",()=>{
 assert.equal(mod.valid(row("a00005",50.9,6.9,350)),true);
 assert.equal(mod.valid({...row("a00005",50.9,6.9,350),recorded_rf:false}),false);
 assert.equal(mod.valid(row("internet",50.9,6.9,350)),false);
 assert.equal(mod.valid(row("a00005",90,6.9,350)),false);
 assert.equal(mod.valid(row("a00005",50.9,6.9,0)),false);
});
test("LIVE10 vs editable X-hour time window excludes older observations",()=>{
 const rows=[...base,row("a00005",50.7,7.2,300,t-45*60000),
  row("a00006",50.8,7.2,290,t-125*60000)];
 assert.equal(mod.filter(rows,{mode:"live10",nowMs:t}).length,4);
 assert.equal(mod.filter(rows,{mode:"liveX",hours:2,nowMs:t}).length,5);
 assert.equal(mod.filter(rows,{mode:"liveX",hours:3,nowMs:t}).length,6);
 assert.equal(mod.filter(rows,{mode:"history",nowMs:t}).length,6);
});
test("HISTORY hard intersection accounts for all records beyond legacy 64",()=>{
 const many=[...base];
 for(let i=0;i<100;i++)
  many.push(row("b"+String(i).padStart(5,"0"),50.8+(i%10)*.004,
   6.9+(i%7)*.004,290));
 const res=mod.hard(many,{nowMs:t,mode:"history"});
 assert.equal(res.count,104);
 assert.equal(res.constraintsUsed,104);
 assert.equal(res.status,"region");
 assert.ok(res.region.extentKm>0);
 assert.equal(res.region.accuracyMeters,null);
 assert.equal(res.region.confidence,null);
});
test("HISTORY BEST weights every constraint and reports violations as heuristic",()=>{
 const rows=[...base,
  row("a00005",52.8,9.8,90),row("a00006",50.7,7.0,75)];
 const weighted=mod.weighted(rows,{nowMs:t,mode:"historyBest"});
 assert.equal(weighted.status,"weighted");
 assert.equal(weighted.count,6);
 assert.equal(weighted.constraintsUsed,6);
 assert.equal(weighted.geometryStatus,"weighted-heuristic");
 assert.equal(weighted.region.extentKm,null);
 assert.equal(weighted.accuracyMeters,null);
 assert.ok(Number.isFinite(weighted.rmsViolationKm));
 assert.ok(weighted.violatedConstraints>0);
});
