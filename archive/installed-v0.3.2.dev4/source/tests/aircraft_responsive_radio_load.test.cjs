"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const root=path.join(__dirname,"../tihulu_flight_radar/web");
const read=file=>fs.readFileSync(path.join(root,file),"utf8");
const html=read("index.html"),css=read("style.css"),
 ui=read("flight_journey_ui.js"),app=read("app.js"),
 js=read("aircraft_panel_resize.js");

function radioSource(){
 const start=ui.indexOf("async function radioSnapshot(){");
 const end=ui.indexOf('\n $("aircraftRadioLoad").addEventListener',start);
 assert.ok(start>=0&&end>start);
 return ui.slice(start,end);
}

test("aircraft side panel is wider and draggable with keyboard support",()=>{
 assert.match(css,/--flight-side-width:580px/);
 assert.match(css,/\.layout\{grid-template-columns:minmax\(0,1fr\) 10px minmax\(0,var\(--flight-side-width\)/);
 assert.match(html,/id="aircraftSideSplitter"/);
 assert.match(html,/aria-orientation="vertical"/);
 assert.match(js,/pointerdown/);assert.match(js,/pointermove/);
 assert.match(js,/ArrowLeft/);assert.match(js,/ArrowRight/);
 assert.match(js,/localStorage\.setItem/);
 assert.match(css,/@container \(max-width:680px\)/);
 assert.match(css,/\.side\{scrollbar-gutter:stable;container-type:inline-size/);
 assert.match(app,/td\.dataset\.label=\["Flight \/ ICAO","Altitude","Speed","Source"\]/);
 assert.match(app,/routeCell\.dataset\.label="From → To \/ times"/);
});

test("load radio and load Internet are independent visible on-demand controls",()=>{
 assert.match(html,/id="aircraftRadioLoad"/);
 assert.match(html,/id="aircraftRoutesLoad"/);
 assert.match(html,/id="aircraftLoadStatus"/);
 assert.match(ui,/\$\("aircraftRadioLoad"\)\.addEventListener\("click"/);
 assert.match(ui,/\$\("aircraftRoutesLoad"\)\.addEventListener\("click"/);
 assert.match(ui,/F\.observeRadio\(data\.rows\)/);
 assert.match(ui,/radioLoaded=true/);
 assert.match(app,/journey\?\.radio/);
 assert.match(css,/\.journey-table/);
});

test("Load Radio requests antenna-only bridge observations; never performs Internet merge",async()=>{
 const source=radioSource(),called=[];
 const bridge={state:"fake"};
 const plane={hex:"a00001",flight:"DLH1234",seen:1,sources:["antenna"],
  observations:{antenna:{seen:1,alt_baro:34000}}};
 const state={connectionKind:"bridge",base:"http://127.0.0.1:8510",
  token:"secret",queryLat:50.91,queryLon:6.95,queryRadius:100};
 const run=vm.runInNewContext(source+"\nradioSnapshot",
  {state,URLSearchParams,Number,Array,Date,api:async url=>{
   called.push(url);
   return {aircraft:[plane,{...plane,hex:"a00002",sources:["internet"],
    observations:{internet:plane.observations.antenna}}],
    sources:{antenna:{state:"receiving"}}};
  }});
 const result=await run();
 assert.equal(called.length,1);
 const query=new URL("http://127.0.0.1:8510"+called[0]);
 assert.equal(query.pathname,"/api/aircraft");
 assert.equal(query.searchParams.get("mode"),"antenna");
 assert.equal(result.rows.length,1);
 assert.equal(result.rows[0].hex,"a00001");
 assert.equal(result.status,"receiving");
});

test("Load Radio works only with already-running WebUSB and never claims SDR hardware",async()=>{
 const source=radioSource();
 const row={hex:"a00001",seen:1,alt_baro:"ground",flight:"DLH1234"};
 const state={connectionKind:"usb",usbSnapshot:{
  updatedAt:Date.now(),aircraft:[row,{...row,hex:"a00002",seen:60}]}};
 const run=vm.runInNewContext(source+"\nradioSnapshot",{state,Date,Number,Array,
  api:()=>{throw Error("must not perform network request")},URLSearchParams});
 const data=await run();
 assert.equal(data.rows.length,1);
 assert.deepEqual(Array.from(data.rows[0].sources),["antenna"]);
 assert.equal(data.rows[0].observations.antenna.alt_baro,"ground");
 assert.match(data.status,/WebUSB local receiver/);
 state.connectionKind="internet";
 const off=await run();
 assert.equal(off.rows.length,0);
 assert.match(off.status,/No active local SDR receiver/);
});
