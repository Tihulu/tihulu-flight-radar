const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
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
