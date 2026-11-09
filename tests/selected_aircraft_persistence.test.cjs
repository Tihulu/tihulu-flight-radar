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
 assert.notEqual(start,-1,"missing "+name);
 const end=app.indexOf("\n}",start);
 assert.ok(end>start,"unclosed "+name);
 return app.slice(start,end+2);
}
test("selecting actual aircraft adds persistent explicit selection without centering",()=>{
 const plane={hex:"4ac660",flight:"SAS2584",sources:["antenna"],
  position_source:"antenna"};
 let renderCount=0,paintCount=0,saved=0,popupCount=0;
 const state={selected:null,lat:50,lon:7,zoom:9};
 const rfPickedPlanes=new Set(),rfSelectedPlanes=new Set();
 const controls={rfAircraftCircleMode:{value:"selected"},details:{textContent:""}};
 const ctx=vm.createContext({
  state,rfPickedPlanes,rfSelectedPlanes,
  $:key=>controls[key],
  renderPopup:()=>popupCount++,renderTable:()=>renderCount++,
  paint:()=>paintCount++,persistRfViewPreferences:()=>saved++
 });
 vm.runInContext("let rfAircraftListSignature='cached';\n"+source("choose"),ctx);
 vm.runInContext("choose(plane)",Object.assign(ctx,{plane}));
 assert.equal(state.selected,"4ac660");
 assert.deepEqual([...rfPickedPlanes],["4ac660"]);
 assert.deepEqual([...rfSelectedPlanes],["4ac660"]);
 assert.equal(state.lat,50,"inspection must not move the map");
 assert.equal(popupCount,1);assert.equal(renderCount,1);
 assert.equal(paintCount,1);assert.equal(saved,1);
});
test("closing Info preserves selected ICAO; stale feed does not erase it",()=>{
 const state={selected:"4ac660",data:[]};
 const nodes=new Map([["aircraftPopup",{hidden:false}]]);
 const $=id=>{
  if(!nodes.has(id))nodes.set(id,{
   replaceChildren(){},textContent:"",hidden:true
  });
  return nodes.get(id);
 };
 let renders=0,paints=0,closed=null;
 const ctx=vm.createContext({$,
  state,visible:()=>true,renderRfPickedPanel:()=>{},renderPopup:a=>closed=a,
  document:{createElement:()=>({})},renderTable:()=>renders++,paint:()=>paints++
 });
 vm.runInContext(source("closePopup"),ctx);
 vm.runInContext("closePopup()",ctx);
 assert.equal(state.selected,"4ac660");
 assert.equal($("aircraftPopup").hidden,true);
 assert.equal(renders,1);assert.equal(paints,1);
 // Real renderTable preserves the ICAO even when the latest feed is empty.
 const stale=vm.createContext({state,$,visible:()=>true,
  renderRfPickedPanel:()=>{},renderPopup:a=>{closed=a;},
  document:{createElement:()=>({})}});
 vm.runInContext(source("renderTable"),stale);
 vm.runInContext("renderTable()",stale);
 assert.equal(state.selected,"4ac660");
 assert.equal(closed,null);
 assert.match($("details").textContent,/no longer in the latest snapshot/);
});
test("selected sidebar distinguishes genuine RF horizons from internet-only choices",()=>{
 const plane1={hex:"4ac660",flight:"SAS2584",sources:["antenna"]};
 const plane2={hex:"abcd01",flight:"TEST123",sources:["internet"]};
 const picked=new Set([plane1.hex,plane2.hex]);
 const nodes=new Map();
 function createElement(){
  return {children:[],textContent:"",disabled:false,className:"",
   classList:{add(){}},setAttribute(){},
   append(...children){this.children.push(...children);},
   replaceChildren(){this.children=[];}};
 }
 const $=id=>{
  if(!nodes.has(id))nodes.set(id,createElement());
  return nodes.get(id);
 };
 $("rfAircraftCircleMode").value="selected";
 let saves=0,table=0,paints=0;
 const ctx=vm.createContext({
  $,document:{createElement},
  state:{selected:"4ac660",data:[plane1,plane2]},
  rfPickedPlanes:picked,rfSelectedPlanes:new Set([...picked]),
  coverageResult:()=>({status:"insufficient",aircraftCircles:[
   {hex:"4ac660",circle:{lat:50,lon:7,radiusKm:400}}]}),
  persistRfViewPreferences:()=>saves++,
  renderTable:()=>table++,paint:()=>paints++
 });
 vm.runInContext("let rfAircraftListSignature='cached';\n"+
  source("renderRfPickedPanel"),ctx);
 vm.runInContext("renderRfPickedPanel()",ctx);
 assert.equal($("rfPickedCount").textContent,"2");
 assert.match($("rfPickedSummary").textContent,/1 genuine RF horizon/);
 const rows=$("rfPickedList").children;
 assert.equal(rows.length,2);
 const statuses=rows.map(r=>r.children[0].children[1].textContent);
 assert.ok(statuses.some(s=>s==="Genuine antenna RF horizon available"));
 assert.ok(statuses.some(s=>s.includes("no verified RF position")));
 // Remove Internet plane explicitly without affecting genuine RF aircraft.
 const internetRow=rows.find(r=>r.children[0].children[0].textContent.includes("ABCD01"));
 internetRow.children[2].onclick();
 assert.deepEqual([...picked],["4ac660"]);
 assert.equal(saves,1);assert.equal(table,1);assert.equal(paints,1);
});
test("individual checkbox in All mode keeps explicit picks, not every automatic circle",()=>{
 const picked=new Set(["a00001"]),rendered=new Set(["a00001","a00002"]);
 const model={aircraftCircles:[
  {hex:"a00001",flight:"LOCAL1",samples:1,circle:{lat:50,lon:7,radiusKm:100}},
  {hex:"a00002",flight:"LOCAL2",samples:1,circle:{lat:51,lon:7,radiusKm:100}}
 ]};
 function element(){
  return {children:[],checked:false,className:"",style:{},value:"",
   setAttribute(){},addEventListener(name,cb){this[name]=cb;},
   append(...nodes){this.children.push(...nodes);},
   replaceChildren(){this.children=[];}};
 }
 const controls={rfAircraftLayers:element(),rfAircraftCircleMode:{value:"all"},
  aircraftPopup:{hidden:true}};
 const ctx=vm.createContext({
  $:id=>controls[id],document:{createElement:element},
  rfPickedPlanes:picked,rfSelectedPlanes:rendered,
  rfPlaneColor:()=>"#00ffff",renderRfPickedPanel:()=>{},
  persistRfViewPreferences:()=>{},paint:()=>{},
  state:{selected:null}
 });
 vm.runInContext("let rfAutoSelectNewPlanes=true,rfAircraftListSignature='';\n"+
  source("renderRfPlaneLayers"),ctx);
 ctx.model=model;
 vm.runInContext("renderRfPlaneLayers(model)",ctx);
 const labels=controls.rfAircraftLayers.children;
 assert.equal(labels.length,2);
 const uncheckSecond=labels[1].children[0];
 uncheckSecond.checked=false;uncheckSecond.change();
 assert.equal(controls.rfAircraftCircleMode.value,"selected");
 assert.deepEqual([...rendered],["a00001"]);
 assert.deepEqual([...picked],["a00001"]);
});
test("Circles popup is above the altitude legend and sidebar includes selected UI",()=>{
 assert.match(css,/\.map-panel>\.mapbar\{position:relative;z-index:15/);
 assert.match(css,/\.map-panel>\.aircraft-legend\{position:relative;z-index:1/);
 for(const id of ["rfPickedList","rfPickedSummary","rfPickedCount","rfPickedClear"])
  assert.equal((html.match(new RegExp('id="'+id+'"',"g"))||[]).length,1);
 assert.match(app,/pickedPlaneHexes:/);
 assert.match(html,/Selected aircraft only \(map \/ table clicks\)/);
});