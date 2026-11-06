"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const {pathToFileURL}=require("node:url");

const root=path.join(__dirname,"../tihulu_flight_radar/web");
const decoder=import(pathToFileURL(path.join(root,"adsb_worker.mjs")).href);
const hex=x=>new Uint8Array((x.match(/../g)||[]).map(p=>parseInt(p,16)));
// Known verified ADS-B DF17 odd/even airborne CPR pair from ADS-B Decoding
// Guide (ICAO 40621D), not fabricated positions:
const EVEN=hex("8D40621D58C382D690C8AC2863A7");
const ODD=hex("8D40621D58C386435CC412692AD6");

test("CRC guard accepts independently documented Mode S frames and rejects bit corruption",async()=>{
 const d=await decoder;
 assert.equal(d.crcValid(EVEN),true);
 assert.equal(d.crcValid(ODD),true);
 const bad=EVEN.slice();bad[7]^=0x08;
 assert.equal(d.crcValid(bad),false);
 assert.equal(d.decodeFrame(bad),null);
 assert.equal(d.crcValid(new Uint8Array(14)),false);
});
test("Global CPR decodes verified genuine even/odd pair only, requires freshness",async()=>{
 const {decodeFrame,decodeGlobalCPR,BrowserAircraftStore}=await decoder;
 const odd=decodeFrame(ODD,1000);
 const even=decodeFrame(EVEN,2000);
 assert.equal(odd.hex,"40621d");
 assert.equal(even.hex,"40621d");
 assert.equal(odd.cpr.odd,true);
 assert.equal(even.cpr.odd,false);
 const pos=decodeGlobalCPR(even.cpr,odd.cpr);
 assert.ok(pos,"known even/odd pair should yield a position");
 assert.ok(Math.abs(pos.lat-52.2572)<0.002);
 assert.ok(Math.abs(pos.lon-3.91937)<0.002);
 assert.equal(decodeGlobalCPR({...even.cpr,time:40000},odd.cpr),null);
 const store=new BrowserAircraftStore();
 assert.equal(store.ingest(ODD,1000),true);
 assert.equal(store.snapshot(1500)[0].lat,undefined,"one CPR frame is NOT a location");
 assert.equal(store.ingest(EVEN,2000),true);
 const row=store.snapshot(2100)[0];
 assert.ok(Math.abs(row.lat-52.2572)<0.002);
 assert.ok(Math.abs(row.lon-3.91937)<0.002);
 assert.equal(store.snapshot(63000).length,0,"stale RF aircraft is removed");
});
function synthesize(frame){
 const n=40+16+112*2+32;
 const out=new Uint8Array(n*2);
 for(let i=0;i<n;i++){out[i*2]=127;out[i*2+1]=127;}
 const set=(sample)=>{const at=(40+sample)*2;out[at]=255;out[at+1]=255;};
 for(const p of [0,2,7,9])set(p);
 for(let bit=0;bit<112;bit++){
  const one=(frame[bit>>3]>>(7-(bit&7)))&1;
  set(16+bit*2+(one?0:1));
 }
 return out;
}
test("2 Msps IQ preamble demodulation yields a known 112-bit CRC-verified frame",async()=>{
 const d=await decoder;
 const iq=synthesize(EVEN);
 const frames=d.extractFrames(iq);
 assert.equal(frames.length,1);
 assert.deepEqual([...frames[0]],[...EVEN]);
 const zero=new Uint8Array(iq.length).fill(127);
 assert.equal(d.extractFrames(zero).length,0);
 const corrupt=EVEN.slice();corrupt[5]^=0x01;
 assert.equal(d.extractFrames(synthesize(corrupt)).length,0);
});
test("Decoder worker does not load a native backend or transfer IQ to the Internet",()=>{
 const text=fs.readFileSync(path.join(root,"adsb_worker.mjs"),"utf8");
 assert.doesNotMatch(text,/fetch\s*\(|XMLHttpRequest|WebSocket|https?:\/\//);
 assert.match(text,/CRC_POLY/);
 assert.match(text,/AIRCRAFT_TTL_MS/);
 assert.match(text,/postMessage\(\{type:"ack"\}\)/);
});
test("GitHub Pages includes an explicit direct WebUSB hard stop and browser worker",()=>{
 const html=fs.readFileSync(path.join(root,"index.html"),"utf8");
 const usb=fs.readFileSync(path.join(root,"browser_usb.mjs"),"utf8");
 const app=fs.readFileSync(path.join(root,"app.js"),"utf8");
 for(const name of ["usbStart","usbStop","usbStatus"])
  assert.match(html,new RegExp('id="'+name+'"'));
 assert.match(html,/type="module" src="\.\/browser_usb\.mjs"/);
 assert.match(usb,/navigator\.usb\.requestDevice/);
 assert.match(usb,/readSamples\(65536\)/);
 assert.match(usb,/new Worker\("\.\/adsb_worker\.mjs"/);
 assert.match(usb,/visibilitychange/);
 assert.match(usb,/pagehide/);
 assert.match(app,/window\.tihuluUsbSnapshot/);
 assert.match(app,/browserSourceResult/);
 assert.match(app,/position_source:"antenna"/);
});
