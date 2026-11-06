"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const js=fs.readFileSync(path.join(__dirname,"../tihulu_flight_radar/web/app.js"),"utf8");
const m=js.match(/function browserSourceResult\([^)]*\)\{[\s\S]*?\n\}/);
if(!m)throw Error("browserSourceResult missing");

function source(mode,withRadio=true){
 const time=Date.now();
 const state={
  usbSnapshot:{updatedAt:time,aircraft:withRadio?[{
   hex:"40621d",lat:52.2572,lon:3.91937,seen:2,seen_pos:2,
   flight:"RADIO1",alt_baro:38000
  }]:[]},
  internetSnapshot:{
   generated_at:time/1000,
   sources:{internet:{provider:"Configured feed",attribution:"Provider license",updated_at:time/1000}},
   aircraft:[
    {hex:"40621d",lat:51.2,lon:10.4,seen:2,seen_pos:2,flight:"NET1"},
    {hex:"deaf00",lat:50.938,lon:6.96,seen:1,seen_pos:1,flight:"NET2"}
   ]
  },
  onlineFeed:"https://feed.example/api/aircraft",
  usbMessageCount:2
 };
 const sandbox={state,Date,Math,Number,Map,String,
  isPositioned:a=>Number.isFinite(a?.lat)&&Number.isFinite(a?.lon)&&
    Number.isFinite(a?.seen_pos)&&a.seen_pos<=60,
  $:id=>({value:mode})};
 const fn=vm.runInNewContext(m[0]+"\nbrowserSourceResult",sandbox);
 return fn(mode);
}
test("Hybrid browser merges matching ICAO without relabeling a radio-derived position",()=>{
 const d=source("hybrid");
 assert.equal(d.counts.antenna,1);
 assert.equal(d.counts.internet,2);
 assert.equal(d.counts.combined,2);
 const matched=d.aircraft.find(a=>a.hex==="40621d");
 assert.equal(matched.sources.join(","),"antenna,internet");
 assert.equal(matched.position_source,"antenna");
 assert.equal(matched.lat,52.2572);
 assert.equal(matched.lon,3.91937);
 assert.equal(matched.observations.internet.lat,51.2);
 assert.equal(d.aircraft.find(a=>a.hex==="deaf00").position_source,"internet");
});
test("Browser antenna-only does not leak Internet planes into RF counts",()=>{
 const d=source("antenna");
 assert.equal(d.counts.antenna,1);
 assert.equal(d.counts.internet,0);
 assert.equal(d.counts.combined,1);
 assert.equal(d.aircraft[0].sources.join(","),"antenna");
});
test("Auto uses real USB planes if available, network fallback otherwise",()=>{
 assert.equal(source("auto",true).counts.combined,1);
 assert.equal(source("auto",false).counts.combined,2);
});
test("Radio browser source cannot be started while a paired bridge owns the receiver",()=>{
 const usb=fs.readFileSync(path.join(__dirname,"../tihulu_flight_radar/web/browser_usb.mjs"),"utf8");
 assert.match(usb,/tihuluUsbCanStart/);
 assert.match(js,/window\.tihuluUsbCanStart/);
});
