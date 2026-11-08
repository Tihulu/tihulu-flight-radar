"use strict";
/* Pure, offline-only RF Timing Laboratory model. This module never requests
 * Internet access and never derives distance from an unsynchronized clock.
 * Imported observations are REPLAY data and never enter the live radar map.
 */
const TihuluTimingLab=(()=>{
 const FORMAT="tihulu.rf-timing-lab.v1",MAX_EVENTS=4000;
 const finite=x=>typeof x==="number"&&Number.isFinite(x);
 const median=values=>{
  if(!values.length)return null;
  const a=values.slice().sort((x,y)=>x-y),k=Math.floor(a.length/2);
  return a.length%2?a[k]:(a[k-1]+a[k])/2;
 };
 function validEvent(raw){
  if(!raw || raw.receipt_source!=="webusb_iq" ||
     !/^[a-f0-9]{6}$/i.test(String(raw.icao24||"")) ||
     !Number.isSafeInteger(raw.sample_index)||raw.sample_index<0 ||
     !Number.isInteger(raw.segment)||raw.segment<0||raw.segment>1000000 ||
     ![17,18].includes(raw.df) || !Number.isInteger(raw.type_code) ||
     raw.type_code<0||raw.type_code>31 ||
     !/^[a-f0-9]{28}$/i.test(String(raw.frame_hex||"")) ||
     !finite(raw.decoder_utc_ms)||raw.decoder_utc_ms<0 ||
     raw.sample_rate_hz!==2000000)return null;
  return {receipt_source:"webusb_iq",icao24:String(raw.icao24).toLowerCase(),
    sample_index:raw.sample_index,segment:raw.segment,
    df:raw.df,type_code:raw.type_code,frame_hex:String(raw.frame_hex).toLowerCase(),
    decoder_utc_ms:raw.decoder_utc_ms,sample_rate_hz:2000000};
 }
 function createSession(limit=MAX_EVENTS){
  const maximum=Math.max(32,Math.min(MAX_EVENTS,Math.floor(limit)||MAX_EVENTS));
  let records=[],received=0,evicted=0,rejected=0,mode="live";
  let telemetry=null,sessionStartedMs=null,lastSample=-1;
  function reset(){
   records=[];received=0;evicted=0;rejected=0;telemetry=null;
   sessionStartedMs=null;lastSample=-1;mode="live";
  }
  function addBatch(events,stats){
   if(mode!=="live")return 0;
   if(stats&&typeof stats==="object")telemetry={
    sample_rate_hz:2000000,
    iq_sample_count:finite(stats.iq_sample_count)?Math.max(0,stats.iq_sample_count):0,
    usb_blocks:finite(stats.usb_blocks)?Math.max(0,stats.usb_blocks):0,
    host_read_last_ms:finite(stats.host_read_last_ms)?Math.max(0,stats.host_read_last_ms):null,
    host_read_max_ms:finite(stats.host_read_max_ms)?Math.max(0,stats.host_read_max_ms):null,
    host_read_mean_ms:finite(stats.host_read_mean_ms)?Math.max(0,stats.host_read_mean_ms):null,
    frames_not_forwarded:finite(stats.frames_not_forwarded)?Math.max(0,stats.frames_not_forwarded):0,
    estimated_usb_gap_count:finite(stats.estimated_usb_gap_count)?Math.max(0,stats.estimated_usb_gap_count):0,
    note:"Host delivery delay is not RF propagation or a proven sample-loss count"
   };
   if(!Array.isArray(events))return 0;
   let added=0;
   for(const item of events.slice(0,1024)){
    const e=validEvent(item);
    if(!e||e.sample_index<=lastSample){rejected++;continue}
    lastSample=e.sample_index;
    if(sessionStartedMs===null)sessionStartedMs=e.decoder_utc_ms;
    records.push(e);received++;added++;
   }
   if(records.length>maximum){
    const n=records.length-maximum;records.splice(0,n);evicted+=n;
   }
   return added;
  }
  function summary(){
   const byId=new Map(),intervals=[],gaps=new Map();
   for(const e of records){
    let s=byId.get(e.icao24);
    if(!s){s={icao24:e.icao24,frames:0,last_segment:null,last_sample:null,
       last_decoder_utc_ms:null};byId.set(e.icao24,s)}
    if(s.last_sample!==null&&s.last_segment===e.segment&&e.sample_index>s.last_sample)
     intervals.push((e.sample_index-s.last_sample)/e.sample_rate_hz*1000);
    if(s.last_segment!==null&&s.last_segment!==e.segment)
     gaps.set(e.icao24,(gaps.get(e.icao24)||0)+1);
    s.last_sample=e.sample_index;s.last_segment=e.segment;
    s.last_decoder_utc_ms=e.decoder_utc_ms;s.frames++;
   }
   const middle=median(intervals);
   const mad=middle===null?null:median(intervals.map(x=>Math.abs(x-middle)));
   return {format:FORMAT,mode,valid_frames:received,retained:records.length,
    unique_aircraft:byId.size,evicted,rejected,
    sampled_intervals:intervals.length,
    median_same_aircraft_interval_ms:middle,
    median_absolute_deviation_ms:mad,
    interruptions_across_segments:[...gaps.values()].reduce((a,b)=>a+b,0),
    nominal_sample_period_us:0.5,absolute_utc_arrival_accuracy:null,
    transmit_timestamp_available:false,propagation_range_available:false,
    receiver_position_fix_available:false,
    coverage_note:"More independently received aircraft may narrow a modeled radio-horizon area; they do not guarantee better positioning accuracy.",
    telemetry,aircraft:[...byId.values()].sort((a,b)=>b.frames-a.frames).slice(0,30)};
  }
  function serialize(){
   return {format:FORMAT,provenance:"local unsynchronized WebUSB I/Q sample clock",
    exported_utc:new Date().toISOString(),sample_rate_hz:2000000,
    mode:"recorded_live",summary:summary(),events:records.slice()};
  }
  function load(raw){
   if(!raw||raw.format!==FORMAT||raw.sample_rate_hz!==2000000||
      !Array.isArray(raw.events)||raw.events.length>MAX_EVENTS)
    throw Error("Unsupported or oversized RF timing session");
   const clean=[];
   let previous=-1;
   for(const item of raw.events){
    const row=validEvent(item);
    if(!row||row.sample_index<=previous)
     throw Error("Invalid, unsorted or non-WebUSB timing record");
    clean.push(row);previous=row.sample_index;
   }
   // Import never creates live RF observations, a GPS position, or a feed.
   reset();mode="offline_replay";records=clean;received=clean.length;
   lastSample=previous;telemetry=null;
   return summary();
  }
  function recent(n=12){return records.slice(-Math.min(100,Math.max(0,n))).reverse();}
  return {reset,addBatch,summary,serialize,load,recent};
 }
 return {FORMAT,MAX_EVENTS,validEvent,median,createSession};
})();
if(typeof module!=="undefined"&&module.exports)module.exports=TihuluTimingLab;
if(typeof window!=="undefined")window.TihuluTimingLab=TihuluTimingLab;
