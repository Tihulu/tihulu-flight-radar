"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const root=path.join(__dirname,"../tihulu_flight_radar/web");
const app=fs.readFileSync(path.join(root,"app.js"),"utf8");
const html=fs.readFileSync(path.join(root,"index.html"),"utf8");
function source(name){
 const start=app.indexOf("function "+name+"(");
 assert.ok(start>=0,name+" missing");
 const end=app.indexOf("\n}",start);
 assert.ok(end>start,name+" function boundary");
 return app.slice(start,end+2);
}
test("LIVE and BEST cards keep independent measured-unknown metadata",()=>{
 const ctx=vm.createContext({rfLocatorActive:true,
  state:{lastFreshAt:1720000},
  rfBest:{lat:50.938,lon:6.960,displayedExtentKm:80,rawExtentKm:76.5,
   aircraftCount:6,liveCount:4,historyCount:2,constraintsUsed:13,
   sampleCount:14,geometryStatus:"bounded-model",updatedAtMs:1720000},
  coverageResult:()=>null});
 vm.runInContext(source("rfModelCardData"),ctx);
 const rows=vm.runInContext(`
 const live={status:"region",count:5,liveCount:3,historyCount:2,
  constraintsUsed:8,geometryStatus:"coarse",
  region:{lat:50.94,lon:6.97,extentKm:100,rawExtentKm:97.2}};
 ({live:rfModelCardData("live",live),best:rfModelCardData("best",live)})
 `,ctx);
 assert.equal(rows.live.count,5);
 assert.equal(rows.live.radiusKm,100);
 assert.equal(rows.best.count,6);
 assert.equal(rows.best.radiusKm,80);
 assert.equal(rows.best.rawKm,76.5);
 assert.equal(rows.best.updatedAtMs,1720000);
 assert.match(app,/UNKNOWN · no calibrated accuracy or GPS error/);
});
test("offline-capable preview auto-fits full model circle with margins",()=>{
 const ctx=vm.createContext({
  Number,Math,
  mercY:lat=>(1-Math.log(Math.tan(lat*Math.PI/180)+
   1/Math.cos(lat*Math.PI/180))/Math.PI)/2,
  TihuluRFCoverage:{horizonPoints:model=>{
   const r=model.radiusKm/111;
   return Array.from({length:97},(_,i)=>{
    const angle=i*Math.PI*2/96;
    return {lat:model.lat+r*Math.cos(angle),
     lon:model.lon+r*Math.sin(angle)/Math.cos(model.lat*Math.PI/180)};
   });
  }}
 });
 vm.runInContext(source("rfMiniMapFit"),ctx);
 ctx.example={kind:"live",lat:50.9,lon:6.9,radiusKm:85};
 const fit=vm.runInContext("rfMiniMapFit(example,280,280)",ctx);
 assert.ok(fit.zoom>=0&&fit.zoom<=12);
 assert.equal(fit.outline.length,97);
 assert.ok(fit.outline.every(([x,y])=>x>=21&&x<=259&&y>=21&&y<=259),
  "model circle must not be cropped");
 assert.equal(vm.runInContext("rfMiniMapFit({...example,radiusKm:-5})",ctx),null);
});
test("airport/airplane click toggling stays independent from RF center inspection",()=>{
 const plane={hex:"4ac660"},rfPickedPlanes=new Set(["4ac660"]);
 const actions=[];
 const ctx=vm.createContext({
  rfPickedPlanes,closeRfModelPopup:()=>actions.push("close model"),
  choose:a=>actions.push("select "+a.hex),
  deselectAircraft:hex=>{rfPickedPlanes.delete(hex);actions.push("deselect "+hex);}
 });
 vm.runInContext(source("toggleAircraftOnMap"),ctx);
 ctx.plane=plane;
 assert.equal(vm.runInContext("toggleAircraftOnMap(plane)",ctx),"deselected");
 assert.deepEqual(actions,["deselect 4ac660"]);
 assert.equal(vm.runInContext("toggleAircraftOnMap(plane)",ctx),"selected");
 assert.deepEqual(actions,["deselect 4ac660","close model","select 4ac660"]);
});
test("model labels have independent hit targets even when text overlaps planes",()=>{
 const ctx=vm.createContext({Math});
 vm.runInContext(source("pickPaintedModel"),ctx);
 ctx.hits=[{kind:"live",x:100,y:100,
  rect:{left:119,top:60,right:240,bottom:87}},
  {kind:"best",x:155,y:155,
   rect:{left:174,top:166,right:290,bottom:192}}];
 assert.equal(vm.runInContext("pickPaintedModel(hits,90,105)?.kind",ctx),"live");
 assert.equal(vm.runInContext("pickPaintedModel(hits,230,75)?.kind",ctx),"live");
 assert.equal(vm.runInContext("pickPaintedModel(hits,230,177)?.kind",ctx),"best");
 assert.equal(vm.runInContext("pickPaintedModel(hits,9,9)",ctx),null);
});
test("model marker respects visibility and right card has details",()=>{
 for(const id of ["rfModelPopup","rfModelMiniMap","rfPopupAccuracy",
  "rfPopupRadius","rfPopupDiameter","rfPopupAircraft",
  "rfPopupCoordinates","rfPopupConstraints","rfPopupFocus"])
  assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(app,/!$("rfBestPin").checked||!rfBest/);
 assert.match(app,/!$("rfModelPin").checked\)return/);
 assert.doesNotMatch(app,/!$("rfBestPin").checked||!$("rfBestCircle").checked/);
 assert.match(app,/openRfModelPopup(modelKind)/);
 assert.match(app,/toggleAircraftOnMap(row)/);
 assert.match(html,/id="placeAddressOnline"/);
});
