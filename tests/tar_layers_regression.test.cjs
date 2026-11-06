"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const vm=require("node:vm");
const fs=require("node:fs");
const path=require("node:path");
const adapter=fs.readFileSync(path.join(__dirname,"../tihulu_flight_radar/web/tar1090-adapter.js"),"utf8");

function harness({selectedWidth=0,mapWidth=900}={}){
 const listeners={},elements=[],intervals=[],upstream={planes:{},planesOrdered:[]};
 const rect=(left,top,width,height)=>({left,top,right:left+width,bottom:top+height,width,height});
 function element(tag){
  const e={tag,id:"",checked:false,style:{},children:[],isConnected:false,
   textContent:"",setAttribute(){},
   appendChild(x){this.children.push(x);x.parentElement=this;x.isConnected=true;return x;},
   insertBefore(x,y){if(x.parentElement)x.parentElement.children=x.parentElement.children.filter(c=>c!==x);
    const i=this.children.indexOf(y);this.children.splice(i<0?0:i,0,x);x.parentElement=this;return x;},
   getBoundingClientRect(){return rect(0,0,100,100)}};
  elements.push(e);return e;
 }
 const mapNode=element("div");mapNode.id="map_container";mapNode.getBoundingClientRect=()=>rect(0,0,mapWidth,700);
 const info=element("div");info.id="selected_infoblock";info.getBoundingClientRect=()=>rect(0,0,selectedWidth,700);
 info.style.display=selectedWidth?"block":"none";
 const sidebar=element("aside");sidebar.id="sidebar_container";sidebar.getBoundingClientRect=()=>rect(mapWidth,0,340,700);
 const chart=element("div");chart.id="altitude_chart";
 const document={body:element("body"),head:element("head"),
  createElement:element,createTextNode:t=>({textContent:t}),
  getElementById:id=>elements.find(e=>e.id===id)||null,
  addEventListener:(key,fn)=>listeners["document."+key]=fn};
 let redraws=0,tableRefresh=0;
 const layers=[];
 class Vector{constructor(){this.features=[]}clear(){this.features=[]}addFeature(f){this.features.push(f)}getFeatures(){return this.features}}
 class Feature{constructor(obj){this.properties=obj}get(k){return this.properties[k]}}
 const ol={Feature,source:{Vector},layer:{Vector:class{constructor(opts){this.source=opts.source;this.style=opts.style}}},
  style:{Style:class{constructor(opts){this.options=opts}},Text:class{constructor(opts){this.options=opts}},
   Fill:class{constructor(opts){this.options=opts}},Stroke:class{constructor(opts){this.options=opts}}},
  geom:{Point:class{constructor(v){this.coordinates=v}}},proj:{fromLonLat:x=>x}};
 const mockMap={addLayer:l=>layers.push(l),render:()=>{redraws++}};
 const parent={postMessage(){}};
 const win={parent,addEventListener:(k,fn)=>listeners[k]=fn,
  setInterval:(fn,ms)=>{intervals.push({fn,ms});return intervals.length},
  getComputedStyle:e=>({display:e.style.display,visibility:e.style.visibility}),
  ol};
 let transport;
 const jQuery={ajaxTransport:(name,fn)=>{assert.equal(name,"+json");transport=fn}};
 function makePlane(hex){
  const p={icao:hex,selected:false,destroyed:false,destroy(){this.destroyed=true}};
  upstream.planes[hex]=p;upstream.planesOrdered.push(p);return p;
 }
 // Lexical "let OLMap" matches real tar1090 upstream script.js;
 // window.OLMap remains intentionally undefined.
 vm.runInNewContext(
  "let OLMap = mockMap; let g = upstream; let TAR = {planeMan:{refresh(){refreshTable()}}};\n"+adapter,
  {document,window:win,location:{origin:"https://tihulu.github.io",
    href:"https://tihulu.github.io/tihulu-flight-radar/tar1090/index.html"},
   mockMap,upstream,refreshTable:()=>{tableRefresh++},jQuery,URL,Math,Number,Date,
   String,Map,Set,queueMicrotask,ol}
 );
 async function json(){
  const t=transport({url:"data/aircraft.json"});
  return new Promise(resolve=>t.send({},(status,reason,result)=>resolve(result.json)));
 }
 function send(aircraft){
  listeners.message({source:parent,origin:"https://tihulu.github.io",
   data:{type:"tihulu:tar-aircraft",now:Date.now()/1000,messages:0,aircraft}});
 }
 function toggles(){const panel=document.getElementById("tihulu-source-layers");return panel.children.filter(c=>c.tag==="label").map(label=>label.children.find(c=>c.tag==="input"))}
 return {document,win,listeners,layers,intervals,upstream,mapNode,info,sidebar,chart,
  makePlane,json,send,toggles,counts:()=>({redraws,tableRefresh})};
}
const airplane=(hex,sources)=>({hex,lat:50.95,lon:6.97,seen:1,seen_pos:2,sources});
test("I/R badges render with upstream lexical OLMap, without window.OLMap",()=>{
 const h=harness();
 h.listeners.DOMContentLoaded();
 h.makePlane("aaa111");h.makePlane("bbb222");h.makePlane("ccc333");
 h.send([airplane("aaa111",["internet"]),airplane("bbb222",["antenna"]),
  airplane("ccc333",["antenna","internet"])]);
 assert.equal(h.layers.length,1,"actual OpenLayers vector badge layer is mounted");
 const features=h.layers[0].source.getFeatures();
 assert.deepEqual(features.map(f=>f.get("badge")),["I","R","I/R"]);
});
test("Source toggles instantly remove hidden map planes AND table rows",async()=>{
 const h=harness();h.listeners.DOMContentLoaded();
 const a=h.makePlane("aaa111"),b=h.makePlane("bbb222"),c=h.makePlane("ccc333");
 h.send([airplane("aaa111",["internet"]),airplane("bbb222",["antenna"]),
  airplane("ccc333",["antenna","internet"])]);
 const [internet,radio,matched]=h.toggles();
 assert.ok(internet.checked&&radio.checked&&matched.checked);
 internet.checked=false;internet.onchange();
 assert.equal(a.destroyed,true);
 assert.equal(b.destroyed,false);
 assert.equal(c.destroyed,false);
 assert.deepEqual(Object.keys(h.upstream.planes),["bbb222","ccc333"]);
 assert.deepEqual((await h.json()).aircraft.map(x=>x.hex),["bbb222","ccc333"]);
 matched.checked=false;matched.onchange();
 assert.equal(c.destroyed,true);
 assert.deepEqual((await h.json()).aircraft.map(x=>x.hex),["bbb222"]);
 radio.checked=false;radio.onchange();
 assert.equal(b.destroyed,true);
 assert.equal((await h.json()).aircraft.length,0);
 assert.ok(h.counts().tableRefresh>=3,"table is redrawn when the source changes");
 radio.checked=true;radio.onchange();
 assert.deepEqual((await h.json()).aircraft.map(x=>x.hex),["bbb222"]);
});
test("Source overlay and altitude ramp move clear of selected aircraft infoblock",()=>{
 const h=harness({selectedWidth:300,mapWidth:1000});
 h.listeners.DOMContentLoaded();
 const panel=h.document.getElementById("tihulu-source-layers");
 assert.equal(panel.parentElement,h.mapNode);
 assert.equal(panel.style.left,"312px");
 assert.ok(Number.parseInt(h.chart.style.width,10)<=1000-312-12);
 h.info.style.display="none";
 h.win.tihuluTarLayout();
 assert.equal(panel.style.left,"12px");
 assert.ok(Number.parseInt(h.chart.style.width,10)>650);
});
test("Very narrow map docks layer controls in right sidebar instead of covering aircraft info",()=>{
 const h=harness({selectedWidth:725,mapWidth:875});
 h.listeners.DOMContentLoaded();
 const panel=h.document.getElementById("tihulu-source-layers");
 assert.equal(panel.parentElement,h.sidebar);
 assert.equal(panel.style.position,"relative");
 assert.ok(Number.parseInt(h.chart.style.width,10)<=125);
});
