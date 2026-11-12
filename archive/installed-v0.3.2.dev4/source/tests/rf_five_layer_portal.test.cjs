"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const root=path.join(__dirname,"../tihulu_flight_radar/web");
const read=p=>fs.readFileSync(path.join(root,p),"utf8");
const app=read("app.js"),html=read("index.html"),css=read("style.css"),
 ui=read("rf_history_ui.js"),client=read("rf_history_client.js");

function source(name){
 const start=app.indexOf("function "+name+"(");
 assert.ok(start>=0,"Missing "+name);
 const end=app.indexOf("\n}",start);
 assert.ok(end>start,"Unclosed "+name);
 return app.slice(start,end+2);
}

test("Circles offers all FIVE independently selectable models and no duplicate selected-model toggle",()=>{
 const ids=["rfLayerLive10","rfLayerLiveX","rfBestCircle",
  "rfLayerHistory","rfLayerHistoryBest"];
 for(const id of ids)
  assert.equal((html.match(new RegExp('id="'+id+'"',"g"))||[]).length,1,id);
 for(const id of ["rfLayerAll","rfLayerNone","rfLayerRefresh","rfCircleLayerStatus"])
  assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/HISTORY BEST <small>Amber · weighted center ONLY/);
 assert.match(html,/id="rfModelCircle" type="checkbox" checked hidden/);
 assert.match(ui,/const layerCheckboxes=/);
 assert.match(ui,/const taskQueue=\[\]/);
 assert.match(ui,/function calculateVisible/);
 assert.match(client,/onSettled/);
 assert.match(css,/\.rf-circles-dropdown\.rf-circles-portaled\{position:fixed/);
 assert.match(app,/document\.body\.appendChild\(dropdown\)/);
 assert.match(app,/vw-width-8/);
 assert.match(app,/document\.addEventListener\("pointerdown"/);
 assert.match(app,/function rfModelCardData\(kind/);
 assert.match(app,/kind\.startsWith\("layer:"\)/);
});

test("two independent valid model rings and a weighted center point coexist",()=>{
 const rings=[],drawn=[],hits=[];
 const ctx={
  save:()=>{},restore:()=>{},beginPath:()=>{},arc:()=>{},
  fill:()=>{},stroke:()=>{},moveTo:()=>{},lineTo:()=>{},
  setLineDash:()=>{}
 };
 const result=[
  {id:"liveX",result:{status:"region",count:7,
   region:{lat:50.8,lon:6.6,extentKm:160}}},
  {id:"history",result:{status:"region",count:22,
   region:{lat:50.9,lon:6.9,extentKm:72}}},
  {id:"historyBest",result:{status:"weighted",count:22,
   region:{lat:50.92,lon:6.91,extentKm:null}}}
 ];
 const context=vm.createContext({
  window:{TihuluRFV2:{comparisons:()=>result}},
  rfLocatorActive:true,rfDrawRing:(r,color,dash,width)=>rings.push({r,color,dash,width}),
  rfHexToRgba:(hex,alpha)=>hex+":"+alpha,rfMapXy:point=>[point.lon*35,point.lat*4],
  ctx,paintedModelHits:hits,paintRfMapLabel:(kind,x,y,label)=>{
   drawn.push({kind,label});return {kind,x,y,label};
  },
  canvas:{clientWidth:700,clientHeight:350}
 });
 vm.runInContext(source("paintRfComparisons"),context);
 assert.equal(rings.length,2,"only actual feasible-region circles may be drawn");
 assert.deepEqual(rings.map(x=>x.r.radiusKm),[160,72]);
 assert.equal(hits.length,3,"all 3 selected model centers are clickable");
 assert.ok(drawn.some(x=>x.kind==="layer:historyBest"&&x.label.includes("weighted point")));
 assert.ok(drawn.some(x=>x.kind==="layer:history"));
 assert.ok(drawn.some(x=>x.kind==="layer:liveX"));
 context.rfLocatorActive=false;
 vm.runInContext("paintRfComparisons()",context);
 assert.equal(rings.length,2,"RF OFF must stop new model drawing");
});

test("Circles menu portaling and Escape/Done behavior keep buttons interactive",()=>{
 const handlers={},docHandlers={};
 const dropdown={parentElement:null,style:{},classList:{
  add:()=>{},remove:()=>{}
 },scrollHeight:490,
  contains:t=>t===dropdown||t?.belongsToDropdown};
 const summary={getBoundingClientRect:()=>({left:210,top:400,bottom:430}),
  focus:()=>{handlers.focused=true}};
 const menu={open:false,querySelector:key=>key==="summary"?summary:dropdown,
  contains:t=>t===menu||t===summary,
  addEventListener:(type,fn)=>{handlers[type]=fn},
  appendChild:el=>{el.parentElement=menu}};
 dropdown.parentElement=menu;
 const done={addEventListener:(name,fn)=>{handlers.done=fn}};
 const body={appendChild:el=>{el.parentElement=body}};
 const document={body,documentElement:{clientWidth:320},
  addEventListener:(type,fn)=>{docHandlers[type]=fn}};
 const window={innerWidth:320,innerHeight:560,
  addEventListener:()=>{}};
 const ctx=vm.createContext({
  $:id=>id==="rfCirclesMenu"?menu:done,document,window,
  Math,Number,console
 });
 vm.runInContext(source("bindRfCirclesMenu")+"\nbindRfCirclesMenu();",ctx);
 menu.open=true;handlers.toggle();
 assert.strictEqual(dropdown.parentElement,body,
  "dropdown must escape the clipped map-panel");
 const left=parseInt(dropdown.style.left,10);
 const top=parseInt(dropdown.style.top,10);
 const width=parseInt(dropdown.style.width,10);
 assert.ok(left>=8 && left+width<=312,"viewport x fit");
 assert.ok(top>=8 && top+parseInt(dropdown.style.maxHeight,10)<=552,
  "viewport y fit");
 docHandlers.pointerdown({target:{belongsToDropdown:true}});
 assert.equal(menu.open,true,"click inside portal must not close menu");
 handlers.done();
 assert.equal(menu.open,false);
 assert.strictEqual(dropdown.parentElement,menu,"close restores original DOM ownership");
 assert.equal(handlers.focused,true);
});
