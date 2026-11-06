"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const js=fs.readFileSync(path.join(__dirname,"../tihulu_flight_radar/web/app.js"),"utf8");
const html=fs.readFileSync(path.join(__dirname,"../tihulu_flight_radar/web/index.html"),"utf8");
const start=js.indexOf("const INTELSKY_URL="),end=js.indexOf("\n// Browser-direct RF",start);
if(start<0||end<0)throw Error("Missing real network feed logic");
const segment=js.slice(start,end);
function mk(extra={}){
 return vm.runInNewContext(segment+
  "\n({normalizeInternetPayload,configuredOnlineFeed,fetchInternetFeed})",{
   Date,Math,Number,URL,AbortController,setTimeout,clearTimeout,
   state:{onlineFeed:"https://intelsky.org/api/",onlineProvider:"intelsky",
      queryLat:50.938,queryLon:6.96,queryRadius:100,internetBackoffUntil:0},
   $:()=>({value:"intelsky"}),getFeedURL:x=>x,...extra
  });
}
const valid=()=>{
 const now=Date.now()/1000;
 return {now,ac:[
  {hex:"3c1234",flight:"RCHXYZ",lat:50.95,lon:6.97,alt_baro:35000,gs:420,track:180},
  {hex:"3C1234",flight:"DUP",lat:50.95,lon:6.97},
  {hex:"fedcba",lat:38.3,lon:27.2,flight:"FAR"},
  {hex:"zzzzzz",lat:50.95,lon:6.97},
  {hex:"aa11bb",lat:300,lon:6.97}
 ]};
};
test("Browser-compatible public source is a LIMITED real snapshot, never radio provenance",()=>{
 const result=mk().normalizeInternetPayload(valid(),"intelsky",50.938,6.960,100);
 assert.equal(result.aircraft.length,1);
 assert.equal(result.aircraft[0].hex,"3c1234");
 assert.deepEqual(Array.from(result.aircraft[0].sources),["internet"]);
 assert.equal(result.aircraft[0].position_source,"internet");
 assert.equal(result.aircraft[0].observations.internet.provider,"intelsky");
 assert.equal(result.counts.antenna,0);
 assert.equal(result.counts.internet,1);
 assert.match(result.sources.internet.attribution,/limited military\/government/i);
 assert.equal(result.sources.internet.limited_coverage,true);
});
test("Timestamp validation does not fabricate live positions or accept expired data",()=>{
 const {normalizeInternetPayload:n}=mk(),live=valid();
 assert.throws(()=>n({ac:live.ac},"intelsky",50,7,100),/timestamp/);
 assert.throws(()=>n({...live,now:Date.now()/1000-180},"intelsky",50,7,100),/timestamp/);
 assert.throws(()=>n({...live,now:Date.now()/1000+180},"intelsky",50,7,100),/timestamp/);
 assert.throws(()=>n({now:Date.now()/1000,ac:{}},"intelsky",50,7,100),/schema/);
});
test("Custom general feed retains its real receiver observation ages and Internet-only attribution",()=>{
 const now=Date.now()/1000;
 const p={generated_at:now,provider:"myAuthorizedCORSRelay",attribution:"Data license",
  aircraft:[
   {hex:"aa12bb",lat:50.96,lon:7.01,seen:2,seen_pos:3},
   {hex:"bb12cc",lat:50.96,lon:7.02,seen:66,seen_pos:2}
  ]};
 const result=mk().normalizeInternetPayload(p,"custom",50.938,6.96,100);
 assert.equal(result.aircraft.length,1);
 assert.equal(result.aircraft[0].seen_pos,3);
 assert.equal(result.counts.antenna,0);
 assert.equal(result.sources.internet.attribution,"Data license");
});
test("Default browser preset loads genuine keyless CORS feed; full-network custom is opt-in",()=>{
 let value="intelsky";
 const state={onlineProvider:null};
 const f=vm.runInNewContext(segment+"\nconfiguredOnlineFeed",{
  Date,Math,Number,URL,
  state,$:id=>({value:id==="onlinePreset"?value:"https://feed.example/api/aircraft"}),
  getFeedURL:x=>x
 });
 assert.equal(f(),"https://intelsky.org/api/");
 assert.equal(state.onlineProvider,"intelsky");
 value="off";assert.equal(f(),"");
 value="custom";assert.equal(f(),"https://feed.example/api/aircraft");
});
test("Real browser request does not upload local RF or position to global IntelSky API",async()=>{
 let fetched=null;
 const now=Date.now()/1000;
 const helper=mk({fetch:async(url,options)=>{
  fetched={url,options};
  return {ok:true,async text(){return JSON.stringify({...valid(),now})}};
 }});
 const rows=await helper.fetchInternetFeed();
 assert.equal(fetched.url,"https://intelsky.org/api/");
 assert.equal(fetched.options.credentials,"omit");
 assert.equal(rows.counts.antenna,0);
 assert.equal(rows.counts.internet,1);
});
test("No clandestine tar1090 endpoint is opened when WebUSB owns the one SDR",()=>{
 assert.match(js,/state\.connectionKind==="usb"[\s\S]{0,230}setRadarExpanded\(true\)/);
 assert.match(js,/tar1090 needs a separate live readsb JSON backend/);
 assert.match(js,/status\.active/);
 assert.match(html,/id="expandMap"/);
 assert.match(html,/id="legacyTar"/);
 assert.doesNotMatch(html,/id="fullMap"/);
 assert.match(html,/value="intelsky"/);
 assert.match(html,/value="custom"/);
});
