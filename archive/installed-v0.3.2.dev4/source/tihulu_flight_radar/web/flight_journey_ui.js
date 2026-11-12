"use strict";
/* Shared browser/native aircraft route & time UI. Online lookups are
 * on-demand per selected callsign or via an explicit bounded batch button.
 * Provider routes are not persisted (adsbdb attribution / license).
 */
(()=>{
 const $=id=>document.getElementById(id);
 const F=TihuluFlightJourney,cache=new Map(),pending=new Map();
 const flightDetails=new Map(),flightPending=new Map();
 let batchSerial=0,radioLoaded=false,radioLoadedAt=0;
 const MAX_AGE=30*60*1000;
 function cached(call){
  const row=cache.get(call);
  return row&&Date.now()-row.at<MAX_AGE?row:null;
 }
 function flight(a){
  const call=F.callsign(a),provider=F.fromProvider(a);
  const route=cached(call)?.route||null;
  const detail=flightDetails.get(call);
  const fresh=detail&&Date.now()-detail.at<MAX_AGE?detail.journey:null;
  return F.combine(fresh,F.combine(provider,route));
 }
 function bestTime(t,phase){
  for(const kind of ["Actual","Estimated","Scheduled"]){
   const time=t?.[phase+kind];
   if(Number.isFinite(time))return kind+": "+F.formatTime(time);
  }
  return "Not available from source";
 }
 function rfText(a){
  const info=F.radioInfo(a);
  if(!info)return a?.sources?.includes("antenna")
   ?"R · RF messages received; no verified ground/air event."
   :"I · no local radio track (Internet only).";
  const parts=["R · First locally heard "+F.formatTime(info.firstAt),
   "Last locally heard "+F.formatTime(info.lastAt)];
  if(info.departure)parts.push("Ground → air observed "+F.formatTime(info.departure)+
   " (approx. RF state transition, NOT airport departure time)");
  if(info.arrival)parts.push("Air → ground observed "+F.formatTime(info.arrival)+
   " (approx. RF state transition, NOT airport arrival time)");
  return parts.join("\n");
 }
 function render(a){
  if(!a)return;
  const journey=flight(a);
  $("popupDepartAirport").textContent=F.formatAirport(journey?.origin);
  $("popupArriveAirport").textContent=F.formatAirport(journey?.destination);
  $("popupDepartureTime").textContent=bestTime(journey?.times,"depart");
  $("popupArrivalTime").textContent=bestTime(journey?.times,"arrive");
  $("popupRadioJourney").textContent=rfText(a);
  const call=F.callsign(a);
  const notFound=call&&cached(call)&&!cached(call).route;
  $("popupJourneySource").textContent=journey
   ?"Airports / timetable source: "+journey.source+
    ". Route is callsign-based, not proof of this specific flight. Local times follow device settings."+
    (journey.source.includes("adsbdb")?
     " Route data: David J Taylor (Edinburgh) and Jim Mason (Glasgow), via adsbdb.com. No route-data archive is created.":"")
   :notFound?"Online callsign route unavailable; ADS-B alone cannot supply origin, destination or schedule.":
    call?"Route not yet retrieved. Opening aircraft Info checks the public callsign database on demand.":
    "No verifiable callsign. Ordinary ADS-B does not carry airport route or scheduled flight times.";
 }
 function row(a){
  const j=flight(a),radio=F.radioInfo(a);
  const time=F.timeSummary(j);
  // The Radio button reveals receiver observation times separately from
  // confirmed provider schedules. Neither is a runway/gate timestamp.
  const lastRadio=radioLoaded&&radio&&radioLoadedAt&&
   radio.lastAt<=Date.now()+12000?
   radio.arrival?"R · air → ground "+F.formatTime(radio.arrival):
   radio.departure?"R · ground → air "+F.formatTime(radio.departure):
   "R · heard "+F.formatTime(radio.lastAt):null;
  return {route:F.shortRoute(j),time,radio:lastRadio};
 }
 async function resolve(a,{force=false}={}){
  const call=F.callsign(a);
  if(!call)return null;
  const old=cached(call);
  if(old&&!force)return old.route;
  if(pending.has(call))return pending.get(call);
  if(navigator.onLine===false)return null;
  const task=(async()=>{
   try{
    let payload;
    if(state.connectionKind==="bridge"&&state.base&&state.token){
     payload=await api("/api/flight-route?callsign="+encodeURIComponent(call));
    }else{
     const controller=new AbortController();
     const timer=setTimeout(()=>controller.abort(),5000);
     try{
      const response=await fetch("https://api.adsbdb.com/v0/callsign/"+
       encodeURIComponent(call),{mode:"cors",credentials:"omit",cache:"no-store",
        signal:controller.signal});
      if(!response.ok && response.status!==404)throw Error("HTTP "+response.status);
      if(response.status===404){payload={response:{flightroute:null}};}
      else{
       const raw=await response.text();
       if(raw.length>32768)throw Error("Unexpectedly large route payload");
       payload=JSON.parse(raw);
      }
     }finally{clearTimeout(timer);}
    }
    if(payload?.error)throw Error(payload.error);
    const route=F.fromAdsbdb(payload,call);
    cache.set(call,{route,at:Date.now()});
    if(cache.size>256)cache.delete(cache.keys().next().value);
    if(state.selected===String(a.hex||"").toLowerCase()&&
       !$("aircraftPopup").hidden){
     const current=state.data.find(p=>p.hex===state.selected);
     if(current)render(current);
    }
    // Update the visible table and selection sidebar with source-tagged data.
    renderTable();
    return route;
   }catch(error){
    // Network error must never show a guessed airport or make Info disappear.
    const message=String(error?.message||error).slice(0,100);
    if(state.selected===String(a.hex||"").toLowerCase()&&
       !$("aircraftPopup").hidden){
     $("popupJourneySource").textContent=
      "Online route lookup unavailable ("+message+"). Radio data stays visible.";
    }
    return null;
   }finally{pending.delete(call);}
  })();
  pending.set(call,task);
  return task;
 }
 async function loadAirLabsDetail(a,{force=false}={}){
  const call=F.callsign(a);
  if(!call||state.onlineProvider!=="airlabs"||navigator.onLine===false)return null;
  const key=String($("airlabsKey")?.value||"").trim();
  if(!key)return null; // Only user-provided personal API key, session-only.
  const existing=flightDetails.get(call);
  if(!force&&existing&&Date.now()-existing.at<MAX_AGE)return existing.journey;
  if(flightPending.has(call))return flightPending.get(call);
  const work=(async()=>{
   const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),6000);
   try{
    const url=new URL("https://airlabs.co/api/v9/flight");
    url.searchParams.set("flight_icao",call);
    url.searchParams.set("api_key",key);
    const response=await fetch(url,{mode:"cors",credentials:"omit",
     cache:"no-store",signal:controller.signal});
    if(!response.ok)throw Error("AirLabs HTTP "+response.status);
    const raw=await response.text();
    if(raw.length>65536)throw Error("AirLabs detail too large");
    const body=JSON.parse(raw);
    if(body?.error)throw Error("AirLabs returned no usable flight data");
    const item=body?.response;
    if(!item||typeof item!=="object"||
       String(item.flight_icao||"").trim().toUpperCase()!==call)return null;
    // /flight returns the closest flight of that number, potentially on a
    // DIFFERENT date. Only accept clearly matching current-day timestamps.
    const stamps=[item.dep_time_ts,item.dep_actual_ts,item.arr_time_ts,
     item.arr_actual_ts,item.dep_estimated_ts,item.arr_estimated_ts]
     .map(F.epoch).filter(Number.isFinite);
    if(!stamps.some(v=>Math.abs(Date.now()-v)<=48*3600000))return null;
    const journey=F.fromProvider({sources:["internet"],
     flight:call,flight_source_fields:item});
    if(!journey)return null;
    journey.source="AirLabs flight detail · callsign+date matched · API-key";
    flightDetails.set(call,{journey,at:Date.now()});
    if(flightDetails.size>100)flightDetails.delete(flightDetails.keys().next().value);
    if(state.selected===String(a.hex||"").toLowerCase()&&
       !$("aircraftPopup").hidden){
     const now=state.data.find(v=>v.hex===state.selected);
     if(now)render(now);
    }
    renderTable();
    return journey;
   }catch{
    return null; // Offline/quota/errors cannot invent an airline schedule.
   }finally{clearTimeout(timer);flightPending.delete(call);}
  })();
  flightPending.set(call,work);
  return work;
 }
 function selected(a){
  render(a);
  if(F.callsign(a))void resolve(a).then(()=>loadAirLabsDetail(a));
 }
 function observe(rows){
  F.observeRadio(rows);
  if(!state.selected||$("aircraftPopup").hidden)return;
  const current=state.data.find(a=>a.hex===state.selected);
  if(current)render(current);
 }
 async function radioSnapshot(){
  // This intentionally does NOT turn on a receiver or replace map sources.
  // In native/paired mode we request genuine readsb-only aircraft from the
  // already-connected private bridge. No Internet merging is permitted.
  if(state.connectionKind==="bridge"&&state.base&&state.token){
   const query=new URLSearchParams({
    mode:"antenna",lat:String(state.queryLat),lon:String(state.queryLon),
    radius:String(state.queryRadius)});
   const payload=await api("/api/aircraft?"+query);
   const status=payload.sources?.antenna?.state||"unknown";
   const rows=(Array.isArray(payload.aircraft)?payload.aircraft:[])
    .filter(r=>Array.isArray(r.sources)&&r.sources.includes("antenna")&&
     r.observations?.antenna&&Number.isFinite(r.observations.antenna.seen)&&
     r.observations.antenna.seen<=12);
   return {rows,status};
  }
  // WebUSB is already controlled elsewhere; never auto-claim SDR hardware.
  if(state.connectionKind==="usb"){
   const age=Date.now()-(state.usbSnapshot?.updatedAt||0);
   if(age>45000)return {rows:[],status:"USB receiver has no fresh frames"};
   const rows=(state.usbSnapshot.aircraft||[]).filter(
    r=>Number.isFinite(r.seen)&&r.seen>=0&&r.seen<=12).map(r=>({
     ...r,sources:["antenna"],observations:{antenna:{...r}}
    }));
   return {rows,status:"WebUSB local receiver"};
  }
  return {rows:[],status:"No active local SDR receiver; Internet aircraft cannot supply RF observations"};
 }
 $("aircraftRadioLoad").addEventListener("click",async()=>{
  const button=$("aircraftRadioLoad");button.disabled=true;
  const statusEl=$("aircraftLoadStatus");
  statusEl.textContent="Loading fresh local antenna observations only…";
  try{
   const data=await radioSnapshot();
   F.observeRadio(data.rows);
   radioLoaded=true;radioLoadedAt=Date.now();
   renderTable();
   const n=data.rows.length,tracked=data.rows.filter(a=>F.radioInfo(a)).length;
   const transitions=data.rows.filter(a=>{
    const info=F.radioInfo(a);return !!(info?.departure||info?.arrival);
   }).length;
   statusEl.textContent=n?
    "Radio refreshed: "+n+" genuine local aircraft; "+tracked+
    " tracked · "+transitions+" observed ground/air transitions. "+
    "Displayed times are RF observations, NOT flight schedules.":
    "Radio: "+data.status+". No airport or departure time was inferred.";
   button.textContent="Refresh · Radio";
  }catch(error){
   statusEl.textContent="Radio load failed: "+String(error?.message||error).slice(0,130)+
    " · existing observations retained.";
  }finally{button.disabled=false;}
 });
 $("popupJourneyRefresh").addEventListener("click",()=>{
  const found=state.data.find(a=>a.hex===state.selected);
  if(!found)return;
  $("popupJourneySource").textContent="Checking online callsign route…";
  void resolve(found,{force:true}).then(()=>loadAirLabsDetail(found,{force:true}));
 });
 $("aircraftRoutesLoad").addEventListener("click",async()=>{
  const button=$("aircraftRoutesLoad");button.disabled=true;
  const serial=++batchSerial;
  try{
   const planes=state.data.filter(a=>F.callsign(a)).filter(
    (a,i,all)=>all.findIndex(x=>F.callsign(x)===F.callsign(a))===i).slice(0,30);
   for(let i=0;i<planes.length&&serial===batchSerial;i++){
    if(document.hidden)break; // user requested foreground-only enrichment
    button.textContent="Routes "+(i+1)+"/"+planes.length;
    await resolve(planes[i]);
   }
  }finally{
   if(serial===batchSerial){
    button.disabled=false;button.textContent="Load routes · Internet";
   }
  }
 });
 window.TihuluJourneyUI={render,selected,observe,row,resolve};
})();
