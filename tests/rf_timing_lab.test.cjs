"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const base=path.join(__dirname,"../tihulu_flight_radar/web");
const src=name=>fs.readFileSync(path.join(base,name),"utf8");
const lab=require(path.join(base,"rf_timing_lab.js"));
const cov=require(path.join(base,"receiver_coverage.js"));
function event(index,icao="40621d",segment=0){
 return {receipt_source:"webusb_iq",icao24:icao,sample_index:index,segment,
  sample_rate_hz:2000000,df:17,type_code:11,
  frame_hex:"8d40621d58c382d690c8ac2863a7",decoder_utc_ms:1700000000000+index/2000};
}
test("RF lab processes only real-tagged sample indices, refuses fabricated timing",()=>{
 const session=lab.createSession();
 assert.equal(session.addBatch([event(10),event(2010),event(4010)]),3);
 const report=session.summary();
 assert.equal(report.valid_frames,3);
 assert.equal(report.unique_aircraft,1);
 assert.equal(report.sampled_intervals,2);
 assert.equal(report.median_same_aircraft_interval_ms,1);
 assert.equal(report.median_absolute_deviation_ms,0);
 assert.equal(report.absolute_utc_arrival_accuracy,null);
 assert.equal(report.transmit_timestamp_available,false);
 assert.equal(report.receiver_position_fix_available,false);
 assert.equal(session.addBatch([{...event(5000),receipt_source:"internet"}]),0);
 assert.equal(session.addBatch([{...event(5000),sample_rate_hz:2400000}]),0);
 assert.equal(session.addBatch([event(3000)]),0);
 assert.equal(session.summary().rejected,3);
});
test("Aircraft diversity does not decrease as older frame rows are evicted",()=>{
 const session=lab.createSession(32);
 const events=Array.from({length:60},(_,i)=>event(i*2000+10,(0xa00000+i).toString(16)));
 session.addBatch(events);
 const report=session.summary();
 assert.equal(report.unique_aircraft,60);
 assert.equal(report.unique_retained,32);
 assert.equal(report.retained,32);
 assert.equal(report.receiver_position_fix_available,false);
});
test("Segment breaks are excluded from interarrival statistics",()=>{
 const session=lab.createSession();
 session.addBatch([event(1),event(2001),event(10000000,"40621d",1),
   event(10002000,"40621d",1)]);
 const report=session.summary();
 assert.equal(report.sampled_intervals,2);
 assert.equal(report.interruptions_across_segments,1);
 assert.equal(report.median_same_aircraft_interval_ms,1);
});
test("Bounded recording and offline replay never create live aircraft",()=>{
 const live=lab.createSession(32);
 live.addBatch(Array.from({length:55},(_,i)=>event(2000*i+10)));
 const report=live.summary();
 assert.equal(report.valid_frames,55);
 assert.equal(report.retained,32);
 assert.equal(report.evicted,23);
 const doc=live.serialize();
 assert.equal(doc.mode,"recorded_live");
 assert.equal(doc.events.length,32);
 const offline=lab.createSession();
 const replay=offline.load(JSON.parse(JSON.stringify(doc)));
 assert.equal(replay.mode,"offline_replay");
 assert.equal(offline.serialize().mode,"offline_replay");
 assert.equal(offline.addBatch([event(500000)]),0);
 assert.equal(offline.summary().valid_frames,32);
 assert.throws(()=>offline.load({...doc,format:"unknown"}),/Unsupported/);
 assert.throws(()=>offline.load({...doc,events:[event(50),event(40)]}),/Invalid/);
 assert.throws(()=>offline.load({...doc,events:[{...event(100),receipt_source:"internet"}]}),/Invalid/);
});
test("Worker emits CRC-verified frames with actual sample indices and host timing, not UTC transmit times",()=>{
 const code=src("adsb_worker.mjs").replace(/^export /gm,"");
 const frames=[],handlers={};
 const self={addEventListener(name,cb){handlers[name]=cb;},
  postMessage(message){frames.push(message)}};
 vm.runInNewContext(code,{self,Date,Math,Map,Uint8Array,Uint16Array,
  ArrayBuffer,Number,Array,Object,Set,console});
 const frame=Uint8Array.from("8d40621d58c382d690c8ac2863a7".match(/../g),x=>parseInt(x,16));
 const iq=new Uint8Array((40+16+224+32)*2).fill(127);
 const set=p=>{iq[(40+p)*2]=255;iq[(40+p)*2+1]=255};
 for(const p of [0,2,7,9])set(p);
 for(let bit=0;bit<112;bit++)
  set(16+bit*2+((frame[bit>>3]>>(7-(bit&7)))&1?0:1));
 handlers.message({data:{type:"reset"}});
 handlers.message({data:{type:"iq",buffer:iq.buffer,host_read_ms:5}});
 const snapshot=frames.find(x=>x.type==="snapshot");
 assert.ok(snapshot,"worker publishes live CRC observations");
 assert.equal(snapshot.timing_events.length,1);
 const found=snapshot.timing_events[0];
 assert.equal(found.icao24,"40621d");
 assert.equal(found.sample_index,40);
 assert.equal(found.frame_hex,"8d40621d58c382d690c8ac2863a7");
 assert.equal(snapshot.timing_stats.usb_blocks,1);
 assert.equal(snapshot.timing_stats.host_read_last_ms,5);
 assert.equal(snapshot.aircraft[0].rf_timing.transmit_timestamp_utc,null);
 assert.equal(snapshot.aircraft[0].rf_timing.receiver_hardware_utc,null);
});
test("RF horizon applies up to 64 genuine independent aircraft; number is not accuracy",()=>{
 const rows=[];
 for(let i=0;i<10;i++){
  const hex=(0xa00000+i).toString(16);
  const x={hex,lat:50.5+i*.025,lon:6.9+i*.02,alt_baro:33000,
   seen:1,seen_pos:1,position_source:"antenna",sources:["antenna"]};
  x.observations={antenna:{hex,lat:x.lat,lon:x.lon,
    alt_baro:x.alt_baro,seen:1,seen_pos:1}};
  rows.push(x);
 }
 const r=cov.compute(rows);
 assert.equal(r.count,10);
 assert.equal(r.constraintsUsed,10);
 assert.equal(r.circles.length,6);
 assert.equal(r.status,"region");
 assert.equal(Object.prototype.hasOwnProperty.call(r,"accuracyMeters"),false);
});
test("Stationary receiver history only accepts real RF and expires after two hours",()=>{
 const make=(hex,lat,lon)=>{
  const a={hex,lat,lon,alt_baro:30000,seen:1,seen_pos:1,
   position_source:"antenna",sources:["antenna"]};
  a.observations={antenna:{hex,lat,lon,alt_baro:30000,seen:1,seen_pos:1}};
  return a;
 };
 const now=Date.now();
 const rows=[make("a00001",50.7,6.7),make("a00002",50.2,7.5),
  make("a00003",51.1,6.2),make("a00004",50.6,7.9)];
 const history=rows.map(a=>cov.recordedCircle(a,now));
 assert.ok(history.every(Boolean));
 const fromHistory=cov.compute([],history);
 assert.equal(fromHistory.count,4);
 assert.equal(fromHistory.status,"region");
 assert.equal(fromHistory.circles.length,4);
 assert.equal(cov.recordedCircle({...rows[0],position_source:"internet"}),null);
 assert.equal(cov.compute([],history.map(x=>({...x,capturedAtMs:now-3*3600000}))).count,0);
});
test("Shared offline UI, native bridge and service-worker expose laboratory without network upload",()=>{
 const html=src("index.html"),app=src("app.js"),sw=src("sw.js"),
  bridge=fs.readFileSync(path.join(__dirname,"../tihulu_flight_radar/bridge.py"),"utf8"),
  native=fs.readFileSync(path.join(__dirname,"../tihulu_flight_radar/native.py"),"utf8");
 for(const id of ["rfRemember","rfClearHistory","timingMode","timingFrames","timingUnique","timingInterval",
   "timingMad","timingHostRead","timingRetained","timingEvents",
   "timingPlot","timingPause","timingReset","timingSaveJson",
   "timingSaveCsv","timingImport","timingQuality"])
  assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/rf_timing_lab\.js/);
 assert.match(sw,/shell-v31/);
 assert.match(sw,/rf_timing_lab\.js/);
 assert.match(bridge,/rf_timing_lab\.js/);
 assert.match(app,/window\.tihuluTimingBatch/);
 assert.match(app,/timingLab\.load/);
 assert.match(app,/timingLab\.serialize/);
 assert.match(native,/downloadRequested\.connect\(self\._save_web_download\)/);
 assert.doesNotMatch(src("rf_timing_lab.js"),/\bfetch\s*\(|XMLHttpRequest|WebSocket/);
});
