"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const base=path.join(__dirname,"../tihulu_flight_radar/web");
const js=fs.readFileSync(path.join(base,"app.js"),"utf8");
const html=fs.readFileSync(path.join(base,"index.html"),"utf8");
const css=fs.readFileSync(path.join(base,"style.css"),"utf8");
test("full upstream tar1090 has a visible primary action, no SDR condition, and direct view URL",()=>{
 assert.match(html,/id="openTarPrimary"/);
 assert.match(html,/id="fullTarFrame"/);
 assert.match(js,/\$\("openTarPrimary"\)\.onclick=\(\)=>void setBrowserTar\(true\)/);
 assert.match(js,/URLSearchParams\(location\.search\)\.get\("view"\)==="tar1090"/);
 assert.match(js,/await resolveTarBrowserURL\(\)/);
 assert.match(js,/publishTarBrowserSnapshot\(\)/);
 assert.match(js,/Internet-only aircraft work without an SDR or readsb/);
 assert.doesNotMatch(js.slice(js.indexOf('async function setBrowserTar('),js.indexOf('$("fullTar1090").onclick')),/readsb\.service|systemctl|navigator\.usb\.requestDevice/);
});
test("native exposes Internet provider layers and applies them via authenticated bridge",()=>{
 assert.match(css,/html\.native \.internet-panel \.internet-controls\{display:flex\}/);
 assert.doesNotMatch(css,/html\.native \.internet-panel \.internet-controls\{display:none\}/);
 assert.match(js,/if\(state\.connectionKind==="bridge"\)\{\s*try\{state\.onlineFeed=configuredOnlineFeed\(\)/);
 assert.match(js,/if\(state\.connectionKind==="bridge"\)\{\s*if\(\$\("onlinePreset"\)\.value==="off"\)/);
 assert.match(js,/args\.set\("net",enabledInternetNetworks\(\)\.join\(","\)\)/);
 assert.match(html,/id="netAdsbLol"/);assert.match(html,/id="netAdsbFi"/);
 assert.match(html,/id="netOpenSky"/);assert.match(html,/id="netIntelSky"/);
});
test("tar1090 embedded map preserves upstream search/filters and genuine I/R markers",()=>{
 const adapter=fs.readFileSync(path.join(base,"tar1090-adapter.js"),"utf8");
 assert.match(adapter,/jQuery\.ajaxTransport\("\+json"/);
 assert.match(adapter,/Internet planes \(I\)/);
 assert.match(adapter,/Both Internet \+ radio \(I\/R\)/);
 assert.match(adapter,/messages:snapshot\.messages/);
 assert.match(adapter,/src\.includes\("antenna"\)&&src\.includes\("internet"\)/);
});
