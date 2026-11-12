"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const source=fs.readFileSync(path.join(__dirname,"../tihulu_flight_radar/web/app.js"),"utf8");
const match=source.match(/function getBase\(raw\)\{[\s\S]*?\n\}/);
if(!match)throw Error("Bridge URL normalizer not present in web app");
const getBase=vm.runInNewContext(match[0]+"\ngetBase", {URL});

test("bare loopback receiver URL gets http scheme",()=>{
 assert.equal(getBase("127.0.0.1:8510"),"http://127.0.0.1:8510");
 assert.equal(getBase("localhost:8510"),"http://localhost:8510");
 assert.equal(getBase("  http://127.0.0.1:8510/ "), "http://127.0.0.1:8510");
});

test("untrusted or credential-bearing endpoint is not accepted",()=>{
 assert.throws(()=>getBase("http://192.168.1.45:8510"),/HTTPS/);
 assert.throws(()=>getBase("http://evil.example:8510"),/HTTPS/);
 assert.throws(()=>getBase("http://user:pass@127.0.0.1:8510"),/without a path or credentials/);
 assert.throws(()=>getBase("ftp://localhost:8510"),/HTTP/);
});

test("browser map contains a built-in bridge URL and live airplane panels",()=>{
 const html=fs.readFileSync(path.join(__dirname,"../tihulu_flight_radar/web/index.html"),"utf8");
 for(const id of ["bridgeUrl","token","mode","showAntenna","showInternet","showBoth","aircraftRows"])
   assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(source,/tihuluNativeConnect/);
});
