"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const {pathToFileURL}=require("node:url");
const root=path.join(__dirname,"../tihulu_flight_radar/web");
const read=name=>fs.readFileSync(path.join(root,name),"utf8");
const coverage=require(path.join(root,"receiver_coverage.js"));
const hex=x=>new Uint8Array(x.match(/../g).map(b=>parseInt(b,16)));
const EVEN=hex("8D40621D58C382D690C8AC2863A7");

function sample(hexid,lat,lon,kind="antenna"){
 const a={hex:hexid,lat,lon,alt_baro:30000,seen:1,seen_pos:1,
   sources:[kind],position_source:kind,
   observations:{}};
 a.observations[kind]={hex:hexid,lat,lon,alt_baro:30000,seen:1,seen_pos:1};
 return a;
}
test("Four real positioned RF aircraft produce possible horizon area, not a GPS fix",()=>{
 const rows=[
  sample("a00001",50.7,6.7),sample("a00002",50.2,7.5),
  sample("a00003",51.1,6.2),sample("a00004",50.6,7.9)
 ];
 const result=coverage.compute(rows);
 assert.equal(result.status,"region");
 assert.equal(result.count,4);
 assert.equal(result.circles.length,4);
 assert.ok(result.region.extentKm>0);
 assert.ok(result.region.possibleSamples.length>1);
 assert.equal(Object.hasOwn(result,"receiverGPS"),false);
});
test("Three genuine positioned RF aircraft permit only a coarse model region",()=>{
 const radios=[
  sample("a00001",50.7,6.7),sample("a00002",50.2,7.5),
  sample("a00003",51.1,6.2)
 ];
 const result=coverage.compute(radios);
 assert.equal(result.status,"region");
 assert.equal(result.count,3);
 assert.equal(result.constraintsUsed,3);
 assert.equal(result.circles.length,3);
 assert.equal(result.region.receiver_position_measured,false);
 assert.equal(result.region.accuracy_km,null);
 assert.ok(result.region.possibleSamples.some(p=>
  p.lat===result.region.lat&&p.lon===result.region.lon),
  "representative centre must be among feasible model samples");
 assert.equal(Object.hasOwn(result,"receiverGPS"),false);
});
test("Internet, invalid source, stale coordinates and insufficient radio aircraft never create a fix",()=>{
 const radios=[sample("a00001",50.7,6.7),sample("a00002",50.2,7.5)];
 const internet=sample("a00004",50.6,7.9,"internet");
 assert.equal(coverage.compute([...radios,internet]).status,"insufficient");
 assert.equal(coverage.compute([...radios,internet]).count,2);
 const mixed=sample("a00005",50.4,7.7);
 mixed.sources.push("internet");
 mixed.position_source="internet";
 assert.equal(coverage.compute([...radios,mixed]).status,"insufficient");
 const stale=sample("a00006",50.4,7.7);
 stale.observations.antenna.seen_pos=90;
 assert.equal(coverage.compute([...radios,stale]).status,"insufficient");
 const duplicate=sample("a00001",50.8,6.7);
 assert.equal(coverage.compute([...radios,duplicate]).count,2);
});
test("Unit selectors, close-on-outside click, raw JSON and timing claims in common web/Qt UI",()=>{
 const html=read("index.html"),js=read("app.js"),css=read("style.css");
 for(const id of ["unitSystem","altitudeColumn","speedColumn","aircraftPopup",
   "popupClose","popupTiming","rawAircraftPanel","showRfCoverage","rfCoverageStatus",
   "rfLocate","rfLocationStatus","rfLocationDetails","rfModelCoordinates",
   "rfModelExtent","rfModelAircraft"])
   assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/Altitude \(ft\)/);
 assert.match(html,/Speed \(kt\)/);
 assert.match(js,/showAltitude\(a,false\),showSpeed\(a,false\)/);
 assert.match(js,/popupClose/);
 assert.match(js,/closePopup\(\)/);
 assert.match(js,/observations\?\.antenna/);
 assert.match(js,/Transmit–receive delay: not computable/);
 assert.match(css,/\.aircraft-popup\[hidden\]/);
 assert.match(css,/\.rf-locate-button/);
 assert.match(js,/\$\("rfLocate"\)\.onclick/);
 assert.match(js,/function paintRfModelCentre\(/);
 assert.match(js,/if\(\$\("showRfCoverage"\)\.checked\)paintRfCoverage\(\);\s*paintRfModelCentre\(\)/);
 assert.doesNotMatch(js,/\$\("rfLocate"\)\.onclick[\s\S]{0,500}navigator\.geolocation/);
});
test("Decoder retains ADC sample index but cannot invent aircraft TX timestamp",async()=>{
 const dec=await import(pathToFileURL(path.join(root,"adsb_worker.mjs")).href);
 const iq=new Uint8Array((40+16+112*2+32)*2).fill(127);
 const set=p=>{iq[(40+p)*2]=255;iq[(40+p)*2+1]=255;};
 for(const p of [0,2,7,9])set(p);
 for(let b=0;b<112;b++)set(16+b*2+((EVEN[b>>3]>>(7-(b&7)))&1?0:1));
 const candidates=dec.extractFrameCandidates(iq);
 assert.equal(candidates.length,1);
 assert.equal(candidates[0].sampleOffset,40);
 const sampleTime={
  arrival_sample_index:123456,
  sample_period_us:0.5,
  decoder_observed_unix_ms:1000000,
  transmit_timestamp_utc:null,
  receiver_hardware_utc:null
 };
 const store=new dec.BrowserAircraftStore();
 assert.equal(store.ingest(EVEN,1000000,sampleTime),true);
 const row=store.snapshot(1000001)[0];
 assert.deepEqual(row.rf_timing,sampleTime);
 assert.equal(row.rf_timing.transmit_timestamp_utc,null);
 assert.equal(row.rf_timing.receiver_hardware_utc,null);
});
