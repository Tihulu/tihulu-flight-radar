"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const root=path.join(__dirname,"../tihulu_flight_radar/web");
const app=fs.readFileSync(path.join(root,"app.js"),"utf8");
const html=fs.readFileSync(path.join(root,"index.html"),"utf8");
const css=fs.readFileSync(path.join(root,"style.css"),"utf8");
function source(name){
 const start=app.indexOf("function "+name+"(");
 if(start<0)throw Error("Missing "+name);
 const end=app.indexOf("\n}",start);
 if(end<0)throw Error("Unterminated "+name);
 return app.slice(start,end+2);
}
test("Airline/operator and flight numbers only come from source metadata",()=>{
 const functions=["firstAircraftField","aircraftOperatorLabel","aircraftFlightLabel"]
  .map(source).join("\n");
 const ctx=vm.createContext({});
 const read=vm.runInContext(functions+"\n({operator:aircraftOperatorLabel,flight:aircraftFlightLabel})",ctx);
 assert.equal(read.operator({ownOp:"Lufthansa"}),"Lufthansa");
 assert.equal(read.operator({observations:{internet:{airline_name:"Eurowings"}}}),"Eurowings");
 assert.equal(read.operator({flight_source_fields:{airline_name:"Turkish Airlines"}}),"Turkish Airlines");
 assert.equal(read.operator({airline_icao:"THY"}),"THY (operator code; name unavailable)");
 assert.equal(read.operator({flight:"THY456"}),"Not provided by source");
 assert.equal(read.flight({flight_source_fields:{flight_iata:"TK1234"},flight:"THY1234"}),"TK1234");
 assert.equal(read.flight({flight:"DLH123"}),"DLH123 (callsign; flight number not verified)");
 assert.equal(read.flight({}),"Not provided by source");
 assert.match(app,/airline_name,airline_icao,airline_iata/);
 assert.match(html,/id="popupAirline"/);
 assert.match(html,/id="popupFlightNumber"/);
});
test("A small aircraft card is opened before optional RF calculations and is visible outside the clipped Qt map",()=>{
 const ids=new Map();
 const node=id=>{
  if(!ids.has(id))ids.set(id,{textContent:"",style:{},hidden:false,scrollHeight:270});
  return ids.get(id);
 };
 const popup=node("aircraftPopup");popup.hidden=true;
 popup.parentElement={};popup.setAttribute=(k,v)=>{popup[k]=v;};
 const body={appendChild(el){el.parentElement=this;}};
 const document={body,documentElement:{clientWidth:1000,clientHeight:720}};
 const canvas={clientWidth:750,clientHeight:500,
  getBoundingClientRect:()=>({left:25,right:775,top:60,bottom:560})};
 const row={hex:"a00001",flight:"DLH456",ownOp:"Lufthansa",
  lat:50.9,lon:6.9,seen_pos:1,seen:1,sources:["antenna"],
  observations:{antenna:{lat:50.9,lon:6.9,seen_pos:1}}};
 const ctx=vm.createContext({$,document,window:{innerWidth:1000,innerHeight:720},
  canvas,state:{dataReceivedAt:Date.now()},
  TihuluMapMotion:{displayedPosition:()=>null},
  TihuluMultiSources:{META:{}},TihuluRFCoverage:{
   modelDistanceInterval(){throw Error("RF model unavailable");}},
  coverageResult(){throw Error("RF unavailable");},
  showAltitude:()=> "30,000 ft",showSpeed:()=> "420 kt",
  showVerticalRate:()=> "0 ft/min",flightValue:n=>Number.isFinite(n)?n:null,
  isPositioned:()=>true,category:()=> "antenna",aircraftSourceBadge:()=> "R",
  xy:()=>[230,140],operatorFromTar:()=>null,
  enrichAircraftOperator:()=>Promise.resolve(),Math,Number,Date,String});
 function $(id){return node(id);}
 const funcs=["firstAircraftField","aircraftOperatorLabel",
  "aircraftFlightLabel","ensureAircraftPopupLayer",
  "displayedAircraftPoint","positionPopup","renderPopup"];
 vm.runInContext(funcs.map(source).join("\n")+"\nrenderPopup(testPlane)",Object.assign(ctx,{testPlane:row}));
 assert.equal(popup.hidden,false,"popup must be visible even if RF calculations throw");
 assert.equal(popup.parentElement,body,"popup must be portaled to body");
 assert.equal(node("popupAirline").textContent,"Lufthansa");
 assert.equal(node("popupFlightNumber").textContent,"DLH456 (callsign; flight number not verified)");
 assert.match(node("popupTiming").textContent,/Optional RF coverage estimate unavailable/);
 assert.match(popup.style.left,/px$/);
 assert.match(popup.style.top,/px$/);
 assert.match(css,/\.aircraft-popup\{position:fixed;z-index:20010/);
});
test("Qt click fallback opens a selected aircraft without a pointer-up event",()=>{
 const sourceCode=["pickPaintedAircraft","pickPaintedModel",
  "inspectCanvasAircraft","inspectCanvasTarget"].map(source).join("\n");
 const handler=app.match(/canvas\.addEventListener\("click",e=>\{[\s\S]*?\n\}\);/)?.[0];
 assert.ok(handler,"native click listener must exist");
 const handlers={};const chosen=[];
 const canvas={
  getBoundingClientRect:()=>({left:10,top:20}),
  addEventListener:(type,fn)=>{handlers[type]=fn;}
 };
 const row={hex:"a00001",lat:50,lon:7,seen_pos:1};
 const ctx=vm.createContext({canvas,paintedModelHits:[],
  paintedAircraftHits:[
  {hex:"a00001",x:100,y:100,badgeRight:29,labelWidth:60}
 ],state:{data:[row]},visible:()=>true,isPositioned:()=>true,
 toggleAircraftOnMap:a=>chosen.push(a.hex),
  openRfModelPopup:()=>false,Math,Date,lastCanvasAircraftOpen:null});
 vm.runInContext(sourceCode+"\n"+handler,ctx);
 handlers.click({clientX:110,clientY:120,detail:0}); // Qt can send detail 0
 assert.deepEqual(chosen,["a00001"]);
 // Browser click after a handled pointerup should not duplicate.
 handlers.click({clientX:111,clientY:120,detail:1});
 assert.deepEqual(chosen,["a00001"]);
 assert.match(app,/if\(typeof canvas\.setPointerCapture==="function"\)/);
});
test("Aircraft rows have a direct Info fallback, not merely a canvas hit target",()=>{
 assert.match(html,/<th>Info<\/th>/);
 assert.match(app,/info\.textContent="Info"/);
 assert.match(app,/info\.onclick=e=>\{e\.stopPropagation\(\);choose\(a\);\}/);
 assert.match(css,/\.aircraft-row-info/);
});
