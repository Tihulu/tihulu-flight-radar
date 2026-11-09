"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const root=path.join(__dirname,"../tihulu_flight_radar/web");
const app=fs.readFileSync(path.join(root,"app.js"),"utf8");
function source(name){
 const start=app.indexOf("function "+name+"(");
 assert.notEqual(start,-1,"missing "+name);
 const end=app.indexOf("\n}",start);
 assert.ok(end>start,"unclosed "+name);
 return app.slice(start,end+2);
}

test("no receiver RF geometry becomes unresolved; valid 4+ result stays region",()=>{
 let computed={status:"region",count:0,region:null,aircraftCircles:[]};
 let calls=0;
 const ctx=vm.createContext({
  state:{data:[]},Map,
  $:()=>({checked:true}),
  TihuluRFCoverage:{compute:()=>{calls++;return computed;}}
 });
 vm.runInContext(`
 let rfLocatorActive=true,coverageCacheRows=null,coverageCacheResult=null,
 coverageCacheRevision=-1,rfHistoryRevision=0;
 const rfHistory=new Map();
 `+source("coverageResult"),ctx);
 const missing=vm.runInContext("coverageResult()",ctx);
 assert.equal(missing.status,"unresolved");
 assert.equal(missing.region,null);
 vm.runInContext("coverageResult()",ctx);
 assert.equal(calls,1,"animation frames reuse cached result");
 computed={status:"region",count:4,region:{lat:50.9,lon:6.9,extentKm:60},
  aircraftCircles:[]};
 const valid=vm.runInContext("coverageCacheRows=null;coverageResult()",ctx);
 assert.equal(valid.status,"region");
 assert.equal(valid.region.extentKm,60);
 assert.equal(calls,2);
});

test("RF status panel never reads extentKm from absent region",()=>{
 let model={status:"insufficient",count:0,liveCount:0,historyCount:0,
  constraintsUsed:0,region:null,aircraftCircles:[]};
 const nodes=new Map();
 const element=()=>({textContent:"",checked:true,disabled:false,
  setAttribute(){},append(){},replaceChildren(){}});
 const $=id=>{
  if(!nodes.has(id))nodes.set(id,element());
  return nodes.get(id);
 };
 const ctx=vm.createContext({
  $,state:{centerLabel:""},
  coverageResult:()=>model,
  renderRfCoordinateReadouts(){},
  renderRfPlaneLayers(){},
  TihuluRFCoverage:{distanceKm:()=>0},
  document:{createElement:element}
 });
 vm.runInContext(`
 let rfLocatorActive=true,rfLastProgressModel=null,rfLastRegion=null,
  rfFollowCenter=true,rfLastFollowModel=null,rfModelProgressText="waiting",
  rfBest=null,rfBestImprovedThisUpdate=false;
 `+source("renderCoverageStatus"),ctx);
 for(const status of ["insufficient","no_overlap","unresolved"]){
  model={...model,status,count:status==="insufficient"?0:4};
  assert.doesNotThrow(()=>vm.runInContext("renderCoverageStatus()",ctx),status);
  assert.notEqual($("rfCoverageStatus").textContent,"");
  assert.equal($("rfFocus").disabled,true,status+" cannot focus unknown RF region");
 }
 assert.match($("rfCoverageStatus").textContent,/grid/);
 model={status:"region",count:4,liveCount:4,historyCount:0,
  constraintsUsed:7,geometryStatus:"coarse",
  aircraftCircles:[],aircraftDistances:[],
  region:{lat:50.9,lon:6.9,extentKm:60,rawExtentKm:54}};
 assert.doesNotThrow(()=>vm.runInContext("renderCoverageStatus()",ctx));
 assert.match($("rfCoverageStatus").textContent,/coarse extent ~60 km/);
 assert.equal($("rfFocus").disabled,false);

 // Losing the LIVE region must not crash the saved BEST status line.
 vm.runInContext(`
 rfBest={lat:50.9,lon:6.9,rawExtentKm:54,aircraftCount:4,
 constraintsUsed:7,updatedAtMs:1720000000000};
 `,ctx);
 model={status:"insufficient",count:1,liveCount:1,historyCount:0,
  constraintsUsed:1,region:null,aircraftCircles:[]};
 assert.doesNotThrow(()=>vm.runInContext("renderCoverageStatus()",ctx));
 assert.match($("rfBestStatus").textContent,/CURRENT MODEL spread unavailable/);
 assert.ok($("rfCoverageStatus").textContent.includes("1/4"));
});

test("Circles panel closes by outside click, Escape and Done",()=>{
 const inside={},outside={};
 let focused=0,doneClick=null;
 const summary={focus:()=>focused++};
 const menu={open:false,querySelector:()=>summary,contains:t=>t===inside};
 const listeners={};
 const ctx=vm.createContext({
  $:id=>id==="rfCirclesMenu"?menu:{
   addEventListener:(name,callback)=>{if(id==="rfCirclesDone"&&name==="click")doneClick=callback;}
  },
  document:{addEventListener:(name,callback)=>{listeners[name]=callback;}}
 });
 vm.runInContext(source("bindRfCirclesMenu")+"
bindRfCirclesMenu()",ctx);
 menu.open=true;listeners.click({target:inside});
 assert.equal(menu.open,true,"editing multiple options should keep panel open");
 listeners.click({target:outside});
 assert.equal(menu.open,false,"outside click must close the panel");
 menu.open=true;let prevented=false;
 listeners.keydown({key:"Escape",preventDefault:()=>{prevented=true;}});
 assert.equal(menu.open,false);
 assert.equal(prevented,true);
 assert.equal(focused,1);
 menu.open=true;doneClick();
 assert.equal(menu.open,false);
 assert.equal(focused,2);
});

test("changed frontend assets invalidate the previous PWA shell",()=>{
 const html=fs.readFileSync(path.join(root,"index.html"),"utf8");
 const css=fs.readFileSync(path.join(root,"style.css"),"utf8");
 const sw=fs.readFileSync(path.join(root,"sw.js"),"utf8");
 assert.match(html,/id="rfCirclesDone"/);
 assert.match(css,/.rf-circles-done/);
 assert.match(sw,/tihulu-flight-radar-shell-v26/);
});
