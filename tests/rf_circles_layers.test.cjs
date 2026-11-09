"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.join(__dirname,"../tihulu_flight_radar/web");
const app=fs.readFileSync(path.join(root,"app.js"),"utf8");
const html=fs.readFileSync(path.join(root,"index.html"),"utf8");
const css=fs.readFileSync(path.join(root,"style.css"),"utf8");
function source(name){
 const start=app.indexOf("function "+name+"(");
 assert.notEqual(start,-1,"missing function "+name);
 const end=app.indexOf("\n}",start);
 assert.ok(end>start,"unclosed function "+name);
 return app.slice(start,end+2);
}
test("Circles top menu exists with independent LIVE, BEST, area and airplane modes",()=>{
 for(const id of ["rfLocate","rfCirclesMenu","rfModelCircle","rfBestCircle",
                    "rfFill","rfAircraftCircleMode","rfModelPin","rfBestPin","rfGaussianBand"])
  assert.equal((html.match(new RegExp('id="'+id+'"',"g"))||[]).length,1,"exactly one "+id);
 assert.match(html,/id="rfModelCircle" type="checkbox" checked/);
 assert.match(html,/id="rfBestCircle" type="checkbox"/);
 assert.match(html,/id="rfAircraftCircleMode"/);
 assert.match(html,/<option value="none" selected>Hidden \(default\)<\/option>/);
 assert.match(css,/\.rf-circles-dropdown/);
 assert.match(css,/\.rf-circles-live/);
 assert.match(css,/\.rf-circles-best/);
 assert.doesNotMatch(html,/id="showRfCoverage"/);
 assert.doesNotMatch(app,/showRfCoverage/);
});
test("RF OFF prevents solver calls and returns stable disabled model",()=>{
 const state={data:[{hex:"a00001"}]};let calls=0;
 const context=vm.createContext({state,Map,$:id=>({checked:true}),
  TihuluRFCoverage:{compute(){calls++;return {status:"region",aircraftCircles:[],region:{}};}}});
 const setup=`
 let rfLocatorActive=false,coverageCacheRows=null,
 coverageCacheRevision=-1,coverageCacheResult=null,rfHistoryRevision=0;
 const rfHistory=new Map();
 const RF_LOCATOR_DISABLED=Object.freeze({status:"disabled",count:0,
   circles:[],aircraftCircles:[],region:null});
 `+source("coverageResult");
 vm.runInContext(setup,context);
 const off1=vm.runInContext("coverageResult()",context);
 const off2=vm.runInContext("coverageResult()",context);
 assert.equal(off1.status,"disabled");assert.strictEqual(off1,off2);
 assert.equal(calls,0);
 vm.runInContext("rfLocatorActive=true;coverageResult()",context);
 assert.equal(calls,1);
 vm.runInContext("coverageResult()",context);
 assert.equal(calls,1,"model cache should prevent animation-frame recomputations");
 vm.runInContext("rfLocatorActive=false;coverageResult()",context);
 assert.equal(calls,1,"turning RF OFF must never recompute");
 vm.runInContext("rfLocatorActive=true;coverageCacheRows=null;coverageResult()",context);
 assert.equal(calls,2);
});
test("Aircraft circle modes never change solver input and selected means selected ICAOs only",()=>{
 const elements={rfAircraftCircleMode:{value:"none"}};
 const selected=new Set();const current={aircraftCircles:[
  {hex:"a00001"},{hex:"a00002"}]};
 let paints=0,saves=0;
 const context=vm.createContext({
  $:id=>elements[id],rfSelectedPlanes:selected,
  coverageResult:()=>current,paint:()=>paints++,persistRfViewPreferences:()=>saves++
 });
 vm.runInContext("let rfAutoSelectNewPlanes=false,rfAircraftListSignature='cached';\n"+
  source("setAircraftCircleMode"),context);
 vm.runInContext('setAircraftCircleMode("all")',context);
 assert.deepEqual([...selected].sort(),["a00001","a00002"]);
 assert.equal(elements.rfAircraftCircleMode.value,"all");
 vm.runInContext('setAircraftCircleMode("selected")',context);
 assert.equal(elements.rfAircraftCircleMode.value,"selected");
 assert.deepEqual([...selected].sort(),["a00001","a00002"]);
 vm.runInContext('setAircraftCircleMode("none")',context);
 assert.equal(selected.size,0);
 assert.equal(elements.rfAircraftCircleMode.value,"none");
 assert.equal(paints,3);assert.equal(saves,3);
});
test("BEST circle and BEST center survive loss of LIVE model",()=>{
 const checked={rfAircraftCircleMode:{value:"none"},rfBestCircle:{checked:true},
  rfModelCircle:{checked:true},rfFill:{checked:true},rfHatch:{checked:false},
  rfBestPin:{checked:true}};
 const rings=[],texts=[],savedBest={lat:50.5,lon:7.1,rawExtentKm:36.5,
  displayedExtentKm:40};
 const ctx={
  save:()=>{},restore:()=>{},beginPath:()=>{},moveTo:()=>{},lineTo:()=>{},
  closePath:()=>{},fill:()=>{},stroke:()=>{},setLineDash:()=>{},
  fillText:s=>texts.push(s)
 };
 const context=vm.createContext({
  rfLocatorActive:true,rfBest:savedBest,rfSelectedPlanes:new Set(),
  $:id=>checked[id]||{checked:false},
  ctx,canvas:{clientWidth:600,clientHeight:300},Math,Number,
  rfDrawRing:(r,c)=>rings.push({radius:r.radiusKm,color:c}),
  rfPlaneColor:()=>"#aaaaff",
  rfDrawGaussianBand:()=>{throw Error("Gaussian should not draw in NONE mode");},
  rfFeasibleHull:()=>[],rfMapXy:()=>[120,80],xy:()=>[120,80],
  rfCoordinateText:()=> "50.50000 N, 7.10000 E"
 });
 vm.runInContext(source("paintRfCoverage")+"\n"+source("paintRfBestPin"),context);
 const noLive={status:"insufficient",aircraftCircles:[{
  hex:"a00001",circle:{lat:50.2,lon:8,radiusKm:400}}]};
 context.missing=noLive;
 vm.runInContext("paintRfCoverage(missing);paintRfBestPin(missing)",context);
 assert.equal(rings.length,1,"only BEST circle must render when LIVE invalid");
 assert.equal(rings[0].radius,40);
 assert.match(rings[0].color,/208,164,252/);
 assert.ok(texts.some(t=>/BEST SESSION/.test(t)));
 const live={status:"region",aircraftCircles:[],region:{
  lat:50.8,lon:6.9,extentKm:120}};
 context.live=live;
 rings.length=0;
 vm.runInContext("paintRfCoverage(live)",context);
 assert.equal(rings.length,2,"LIVE and BEST circles are independent");
 assert.ok(rings.some(x=>x.radius===120));
 assert.ok(rings.some(x=>x.radius===40));
 checked.rfModelCircle.checked=false;rings.length=0;
 vm.runInContext("paintRfCoverage(live)",context);
 assert.deepEqual(rings.map(x=>x.radius),[40],"BEST-only view");
 checked.rfBestCircle.checked=false;checked.rfModelCircle.checked=true;
 rings.length=0;vm.runInContext("paintRfCoverage(live)",context);
 assert.deepEqual(rings.map(x=>x.radius),[120],"LIVE-only view");
 context.rfLocatorActive=false;rings.length=0;
 vm.runInContext("paintRfCoverage(live)",context);
 assert.equal(rings.length,0,"RF OFF hides all model overlays");
});
test("RF ON/OFF is sole engine toggle, not Follow or Circles or Gaussian",()=>{
 const switchHandler=app.match(/\$\("rfLocate"\)\.onclick=\(\)=>\{[\s\S]*?\n\};/)?.[0];
 assert.ok(switchHandler);
 const listeners={},best={lat:51,lon:7,rawExtentKm:36};
 let persisted=0,painted=0;
 const ctx=vm.createContext({
  $:id=>{if(!listeners[id])listeners[id]={};return listeners[id];},
  rfBest:best,persistRfViewPreferences:()=>persisted++,
  paint:()=>painted++,notice:()=>{}
 });
 vm.runInContext(`
 let rfLocatorActive=true,rfLocatorFocused=true,rfLastFollowModel={},
 coverageCacheRows={};
 `+switchHandler,ctx);
 listeners.rfLocate.onclick();
 assert.equal(vm.runInContext("rfLocatorActive",ctx),false);
 assert.strictEqual(ctx.rfBest,best);
 listeners.rfLocate.onclick();
 assert.equal(vm.runInContext("rfLocatorActive",ctx),true);
 assert.equal(vm.runInContext("coverageCacheRows",ctx),null);
 assert.equal(persisted,2);
 assert.equal(painted,2);
 assert.match(app,/if\(!rfLocatorActive\|\|!\$\("rfRemember"\)\.checked\)return/);
 assert.match(app,/if\(rfLocatorActive\)\{\s*updateRfBest\(model\)/);
 assert.doesNotMatch(app, /rfFollowCenter=\$\("rfFollow"\)\.checked;\s*if\(rfFollowCenter\)\{rfLocatorActive=true/);
});
test("Cross-platform code is shared, circle preferences are browser/native-safe",()=>{
 assert.match(app,/tihulu-flight-rf-circles-v1/);
 assert.match(app,/function persistRfViewPreferences/);
 assert.match(app,/function restoreRfViewPreferences/);
 assert.match(app,/try\{window\.localStorage\.setItem/);
 assert.match(app,/catch\{ \/\* Session controls still work/);
 assert.match(app,/rfSelectedPlanes\.has\(item\.hex\)/);
 const coverage=fs.readFileSync(path.join(root,"receiver_coverage.js"),"utf8");
 assert.doesNotMatch(coverage,/navigator\.geolocation|navigator\.usb|fetch\s*\(/);
 assert.match(app,/NOT ACCURACY/);
});
