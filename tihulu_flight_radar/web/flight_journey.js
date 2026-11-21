"use strict";
/* Aircraft journey details: data provenance is mandatory.
 * ADS-B gives radio callsign/position/ground events; NOT airport schedules.
 * adsbdb provides callsign route airports; NOT departure/arrival times.
 * Never write adsbdb route information to a database (source license).
 */
const TihuluFlightJourney=(()=>{
 const CALL=/^[A-Z0-9]{3,10}$/,HEX=/^[0-9a-f]{6}$/i;
 const trim=(v,max=110)=>typeof v==="string"&&v.trim().length>0&&
  v.trim().length<=max?v.trim():null;
 function callsign(a){
  const rows=[a?.flight_source_fields,a?.observations?.internet?.flight_source_fields,
   a?.observations?.internet,a];
  for(const row of rows){
   const c=trim(row?.flight_icao)||trim(row?.flight_iata)||
    trim(row?.flight)||trim(row?.callsign);
   if(c&&CALL.test(c.toUpperCase().replace(/\s/g,"")))
    return c.toUpperCase().replace(/\s/g,"");
  }
  return null;
 }
 function airport(raw){
  if(typeof raw==="string"){
   const code=raw.trim().toUpperCase();
   return /^[A-Z0-9]{3,4}$/.test(code)?
    {code,name:null,municipality:null}:null;
  }
  if(!raw||typeof raw!=="object")return null;
  const code=trim(raw.iata_code)||trim(raw.iata)||trim(raw.icao_code)||
   trim(raw.icao)||trim(raw.code);
  const value=code?.toUpperCase();
  if(!value||!/^[A-Z0-9]{3,4}$/.test(value))return null;
  return {code:value,name:trim(raw.name,110),
   municipality:trim(raw.municipality)||trim(raw.city)};
 }
 function epoch(value){
  if(typeof value==="number"&&Number.isFinite(value)){
   const ms=value<1e11?value*1000:value;
   return ms>=Date.UTC(2010,0,1)&&ms<=Date.UTC(2100,0,1)?ms:null;
  }
  if(typeof value==="string"&&/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d)$/i.test(value)){
   const ms=Date.parse(value);
   return Number.isFinite(ms)&&ms>=Date.UTC(2010,0,1)&&
    ms<=Date.UTC(2100,0,1)?ms:null;
  }
  return null; // No guessing timezone from HH:MM or local date-only strings.
 }
 function fromAdsbdb(payload,expectedCallsign){
  const raw=payload?.response?.flightroute;
  if(!raw||typeof raw!=="object")return null;
  const expected=trim(expectedCallsign,10)?.replace(/\s/g,"").toUpperCase();
  const returned=[raw.callsign,raw.callsign_icao,raw.callsign_iata]
   .map(v=>trim(v,10)?.toUpperCase()).filter(Boolean);
  if(!expected||!CALL.test(expected)||returned.length&&
   !returned.includes(expected))return null;
  const origin=airport(raw.origin),destination=airport(raw.destination);
  if(!origin&&!destination)return null;
  return {origin,destination,midpoint:airport(raw.midpoint),times:{},
   source:"adsbdb callsign route · online (not live schedule)",
   matchedCallsign:expected,airline:trim(raw.airline?.name,110),at:Date.now()};
 }
 function utcEpoch(value){
  // Only parse strings expressly documented by the source as UTC.
  if(typeof value!=="string")return null;
  const input=value.trim().replace(" ","T");
  const match=/^(\d{4}-\d\d-\d\dT\d\d:\d\d)(?::(\d\d))?$/.exec(input);
  return match?epoch(match[1]+":"+(match[2]||"00")+"Z"):null;
 }
 function timesFrom(row){
  const t={},d=row?.departure,ar=row?.arrival;
  const fields=[["departScheduled",d?.scheduled,row?.departure_scheduled,
    row?.dep_scheduled,row?.dep_time_ts,utcEpoch(row?.dep_time_utc)],
   ["departEstimated",d?.estimated,row?.departure_estimated,
    row?.dep_estimated,row?.dep_estimated_ts,utcEpoch(row?.dep_estimated_utc)],
   ["departActual",d?.actual,row?.departure_actual,row?.dep_actual,
    row?.dep_actual_ts,utcEpoch(row?.dep_actual_utc)],
   ["arriveScheduled",ar?.scheduled,row?.arrival_scheduled,
    row?.arr_scheduled,row?.arr_time_ts,utcEpoch(row?.arr_time_utc)],
   ["arriveEstimated",ar?.estimated,row?.arrival_estimated,
    row?.arr_estimated,row?.arr_estimated_ts,utcEpoch(row?.arr_estimated_utc)],
   ["arriveActual",ar?.actual,row?.arrival_actual,row?.arr_actual,
    row?.arr_actual_ts,utcEpoch(row?.arr_actual_utc)]];
  for(const [key,...values] of fields){
   const stamp=values.map(epoch).find(Number.isFinite);
   if(stamp!==undefined)t[key]=stamp;
  }
  return t;
 }
 function fromProvider(a){
  if(!a?.sources?.includes("internet")&&!a?.flight_source_fields)return null;
  const rows=[a?.flight_source_fields,
   a?.observations?.internet?.flight_source_fields,
   a?.observations?.internet,a].filter(Boolean);
  let origin=null,destination=null,midpoint=null,times={};
  for(const row of rows){
   origin ||= airport(row.origin||row.departure?.airport||
    row.departure_airport||row.dep_iata||row.dep_icao);
   destination ||= airport(row.destination||row.arrival?.airport||
    row.arrival_airport||row.arr_iata||row.arr_icao);
   midpoint ||= airport(row.midpoint);
   times={...times,...timesFrom(row)};
  }
  if(!origin&&!destination&&!Object.keys(times).length)return null;
  return {origin,destination,midpoint,times,source:"Internet flight provider metadata",
   matchedCallsign:callsign(a),at:Date.now()};
 }
 function combine(provider,lookedUp){
  if(!provider)return lookedUp||null;
  if(!lookedUp)return provider;
  // Route lookup is a separate callsign-level (not aircraft-level) database.
  return {...provider,origin:provider.origin||lookedUp.origin,
   destination:provider.destination||lookedUp.destination,
   midpoint:provider.midpoint||lookedUp.midpoint,
   times:{...(lookedUp.times||{}),...(provider.times||{})},
   source:provider.origin&&provider.destination?provider.source:
    provider.source+" + "+lookedUp.source};
 }
 function formatAirport(entry){
  if(!entry)return "Not verified";
  return entry.code+(entry.municipality?" · "+entry.municipality:
   entry.name?" · "+entry.name:"");
 }
 function shortRoute(journey){
  if(!journey?.origin&&!journey?.destination)return "Route unknown";
  return (journey.origin?.code||"—")+" → "+(journey.destination?.code||"—");
 }
 function formatTime(ms,zone="local"){
  if(!Number.isFinite(ms))return "—";
  const options={day:"2-digit",month:"2-digit",hour:"2-digit",
   minute:"2-digit",hour12:false};
  if(zone==="UTC")options.timeZone="UTC";
  return new Intl.DateTimeFormat("en-GB",options).format(new Date(ms))+
   (zone==="UTC"?" UTC":" (local)");
 }
 function timeSummary(j){
  if(!j?.times)return "Timetable unavailable";
  const t=j.times;
  const dep=t.departActual??t.departEstimated??t.departScheduled;
  const arr=t.arriveActual??t.arriveEstimated??t.arriveScheduled;
  if(!Number.isFinite(dep)&&!Number.isFinite(arr))return "Timetable unavailable";
  const kind=(keys)=>t[keys[0]]!=null?"actual":t[keys[1]]!=null?"estimated":"scheduled";
  return "DEP "+(Number.isFinite(dep)?formatTime(dep)+" "+kind(
   ["departActual","departEstimated","departScheduled"]):"—")+
   " · ARR "+(Number.isFinite(arr)?formatTime(arr)+" "+kind(
    ["arriveActual","arriveEstimated","arriveScheduled"]):"—");
 }
 const tracks=new Map();
 function radioState(a){
  const r=a?.observations?.antenna;
  if(!r||!Array.isArray(a.sources)||!a.sources.includes("antenna")||
   !HEX.test(String(a.hex||"")))return null;
  if(!Number.isFinite(r.seen)||r.seen<0||r.seen>12)return null;
  const g=r.alt_baro=== "ground" ||r.airground==="ground" ||
   r.on_ground===true;
  const air=Number.isFinite(r.alt_baro)||Number.isFinite(r.alt_geom)||
   r.airground==="airborne"||r.on_ground===false;
  return g?"ground":air?"air":null;
 }
 function observeRadio(rows,nowMs=Date.now()){
  const prune=nowMs-18*3600*1000;
  for(const [hex,v] of tracks)if(v.lastAt<prune)tracks.delete(hex);
  for(const a of Array.isArray(rows)?rows:[]){
   const kind=radioState(a);if(!kind)continue;
   const key=String(a.hex).toLowerCase(),rf=a.observations.antenna;
   const stamp=nowMs-Math.min(12000,Math.max(0,rf.seen*1000));
   let t=tracks.get(key);
   const call=callsign(a);
   if(!t||call&&t.call&&t.call!==call){
    t={call,firstAt:stamp,lastAt:stamp,stable:kind,
     lastProcessedAt:stamp,pending:null,pendingAt:null,departure:null,arrival:null};
   }else{
    if(stamp<=t.lastProcessedAt+1000)continue;
    t.lastAt=stamp;t.lastProcessedAt=stamp;
    if(call)t.call=call;
    if(kind===t.stable){t.pending=null;t.pendingAt=null;}
    else if(t.pending===kind&&stamp-t.pendingAt>=3000){
     // Observed state transition only after two distinct fresh SDR updates.
     // This is NOT a scheduled/actual runway timestamp or airport identity.
     if(t.stable==="ground"&&kind==="air")t.departure=stamp;
     if(t.stable==="air"&&kind==="ground")t.arrival=stamp;
     t.stable=kind;t.pending=null;t.pendingAt=null;
    }else if(t.pending!==kind){t.pending=kind;t.pendingAt=stamp;}
   }
   tracks.set(key,t);
  }
  while(tracks.size>512)tracks.delete(tracks.keys().next().value);
 }
 function radioInfo(a){return tracks.get(String(a?.hex||"").toLowerCase())||null;}
 return {callsign,airport,epoch,fromAdsbdb,fromProvider,combine,formatAirport,
  shortRoute,formatTime,timeSummary,observeRadio,radioInfo,radioState};
})();
if(typeof module!=="undefined"&&module.exports)module.exports=TihuluFlightJourney;
if(typeof window!=="undefined")window.TihuluFlightJourney=TihuluFlightJourney;
