const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const root=path.resolve(__dirname,"..");
const read=p=>fs.readFileSync(path.join(root,p),"utf8");

test("desktop hides redundant Install desktop link without removing website installer",()=>{
 const css=read("tihulu_flight_radar/web/style.css");
 const html=read("tihulu_flight_radar/web/index.html");
 const app=read("tihulu_flight_radar/web/app.js");
 assert.match(css,/html\.native \.install-link\s*\{display:none!important\}/);
 assert.match(html,/class="install-link".*Install desktop/);
 assert.match(app,/desktop-installed-label/);
 assert.match(app,/Desktop app · installed/);
});

test("native pairing is established before any optional aircraft refresh",()=>{
 const app=read("tihulu_flight_radar/web/app.js");
 const start=app.indexOf("async function connect(){");
 const end=app.indexOf("function disconnect(){",start);
 const handler=app.slice(start,end);
 assert.ok(start>0&&end>start);
 assert.match(handler,/await checkReceiver\(\)/);
 assert.match(handler,/state\.connected=true;[\s\S]*?connection\(true,[\s\S]*?try\{await refresh\(true\);\}/);
 assert.match(handler,/Receiver pairing retained; aircraft refresh failed/);
 assert.match(handler,/Receiver bridge paired; initial data unavailable/);
 assert.doesNotMatch(handler,/state\.connected=true;\s*await refresh\(true\);\s*connection\(true/);
});

test("native wrapper never downgrades receiver status merely because public feed fails",()=>{
 const app=read("tihulu_flight_radar/web/app.js");
 assert.match(app,/window\.tihuluNativeDesktop=true/);
 assert.match(app,/Desktop receiver pairing failed/);
 assert.match(app,/state\.connectionKind==="bridge" && state\.token/);
 const native=read("tihulu_flight_radar/native.py");
 assert.match(native,/runJavaScript\(script, result\)/);
 assert.match(native,/attempt < 16/);
});

function simulateNativePair({authorized=true,refreshFails=true}={}){
 const text=read("tihulu_flight_radar/web/app.js");
 const start=text.indexOf("async function connect(){");
 const end=text.indexOf("function disconnect(){",start);
 assert.ok(start>=0&&end>start);
 const controls={token:{value:"private-temporary-token"},
   bridgeUrl:{value:"http://127.0.0.1:12345"},mode:{value:"hybrid"},
   receiverStatus:{textContent:"",dataset:{}},
   start:{disabled:true},stop:{disabled:true},restart:{disabled:true}};
 const statuses=[];
 const state={timer:null,connectionKind:"none",connected:false,
   base:"",token:"",onlineFeed:"",moved:false};
 const context={
   state,window:{tihuluNativeDesktop:true},document:{hidden:false},
   $:name=>controls[name]||(controls[name]={value:"",textContent:"",dataset:{}}),
   configuredOnlineFeed:()=> "https://example.invalid/feed",
   getBase:raw=>raw,
   checkReceiver:async()=>{
     if(!authorized)throw Error("unauthorized bridge");
     controls.start.disabled=false;
   },
   refresh:async()=>{if(refreshFails)throw Error("no aircraft.json yet");},
   connection:(on,label)=>{state.connected=on;statuses.push(label);},
   notice:message=>statuses.push(message),
   setInterval:()=>123,clearInterval:()=>{},
   api:async()=>({}),applyPlaceToFlightRadar:()=>{},
   displayUsbSnapshot:()=>{},Error,
 };
 const connect=vm.runInNewContext(text.slice(start,end)+"\nconnect",context);
 return {run:()=>connect(),state,controls,statuses};
}

test("a healthy native handshake survives an aircraft refresh failure",async()=>{
 const testCase=simulateNativePair();
 await testCase.run();
 assert.equal(testCase.state.connectionKind,"bridge");
 assert.equal(testCase.state.connected,true);
 assert.equal(testCase.state.token,"private-temporary-token");
 assert.equal(testCase.controls.token.value,"");
 assert.ok(testCase.statuses.some(s=>s.includes("Desktop paired")));
});

test("an unauthorized native handshake does not falsely mark receiver as paired",async()=>{
 const testCase=simulateNativePair({authorized:false});
 await testCase.run();
 assert.equal(testCase.state.connectionKind,"none");
 assert.equal(testCase.state.connected,false);
 assert.ok(testCase.statuses.some(s=>s.includes("Desktop receiver pairing failed")));
});
