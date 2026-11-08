"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const root=path.join(__dirname,"../tihulu_flight_radar/web");
const model=require(path.join(root,"receiver_coverage.js"));
const read=name=>fs.readFileSync(path.join(root,name),"utf8");
function plane(hex,lat,lon){
 const a={hex,lat,lon,seen:1,seen_pos:1,alt_baro:30000,gs:480,track:90,
  position_source:"antenna",sources:["antenna"]};
 a.observations={antenna:{...a}};
 return a;
}
test("Recorded RF samples preserve speed/course but never create projected constraints",()=>{
 const record=model.recordedCircle(plane("a00001",50,7),100000);
 assert.equal(record.speedKt,480);
 assert.equal(record.headingDeg,90);
 assert.equal(record.lat,50);
 assert.equal(record.lon,7);
 assert.equal(record.recorded_rf,true);
 assert.equal(Object.hasOwn(record,"projected"),false);
});
test("Speed-adaptive sampler rejects duplicates, invalid chronology and impossible jumps",()=>{
 const a={...model.recordedCircle(plane("a00001",50,7),100000),positionAgeSeconds:1};
 const near={...a,lon:7.012,capturedAtMs:150000,observationTimeMs:149000};
 const next={...a,lon:7.15,capturedAtMs:150000,observationTimeMs:149000};
 assert.equal(model.trackSampleDecision(null,a).keep,true);
 assert.equal(model.trackSampleDecision(a,near).keep,false);
 assert.equal(model.trackSampleDecision(a,next).keep,true);
 assert.equal(model.trackSampleDecision(a,{...next,capturedAtMs:90000,observationTimeMs:89000}).reason,"non-monotonic");
 assert.equal(model.trackSampleDecision(a,{...next,lon:16,capturedAtMs:105000,observationTimeMs:104000}).reason,"implausible-rf-jump");
});
test("Independent aircraft count is not inflated by along-track samples",()=>{
 const rows=[plane("a00001",50.7,6.7),plane("a00002",50.2,7.5),
  plane("a00003",51.1,6.2),plane("a00004",50.6,7.9)];
 const initial=model.compute(rows.slice(0,3));
 assert.equal(initial.status,"insufficient");
 assert.equal(initial.aircraftCircles.length,3);
 const rec=model.recordedCircle(rows[0]);
 const past={...rec,lon:rec.lon+.26,capturedAtMs:Date.now()-45000};
 const result=model.compute(rows,[past]);
 assert.equal(result.count,4);
 assert.equal(result.status,"region");
 assert.equal(result.aircraftCircles.length,4);
 assert.equal(result.aircraftCircles.find(x=>x.hex==="a00001").samples,2);
 assert.equal(result.region.confidence,null);
 assert.equal(result.region.accuracyMeters,null);
});
test("RF model visuals expose independent live-follow and per-aircraft toggles",()=>{
 const html=read("index.html"),js=read("app.js"),css=read("style.css");
 for(const id of ["rfFollow","rfFill","rfHatch","rfModelCircle","rfModelPin",
  "rfAircraftLayers","rfAllPlanes","rfNoPlanes","rfProgress"]){
  assert.match(html,new RegExp('id="'+id+'"'));
 }
 assert.match(js,/function disableRfFollow\(\)/);
 assert.match(js,/function rfFeasibleHull\(result\)/);
 assert.match(js,/function rfDrawRing\(ring,color/);
 assert.match(js,/rfSelectedPlanes\.has\(item\.hex\)/);
 assert.match(js,/function rfPlaneColor\(hex\)/);
 assert.match(js,/rfLastFollowModel===result/);
 assert.match(js,/ctx\.clip\(\)/);
 assert.match(css,/\.rf-aircraft-layer/);
 assert.match(html,/NOT a statistical accuracy\/error circle/);
 assert.doesNotMatch(read("receiver_coverage.js"),/navigator\.geolocation|\bfetch\s*\(/);
});

test("RF camera follows new model revisions and keeps zoom after first focus",()=>{
 const js=read("app.js");
 const source=js.match(/function focusRfModelWhenReady\(result\)\{[\s\S]*?\n\}/)?.[0];
 assert.ok(source,"RF focus function exists");
 const state={lat:50,lon:7,zoom:9,moved:false,autoFocused:false,centerLabel:""};
 const first={status:"region",region:{lat:50.9,lon:7.2,extentKm:120}};
 const second={status:"region",region:{lat:51.1,lon:7.8,extentKm:70}};
 const ctx={state,first,second,Math};
 vm.runInNewContext([
  "let rfLocatorActive=true,rfLocatorFocused=false,rfFollowCenter=true,rfLastFollowModel=null;",
  source,
  "focusRfModelWhenReady(first);",
  "const oldZoom=state.zoom;",
  "focusRfModelWhenReady(second);",
  "if(state.zoom!==oldZoom)throw Error('follow unexpectedly changed zoom');"
 ].join("\n"),ctx);
 assert.equal(state.lat,second.region.lat);
 assert.equal(state.lon,second.region.lon);
 assert.match(state.centerLabel,/NOT GPS/);
});

test("Mixed Internet metadata never supplies a missing local RF speed",()=>{
 const a=plane("a00011",50,7);
 delete a.observations.antenna.gs;
 delete a.observations.antenna.track;
 a.sources.push("internet");
 a.gs=999;a.track=180;
 const item=model.recordedCircle(a);
 assert.equal(item.speedKt,null);
 assert.equal(item.headingDeg,null);
});
test("Solver still uses distinct aircraft after high-density one-aircraft track history",()=>{
 const rows=[plane("a00001",50.7,6.7),plane("a00002",50.2,7.5),
  plane("a00003",51.1,6.2),plane("a00004",50.6,7.9)];
 const base=model.recordedCircle(rows[0]);
 const history=Array.from({length:60},(_,i)=>({
  ...base,lat:base.lat+.001*i,lon:base.lon+.26+.02*i,
  capturedAtMs:Date.now()-(i+1)*25000
 }));
 const out=model.compute(rows,history);
 assert.equal(out.status,"region");
 assert.equal(out.count,4);
 assert.equal(out.constraintsUsed<=64,true);
 assert.equal(out.aircraftCircles.length,4);
});
