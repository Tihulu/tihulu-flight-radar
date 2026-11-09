"use strict";
/* Shared browser/native aircraft route & time UI. Online lookups are
 * on-demand per selected callsign or via an explicit bounded batch button.
 * Provider routes are not persisted (adsbdb attribution / license).
 */
(()=>{
 const $=id=>document.getElementById(id);
 const F=TihuluFlightJourney,cache=new Map(),pending=new Map();
 let batchSerial=0;
 const MAX_AGE=30*60*1000;
 function cached(call){
  const row=cache.get(call);
  return row&&Date.now()-row.at<MAX_AGE?row:null;
 }
 function flight(a){
  const call=F.callsign(a),provider=F.fromProvider(a);
  const route=cached(call)?.route||null;
  return F.combine(provider,route);
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
  let time=F.timeSummary(j);
  if(time==="Timetable unavailable"&&radio?.departure)
   time="RF ground → air "+F.formatTime(radio.departure);
  if(time==="Timetable unavailable"&&radio?.arrival)
   time="RF air → ground "+F.formatTime(radio.arrival);
  return {route:F.shortRoute(j),time};
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
 function selected(a){
  render(a);if(F.callsign(a))void resolve(a);
 }
 function observe(rows){
  F.observeRadio(rows);
  if(!state.selected||$("aircraftPopup").hidden)return;
  const current=state.data.find(a=>a.hex===state.selected);
  if(current)render(current);
 }
 $("popupJourneyRefresh").addEventListener("click",()=>{
  const found=state.data.find(a=>a.hex===state.selected);
  if(!found)return;
  $("popupJourneySource").textContent="Checking online callsign route…";
  void resolve(found,{force:true});
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
