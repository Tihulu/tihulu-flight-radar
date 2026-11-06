"use strict";
/* Shared, bounded browser Internet providers. Never handles raw SDR I/Q.
 * Only public, ICAO24-grounded positions become map markers. A static Pages
 * page cannot bypass CORS; public relay availability is best-effort.
 */
const TihuluMultiSources = (() => {
 const ORDER=["adsblol","adsbfi","opensky","intelsky"];
 const META={
  adsblol:{name:"adsb.lol",credit:"adsb.lol (ODbL 1.0)",interval:35000},
  adsbfi:{name:"adsb.fi",credit:"adsb.fi (personal, non-commercial; https://adsb.fi)",interval:35000},
  opensky:{name:"OpenSky",credit:"OpenSky Network (API quotas apply)",interval:300000},
  intelsky:{name:"IntelSky",credit:"IntelSky.org (limited military/government coverage)",interval:60000}
 };
 const RELAY="https://proxy.cors.dev/";
 const validId=id=>ORDER.includes(id);
 const hexValue=a=>{
  const hex=String(a?.hex||"").toLowerCase();
  return /^[0-9a-f]{6}$/.test(hex)?hex:null;
 };
 const positionOk=a=>Number.isFinite(a?.lat)&&Number.isFinite(a?.lon)&&
   Math.abs(a.lat)<=90&&Math.abs(a.lon)<=180;
 function distanceNM(lat1,lon1,lat2,lon2){
  const r=Math.PI/180,p=(lat2-lat1)*r,q=(lon2-lon1)*r;
  return 3440.065*2*Math.asin(Math.min(1,Math.sqrt(Math.max(0,
    Math.sin(p/2)**2+Math.cos(lat1*r)*Math.cos(lat2*r)*Math.sin(q/2)**2))));
 }
 function sourceURL(id,lat,lon,radius){
  if(!validId(id))throw Error("Unknown Internet network.");
  const a=(Math.round(lat*10)/10).toFixed(1),b=(Math.round(lon*10)/10).toFixed(1);
  const r=Math.max(10,Math.min(250,Math.round(radius)));
  if(id==="intelsky")return "https://intelsky.org/api/";
  let upstream;
  if(id==="adsblol")upstream="https://api.adsb.lol/v2/point/"+a+"/"+b+"/"+r;
  if(id==="adsbfi")upstream="https://opendata.adsb.fi/api/v3/lat/"+a+"/lon/"+b+"/dist/"+r;
  if(id==="opensky"){
   // Bounded approximate circle -> a small bounding box, then exact great-circle filter.
   const dl=r/60,dn=dl/Math.max(0.15,Math.cos(lat*Math.PI/180));
   const u=new URL("https://opensky-network.org/api/states/all");
   u.searchParams.set("lamin",String(Math.max(-90,lat-dl)));
   u.searchParams.set("lamax",String(Math.min(90,lat+dl)));
   u.searchParams.set("lomin",String(Math.max(-180,lon-dn)));
   u.searchParams.set("lomax",String(Math.min(180,lon+dn)));
   upstream=u.href;
  }
  // Third-party public relay; never pass raw IQ, credentials, pairing tokens,
  // device positions without explicit search permission, or arbitrary URLs.
  return RELAY+upstream;
 }
 function normalise(id,payload,lat,lon,radius,now=Date.now()/1000){
  if(!validId(id))throw Error("Unknown provider schema.");
  if(!payload||typeof payload!=="object")throw Error(id+": invalid payload.");
  let stamp=Number(id==="opensky"?payload.time:payload.now);
  if(stamp>1e12)stamp/=1000; // adsb.fi/ADSBexchange v2 may send milliseconds.
  if(!Number.isFinite(stamp)||now-stamp>120||stamp-now>10)
   throw Error(id+": missing or stale timestamp.");
  const raw=id==="opensky"?payload.states:payload.ac;
  if(!Array.isArray(raw))throw Error(id+": unexpected aircraft schema.");
  const seenIds=new Set(),planes=[];
  for(const record of raw.slice(0,10000)){
   let a;
   if(id==="opensky"){
    if(!Array.isArray(record)||record.length<12)continue;
    const [hex,flight,,posTime,lastContact,lon0,lat0,altM,,velocity,track,rate,,
           geomM,squawk]=record;
    const seen=now-Number(lastContact);
    const seenPos=posTime==null?Infinity:now-Number(posTime);
    a={hex,flight,lat:lat0,lon:lon0,alt_baro:Number.isFinite(altM)?altM*3.280839895:null,
      alt_geom:Number.isFinite(geomM)?geomM*3.280839895:null,
      gs:Number.isFinite(velocity)?velocity*1.943844492:null,track,
      baro_rate:Number.isFinite(rate)?rate*196.850394:null,
      squawk,seen,seen_pos:seenPos};
   }else{
    a=record;
    if(id==="intelsky"){
     // IntelSky contains a real snapshot time, but not per-plane observation ages.
     a={...a,seen:Math.max(0,now-stamp),seen_pos:Math.max(0,now-stamp),
       observation_age_unknown:true};
    }
   }
   const hex=hexValue(a);
   if(!hex||seenIds.has(hex)||!positionOk(a)||
      distanceNM(lat,lon,a.lat,a.lon)>radius)continue;
   const seen=Number(a.seen),seenPos=Number(a.seen_pos);
   if(!Number.isFinite(seen)||seen<0||seen>60||
      !Number.isFinite(seenPos)||seenPos<0||seenPos>60)continue;
   seenIds.add(hex);
   planes.push({...a,hex,seen,seen_pos:seenPos,
     internet_providers:[id],sources:["internet"],position_source:"internet",
     observations:{internet_sources:{[id]:{...a,provider:id,observed_at:stamp}}}});
  }
  return {generated_at:now,aircraft:planes,provider:id,provider_stamp:stamp};
 }
 function aggregate(snapshots,selected,now=Date.now()/1000){
  const rows=[],byId=new Map(),counts={};
  const all=selected.filter(validId);
  for(const id of all){
   const snap=snapshots[id],elapsed=snap?Math.max(0,now-snap.generated_at):Infinity;
   counts[id]=0;
   if(!snap)continue;
   for(const a of snap.aircraft){
    const seen=a.seen+elapsed,seenPos=a.seen_pos+elapsed;
    if(seen>60||seenPos>60)continue;
    counts[id]++;
    const prev=byId.get(a.hex);
    const observation=a.observations.internet_sources[id];
    if(prev){
     prev.internet_providers.push(id);
     prev.observations.internet_sources[id]=observation;
     // Never replace a fresh adsb.lol position with a less fresh network estimate.
     if(!Number.isFinite(prev.seen_pos)||seenPos<prev.seen_pos){
      prev.seen=seen;prev.seen_pos=seenPos;
      prev.lat=a.lat;prev.lon=a.lon;prev.position_provider=id;
     }
     if(!prev.flight&&a.flight)prev.flight=a.flight;
    }else{
     const row={...a,seen,seen_pos:seenPos,position_provider:id,
       internet_providers:[id],sources:["internet"],
       observations:{internet_sources:{[id]:observation}}};
     rows.push(row);byId.set(a.hex,row);
    }
   }
  }
  return {generated_at:now,aircraft:rows,counts,unique:rows.length};
 }
 function createManager(fetchImpl=fetch){
  const snapshots={},lastKeys={},lastFetch={},backoff={},errors={};
  async function poll(selected,lat,lon,radius){
   const chosen=[...new Set(selected.filter(validId))];
   const key=[(Math.round(lat*10)/10).toFixed(1),
     (Math.round(lon*10)/10).toFixed(1),Math.round(radius)].join("/");
   const tasks=chosen.map(async id=>{
    const nowMs=Date.now();
    if(lastKeys[id]!==key){
     delete snapshots[id];lastKeys[id]=key;lastFetch[id]=0;
    }
    if(nowMs<(backoff[id]||0)||nowMs-(lastFetch[id]||0)<META[id].interval)return;
    lastFetch[id]=nowMs;
    const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),9000);
    try{
     const response=await fetchImpl(sourceURL(id,lat,lon,radius),{
      mode:"cors",credentials:"omit",cache:"no-store",signal:abort.signal});
     if(!response.ok){
      const retry=Number(response.headers?.get?.("Retry-After"));
      if(response.status===429)backoff[id]=Date.now()+
       (Number.isFinite(retry)&&retry>0?Math.min(3600,retry):120)*1000;
      else if(response.status>=500||response.status===403)backoff[id]=Date.now()+120000;
      throw Error(id+": HTTP "+response.status);
     }
     const relayError=response.headers?.get?.("X-Cors-Error");
     if(relayError)throw Error(id+": relay rejected upstream.");
     const body=await response.text();
     if(body.length>4*1024*1024)throw Error(id+": response exceeds 4 MiB.");
     const parsed=normalise(id,JSON.parse(body),lat,lon,radius);
     snapshots[id]=parsed;errors[id]=null;
    }catch(e){
     errors[id]=e?.name==="AbortError"?id+": timeout":id+": "+String(e.message||e);
     // CORS outages are neither zero planes nor fake successful observations.
     backoff[id]=Math.max(backoff[id]||0,Date.now()+60000);
    }finally{clearTimeout(timeout)}
   });
   await Promise.all(tasks);
   const joined=aggregate(snapshots,chosen);
   const successful=chosen.filter(id=>snapshots[id]&&
     Date.now()/1000-snapshots[id].generated_at<=60);
   const providerStates=Object.fromEntries(chosen.map(id=>[id,{
    state:successful.includes(id)?"available":errors[id]?"unavailable":"waiting",
    error:errors[id]||null,count:joined.counts[id],
    updated_at:snapshots[id]?.provider_stamp||null,
    attribution:META[id].credit}]));
   return {generated_at:joined.generated_at,active_sources:["internet"],
    aircraft:joined.aircraft,
    counts:{antenna:0,internet:joined.unique,combined:joined.unique},
    sources:{antenna:{state:"unavailable",error:"No local receiver selected"},
      internet:{state:successful.length?"available":"unavailable",
       error:successful.length?null:chosen.map(id=>errors[id]).filter(Boolean).join(" | ")||
        "No live provider data.",
       provider:successful.map(id=>META[id].name).join(" + ")||"Selected public networks",
       attribution:chosen.map(id=>META[id].credit).join(" · "),
       updated_at:Math.max(0,...successful.map(id=>snapshots[id].provider_stamp)),
       providers:providerStates}},
    provider_counts:joined.counts};
  }
  return {poll};
 }
 return {ORDER,META,sourceURL,normalise,aggregate,createManager};
})();
if(typeof module!=="undefined"&&module.exports)module.exports=TihuluMultiSources;
if(typeof window!=="undefined")window.TihuluMultiSources=TihuluMultiSources;
