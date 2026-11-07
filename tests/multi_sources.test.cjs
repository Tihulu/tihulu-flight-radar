"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const {normalise,aggregate,sourceURL,createManager}=require("../tihulu_flight_radar/web/multi_sources.js");
const epoch=()=>Date.now()/1000;
const plane=(hex,lat=50.95,lon=6.97)=>({hex,lat,lon,flight:"TEST",
  seen:2,seen_pos:2,alt_baro:30000});
const reply=data=>({ok:true,headers:{get:()=>null},text:async()=>JSON.stringify(data)});
test("adsb.lol and adsb.fi normalize real timestamp units, reject stale/invalid identities",()=>{
 const now=epoch(),a={now,ac:[plane("3C1234"),plane("!notid"),plane("123456",15,55)]};
 const b={now:now*1000,ac:[plane("3c1234"),plane("abcdef")]};
 assert.equal(normalise("adsblol",a,50.9,7,100,now).aircraft.length,1);
 assert.equal(normalise("adsbfi",b,50.9,7,100,now).aircraft.length,2);
 assert.throws(()=>normalise("adsbfi",{...b,now:(now-200)*1000},50.9,7,100,now),/stale/);
 assert.throws(()=>normalise("adsbfi",{now,ac:{}},50.9,7,100,now),/schema/);
 assert.equal(normalise("adsblol",{now,ac:[{...plane("123456"),seen_pos:99}]},50.9,7,100,now).aircraft.length,0);
});
test("OpenSky vectors are mapped to feet and knots with valid ICAO and recent positions",()=>{
 const now=epoch();
 const vector=["3c1234","TST123","Germany",now-2,now-1,6.97,50.95,
   10000,false,220,165,2,null,10050,"7000",false,0];
 const r=normalise("opensky",{time:now,states:[vector]},50.9,7,100,now);
 assert.equal(r.aircraft.length,1);
 assert.ok(Math.abs(r.aircraft[0].alt_baro-32808)<2);
 assert.ok(Math.abs(r.aircraft[0].gs-427.64)<1);
 assert.equal(r.aircraft[0].position_source,"internet");
});
test("Combine retains one marker per ICAO, raw per-provider observations and no radio provenance",()=>{
 const now=epoch();
 const lol=normalise("adsblol",{now,ac:[plane("3c1234")]},50.9,7,100,now);
 const fi=normalise("adsbfi",{now:now*1000,ac:[plane("3c1234"),plane("abcdef")]},50.9,7,100,now);
 const all=aggregate({adsblol:lol,adsbfi:fi},["adsblol","adsbfi"],now);
 assert.equal(all.unique,2);
 assert.equal(all.counts.adsblol,1);
 assert.equal(all.counts.adsbfi,2);
 const a=all.aircraft.find(x=>x.hex==="3c1234");
 assert.deepEqual(a.internet_providers,["adsblol","adsbfi"]);
 assert.equal(a.sources.join(","),"internet");
 assert.ok(a.observations.internet_sources.adsblol);
 assert.ok(a.observations.internet_sources.adsbfi);
 assert.equal(aggregate({adsblol:lol,adsbfi:fi},["adsbfi"],now).unique,2);
 assert.equal(aggregate({adsblol:lol,adsbfi:fi},["adsblol"],now).unique,1);
 assert.equal(aggregate({adsblol:lol,adsbfi:fi},["adsblol","adsbfi"],now+80).unique,0);
});
test("Network requests only selected bounded providers; no airplanes.live, no RF upload",async()=>{
 const seen=[],now=epoch();
 const fetcher=async (u,options)=>{
  seen.push({u,options});
  return reply({now:u.includes("adsb.fi")?now*1000:now,ac:[plane("3c1234")]});
 };
 const engine=createManager(fetcher);
 const s=await engine.poll(["adsblol","adsbfi"],50.938,6.96,100);
 assert.equal(s.aircraft.length,1);
 assert.equal(s.counts.internet,1);
 assert.equal(s.sources.internet.providers.adsblol.count,1);
 assert.equal(s.sources.internet.providers.adsbfi.count,1);
 assert.equal(seen.length,2);
 assert.ok(seen.every(({u,options})=>u.startsWith("https://proxy.cors.dev/https://")
   &&options.credentials==="omit" &&options.mode==="cors"));
 assert.doesNotMatch(JSON.stringify(seen),/airplanes\.live/);
 await engine.poll(["adsblol","adsbfi"],50.938,6.96,100);
 assert.equal(seen.length,2,"cached identical regions must not re-poll providers");
 const changed=await engine.poll(["adsblol"],50.938,6.96,100);
 assert.equal(changed.aircraft.length,1);
});
test("Offline provider preserves only fresh cached observations, reports outages",async()=>{
 let fail=false,now=epoch();
 const fetcher=async()=>{
  if(fail)throw new TypeError("CORS denied");
  return reply({now,ac:[plane("3c1234")]});
 };
 const engine=createManager(fetcher);
 const ok=await engine.poll(["adsblol"],50.938,6.96,100);
 assert.equal(ok.counts.internet,1);
 fail=true;
 const other=await engine.poll(["adsblol"],48.1,11.5,100);
 assert.equal(other.counts.internet,0);
 assert.equal(other.sources.internet.providers.adsblol.state,"unavailable");
 assert.match(other.sources.internet.providers.adsblol.error,/CORS denied/);
});
test("OpenSky bbox uses a bounded search and source-specific rate controls",()=>{
 const url=sourceURL("opensky",50.938,6.96,100);
 assert.match(url,/https:\/\/opensky-network\.org\/api\/states\/all\?/);
 assert.match(url,/lamin=/);
 assert.throws(()=>sourceURL("airplaneslive",50,7,100),/Unknown/);
});
