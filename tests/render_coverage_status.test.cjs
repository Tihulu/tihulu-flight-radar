"use strict";
/* Negative regression for the deployed renderCoverageStatus() TypeError:
 * eager evaluation of result.region.extentKm threw on EVERY paint when no RF
 * region existed (Internet-only / no antenna), freezing the coverage label and
 * spamming the console. Status text must now be built lazily. */
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const js=fs.readFileSync(path.join(__dirname,"../tihulu_flight_radar/web/app.js"),"utf8");
const start=js.indexOf("function renderCoverageStatus()");
const end=js.indexOf("\n$(\"rfLocate\").onclick",start);
if(start<0||end<0)throw Error("renderCoverageStatus missing");
const standalone=js.slice(start,end);

function run(result){
 const els={rfCoverageStatus:{textContent:""},rfLocate:{textContent:"",setAttribute(){}},
   rfLocateStatus:{textContent:""}};
 const sandbox={
  $:(id)=>els[id],
  coverageResult:()=>result,
  notice:()=>{},
  rfLocatorActive:false,
  state:{data:[]},
  TihuluRFCoverage:{compute:()=>result},
 };
 vm.createContext(sandbox);
 vm.runInContext(sandbox2source(sandbox),sandbox);
 return els;
}
function sandbox2source(sandbox){
 // rfLocatorActive is a module-level `let`; declare it inside the snippet scope.
 return "let rfLocatorActive=false;\n"+standalone+"\nrenderCoverageStatus();";
}

test("insufficient coverage result does not throw (regression: extentKm of null)",()=>{
 const els=run({status:"insufficient",count:0,region:null,constraintsUsed:0});
 assert.match(els.rfCoverageStatus.textContent,/0 independently positioned/);
});

test("no_overlap coverage result does not throw",()=>{
 const els=run({status:"no_overlap",count:3,region:null,constraintsUsed:3});
 assert.match(els.rfCoverageStatus.textContent,/no common overlap/);
});

test("unresolved coverage result does not throw",()=>{
 const els=run({status:"unresolved",count:5,region:null,constraintsUsed:5});
 assert.match(els.rfCoverageStatus.textContent,/too thin or fragmented/);
});

test("region result still reports the modeled extent",()=>{
 const els=run({status:"region",count:3,region:{lat:50.94,lon:6.96,extentKm:42.4},
   constraintsUsed:3});
 assert.match(els.rfCoverageStatus.textContent,/3 independent RF aircraft/);
 assert.match(els.rfCoverageStatus.textContent,/~42 km/);
});

test("unknown status falls back without throwing",()=>{
 const els=run({status:"future_status",count:1,region:null});
 assert.equal(els.rfCoverageStatus.textContent,"Insufficient evidence");
});
