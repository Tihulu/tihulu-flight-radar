"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.join(__dirname,"..");
const adapter=fs.readFileSync(path.join(root,"tihulu_flight_radar/web/tar1090-adapter.js"),"utf8");
const browser=fs.readFileSync(path.join(root,"tihulu_flight_radar/web/app.js"),"utf8");
const html=fs.readFileSync(path.join(root,"tihulu_flight_radar/web/index.html"),"utf8");
const build=fs.readFileSync(path.join(root,"scripts/build-web-tar1090.sh"),"utf8");
function harness(){
 const handlers={},requests=[];
 let transport;
 const parent={postMessage:(v,origin)=>requests.push({v,origin})};
 const win={parent,addEventListener:(event,fn)=>handlers[event]=fn,
  setInterval:()=>0};
 const status={isConnected:false,setAttribute(){},style:{},textContent:""};
 const document={
  createElement:()=>status,
  addEventListener:(event,fn)=>handlers["document."+event]=fn,
  body:{appendChild:el=>el.isConnected=true}
 };
 const jquery={ajaxTransport:(key,fn)=>{
  assert.equal(key,"+json");transport=fn;
 }};
 vm.runInNewContext(adapter,{window:win,document,jQuery:jquery,
  location:{origin:"https://tihulu.github.io",href:"https://tihulu.github.io/tihulu-flight-radar/tar1090/index.html"},
  Date,Math,Number,String,Map,URL,queueMicrotask});
 return {handlers,requests,parent,win,transport,document,status};
}
async function requestJson(h,url){
 const transport=h.transport({url,dataType:"json"});
 assert.ok(transport,"expected upstream tar1090 AJAX handler for "+url);
 return await new Promise((resolve,reject)=>{
  transport.send({},(status,msg,response)=>status===200?resolve(response.json):reject(Error(msg)));
 });
}
test("Original tar1090 frontend is built from an explicitly pinned upstream source with GPL provenance",()=>{
 assert.match(build,/5d59b1ba2c5e30eb23f1161940367b7767f10ad5/);
 assert.match(build,/wiedehopf\/tar1090/);
 assert.match(build,/UPSTREAM-GPL-LICENSE\.txt/);
 assert.match(build,/html\/index\.html|OUT\/index\.html/);
 assert.match(build,/tihulu-browser-bridge\.js/);
 assert.match(html,/id="fullTar1090"/);
 assert.match(html,/id="tarBrowserShell"/);
 assert.match(html,/id="fullTarFrame"/);
 assert.match(browser,/publishTarBrowserSnapshot/);
 assert.match(browser,/postMessage\(\{type:"tihulu:tar-aircraft"/);
 assert.match(browser,/location\.origin/);
});
test("Full tar frontend always gets live receiver descriptor, no readsb required",async()=>{
 const h=harness();
 const result=await requestJson(h,"data/receiver.json");
 assert.equal(result.version,"TIHULU browser");
 assert.equal(result.readsb,false);
 assert.equal(result.zstd,false);
 assert.equal(result.binCraft,false);
 const empty=await requestJson(h,"data/aircraft.json");
 assert.equal(empty.aircraft.length,0);
 assert.equal(empty.messages,0);
 const history=await requestJson(h,"data/history_0.json");
 assert.equal(history.aircraft.length,0);
});
test("Only same-origin parent may deliver genuine aircraft; stale, invalid and fake position ignored",async()=>{
 const h=harness();
 h.handlers["document.DOMContentLoaded"]();
 assert.equal(h.requests[0].v.type,"tihulu:tar-ready");
 h.handlers.message({origin:"https://attacker.example",source:h.parent,
  data:{type:"tihulu:tar-aircraft",now:Date.now()/1000,aircraft:[{hex:"aabbcc",lat:0,lon:0}]}});
 assert.equal((await requestJson(h,"data/aircraft.json")).aircraft.length,0);
 h.handlers.message({origin:"https://tihulu.github.io",source:h.parent,
  data:{type:"tihulu:tar-aircraft",now:Date.now()/1000-10000,aircraft:[{hex:"aabbcc",lat:0,lon:0}]}});
 assert.equal((await requestJson(h,"data/aircraft.json")).aircraft.length,0);
 h.handlers.message({origin:"https://tihulu.github.io",source:h.parent,
  data:{type:"tihulu:tar-aircraft",now:Date.now()/1000,messages:228,aircraft:[
   {hex:"3C1234",flight:"DLH123",lat:50.94,lon:6.96,seen:2,seen_pos:2,alt_baro:25000,sources:["antenna","internet"]},
   {hex:"dEaDf0",lat:51,lon:7,seen:3,seen_pos:120,sources:["internet"]},
   {hex:"bad hex",lat:51,lon:7,seen:0,seen_pos:0,sources:["internet"]}
  ]}});
 const payload=await requestJson(h,"data/aircraft.json");
 assert.equal(payload.messages,228);
 assert.equal(payload.aircraft.length,2);
 assert.equal(payload.aircraft[0].hex,"3c1234");
 assert.equal(payload.aircraft[0].flight,"DLH123");
 assert.equal(payload.aircraft[0].lat,50.94);
 assert.equal(payload.aircraft[0].alt_baro,25000);
 assert.equal(payload.aircraft[1].lat,undefined,"stale position not shown");
 assert.match(h.status.textContent,/R 1 · I 2/);
 assert.ok(!adapter.includes("Math.random"),"no fabricated aircraft");
});
test("No extra USB or readsb process is started by the tar frontend adapter",()=>{
 assert.doesNotMatch(adapter,/navigator\.usb|requestDevice|claimInterface|systemctl|startService|WebSocket\(/);
 assert.match(adapter,/jQuery\.ajaxTransport\("\+json"/);
 assert.match(adapter,/data\/\(receiver|aircraft/);
});
