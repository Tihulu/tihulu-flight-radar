"use strict";
// Shared static frontend: hosted by GitHub Pages or the paired local bridge.
// Never fabricates receiver observations or sends a pairing token elsewhere.
const $ = id => document.getElementById(id);
const GERMANY = {lat:51.1657, lon:10.4515};
const COLOGNE = {lat:50.938, lon:6.960};
const startRegion = new URLSearchParams(location.search).get("region");
// Startup priority: consented geolocation > nearest real RF-positioned plane > Cologne.
// The old region query is retained only for explicit later user controls.
const initialCenter = COLOGNE;
const COLORS = {antenna:"#50dcad", internet:"#5cafe8", both:"#e6b56b"};
// Shared altitude scale for all sources. Unknown altitude is neutral.
const ALTITUDE_STOPS = [
 [0,"#f36b3e"],[2000,"#f0aa38"],[6000,"#d8d941"],[10000,"#61d65b"],
 [18000,"#25c8c0"],[26000,"#417ded"],[35000,"#a15be7"],[40000,"#e44bc3"]
];
function aircraftAltitude(a){
 const raw=a?.alt_baro??a?.alt_geom??a?.altitude;
 if(raw==="ground")return 0;
 return (typeof raw==="number"&&Number.isFinite(raw))?raw:null;
}
function altitudeColor(a){
 const altitude=aircraftAltitude(a);
 if(altitude===null)return "#abb6c5";
 const feet=Math.max(0,Math.min(40000,altitude));
 for(let i=1;i<ALTITUDE_STOPS.length;i++){
  const [top,high]=ALTITUDE_STOPS[i], [bottom,low]=ALTITUDE_STOPS[i-1];
  if(feet>top)continue;
  const t=(feet-bottom)/(top-bottom);
  const v=k=>Math.round(parseInt(low.slice(k,k+2),16)*(1-t)+parseInt(high.slice(k,k+2),16)*t);
  return "#"+[1,3,5].map(k=>v(k).toString(16).padStart(2,"0")).join("");
 }
 return ALTITUDE_STOPS[ALTITUDE_STOPS.length-1][1];
}
function aircraftSourceBadge(a){
 const sources=Array.isArray(a?.sources)?a.sources:[];
 const radio=sources.includes("antenna"),internet=sources.includes("internet");
 return radio&&internet?"I/R":radio?"R":internet?"I":"?";
}
function paintAircraft(ctx,a,x,y){
 const color=altitudeColor(a),badge=aircraftSourceBadge(a);
 const heading=Number.isFinite(a.track)?a.track:Number.isFinite(a.true_heading)?a.true_heading:0;
 ctx.save();ctx.translate(x,y);ctx.rotate(heading*Math.PI/180);
 // Full airplane silhouette, nose-up with broad wings and tailplane.
 ctx.beginPath();
 ctx.moveTo(0,-17);ctx.lineTo(3,-11);ctx.lineTo(3,-4);
 ctx.lineTo(15,2);ctx.lineTo(15,5);ctx.lineTo(3,4);
 ctx.lineTo(3,11);ctx.lineTo(8,15);ctx.lineTo(8,17);
 ctx.lineTo(0,14);ctx.lineTo(-8,17);ctx.lineTo(-8,15);
 ctx.lineTo(-3,11);ctx.lineTo(-3,4);ctx.lineTo(-15,5);
 ctx.lineTo(-15,2);ctx.lineTo(-3,-4);ctx.lineTo(-3,-11);
 ctx.closePath();
 ctx.lineWidth=2.5;ctx.strokeStyle="#102030";ctx.stroke();
 ctx.fillStyle=color;ctx.fill();ctx.restore();
 // Independent, upright badge never rotates with aircraft heading.
 const bw=badge==="I/R"?29:18,bx=x+10,by=y+9;
 ctx.fillStyle="rgba(8,24,37,.94)";ctx.fillRect(bx,by,bw,17);
 ctx.strokeStyle=color;ctx.lineWidth=1;ctx.strokeRect(bx+.5,by+.5,bw-1,16);
 ctx.fillStyle="#fff";ctx.font="bold 10px system-ui";ctx.textAlign="center";
 ctx.fillText(badge,bx+bw/2,by+12);ctx.textAlign="start";
}
const canvas = $("map"), ctx = canvas.getContext("2d");
const state = {
  base:"", token:"", onlineFeed:"", onlineProvider:"adsblol-relay", internetBackoffUntil:0, airlabsLastFetch:0, relayLastFetch:0, relayLastQueryKey:"", connectionKind:"none", connected:false, data:[], mode:"auto", selected:null, 
  lat:initialCenter.lat, lon:initialCenter.lon, zoom:9, moved:false, autoFocused:false,
  startupLocationPending:true, startupGeo:null, startupRank:1, startupSource:"cologne",
  startupQueryDirty:false,
  // Camera movement must not change the API search key during feed cooldown.
  queryLat:initialCenter.lat, queryLon:initialCenter.lon, queryRadius:100,
  lastFreshAt:0, lastData:[], dataReceivedAt:0,
  usbSnapshot:{aircraft:[],messages:0,updatedAt:0},internetSnapshot:null,
  usbMessageCount:0,
  pointer:null, tracks:new Map(), tiles:new Map(), tileFailures:0, fetching:false, timer:null,
  centerLabel:"Cologne startup fallback · awaiting location permission / radio aircraft",
  units:"aviation"
};
const selectors = ["showAntenna","showInternet","showBoth","showTracks","showTiles","showRfCoverage","smoothMotion"];
const multiInternet = TihuluMultiSources.createManager();
const multiIds = ["adsblol","adsbfi","opensky","intelsky"];
const layerFields = {adsblol:"netAdsbLol",adsbfi:"netAdsbFi",opensky:"netOpenSky",intelsky:"netIntelSky"};
const statusFields = {adsblol:"statusAdsbLol",adsbfi:"statusAdsbFi",opensky:"statusOpenSky",intelsky:"statusIntelSky"};
function enabledInternetNetworks(){return multiIds.filter(id=>$(layerFields[id]).checked);}
function sourceLayerStatus(result){
 const statuses=result?.sources?.internet?.providers||{};
 for(const id of multiIds){
  const el=$(statusFields[id]),status=statuses[id];
  el.textContent=status?(status.count??0)+" observed · "+status.state+
    (status.error?" ("+status.error+")":""):TihuluMultiSources.META[id].credit;
 }
}
function notice(s){$("message").textContent=s}
function isPositioned(a){
 return a && Number.isFinite(a.lat) && Number.isFinite(a.lon) &&
  a.lat >= -90 && a.lat <= 90 && a.lon >= -180 && a.lon <= 180 &&
  Number.isFinite(a.seen_pos) && a.seen_pos >= 0 && a.seen_pos <= 60;
}
// Pure startup choice; only the radio-sourced position qualifies as RF.
// A merged aircraft whose position came from the Internet is not radio GPS.
// Map startup is NEVER a one-plane RF receiver site estimate.
// Only the independent four-aircraft horizon solver may focus the RF model.
function chooseStartupTarget(geo,aircraft){
 const valid=p=>p&&Number.isFinite(p.lat)&&Number.isFinite(p.lon)&&
  Math.abs(p.lat)<=90&&Math.abs(p.lon)<=180;
 if(valid(geo))return {lat:geo.lat,lon:geo.lon,zoom:10,rank:3,source:"location"};
 return {lat:COLOGNE.lat,lon:COLOGNE.lon,zoom:9,rank:1,source:"cologne"};
}
function applyStartupPriority(){
 // Manual map movement/selection always wins; do not steal camera focus.
 if(state.moved || state.startupLocationPending)return;
 const selected=chooseStartupTarget(state.startupGeo,state.data);
 if(selected.rank<=state.startupRank)return;
 state.startupRank=selected.rank;state.startupSource=selected.source;
 state.lat=selected.lat;state.lon=selected.lon;state.zoom=selected.zoom;
 state.queryLat=selected.lat;state.queryLon=selected.lon;
 state.autoFocused=true;
 state.centerLabel=selected.source==="location"
   ? "Your permitted current location · startup"
   : "Cologne default map (not an inferred receiver position)";
 state.startupQueryDirty=state.connected;
 paint();
}
function initializeStartupLocation(){
 const fallback=()=>{state.startupLocationPending=false;applyStartupPriority();};
 if(!navigator.geolocation){fallback();return;}
 // Match Satellite Center: no automatic GPS permission prompts.
 // Existing browser consent may be used for initial camera preference.
 if(!navigator.permissions?.query){fallback();return;}
 navigator.permissions.query({name:"geolocation"}).then(permission=>{
  if(permission.state!=="granted"){fallback();return;}
  navigator.geolocation.getCurrentPosition(
   fix=>{
    const p=fix?.coords;
    if(p && Number.isFinite(p.latitude) && Number.isFinite(p.longitude))
     state.startupGeo={lat:p.latitude,lon:p.longitude};
    fallback();
    if(state.startupQueryDirty && !state.fetching && state.connected){
     state.startupQueryDirty=false;refresh();
    }
   },fallback,{enableHighAccuracy:false,timeout:6500,maximumAge:300000});
 }).catch(fallback);
}
function category(a){return a.sources?.length > 1 ? "both" : (a.sources?.[0] || "internet")}
function visible(a){
 const c = category(a);
 return (c==="both" && $("showBoth").checked) ||
        (c==="antenna" && $("showAntenna").checked) ||
        (c==="internet" && $("showInternet").checked);
}
function getBase(raw){
 // People naturally type "127.0.0.1:8510" without a scheme.
 // Normalize only known loopback origins; never downgrade arbitrary hosts.
 raw=String(raw||"").trim();
 if(/^(?:localhost|127\.0\.0\.1)(?::[0-9]{1,5})?\/?$/i.test(raw)) raw="http://"+raw;
 const u=new URL(raw);
 if(u.username || u.password || u.search || u.hash || u.pathname!=="/") throw Error("Use a bridge origin without a path or credentials.");
 if(u.protocol==="http:" && !["127.0.0.1","localhost","[::1]"].includes(u.hostname))
   throw Error("Remote bridges must use HTTPS. Plain HTTP is permitted only for loopback.");
 if(u.protocol!=="https:" && u.protocol!=="http:") throw Error("Bridge URL must use HTTP(S).");
 return u.origin;
}
function getFeedURL(raw){
 raw=String(raw||"").trim();
 if(!raw)return "";
 const url=new URL(raw);
 if(url.protocol!=="https:" || url.username || url.password || url.search || url.hash ||
    !url.pathname.endsWith("/api/aircraft"))
   throw Error("Internet feed must be a trusted HTTPS /api/aircraft endpoint without embedded keys.");
 return url.origin+url.pathname;
}
// A keyless browser-compatible limited network source; not the full ADS-B
// population. Public general ADS-B APIs commonly require a CORS-enabled relay.
const INTELSKY_URL="https://intelsky.org/api/";
const ADSBLOL_PUBLIC_RELAY="https://proxy.cors.dev/";
// Shared third-party relay (not controlled by TIHULU), not a production SLA.
// Only public map center is sent; never antenna IQ, browser keys or location permission.
function configuredOnlineFeed(){
 const provider=$("onlinePreset")?.value||"intelsky";
 let url="";
 if(provider==="intelsky")url=INTELSKY_URL;
 else if(provider==="adsblol-relay"||provider==="multi"){
  if(provider==="multi"&&!enabledInternetNetworks().length)
   throw Error("Select at least one Internet layer.");
  url=ADSBLOL_PUBLIC_RELAY;
 }
 else if(provider==="airlabs"){
  if(!String($("airlabsKey")?.value||"").trim())
   throw Error("AirLabs needs your personal API key (session only).");
  url="https://airlabs.co/api/v9/flights";
 }else if(provider==="custom")url=getFeedURL($("onlineFeedUrl").value);
 else if(provider!=="off")throw Error("Unknown Internet provider choice.");
 // Atomic config: invalid key/URL must not change a working source.
 state.onlineProvider=provider;
 return url;
}
function greatCircleNM(lat1,lon1,lat2,lon2){
 const r=Math.PI/180,p=(lat2-lat1)*r,q=(lon2-lon1)*r;
 return 3440.065*2*Math.asin(Math.min(1,Math.sqrt(Math.max(0,
  Math.sin(p/2)**2+Math.cos(lat1*r)*Math.cos(lat2*r)*Math.sin(q/2)**2))));
}
function normalizeInternetPayload(raw,provider,lat,lon,radius,now=Date.now()/1000){
 const limited=provider==="intelsky", relay=provider==="adsblol-relay";
 if(provider==="airlabs"){
  if(raw?.error)throw Error("AirLabs: "+String(raw.error.message||raw.error.code||"API error").slice(0,150));
  if(!Array.isArray(raw?.response))throw Error("AirLabs response has no aircraft array.");
  const rows=raw.response.slice(0,10000).map(a=>{
   if(!a||typeof a!=="object")return null;
   const updateAge=Number.isFinite(a.updated)?now-a.updated:0;
   return {
    hex:a.hex,flight:a.flight_icao||a.flight_iata||a.flight_number||null,
    lat:a.lat,lon:a.lng,
    alt_baro:Number.isFinite(a.alt)?a.alt*3.280839895:null,
    gs:Number.isFinite(a.speed)?a.speed/1.852:null,
    track:Number.isFinite(a.dir)?a.dir:null,
    seen:updateAge,seen_pos:updateAge,
    observation_age_unknown:!Number.isFinite(a.updated),
    flight_source_fields:{aircraft_icao:a.aircraft_icao,registration:a.reg_number}
   };
  }).filter(Boolean);
  raw={generated_at:now,aircraft:rows,provider:"AirLabs",
    attribution:"AirLabs.co · API-key-based live flight data (plan coverage and quotas apply)"};
 }
 const stamp=Number((limited||relay)?raw?.now:raw?.generated_at);
 const age=now-stamp;
 if(!Number.isFinite(stamp)||age < -10||age > 90)
  throw Error("Missing or stale Internet snapshot timestamp.");
 const records=(limited||relay)?raw?.ac:raw?.aircraft;
 if(!Array.isArray(records))throw Error("Invalid Internet aircraft schema.");
 const seenIds=new Set(),planes=[];
 for(const a of records.slice(0,10000)){
  if(!a||typeof a!=="object")continue;
  const hex=String(a.hex||"").toLowerCase();
  if(!/^[0-9a-f]{6}$/.test(hex)||seenIds.has(hex)||
     !Number.isFinite(a.lat)||!Number.isFinite(a.lon)||
     a.lat < -90||a.lat > 90||a.lon < -180||a.lon > 180||
     greatCircleNM(lat,lon,a.lat,a.lon)>radius)continue;
  // IntelSky supplies snapshot timestamp but not per-aircraft age.
  // This is a network snapshot, NOT RF reception by the user's antenna.
  const seen=limited?0:a.seen,seenPos=limited?0:a.seen_pos;
  if(!Number.isFinite(seen)||seen<0||seen>60||
     !Number.isFinite(seenPos)||seenPos<0||seenPos>60)continue;
  seenIds.add(hex);
  planes.push({...a,hex,seen,seen_pos:seenPos,
   sources:["internet"],position_source:"internet",
   observations:{internet:{...a,provider,timestamp:stamp}}});
 }
 const attribution=limited
  ?"IntelSky.org · limited military/government network coverage"
  :relay?"adsb.lol (ODbL 1.0) · via public cors.dev relay"
  :raw.attribution||"Check provider's attribution and usage terms";
 return {generated_at:stamp,active_sources:["internet"],aircraft:planes,
  counts:{antenna:0,internet:planes.length,combined:planes.length},
  sources:{antenna:{state:"unavailable",error:"No local receiver selected"},
   internet:{state:"available",provider:limited?"IntelSky":relay?"adsb.lol (public CORS relay)":raw.provider||"Custom CORS feed",
     attribution,updated_at:stamp,limited_coverage:limited}}};
}
async function fetchInternetFeed(){
 if(!state.onlineFeed)throw Error("No Internet source is configured.");
 if(state.onlineProvider==="multi"){
  return multiInternet.poll(enabledInternetNetworks(),state.queryLat,
   state.queryLon,state.queryRadius);
 }
 if(Date.now()<state.internetBackoffUntil)
  throw Error("Internet feed cooling down after rate limit or outage; retry later.");
 const limited=state.onlineProvider==="intelsky",airlabs=state.onlineProvider==="airlabs";
 const relay=state.onlineProvider==="adsblol-relay";
 // User-owned free API keys have quotas; avoid spending one every 15 seconds.
 // Old provider snapshots age out naturally in browserSourceResult.
 if(airlabs && state.internetSnapshot && Date.now()-state.airlabsLastFetch<60000)
  return state.internetSnapshot;
 const publicQueryKey=relay?[
  (Math.round(state.queryLat*10)/10).toFixed(1),
  (Math.round(state.queryLon*10)/10).toFixed(1),
  Math.max(10,Math.min(250,state.queryRadius))
 ].join("/"):"";
 if(relay && state.internetSnapshot && state.relayLastQueryKey===publicQueryKey &&
    Date.now()-state.relayLastFetch<30000)
  return state.internetSnapshot;
 const u=new URL(state.onlineFeed);
 if(airlabs){
  u.searchParams.set("api_key",String($("airlabsKey").value).trim());
  const radius=Math.min(250,state.queryRadius),latD=radius/60;
  const lonD=latD/Math.max(0.15,Math.cos(state.queryLat*Math.PI/180));
  u.searchParams.set("bbox",[
    Math.max(-90,state.queryLat-latD),Math.max(-180,state.queryLon-lonD),
    Math.min(90,state.queryLat+latD),Math.min(180,state.queryLon+lonD)
  ].map(x=>x.toFixed(3)).join(","));
  u.searchParams.set("_fields","hex,flight_icao,flight_iata,flight_number,lat,lng,alt,dir,speed,updated,aircraft_icao,reg_number");
 }else if(relay){
  // Do not send precise GPS coordinates through an unowned relay.
  const lat=(Math.round(state.queryLat*10)/10).toFixed(1);
  const lon=(Math.round(state.queryLon*10)/10).toFixed(1);
  const radius=Math.max(10,Math.min(250,state.queryRadius));
  // Strictly fixed upstream target; no user-supplied arbitrary fetch URLs.
  u.pathname="/https://api.adsb.lol/v2/point/"+lat+"/"+lon+"/"+radius;
 }else if(!limited){
  u.searchParams.set("lat",state.queryLat.toFixed(3));
  u.searchParams.set("lon",state.queryLon.toFixed(3));
  u.searchParams.set("radius",String(state.queryRadius));
 }
 const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),10000);
 try{
  const response=await fetch(u.href,{mode:"cors",credentials:"omit",cache:"no-store",signal:abort.signal});
  if(!response.ok){
   if(response.status===429){
    const retry=Number(response.headers?.get?.("Retry-After"));
    state.internetBackoffUntil=Date.now()+1000*
      (Number.isFinite(retry)&&retry>0?Math.min(3600,retry):90);
   }else if(response.status>=500)state.internetBackoffUntil=Date.now()+60000;
   throw Error("Internet provider HTTP "+response.status+(response.status===429?" (rate limited)":""));
  }
  const relayError=response.headers?.get?.("X-Cors-Error");
  if(relayError)throw Error("CORS relay: "+String(relayError).slice(0,120));
  const text=await response.text();
  if(text.length>4*1024*1024)throw Error("Internet response exceeds 4 MiB.");
  const normalized=normalizeInternetPayload(JSON.parse(text),limited?"intelsky":airlabs?"airlabs":relay?"adsblol-relay":"custom",
    state.queryLat,state.queryLon,state.queryRadius);
  if(airlabs)state.airlabsLastFetch=Date.now();
  if(relay){
   state.relayLastFetch=Date.now();
   state.relayLastQueryKey=publicQueryKey;
  }
  return normalized;
 }catch(error){
  if(error?.name==="AbortError")throw Error("Internet feed timeout (10 seconds).");
  if(error instanceof TypeError || error?.name==="TypeError")
   throw Error("Network or CORS blocked this feed. Public relay may be unavailable, throttled or blocked; try again later.");
  throw error;
 }finally{clearTimeout(timeout)}
}
// Browser-direct RF (from adsb_worker.mjs) is a distinct proven observation
// source. Never replace RF positions with a network position silently.
function browserSourceResult(mode=String($("mode").value),internetError=null){
 const now=Date.now();
 const age=Math.max(0,(now-(state.usbSnapshot.updatedAt||now))/1000);
 const local=(state.usbSnapshot.aircraft||[]).map(a=>{
  const row={...a};
  if(Number.isFinite(row.seen))row.seen+=age;
  if(Number.isFinite(row.seen_pos))row.seen_pos+=age;
  return row;
 }).filter(a=>Number.isFinite(a.seen)&&a.seen<=60);
 const netAge=state.internetSnapshot?.generated_at
   ? Math.max(0,now/1000-state.internetSnapshot.generated_at):Infinity;
 const remote=(state.internetSnapshot?.aircraft||[]).map(a=>{
  const row={...a};
  if(Number.isFinite(row.seen))row.seen+=netAge;
  if(Number.isFinite(row.seen_pos))row.seen_pos+=netAge;
  return row;
 }).filter(a=>Number.isFinite(a.seen)&&a.seen<=60);
 const wantLocal=mode!=="internet",wantOnline=mode!=="antenna"&&
   (mode!=="auto"||local.length===0);
 const byId=new Map(),rows=[];
 if(wantLocal)for(const a of local){
  const id=String(a.hex||"").toLowerCase();
  if(!/^[0-9a-f]{6}$/.test(id))continue;
  const row={...a,hex:id,sources:["antenna"],
    position_source:isPositioned(a)?"antenna":null,
    observations:{antenna:{...a}}};
  rows.push(row);byId.set(id,row);
 }
 if(wantOnline)for(const a of remote){
  const id=String(a.hex||"").toLowerCase();
  if(!/^[0-9a-f]{6}$/.test(id))continue;
  const exists=byId.get(id);
  if(exists){
   exists.sources=["antenna","internet"];
   exists.observations.internet=a;
   exists.internet_providers=[...(a.internet_providers||[])];
   if(!isPositioned(exists)&&isPositioned(a)){
    exists.lat=a.lat;exists.lon=a.lon;exists.seen_pos=a.seen_pos;
    exists.position_source="internet";
   }
   if(!exists.flight&&a.flight)exists.flight=a.flight;
   if(!Number.isFinite(exists.alt_baro)&&Number.isFinite(a.alt_baro))exists.alt_baro=a.alt_baro;
  }else{
   const row={...a,hex:id,sources:["internet"],
     internet_providers:[...(a.internet_providers||[])],
     position_source:isPositioned(a)?"internet":null,
     observations:{internet:a}};
   rows.push(row);byId.set(id,row);
  }
 }
 const attribution=state.internetSnapshot?.sources?.internet?.attribution;
 return {
  generated_at:now/1000,
  active_sources:[...(wantLocal?["antenna"]:[]),...(wantOnline&&state.onlineFeed?["internet"]:[])],
  aircraft:rows,
  counts:{antenna:wantLocal?local.length:0,
    internet:wantOnline?remote.length:0,combined:rows.length},
  sources:{
   antenna:{state:local.length?"receiving":state.usbSnapshot.updatedAt?"no_recent_aircraft":"starting",
     messages:state.usbMessageCount,
     note:"Direct WebUSB 1090 MHz / CRC-verified Mode S; no readsb service."},
   internet:{state:!state.onlineFeed?"not_configured":
       internetError?"error":state.internetSnapshot?"available":"not_yet_loaded",
      error:internetError,provider:state.internetSnapshot?.sources?.internet?.provider,
      attribution:attribution||(
        state.onlineProvider==="intelsky"?"IntelSky.org · limited military/government coverage":
       state.onlineProvider==="adsblol-relay"?"adsb.lol (ODbL 1.0) via public CORS relay":
        "Network provider attribution not yet available"),
      limited_coverage:state.onlineProvider==="intelsky",
      providers:state.internetSnapshot?.sources?.internet?.providers,
      updated_at:state.internetSnapshot?.sources?.internet?.updated_at}
  }
 };
}
function displayUsbSnapshot(){
 if(state.connectionKind!=="usb")return;
 const result=browserSourceResult();
 state.data=result.aircraft;
 updateCounters(result.counts);feedSummary(result.sources);recordTracks();rememberRfPlanes();
 applyStartupPriority();
 renderTable();paint();
 $("receiverStatus").textContent="Direct WebUSB 1090 MHz receiver · "+
   state.usbMessageCount+" CRC-verified Mode S messages. RF access is held only by this browser tab.";
 $("lastUpdate").textContent=formatTime(result.generated_at);
 $("sourceCredits").textContent=result.sources.internet.attribution;
}
// The RF timing lab runs fully locally: no API calls, no simulated packets,
// no automatic storage or upload. Imported session files never reach the map.
const timingLab=TihuluTimingLab.createSession();
let timingPaused=false;
function formatInterval(ms){
 return Number.isFinite(ms)?(ms>=1000?(ms/1000).toFixed(2)+" s":ms.toFixed(2)+" ms"):"—";
}
function paintTimingPlot(){
 const canvas=$("timingPlot"),context=canvas?.getContext("2d");
 if(!context)return;
 const w=canvas.width,h=canvas.height;
 context.clearRect(0,0,w,h);context.fillStyle="#0b1928";context.fillRect(0,0,w,h);
 const samples=timingLab.recent(120).reverse(),last=new Map(),intervals=[];
 for(const e of samples){
  const p=last.get(e.icao24);
  if(p&&p.segment===e.segment&&e.sample_index>p.sample_index)
   intervals.push((e.sample_index-p.sample_index)/2000000*1000);
  last.set(e.icao24,e);
 }
 context.font="10px system-ui";context.fillStyle="#acc7db";
 if(!intervals.length){
  context.fillText("Waiting for repeated CRC-valid frames from one aircraft",9,47);
  return;
 }
 // Relative local intervals only, never aircraft-to-antenna propagation.
 const values=intervals.slice(-48),peak=Math.max(1,...values);
 const bar=(w-14)/values.length;
 values.forEach((v,i)=>{
  const height=Math.max(1,Math.min(h-27,(v/peak)*(h-29)));
  context.fillStyle="#5ed7af";context.fillRect(7+i*bar,h-16-height,Math.max(1,bar-2),height);
 });
 context.fillStyle="#b7cbdf";context.fillText("Same-aircraft message intervals (local sample clock)",7,11);
 context.fillText("max "+formatInterval(peak),7,h-3);
}
function renderTimingLab(){
 const info=timingLab.summary(),t=info.telemetry;
 $("timingFrames").textContent=info.valid_frames.toLocaleString("en");
 $("timingUnique").textContent=String(info.unique_aircraft);
 $("timingInterval").textContent=formatInterval(info.median_same_aircraft_interval_ms);
 $("timingMad").textContent=formatInterval(info.median_absolute_deviation_ms);
 $("timingHostRead").textContent=t&&Number.isFinite(t.host_read_last_ms)?
  t.host_read_last_ms.toFixed(2)+" ms":"—";
 $("timingRetained").textContent=info.retained.toLocaleString("en")+
  (info.evicted?" · "+info.evicted+" older removed":"");
 const replay=info.mode==="offline_replay";
 let modeText=replay?"Offline replay · imported, untrusted local file (not live RF)":
   state.connectionKind==="usb"?(timingPaused?"WebUSB active · recording paused":"WebUSB 1090 MHz · recording CRC-verified frames locally"):
   info.retained?"Receiver stopped · last WebUSB timing session remains available for export":
   state.connectionKind==="bridge"?
    "Native readsb provides aircraft.json ages only; per-message ADC timing is not available from this backend.":
    "No local RF timing stream · start WebUSB in supported Chromium, or open a saved offline recording.";
 $("timingMode").textContent=modeText;
 $("timingPause").textContent=replay?"Start new live session":timingPaused?"Resume record":"Pause record";
 $("timingPause").setAttribute("aria-pressed",String(timingPaused));
 $("timingQuality").textContent="Sample resolution: 0.5 µs nominal (2 Msps), not calibrated UTC. "+
  "Aircraft transmission epoch: unavailable. Receiver distance: unavailable. "+
  (t?"Host read avg/max: "+Number(t.host_read_mean_ms).toFixed(2)+"/"+
   Number(t.host_read_max_ms).toFixed(2)+" ms; possible scheduling delays: "+
   t.estimated_usb_gap_count+"; records not forwarded: "+t.frames_not_forwarded+
   ". Neither counter proves RF sample loss. ":"")+
  "Unique-aircraft count is not a positioning accuracy score.";
 const body=$("timingEvents");body.replaceChildren();
 const items=timingLab.recent(12);
 if(!items.length){
  const tr=document.createElement("tr"),td=document.createElement("td");
  td.colSpan=4;td.textContent="No recorded CRC-valid radio frames";
  tr.append(td);body.append(tr);
 }
 for(const e of items){
  const tr=document.createElement("tr");
  const vals=[e.icao24.toUpperCase(),e.sample_index.toLocaleString("en"),
    "DF"+e.df+"/TC"+e.type_code,
    new Date(e.decoder_utc_ms).toISOString().slice(11,23)+"Z"];
  for(const val of vals){
   const td=document.createElement("td");td.textContent=val;tr.append(td);
  }
  body.append(tr);
 }
 paintTimingPlot();
}
window.tihuluTimingBatch=(events,telemetry)=>{
 if(state.connectionKind!=="usb"||timingPaused)return;
 timingLab.addBatch(events,telemetry);
 renderTimingLab();
};
$("timingPause").onclick=()=>{
 if(timingLab.summary().mode==="offline_replay"){
  timingLab.reset();timingPaused=false;
  window.tihuluTimingClear?.();window.tihuluTimingRecord?.(true);
 }else{
  timingPaused=!timingPaused;
  window.tihuluTimingRecord?.(!timingPaused);
 }
 renderTimingLab();
};
$("timingReset").onclick=()=>{
 timingLab.reset();timingPaused=false;
 window.tihuluTimingClear?.();window.tihuluTimingRecord?.(true);
 renderTimingLab();
};
function saveTimingText(name,body,mime){
 const blob=new Blob([body],{type:mime}),url=URL.createObjectURL(blob);
 const a=document.createElement("a");a.href=url;a.download=name;
 document.body.append(a);a.click();a.remove();
 // Defer revocation to allow Qt WebEngine and desktop download handlers to see it.
 setTimeout(()=>URL.revokeObjectURL(url),30000);
}
function exportName(extension){
 return "tihulu-rf-timing-"+new Date().toISOString().replace(/[:.]/g,"-")+"."+extension;
}
$("timingSaveJson").onclick=()=>{
 saveTimingText(exportName("json"),JSON.stringify(timingLab.serialize(),null,2),"application/json");
};
$("timingSaveCsv").onclick=()=>{
 const head=["icao24","sample_index","segment","df","type_code","decoder_utc_ms",
   "sample_rate_hz","frame_hex","receipt_source"];
 const csv=[head.join(",")].concat(timingLab.serialize().events.map(e=>
   head.map(key=>String(e[key])).join(","))).join("\r\n")+"\r\n";
 saveTimingText(exportName("csv"),csv,"text/csv;charset=utf-8");
};
$("timingImport").onchange=async()=>{
 const input=$("timingImport"),file=input.files?.[0];
 if(!file)return;
 try{
  if(file.size>4*1024*1024)throw Error("File exceeds the 4 MiB offline import limit");
  const raw=JSON.parse(await file.text());
  timingLab.load(raw);timingPaused=true;
  window.tihuluTimingRecord?.(false);
  renderTimingLab();
  notice("Offline timing recording opened locally; live aircraft map remains unchanged.");
 }catch(error){notice("Offline session rejected: "+String(error.message||error))}
 finally{input.value="";}
};
renderTimingLab();


window.tihuluUsbCanStart=()=>state.connectionKind!=="bridge";
window.tihuluUsbStarted=()=>{
 state.usbSnapshot={aircraft:[],messages:0,updatedAt:Date.now()};
 state.usbMessageCount=0;state.connectionKind="usb";state.connected=true;
 rfHistory.clear();rfHistoryRevision++;
 timingLab.reset();timingPaused=false;renderTimingLab();
 let networkSetupError=null;
 try{
  if(navigator.onLine===false){
   state.onlineFeed="";state.onlineProvider="off";
  }else state.onlineFeed=configuredOnlineFeed();
 }
 catch(error){
  networkSetupError=String(error.message||error);
  state.onlineFeed="";state.onlineProvider="off";
 }
 state.internetBackoffUntil=0;state.airlabsLastFetch=0;
 $("mode").value=state.onlineFeed?"hybrid":"antenna";
 connection(true,"Direct browser WebUSB · 1090 MHz");
 for(const id of ["start","stop","restart"])$(id).disabled=true;
 if(!state.timer)state.timer=setInterval(()=>{if(!document.hidden)refresh()},15000);
 displayUsbSnapshot();
 void refresh();
 notice(networkSetupError
  ?"WebUSB started with antenna only; Internet configuration requires attention: "+networkSetupError
  :"Browser SDR connected. Loading the selected Internet network alongside real RF.");
};
window.tihuluUsbSnapshot=packet=>{
 if(state.connectionKind!=="usb")return;
 state.usbSnapshot=packet;
 state.usbMessageCount=packet.messages||0;
 displayUsbSnapshot();
};
window.tihuluUsbError=message=>notice("Direct USB: "+message);
window.tihuluUsbStopped=()=>{
 if(state.connectionKind!=="usb")return;
 state.usbSnapshot={aircraft:[],messages:0,updatedAt:0};
 state.usbMessageCount=0;state.data=[];state.lastData=[];
 if(state.onlineFeed){
  state.connectionKind="internet";state.connected=true;$("mode").value="internet";
  connection(true,"Internet feed only · USB released");
  refresh();
 }else{
  if(state.timer)clearInterval(state.timer);
  state.timer=null;state.connected=false;state.connectionKind="none";
  updateCounters();renderTable();paint();connection(false,"USB released");
  $("receiverStatus").textContent="Direct WebUSB stopped; this tab released its SDR.";
 }
 renderTimingLab();
};
// Called only by our packaged Qt WebEngine wrapper after the trusted local
// page is loaded. The token is never placed in a URL, cookies or storage.
window.tihuluNativeConnect=async function(base, token){
 // Qt desktop is already installed; keep the native UI identity regardless
 // of whether optional online aircraft data loads.
 window.tihuluNativeDesktop=true;
 document.documentElement.classList.add("native");
 const pairingPanel=document.querySelector(".bridge-advanced");
 if(pairingPanel)pairingPanel.open=true;
 const indicator=document.querySelector(".desktop-installed-label")||
   document.createElement("span");
 indicator.className="desktop-installed-label";
 indicator.textContent="Desktop app · installed";
 const header=document.querySelector(".masthead .connection");
 if(header&&!indicator.isConnected)header.prepend(indicator);
 $("connectionLabel").textContent="Pairing desktop receiver…";
 // Desktop explicitly opts into both observed RF and public online layers.
 $("mode").value="hybrid";
 $("bridgeUrl").value=base;
 $("token").value=token;
 await connect();
};
async function api(path,options={}){
 if(!state.base || !state.token) throw Error("Pair with your local bridge first.");
 const abort=new AbortController(), timeout=setTimeout(()=>abort.abort(),10000);
 try{
  const r=await fetch(state.base+path,{
   ...options,headers:{"Authorization":"Bearer "+state.token,...options.headers},
   cache:"no-store",signal:abort.signal
  });
  const result=await r.json();
  if(!r.ok) throw Error(result.error||"Bridge returned HTTP "+r.status);
  return result;
 }finally{clearTimeout(timeout)}
}
function connection(active,text){
 state.connected=active; $("connectionLabel").textContent=text;
 $("connectionDot").classList.toggle("online",active);
 if(!active){
  for(const id of ["start","stop","restart"])$(id).disabled=true;
 }
}
async function checkReceiver(){
 const r=await api("/api/status");
 const canControl=Boolean(r.control_enabled)&&r.mode!=="Remote JSON";
 $("receiverStatus").textContent=(r.active?"Decoder running — ":"Decoder stopped — ")+r.detail+
   (canControl?" · local controls available":" · receiver controls read-only")+
   (r.startup_error?" · START FAILED: "+r.startup_error:"")+
   (!r.active&&canControl
     ?" · Press Start for real local 1090 MHz ADS-B. Release this SDR from SatDump/Satellite Center first."
     :"")+
   " Internet aircraft are independent; decoder activity alone does not prove RF reception.";
 $("receiverStatus").dataset.pairState="paired";
 $("start").disabled=!canControl||Boolean(r.active);
 $("stop").disabled=!canControl||!r.active;
 $("restart").disabled=!canControl||!r.active;
}
async function connect(){
 if(state.timer){clearInterval(state.timer);state.timer=null;}
 let verifiedBridge=false; // only authenticated /api/status counts as paired
 try{
  if(state.connectionKind==="usb"){
   // The Connect button is for optional Internet feed configuration when the
   // USB receiver is already running — never launch a second RF process.
   state.onlineFeed=configuredOnlineFeed();
   state.internetBackoffUntil=0;state.airlabsLastFetch=0;
   state.internetSnapshot=null;
   $("mode").value=state.onlineFeed?"hybrid":"antenna";
   await refresh(true);
   state.timer=setInterval(()=>{if(!document.hidden)refresh()},15000);
   return;
  }
  const token=$("token").value.trim();
  // A bad optional Internet provider is NOT an unsuccessful native pairing.
  let networkError=null;
  try{state.onlineFeed=configuredOnlineFeed();}
  catch(error){
   if(!token)throw error;
   state.onlineFeed="";
   networkError=String(error?.message||error);
  }
  state.internetBackoffUntil=0;state.airlabsLastFetch=0;
  if(token){
   state.base=getBase($("bridgeUrl").value.trim());
   state.token=token;state.connectionKind="bridge";
   await checkReceiver();
   verifiedBridge=true;
  }else if(state.onlineFeed){
   state.base="";state.token="";state.connectionKind="internet";
   $("receiverStatus").textContent="Internet-only: no local hardware connected. Pair a bridge for antenna data.";
   for(const id of ["start","stop","restart"])$(id).disabled=true;
  }else{
   throw Error("For antenna data enter a local pairing token; for Internet only enter an HTTPS Internet feed URL.");
  }
  state.connected=true;
  // Authenticated /api/status has already completed in checkReceiver().
  // Aircraft.json / external Internet feed refresh may fail independently.
  // Previously this failure reset connectionKind and disabled Start/Stop,
  // while still displaying old Internet aircraft and "controls enabled".
  connection(true,state.connectionKind==="bridge"
    ?"Desktop paired · local SDR control available"
    :"Internet source configured · check individual provider statuses");
  $("token").value="";
  state.timer=setInterval(()=>{if(!document.hidden)refresh()},15000);
  try{await refresh(true);}
  catch(error){
   notice("Receiver pairing retained; aircraft refresh failed: "+
     String(error?.message||error)+". Check readsb, USB ownership and Internet provider.");
  }
  if(networkError)notice("Desktop receiver paired; optional Internet feed unavailable: "+networkError);
  if(state.connectionKind==="bridge"){
   // Native Qt changes its loopback port each time. Synchronize only the
   // explicitly selected place, never a receiver/GPS site coordinate.
   try{
    const locationModule=await import("./flight_location_ui.mjs");
    const tabPlace=locationModule.readSavedPlace();
    if(state.moved && tabPlace){
     await api("/api/search-location",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify(tabPlace)});
    }else if(!state.moved){
     const stored=await api("/api/search-location");
     if(stored?.place&&!state.moved)applyPlaceToFlightRadar(stored.place,false);
    }
   }catch(error){notice("Native location preference unavailable: "+error.message);}
  }
 }catch(e){
  if(state.connectionKind==="usb"){
   // A bad optional network key/URL must not disconnect healthy WebUSB
   // or permanently cancel the already-running RF refresh timer.
   state.connected=true;displayUsbSnapshot();
   if(!state.timer)state.timer=setInterval(()=>{if(!document.hidden)refresh()},15000);
   notice("Optional Internet feed failed; direct WebUSB remains connected: "+e.message);
  }else if(state.connectionKind==="bridge" && state.token && verifiedBridge){
   // Preserve independently verified native bridge after an optional error.
   state.connected=true;
   connection(true,"Desktop receiver paired · no current aircraft data");
   if(!state.timer)state.timer=setInterval(()=>{if(!document.hidden)refresh()},15000);
   notice("Receiver bridge paired; initial data unavailable: "+e.message);
  }else if(state.connectionKind==="internet" && state.onlineFeed){
   // A public CORS relay outage should not permanently end the browser's
   // Internet-only session. Retry while visible without touching RF devices.
   state.token="";state.connected=true;
   connection(true,"Internet source configured · awaiting live observations");
   $("networkStatus").textContent="Internet unavailable: "+e.message+" · automatic retry while tab is visible.";
   $("feedStatus").textContent="Antenna: not connected\nInternet: unavailable ("+e.message+")";
   if(!state.timer)state.timer=setInterval(()=>{if(!document.hidden)refresh()},15000);
   notice("Internet source unavailable: "+e.message+". Retrying automatically; no aircraft will be shown without fresh observations.");
  }else{
   state.connected=false;state.token="";state.connectionKind="none";
   connection(false,window.tihuluNativeDesktop
     ?"Desktop receiver pairing failed":"Not connected");
   $("receiverStatus").dataset.pairState="failed";
   $("receiverStatus").textContent="Receiver pairing failed: "+String(e.message||e)+
     ". Internet-only aircraft may still appear, but native SDR controls are unavailable.";
   notice("Connection failed: "+e.message+". Check native bridge/receiver permissions.");
  }
 }
}
function disconnect(){
 if(state.connectionKind==="usb")void window.tihuluStopUsb?.();
 if(state.timer)clearInterval(state.timer);
 state.timer=null;state.token="";state.base="";state.onlineFeed="";state.connectionKind="none";state.data=[];state.lastData=[];state.lastFreshAt=0;state.dataReceivedAt=0;
 state.tracks.clear();state.autoFocused=false;
 connection(false,"Disconnected");updateCounters();renderTable();paint();
 $("feedStatus").textContent="No source connected.";
 $("receiverStatus").textContent="Disconnected.";
 notice("Disconnected. No local hardware commands were issued.");
}
function updateCounters(counts){
 $("localCount").textContent=counts?.antenna??"—";
 $("onlineCount").textContent=counts?.internet??"—";
 $("combinedCount").textContent=counts?.combined??"—";
 $("visibleCount").textContent=state.data.filter(visible).length;
}
function formatTime(value){
 return Number.isFinite(value)?new Date(value*1000).toLocaleTimeString():"—";
}
// The source schema normalizes altitudes to feet and ground speed to knots.
const flightValue=v=>typeof v==="number"&&Number.isFinite(v)?v:null;
function showAltitude(a,unit=true){
 const raw=aircraftAltitude(a);
 return raw===null?"—":new Intl.NumberFormat("en",{maximumFractionDigits:0})
  .format(state.units==="metric"?raw*0.3048:raw)+(unit?(state.units==="metric"?" m":" ft"):"");
}
function showSpeed(a,unit=true){
 const kts=flightValue(a?.gs);
 return kts===null?"—":new Intl.NumberFormat("en",{maximumFractionDigits:1})
  .format(state.units==="metric"?kts*1.852:kts)+(unit?(state.units==="metric"?" km/h":" kt"):"");
}
function showVerticalRate(a){
 const raw=flightValue(a?.baro_rate)??flightValue(a?.geom_rate);
 return raw===null?"—":new Intl.NumberFormat("en",{maximumFractionDigits:0})
  .format(state.units==="metric"?raw*0.3048:raw)+(state.units==="metric"?" m/min":" ft/min");
}
// Historical constraints remain distinct from live aircraft observations.
// The assumption is valid only while the RF receiver stays physically fixed.
const rfHistory=new Map();
let rfHistoryRevision=0,coverageCacheRows=null,coverageCacheResult=null,coverageCacheRevision=-1;
let rfLocatorActive=true,rfLocatorFocused=true; // layer on; camera is not automatically stolen
let rfFollowCenter=true,rfLastFollowModel=null,rfLastProgressModel=null;
let rfLastRegion=null,rfModelProgressText="Waiting for positioned RF aircraft.";
const rfSelectedPlanes=new Set();
let rfAircraftListSignature="";
const RF_PLANE_COLORS=["#61c5e7","#8dafff","#b5a1f0","#6ddbbd","#f69bba","#eeaea0"];
function rfPlaneColor(hex){
 let hash=0;for(const c of hex)hash=(hash*31+c.charCodeAt(0))>>>0;
 return RF_PLANE_COLORS[hash%RF_PLANE_COLORS.length];
}
function rememberRfPlanes(){
 if(!$("rfRemember").checked)return;
 let changed=false,now=Date.now();
 for(const a of state.data){
  if(!Number.isFinite(a.seen)||!Number.isFinite(a.seen_pos)||
     a.seen>10||a.seen_pos>5)continue;
  const record=TihuluRFCoverage.recordedCircle(a,now);
  if(!record)continue;
  // Only store direct radio positions. Use real ground speed / heading
  // to choose spatially useful successive fixes and reject impossible jumps.
  // Never project RF positions from velocity (map animation is separate).
  const same=[...rfHistory.values()].filter(r=>r.hex===record.hex);
  const previous=same.length?same[same.length-1]:null;
  const decision=TihuluRFCoverage.trackSampleDecision(previous,record);
  if(!decision.keep)continue;
  const key=record.hex+":"+Math.round(record.capturedAtMs);
  rfHistory.set(key,record);changed=true;
 }
 // Fixed-site history is session-only, never persisted.
 for(const [key,r] of rfHistory)if(now-r.capturedAtMs>2*3600*1000){
  rfHistory.delete(key);changed=true;
 }
 while(rfHistory.size>64){
  // Preserve a recent constraint for each independent aircraft before
  // trimming duplicate path samples from a busy aircraft.
  const remainingByIcao=new Map();
  for(const row of rfHistory.values())
   remainingByIcao.set(row.hex,(remainingByIcao.get(row.hex)||0)+1);
  let keyToDrop=null;
  for(const [key,row] of rfHistory){
   if(remainingByIcao.get(row.hex)>1){keyToDrop=key;break;}
  }
  if(keyToDrop===null)keyToDrop=rfHistory.keys().next().value;
  rfHistory.delete(keyToDrop);changed=true;
 }
 if(changed)rfHistoryRevision++;
}
function coverageResult(){
 if(state.data!==coverageCacheRows||coverageCacheRevision!==rfHistoryRevision){
  coverageCacheRows=state.data;coverageCacheRevision=rfHistoryRevision;
  coverageCacheResult=TihuluRFCoverage.compute(state.data,
   $("rfRemember").checked?[...rfHistory.values()]:[]);
 }
 return coverageCacheResult;
}
function renderRfPlaneLayers(result){
 const layers=result.aircraftCircles||[];
 const signature=layers.map(item=>[
  item.hex,item.flight,item.samples,item.circle.lat.toFixed(3),
  item.circle.lon.toFixed(3),item.circle.radiusKm.toFixed(1)
 ].join(":")).join("|");
 if(signature===rfAircraftListSignature)return;
 rfAircraftListSignature=signature;
 const node=$("rfAircraftLayers");node.replaceChildren();
 if(!layers.length){node.textContent="No genuinely radio-positioned aircraft yet.";return;}
 for(const item of layers){
  const label=document.createElement("label");
  label.className="rf-aircraft-layer";
  const input=document.createElement("input");input.type="checkbox";
  input.value=item.hex;input.checked=rfSelectedPlanes.has(item.hex);
  input.setAttribute("aria-label","Show RF horizon for "+item.hex);
  input.addEventListener("change",()=>{
   if(input.checked)rfSelectedPlanes.add(item.hex);else rfSelectedPlanes.delete(item.hex);
   paint();
  });
  const swatch=document.createElement("span");swatch.className="rf-aircraft-swatch";
  swatch.style.background=rfPlaneColor(item.hex);
  const title=document.createElement("span");
  title.textContent=(item.flight||item.hex).trim()+" · "+item.hex.toUpperCase()+
   " · "+item.samples+" real RF fix"+(item.samples===1?"":"es");
  label.append(input,swatch,title);node.append(label);
 }
}
$("rfAllPlanes").onclick=()=>{
 for(const item of coverageResult().aircraftCircles||[])rfSelectedPlanes.add(item.hex);
 for(const cb of $("rfAircraftLayers").querySelectorAll('input[type="checkbox"]'))cb.checked=true;
 paint();
};
$("rfNoPlanes").onclick=()=>{
 rfSelectedPlanes.clear();
 for(const cb of $("rfAircraftLayers").querySelectorAll('input[type="checkbox"]'))cb.checked=false;
 paint();
};
for(const id of ["rfFill","rfHatch","rfModelCircle","rfModelPin"])
 $(id).addEventListener("change",()=>paint());
$("rfFollow").onchange=()=>{
 rfFollowCenter=$("rfFollow").checked;
 if(rfFollowCenter){rfLocatorActive=true;rfLocatorFocused=false;rfLastFollowModel=null;}
 paint();
};
function disableRfFollow(){
 if(!rfFollowCenter)return;
 rfFollowCenter=false;$("rfFollow").checked=false;
}
$("rfRemember").onchange=()=>{
 if(!$("rfRemember").checked){rfHistory.clear();rfHistoryRevision++;}
 else rememberRfPlanes();
 paint();
};
$("rfClearHistory").onclick=()=>{
 rfHistory.clear();rfHistoryRevision++;paint();
 notice("Only historic RF constraints cleared; live radio reception is unchanged.");
};
function renderCoverageStatus(){
 const result=coverageResult();
 renderRfPlaneLayers(result);
 if(result!==rfLastProgressModel){
 const evidence=$("rfEvidence");
 if(result.status==="region"){
  const items=result.aircraftDistances||[];
  evidence.replaceChildren();
  const heading=document.createElement("strong");
  heading.textContent="Combined RF horizon constraints · "+items.length+
   " independent aircraft / "+result.constraintsUsed+" genuine position samples";
  evidence.append(heading);
  for(const item of items){
   const line=document.createElement("div");line.className="rf-evidence-line";
   const name=document.createElement("span");
   name.textContent=(item.flight||item.hex)+" · "+item.hex.toUpperCase()+
    " · "+item.sampleCount+" real fix"+(item.sampleCount===1?"":"es");
   const numbers=document.createElement("span");
   const age=Number.isFinite(item.approximatePositionAgeSeconds)
    ?item.approximatePositionAgeSeconds.toFixed(1)+" s position age":"unknown age";
   const speed=Number.isFinite(item.speedKt)
    ?" · "+item.speedKt.toFixed(0)+" kt RF speed":"";
   numbers.textContent=Math.round(item.centerDistanceKm)+" km model center-to-plane / "+
    Math.round(item.horizonKm)+" km horizon · "+age+speed;
   line.append(name,numbers);evidence.append(line);
  }
  const note=document.createElement("small");
  note.textContent="These are independently evaluated RF upper-bound disks. "+
   "Center-to-plane distances are geometric consequences of the MODEL, "+
   "not signal travel-time measurements. Snapshot position age is used "+
   "only for historical time ordering; it is not propagation delay.";
  evidence.append(note);
 }else{
  evidence.textContent="No multi-aircraft RF center yet: "+
   (result.count||0)+" independent eligible radio aircraft; "+
   "4 required. The map does not infer its center from a single airplane.";
 }
  rfLastProgressModel=result;
  if(result.status==="region"){
   const r=result.region;
   if(rfLastRegion){
    const shiftKm=TihuluRFCoverage.distanceKm(rfLastRegion,r);
    const changed=r.extentKm-rfLastRegion.extentKm;
    rfModelProgressText="Sampled model spread "+
     (changed<0?"narrowed":changed>0?"widened":"unchanged")+
     " by "+Math.abs(Math.round(changed))+" km · center shifted "+
     shiftKm.toFixed(1)+" km on latest RF update. "+
     "This is NOT measured accuracy or a statistical error radius.";
   }else rfModelProgressText="RF feasible region initialized; center and sampled spread update as genuine fixes arrive.";
   rfLastRegion={lat:r.lat,lon:r.lon,extentKm:r.extentKm};
  }else rfModelProgressText="RF area unavailable ("+result.status+
    "). No center or error estimate is inferred.";
 }
 $("rfProgress").textContent=rfModelProgressText;
 const label=$("rfCoverageStatus");
 const info={
  insufficient:result.count+"/4 independently positioned local RF aircraft ("+(result.liveCount||0)+" live, "+(result.historyCount||0)+" stationary-history). Internet-only aircraft, missing radio positions and Mode S without coordinates cannot qualify.",
  no_overlap:"Radio-horizon model has no common overlap. Check altitude/age/source validity.",
  unresolved:"Possible region too thin or fragmented for current grid. No coordinate fix.",
  region:"MULTI-AIRCRAFT RF MODEL ("+result.geometryStatus+") · "+result.count+
  " distinct RF aircraft ("+result.liveCount+" live, "+result.historyCount+" stationary-history) · "+
   (result.constraintsUsed||result.count)+" constraints applied · coarse extent ~"+
    Math.round(result.region.extentKm)+" km. More planes may narrow this area, NOT establish GPS accuracy."
 };
 label.textContent=info[result.status]||"Insufficient evidence";
 const output=$("rfLocateStatus"),button=$("rfLocate");
 button.textContent=rfLocatorActive?"RF area · ON":"RF area · OFF";
 $("rfFocus").disabled=result.status!=="region";
 button.setAttribute("aria-pressed",String(rfLocatorActive));
 if(!rfLocatorActive){
  output.textContent="RF area overlay is off. Enable RF area to see the modeled region without drawing giant horizon rings.";
 }else if(result.status==="region"){
  const r=result.region;
  output.textContent="LIVE MODEL CENTER (NOT GPS): "+
   r.lat.toFixed(4)+"°, "+r.lon.toFixed(4)+"° · Sampled spread-circle radius ~"+
   Math.round(r.extentKm)+" km from this center · "+
   result.count+" independent RF aircraft and "+result.constraintsUsed+
   " real position constraints. Circle radius is a map-model bound, not "+
   "measured error, statistical confidence or GPS accuracy. "+
   "No manual latitude/longitude, GPS, or Internet data used.";
 }else{
  output.textContent=result.status==="insufficient"
   ?"Waiting for 4+ independently positioned antenna aircraft ("+
     result.count+" eligible). Total decoded aircraft may include records without positions."
   :result.status==="no_overlap"
    ?"Conflicting RF horizon constraints: there is no shared feasible area. No coordinate is shown; clear stationary history if the antenna moved."
    :"No stable possible-area centroid at this grid resolution; no receiver coordinate is shown.";
 }
 return result;
}
$("rfLocate").onclick=()=>{
 rfLocatorActive=!rfLocatorActive;
 rfLocatorFocused=true;
 paint();
 if(rfLocatorActive)notice("RF possible-area overlay enabled: positioned antenna aircraft only. Use Focus RF area to center the map; not GPS.");
};
$("rfFocus").onclick=()=>{
 rfLocatorActive=true;rfLocatorFocused=false;rfLastFollowModel=null;paint();
 notice("Map centered on a modeled RF feasible area, NOT your measured position.");
};
function focusRfModelWhenReady(result){
 if(!rfLocatorActive||result.status!=="region")return;
 if(rfLocatorFocused && (!rfFollowCenter||rfLastFollowModel===result))return;
 const r=result.region,km=r.extentKm;
 const initialFocus=!rfLocatorFocused||rfLastFollowModel===null;
 // Don't force zoom on every new RF observation: the center can move,
 // but manual zoom remains in the user's control while following.
 state.lat=r.lat;state.lon=r.lon;
 if(initialFocus)state.zoom=km>850?4:km>420?5:km>200?6:km>95?7:km>45?8:km>22?9:10;
 state.moved=true;state.autoFocused=false;
 state.centerLabel="4+ AIRCRAFT RF MODEL CENTER · NOT GPS · sampled spread ~"+
  Math.round(km)+" km";
 rfLocatorFocused=true;rfLastFollowModel=result;
}
function paintRfLocator(result){
 if(!rfLocatorActive||result.status!=="region"||!$("rfModelPin").checked)return;
 const [x,y]=xy(result.region.lat,result.region.lon);
 if(x<0||x>canvas.clientWidth||y<0||y>canvas.clientHeight)return;
 ctx.save();
 ctx.fillStyle="rgba(8,34,45,.94)";ctx.strokeStyle="#6fe4ef";
 ctx.lineWidth=2.5;ctx.setLineDash([]);
 ctx.beginPath();ctx.arc(x,y,9,0,Math.PI*2);ctx.fill();ctx.stroke();
 ctx.beginPath();ctx.moveTo(x-16,y);ctx.lineTo(x+16,y);
 ctx.moveTo(x,y-16);ctx.lineTo(x,y+16);ctx.stroke();
 ctx.font="bold 11px system-ui";ctx.fillStyle="#97eef5";
 ctx.shadowColor="#0a1a27";ctx.shadowBlur=5;
 ctx.fillText("RF MODEL CENTER · NOT GPS",x+18,y-12);
 ctx.restore();
}
function renderPopup(a){
 const popup=$("aircraftPopup");
 if(!a){popup.hidden=true;return}
 $("popupFlight").textContent=String(a.flight||a.hex||"Aircraft").trim();
 $("popupIcao").textContent="ICAO24 "+String(a.hex||"—").toUpperCase()+
   (a.r?" · "+String(a.r):"");
 $("popupSources").textContent=aircraftSourceBadge(a)+" · "+category(a)+
   (a.internet_providers?.length?" · "+a.internet_providers.map(id=>
   TihuluMultiSources.META[id]?.name||id).join(", "):"")+
   " · displayed position: "+(a.position_source||"unknown");
 $("popupAltitude").textContent=showAltitude(a);
 $("popupSpeed").textContent=showSpeed(a);
 const hdg=flightValue(a.track)??flightValue(a.true_heading);
 $("popupHeading").textContent=hdg===null?"—":hdg.toFixed(0)+"°";
 $("popupVerticalRate").textContent=showVerticalRate(a);
 $("popupType").textContent=String(a.t||a.type||a.flight_source_fields?.aircraft_icao||"—");
 $("popupSquawk").textContent=String(a.squawk||"—");
 $("popupPosition").textContent=isPositioned(a)
  ?a.lat.toFixed(5)+"°, "+a.lon.toFixed(5)+"°":"No fresh position";
 $("popupSeen").textContent=Number.isFinite(a.seen)
  ?"Last received "+a.seen.toFixed(1)+" s ago":"No observation age";
 const rf=a.observations?.antenna;
 const rfRssi=Number.isFinite(rf?.rssi)?rf.rssi:null;
 const timing=rf?.rf_timing;
 const lines=[
  "Aircraft transmit UTC: unavailable — ordinary ADS-B contains no precise departure timestamp.",
  "Receiver arrival UTC: not calibrated; USB buffering and transfer latency unknown."
 ];
 const modeledDistance=TihuluRFCoverage.modelDistanceInterval(coverageResult(),a);
 if(modeledDistance){
  lines.push("Conditional aircraft distance from feasible RF grid: ~"+
    modeledDistance.minKm+"–"+modeledDistance.maxKm+
    " km. This range assumes the radio-horizon model and its sampled receiver area; "+
    "NOT a measured slant range, GPS location, confidence interval or radio ranging.");
 }else if(rf && a.position_source==="antenna"){
  lines.push("Distance to this aircraft: unavailable; four verified positioned "+
    "antenna aircraft and a compatible feasible area are required for a conditional model interval.");
 }
 if(rfRssi!==null)lines.push("Local RF signal strength indicator: "+
  rfRssi.toFixed(1)+" dBFS (readsb relative reading, NOT distance). "+
  "Aircraft transmit power, antenna direction, buildings, gain and fading prevent reliable single-reading ranging.");
 else lines.push("RF RSSI: unavailable on this aircraft/backend; range cannot be measured.");
 if(timing && Number.isSafeInteger(timing.arrival_sample_index)){
  lines.push("RF preamble sample index: "+timing.arrival_sample_index.toLocaleString("en")+
    " · nominal sample interval "+timing.sample_period_us+" µs.");
  if(Number.isFinite(timing.decoder_observed_unix_ms))
   lines.push("Decoder processed UTC: "+new Date(timing.decoder_observed_unix_ms).toISOString()+
    " (software processing timestamp, NOT measured RF arrival).");
 }else{
  lines.push("Per-message sample-index timing unavailable from this receiver/backend.");
 }
 lines.push("Transmit–receive delay: not computable. Single unsynchronized RTL-SDR cannot solve location by flight timestamps.");
 $("popupTiming").textContent=lines.join("\n");
 popup.hidden=false;
 positionPopup(a);
}
function positionPopup(a){
 const popup=$("aircraftPopup");
 if(popup.hidden)return;
 const panel=popup.parentElement, cw=panel.clientWidth, ch=panel.clientHeight;
 let x=cw-340,y=canvas.offsetTop+12;
 if(isPositioned(a)){
  const [px,py]=xy(a.lat,a.lon);
  if(px>=0&&px<=canvas.clientWidth&&py>=0&&py<=canvas.clientHeight){
   x=canvas.offsetLeft+px+22;y=canvas.offsetTop+py-30;
  }
 }
 const width=Math.min(328,cw-16),height=Math.min(popup.scrollHeight,Math.min(ch*.74,510));
 popup.style.left=Math.max(8,Math.min(x,cw-width-8))+"px";
 popup.style.top=Math.max(8,Math.min(y,ch-height-8))+"px";
}
function closePopup(){
 if($("aircraftPopup").hidden)return;
 $("aircraftPopup").hidden=true;state.selected=null;renderTable();paint();
}
$("unitSystem").onchange=e=>{
 state.units=e.target.value==="metric"?"metric":"aviation";
 $("altitudeColumn").textContent="Altitude ("+(state.units==="metric"?"m":"ft")+")";
 $("speedColumn").textContent="Speed ("+(state.units==="metric"?"km/h":"kt")+")";
 renderTable();
 const found=state.data.find(a=>a.hex===state.selected);
 if(found)renderPopup(found);
};
$("popupClose").onclick=closePopup;
$("popupCenter").onclick=()=>{
 const found=state.data.find(a=>a.hex===state.selected);
 if(found&&isPositioned(found)){
  state.lat=found.lat;state.lon=found.lon;state.moved=true;
  state.centerLabel="Focused on selected "+(found.flight||found.hex);
  paint();positionPopup(found);
 }
};
$("popupCopy").onclick=()=>{
 if(state.selected && navigator.clipboard?.writeText)
  navigator.clipboard.writeText(state.selected.toUpperCase()).catch(()=>notice("Clipboard unavailable"));
};
$("popupRaw").onclick=()=>{
 $("rawAircraftPanel").open=true;
 $("rawAircraftPanel").scrollIntoView({behavior:"smooth",block:"nearest"});
};
document.addEventListener("pointerdown",e=>{
 if(!$("aircraftPopup").hidden && !$("aircraftPopup").contains(e.target) &&
    !canvas.contains(e.target) && !$("aircraftRows").contains(e.target))closePopup();
});
window.addEventListener("keydown",e=>{if(e.key==="Escape")closePopup()});

function renderTable(){
 const rows=$("aircraftRows"); rows.replaceChildren();
 const displayed=state.data.filter(visible);
 $("visibleCount").textContent=displayed.length;
 for(const a of displayed.slice(0,400)){
  const tr=document.createElement("tr");
  if(state.selected && a.hex===state.selected)tr.className="selected";
  for(const [index,value] of [
   (a.flight||"—").trim()+" / "+(a.hex||"—"),
   showAltitude(a,false),showSpeed(a,false),
   aircraftSourceBadge(a)+" · "+category(a)+
     (a.internet_providers?.length?" · "+a.internet_providers.map(id=>
       TihuluMultiSources.META[id]?.name||id).join(", "):"")
  ].entries()){
   const td=document.createElement("td");
   td.textContent=String(value);
   if(index===3)td.className="tag "+category(a);
   if(index===1)td.style.color=altitudeColor(a);
   tr.append(td);
  }
  tr.onclick=()=>choose(a,{center:true});
  rows.append(tr);
 }
 if(state.selected){
  const found=state.data.find(a=>a.hex===state.selected);
  if(!found){$("details").textContent="Selected aircraft no longer in the latest snapshot.";renderPopup(null);state.selected=null;}
  else if(!$("aircraftPopup").hidden)renderPopup(found);
 }
}
function choose(a,{center=false}={}){
 state.selected=a.hex||null;
 $("details").textContent=JSON.stringify({
  callsign:a.flight||null,icao24:a.hex||null,sources:a.sources,
  internet_providers:a.internet_providers||[],
  displayed_position_source:a.position_source,observations:a.observations
 },null,2);
 if(center&&isPositioned(a)){
  state.lat=a.lat;state.lon=a.lon;state.zoom=Math.max(state.zoom,9);
  state.moved=true;state.centerLabel="Selected "+(a.flight||a.hex||"aircraft");
 }
 renderTable();paint();renderPopup(a);
}
function feedSummary(feed){
 const l=feed?.antenna||{},i=feed?.internet||{};
 const details=[
  "Antenna: "+(l.state||"unknown")+(l.error?" ("+l.error+")":"")+
  (l.messages!=null?" · "+l.messages+" receiver messages":"")+
  (l.note?" · "+l.note:""),
  "Internet: "+(i.state||"unknown")+(i.error?" ("+i.error+")":"")+
  (i.updated_at?" · observed "+formatTime(i.updated_at):"")+
  (i.provider?" · "+i.provider:"")+
  (i.attribution?" · "+i.attribution:"")+
  (i.limited_coverage?" · Limited network coverage; 0 nearby does not mean the antenna failed.":"")
 ];
 $("feedStatus").textContent=details.join("\n");
 $("feedStatus").style.whiteSpace="pre-line";
 const status=$("networkStatus");
 if(status){
  const count=state.data.filter(a=>a.sources?.includes("internet")).length;
  status.textContent=i.state==="not_configured"
    ?"Internet off / not configured. Select a provider and Enable Internet."
    :i.error?"Internet error: "+i.error
    :i.state==="available"&&count===0
      ?(i.limited_coverage?"IntelSky connected — 0 covered aircraft in this region (limited military/government feed).":
         "Network connected — 0 fresh positioned aircraft in this search area.")
    :i.state==="available"
      ?"Internet active: "+count+" aircraft · "+(i.provider||"configured provider")
    :"Internet: "+(i.state||"not connected")+". "+(i.provider||"Select a provider to connect.");
 }
}
function recordTracks(){
 for(const a of state.data){
  if(!isPositioned(a) || !a.hex)continue;
  const key=a.hex+"_"+(a.position_source||"unknown");
  const points=state.tracks.get(key)||[];
  const last=points[points.length-1];
  if(!last || a.lat!==last[0] || a.lon!==last[1]){
   points.push([a.lat,a.lon]);if(points.length>60)points.shift();
   state.tracks.set(key,points);
  }
 }
 if(state.tracks.size>800)state.tracks.clear();
}
function focusAir(force=false){
 if(state.moved&&!force)return;
 const has=state.data.filter(a=>visible(a)&&isPositioned(a));
 if(!has.length){
  state.lat=state.queryLat;state.lon=state.queryLon;state.zoom=8;
  state.centerLabel="Selected region · no fresh aircraft position";
  if(force)state.moved=false;paint();return;
 }
 const distance=a=>Math.pow(a.lat-state.queryLat,2)+
    Math.pow((a.lon-state.queryLon)*Math.cos(state.queryLat*Math.PI/180),2);
 has.sort((a,b)=>distance(a)-distance(b));
 state.lat=has[0].lat;state.lon=has[0].lon;state.zoom=9;
 state.autoFocused=true;
 if(force)state.moved=false;
 state.centerLabel="Focused on observed "+(has[0].flight||has[0].hex||"aircraft");
 paint();
}
async function refresh(raise=false){
 if(!state.connected || state.fetching)return false;
 state.fetching=true;
 try{
  const mode=$("mode").value;
  if(state.connectionKind==="internet" && mode==="antenna")
   throw Error("Antenna-only mode requires a paired bridge or direct WebUSB.");
  const args=new URLSearchParams({mode,lat:state.queryLat.toFixed(3),lon:state.queryLon.toFixed(3),radius:String(state.queryRadius)});
  if(state.onlineProvider==="multi")args.set("net",enabledInternetNetworks().join(","));
  let result;
  if(state.connectionKind==="bridge"){
   result=await api("/api/aircraft?"+args.toString());
  }else if(state.connectionKind==="usb"){
   let onlineError=null;
   if(state.onlineFeed && mode!=="antenna"){
    try{state.internetSnapshot=await fetchInternetFeed();}
    catch(error){onlineError=String(error.message||error);}
   }
   result=browserSourceResult(mode,onlineError);
  }else{
   result=await fetchInternetFeed();
  }
  state.data=Array.isArray(result.aircraft)?result.aircraft:[];
  state.dataReceivedAt=Date.now();
  state.lastData=state.data.map(a=>({...a}));
  state.lastFreshAt=Date.now();
  updateCounters(result.counts);feedSummary(result.sources);recordTracks();rememberRfPlanes();
  applyStartupPriority();
  const providerTime=result.sources?.internet?.updated_at;
  $("lastUpdate").textContent=formatTime(providerTime ?? result.generated_at);
  $("sourceCredits").textContent=result.sources?.internet?.attribution ||
     "Antenna only (no Internet source)";
  renderTable();paint();
  renderTimingLab();
  sourceLayerStatus(result);
  const internetError=result.sources?.internet?.error;
  notice((internetError
    ? "Internet feed issue: "+internetError+". Any visible aircraft are age-verified real observations."
    : "Updated observed "+(result.active_sources||[]).join(" + ")+" sources.")+
     (state.connectionKind==="internet"&&mode==="hybrid"?" Antenna layer requires a local bridge.":""));
  if(state.connectionKind==="bridge")checkReceiver().catch(()=>{});
  return true;
 }catch(e){
  const elapsed=Math.max(0,(Date.now()-state.lastFreshAt)/1000);
  // Last-known real observations retain their original observation time.
  state.data=state.lastData.map(a=>{
    const row={...a};
    if(Number.isFinite(row.seen))row.seen+=elapsed;
    if(Number.isFinite(row.seen_pos))row.seen_pos+=elapsed;
    return row;
  }).filter(a=>Number.isFinite(a.seen)&&a.seen<=60);
  state.dataReceivedAt=Date.now();
  updateCounters({antenna:state.data.filter(a=>a.sources?.includes("antenna")).length,
                  internet:state.data.filter(a=>a.sources?.includes("internet")).length,
                  combined:state.data.length});
  renderTable();paint();
  if(state.connectionKind==="internet"){
   $("networkStatus").textContent="Internet unavailable: "+e.message+
     ". Retrying while this tab remains open; no simulated aircraft.";
   $("feedStatus").textContent="Antenna: not connected\nInternet: unavailable ("+e.message+")";
  }
  notice("Feed unavailable: "+e.message+". Showing only remaining fresh real observations, not new aircraft.");
  if(raise)throw e;
  return false;
 }finally{
  state.fetching=false;
  if(state.startupQueryDirty && state.connected){
   state.startupQueryDirty=false;
   // A current-location search may have arrived during an older request.
   setTimeout(()=>refresh(),0);
  }
 }
}
async function control(action){
 if(!state.connected)return;
 if(!window.confirm("Send "+action+" to the local receiver? This may affect SDR sharing."))return;
 try{
  const answer=await api("/api/control",{method:"POST",
   headers:{"Content-Type":"application/json"},body:JSON.stringify({action})});
  notice(answer.message);await checkReceiver();await refresh();
 }catch(e){notice(action+" failed: "+e.message)}
}
const mercY=lat=>(1-Math.log(Math.tan(Math.max(-85,Math.min(85,lat))*Math.PI/180)+1/Math.cos(Math.max(-85,Math.min(85,lat))*Math.PI/180))/Math.PI)/2;
const worldX=lon=>(lon+180)/360*2**state.zoom*256;
const worldY=lat=>mercY(lat)*2**state.zoom*256;
function xy(lat,lon){
 const w=canvas.clientWidth,h=canvas.clientHeight;
 return [w/2+worldX(lon)-worldX(state.lon),h/2+worldY(lat)-worldY(state.lat)];
}
function resize(){
 const dpr=window.devicePixelRatio||1;
 const w=canvas.clientWidth,h=canvas.clientHeight;
 canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
 ctx.setTransform(dpr,0,0,dpr,0,0);paint();
}
function grid(){
 const w=canvas.clientWidth,h=canvas.clientHeight;
 ctx.strokeStyle="rgba(155,183,210,.25)";ctx.fillStyle="#b6c8dc";ctx.lineWidth=1;
 ctx.font="11px system-ui";
 const step=state.zoom<5?10:state.zoom<7?3:state.zoom<9?1:state.zoom<11?.2:.05;
 const d=360*w/(2**state.zoom*256);
 for(let lon=Math.floor((state.lon-d)/step)*step;lon<=state.lon+d;lon+=step){
  const x=xy(state.lat,lon)[0];
  if(x<0||x>w)continue;
  ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();
  ctx.fillText(lon.toFixed(2)+"°",x+3,12);
 }
 for(let lat=Math.floor((state.lat-d)/step)*step;lat<=state.lat+d;lat+=step){
  const y=xy(lat,state.lon)[1];
  if(y<0||y>h)continue;
  ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();
  ctx.fillText(lat.toFixed(2)+"°",5,y-4);
 }
}
function getTile(z,x,y){
 const key=z+"/"+x+"/"+y,old=state.tiles.get(key);
 if(old && (!old.failedAt || Date.now()-old.failedAt<300000))return old;
 if(state.tiles.size>120){
  for(const entry of state.tiles.values())if(entry.objectURL)URL.revokeObjectURL(entry.objectURL);
  state.tiles.clear();
 }
 const info={img:null,failedAt:0,objectURL:null};
 state.tiles.set(key,info);
 // Inspect HTTP status before drawing, so OSM's 403 "Access blocked"
 // image never appears as if it were a legitimate map tile.
 fetch("https://tile.openstreetmap.org/"+key+".png",{
  mode:"cors",credentials:"omit",cache:"default",
  referrerPolicy:"strict-origin-when-cross-origin"
 }).then(response=>{
  if(!response.ok)throw Error("Map tile HTTP "+response.status);
  return response.blob();
 }).then(blob=>{
  if(!blob.type.startsWith("image/"))throw Error("Tile is not an image");
  info.objectURL=URL.createObjectURL(blob);
  const img=new Image();
  info.img=img;
  img.onload=()=>paint();
  img.onerror=()=>{info.failedAt=Date.now();paint()};
  img.src=info.objectURL;
 }).catch(error=>{
  info.failedAt=Date.now();state.tileFailures++;
  if(state.tileFailures>=3 && $("showTiles").checked){
   $("showTiles").checked=false;
   notice("Map tiles blocked or unavailable. Showing offline coordinate grid. "+error.message);
  }
  paint();
 });
 return info;
}
function tiles(){
 if(!$("showTiles").checked)return;
 const z=state.zoom,n=2**z,w=canvas.clientWidth,h=canvas.clientHeight;
 const x0=worldX(state.lon)/256-w/512,y0=worldY(state.lat)/256-h/512;
 const nx=Math.ceil(w/256)+2,ny=Math.ceil(h/256)+2;
 for(let dx=0;dx<nx;dx++)for(let dy=0;dy<ny;dy++){
  const tx=Math.floor(x0)+dx,ty=Math.floor(y0)+dy;
  if(ty<0||ty>=n)continue;
  const t=getTile(z,((tx%n)+n)%n,ty);
  if(t.img&&t.img.complete&&t.img.naturalWidth)
   ctx.drawImage(t.img,(tx-x0)*256,(ty-y0)*256,256,256);
 }
}
function rfConvexHull(points){
 // Convex hull of sampled feasible cells; NOT a GPS confidence ellipse.
 const sorted=points.slice().sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
 const cross=(o,a,b)=>(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]);
 const lower=[],upper=[];
 for(const p of sorted){
  while(lower.length>=2&&cross(lower[lower.length-2],lower[lower.length-1],p)<=0)lower.pop();
  lower.push(p);
 }
 for(let i=sorted.length-1;i>=0;i--){
  const p=sorted[i];
  while(upper.length>=2&&cross(upper[upper.length-2],upper[upper.length-1],p)<=0)upper.pop();
  upper.push(p);
 }
 lower.pop();upper.pop();
 return lower.concat(upper);
}
// Hull is calculated once per RF model revision, not on each smooth map frame.
let rfHullModel=null,rfHullCoordinates=[];
function rfFeasibleHull(result){
 if(rfHullModel!==result){
  rfHullModel=result;rfHullCoordinates=[];
  if(result.status==="region"){
   const candidates=result.region.possibleSamples||[];
   const anchor=result.region.lon;
   const coords=candidates.map(p=>[
    anchor+((p.lon-anchor+540)%360)-180,p.lat
   ]);
   rfHullCoordinates=rfConvexHull(coords).map(p=>({lon:p[0],lat:p[1]}));
  }
 }
 return rfHullCoordinates;
}
function rfMapXy(p){
 // Draw the shortest longitude crossing near the current camera center.
 const lon=state.lon+((p.lon-state.lon+540)%360)-180;
 return xy(p.lat,lon);
}
function rfDrawRing(ring,color,dash=[5,8],width=1.4){
 const path=TihuluRFCoverage.horizonPoints(ring,80);
 ctx.save();ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dash);
 ctx.beginPath();
 path.forEach((p,i)=>{
  const [x,y]=rfMapXy(p);
  if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);
 });
 ctx.stroke();ctx.restore();
}
function paintRfCoverage(result){
 ctx.save();
 if($("showRfCoverage").checked){
  // Retain the quick three-horizon diagnostic toggle for compatibility.
  for(const ring of result.circles.slice(0,3))
   rfDrawRing(ring,"rgba(88,194,219,.30)",[4,9],1);
 }
 // Every real RF aircraft has its own independently switchable outline,
 // even if there are fewer than four aircraft for a region model.
 for(const item of result.aircraftCircles||[]){
  if(!rfSelectedPlanes.has(item.hex))continue;
  rfDrawRing(item.circle,rfPlaneColor(item.hex),[5,6],1.7);
 }
 if(result.status==="region"&&rfLocatorActive){
  const r=result.region;
  const hull=rfFeasibleHull(result).map(rfMapXy);
  if(hull.length>=3){
   ctx.beginPath();
   hull.forEach((p,i)=>{if(i===0)ctx.moveTo(p[0],p[1]);else ctx.lineTo(p[0],p[1])});
   ctx.closePath();
   if($("rfFill").checked){
    ctx.fillStyle="rgba(30,178,205,.17)";ctx.fill();
   }
   if($("rfHatch").checked){
    ctx.save();ctx.clip();
    const xs=hull.map(p=>p[0]),ys=hull.map(p=>p[1]);
    const left=Math.max(-100,Math.min(...xs)),right=Math.min(canvas.clientWidth+100,Math.max(...xs));
    const top=Math.max(-100,Math.min(...ys)),bottom=Math.min(canvas.clientHeight+100,Math.max(...ys));
    const dy=bottom-top;
    ctx.strokeStyle="rgba(100,225,238,.56)";ctx.lineWidth=1.2;
    for(let offset=left-dy,i=0;offset<=right+dy&&i<350;offset+=12,i++){
     ctx.beginPath();ctx.moveTo(offset,top);ctx.lineTo(offset+dy,bottom);ctx.stroke();
    }
    ctx.restore();
   }
   if($("rfFill").checked||$("rfHatch").checked){
    // Hatch strokes alter the active Canvas path; retrace polygon after
    // clipping so the cyan border always follows the actual feasible hull.
    ctx.beginPath();
    hull.forEach((p,i)=>{if(i===0)ctx.moveTo(p[0],p[1]);else ctx.lineTo(p[0],p[1])});
    ctx.closePath();
    ctx.strokeStyle="rgba(104,230,238,.88)";ctx.lineWidth=2.2;ctx.stroke();
   }
  }
  if($("rfModelCircle").checked){
   // Approximate maximum sampled distance from the *modeled* centroid.
   // This is deliberately NOT called a confidence/error radius.
   rfDrawRing({lat:r.lat,lon:r.lon,radiusKm:r.extentKm},
    "rgba(226,244,255,.95)",[10,6],2);
   const [cx,cy]=rfMapXy(r);
   if(cx>=0&&cx<=canvas.clientWidth&&cy>=0&&cy<=canvas.clientHeight){
    ctx.font="bold 11px system-ui";ctx.fillStyle="#e5f7ff";
    ctx.fillText("MODEL SPREAD ~"+Math.round(r.extentKm)+" km · NOT ACCURACY",cx+19,cy+28);
   }
  }
 }
 ctx.restore();
}
function paint(){
 const w=canvas.clientWidth,h=canvas.clientHeight;
 if(!w||!h)return;
 const model=coverageResult();
 focusRfModelWhenReady(model);
 ctx.clearRect(0,0,w,h);ctx.fillStyle="#102231";ctx.fillRect(0,0,w,h);
 tiles();grid();
 if($("showRfCoverage").checked||rfLocatorActive||rfSelectedPlanes.size)paintRfCoverage(model);
 if($("showTracks").checked){
  for(const [key,points] of state.tracks.entries()){
   if(points.length<2)continue;
   const icao=key.split("_")[0],a=state.data.find(a=>a.hex===icao);
   if(!a||!visible(a))continue;
   ctx.strokeStyle=altitudeColor(a);ctx.globalAlpha=.5;ctx.lineWidth=2;
   ctx.beginPath();
   points.forEach((p,i)=>{const [x,y]=xy(p[0],p[1]);if(!i)ctx.moveTo(x,y);else ctx.lineTo(x,y)});
   ctx.stroke();ctx.globalAlpha=1;
  }
 }
 let markers=0;
 for(const a of state.data){
  if(!visible(a)||!isPositioned(a))continue;
  const shown=$("smoothMotion").checked
   ?TihuluMapMotion.displayedPosition(a,state.dataReceivedAt,Date.now())
   :null;
  const [x,y]=xy(shown?.lat??a.lat,shown?.lon??a.lon);
  if(x< -15||x>w+15||y< -15||y>h+15)continue;
  markers++;
  paintAircraft(ctx,a,x,y);
  if(shown?.projected){
   // Dashed halo explicitly distinguishes predicted motion from an RF fix.
   ctx.save();ctx.strokeStyle="rgba(190,228,245,.5)";
   ctx.setLineDash([2,4]);ctx.lineWidth=1.2;
   ctx.beginPath();ctx.arc(x,y,22,0,Math.PI*2);ctx.stroke();ctx.restore();
  }
  ctx.font="12px system-ui";ctx.fillStyle="#fff";
  ctx.shadowColor="#102030";ctx.shadowBlur=3;
  ctx.fillText((a.flight||a.hex||"Aircraft").trim(),x+19,y-10);
  ctx.shadowBlur=0;
 }
 paintRfLocator(model); // independent of the optional ring display.
 if(!markers){
  ctx.fillStyle="rgba(13,23,33,.9)";ctx.fillRect(12,12,Math.min(420,w-24),38);
  ctx.fillStyle="#d6e7f7";ctx.font="13px system-ui";
  ctx.fillText("No fresh aircraft positions in selected layers",22,36);
 }
 $("mapLabel").textContent=state.centerLabel;
 renderCoverageStatus();
}
canvas.addEventListener("pointerdown",e=>{
 state.pointer=[e.clientX,e.clientY,state.lon,state.lat];
 canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener("pointermove",e=>{
 if(!state.pointer)return;
 const p=state.pointer,state_zoom=2**state.zoom*256;
 disableRfFollow();state.moved=true;state.lon=p[2]-(e.clientX-p[0])/state_zoom*360;
 const target=mercY(p[3])*state_zoom-(e.clientY-p[1]);
 state.lat=Math.max(-85,Math.min(85,Math.atan(Math.sinh(Math.PI*(1-2*target/state_zoom)))*180/Math.PI));
 state.centerLabel="Manual map position";paint();
});
canvas.addEventListener("pointerup",e=>{
 if(!state.pointer)return;
 const p=state.pointer;state.pointer=null;
 if(Math.hypot(e.clientX-p[0],e.clientY-p[1])>8)return;
 let best=null,bestD=18;
 for(const a of state.data){
  if(!visible(a)||!isPositioned(a))continue;
  const shown=$("smoothMotion").checked
   ?TihuluMapMotion.displayedPosition(a,state.dataReceivedAt,Date.now())
   :null;
  const [x,y]=xy(shown?.lat??a.lat,shown?.lon??a.lon);
  const d=Math.hypot(x-(e.clientX-canvas.getBoundingClientRect().left),y-(e.clientY-canvas.getBoundingClientRect().top));
  if(d<bestD){bestD=d;best=a}
 }
 if(best)choose(best);else closePopup();
});
canvas.addEventListener("wheel",e=>{
 e.preventDefault();disableRfFollow();state.moved=true;state.zoom=Math.max(2,Math.min(12,state.zoom+(e.deltaY<0?1:-1)));paint();
},{passive:false});
// Provider selection is explicit and never creates a hidden proxy/key.
const preset=$("onlinePreset");
const customFeed=$("onlineFeedUrl");
function showProviderChoice(){
 $("multiProviderLayers").hidden=preset.value!=="multi";
 customFeed.disabled=preset.value!=="custom";
 $("airlabsKeyField").hidden=preset.value!=="airlabs";
 customFeed.title=customFeed.disabled
  ?"Select Custom HTTPS/CORS ADS-B feed to enter a URL."
  :"Only trusted /api/aircraft endpoints with documented CORS and source attribution.";
}
preset.onchange=()=>{
 showProviderChoice();
 if(state.connectionKind==="bridge"){
  try{state.onlineFeed=configuredOnlineFeed();state.internetSnapshot=null;void refresh();}
  catch(error){notice("Internet layers: "+error.message);}
 }else if(state.connectionKind==="usb"||state.connectionKind==="internet"){
  state.internetSnapshot=null;state.internetBackoffUntil=0;state.airlabsLastFetch=0;
  if(preset.value==="off"&&state.connectionKind==="internet")disconnect();
  else void connect();
 }
};
showProviderChoice();
$("allOnlineLayers").onclick=()=>{
 for(const id of multiIds)$(layerFields[id]).checked=true;
 if(preset.value==="multi"&&state.connected)void refresh();
};
for(const id of multiIds)$(layerFields[id]).onchange=()=>{
 if(preset.value==="multi"&&state.connected)void refresh();
};
$("networkApply").onclick=()=>{
 if(state.connectionKind==="bridge"){
  if($("onlinePreset").value==="off"){
   state.onlineFeed="";$("mode").value="antenna";void refresh();return;
  }
  try{
   state.onlineFeed=configuredOnlineFeed();
   if($("mode").value==="antenna")$("mode").value="hybrid";
   void refresh();
  }catch(error){notice("Internet layers: "+error.message);}
  return;
 }
 if($("onlinePreset").value==="off"){
  if(state.connectionKind==="usb"){
   state.onlineFeed="";state.internetSnapshot=null;$("mode").value="antenna";
   displayUsbSnapshot();feedSummary(browserSourceResult().sources);
  }else if(state.connectionKind==="internet")disconnect();
  $("networkStatus").textContent="Internet overlay disabled; radio continues independently.";
  return;
 }
 void connect();
};
$("connect").onclick=connect;
$("disconnect").onclick=disconnect;
$("refresh").onclick=()=>{
 // Explicit refresh may spend one more call from a personal AirLabs quota.
 state.airlabsLastFetch=0;
 void refresh(true);
};
function tarFocusURL(raw){
 const url=new URL(raw);
 if(!["http:","https:"].includes(url.protocol) || url.username || url.password)
  throw Error("Use a valid HTTP(S) tar1090 URL without embedded credentials.");
 // Inherit the already resolved startup camera: permitted location,
 // genuine nearest RF plane, or Cologne. Do not recenter on arbitrary
 // Internet aircraft merely because they happen to be visible.
 const center={lat:state.lat,lon:state.lon};
 const selected=state.data.find(a=>state.selected===a.hex && isPositioned(a));
 const bestRadio=selected?.position_source==="antenna" ? selected :
   (state.startupSource==="antenna"&&!state.moved
     ? state.data.find(a=>a.position_source==="antenna" &&
         a.sources?.includes("antenna") && isPositioned(a) &&
         Math.abs(a.lat-center.lat)<0.01 && Math.abs(a.lon-center.lon)<0.01)
     : null);
 for(const param of ["icao","noIsolation","SiteLat","SiteLon","centerReceiver",
                      "lockDotCentered","zoom","rangeRings",
                      "tihuluFocusLat","tihuluFocusLon"])
  url.searchParams.delete(param);
 // The camera focus must not masquerade as the physical receiver location.
 url.searchParams.set("tihuluFocusLat",center.lat.toFixed(6));
 url.searchParams.set("tihuluFocusLon",center.lon.toFixed(6));
 url.searchParams.set("rangeRings","0");
 url.searchParams.set("zoom",String(state.zoom||9));
 // ICAO selection only if the aircraft really came from our antenna.
 if(bestRadio && /^[0-9a-f]{6}$/i.test(bestRadio.hex||"")){
  url.searchParams.set("icao",bestRadio.hex);
  url.searchParams.set("noIsolation","");
 }
 return url.href;
}
function setRadarExpanded(force){
 const enabled=typeof force==="boolean"?force:!document.body.classList.contains("radar-expanded");
 document.body.classList.toggle("radar-expanded",enabled);
 $("expandMap").textContent=enabled?"Exit full radar":"Full radar map";
 $("expandMap").setAttribute("aria-pressed",String(enabled));
 resize();paint();
 if(enabled)notice("Full browser radar is using this tab's real RF and configured network sources; no readsb backend required.");
}
$("expandMap").onclick=()=>setRadarExpanded();
window.addEventListener("keydown",event=>{
 if(event.key==="Escape"&&document.body.classList.contains("radar-expanded"))
  setRadarExpanded(false);
});
// Full original tar1090 browser frontend: it only displays aircraft coming
// from this page. It never starts readsb or claims the USB a second time.
let tarFrameOpen=false;
const TRUSTED_HOSTED_TAR="https://tihulu.github.io/tihulu-flight-radar/tar1090/index.html";
let tarTargetOrigin=location.origin;
function tarIframeOrigin(){
 const frame=$("fullTarFrame");
 if(!frame?.getAttribute("src"))return null;
 try{return new URL(frame.getAttribute("src"),location.href).origin;}
 catch{return null;}
}
function publishTarBrowserSnapshot(){
 const frame=$("fullTarFrame");
 if(!tarFrameOpen||!frame?.contentWindow)return;
 // Always age measurements, and never turn an unavailable local decoder
 // into a claimed RF observation. Same ICAO24 from multiple Internet feeds
 // is already one aircraft in state.data, with full provider provenance.
 const elapsed=Math.max(0,(Date.now()-state.lastFreshAt)/1000);
 const byId=new Map();
 for(const a of state.data||[]){
  if(!a||!Number.isFinite(a.seen)||a.seen+elapsed>60)continue;
  const hex=String(a.hex||"").toLowerCase();
  if(!/^[a-f0-9]{6}$/.test(hex))continue;
  const isRf=Array.isArray(a.sources)&&a.sources.includes("antenna");
  const prior=byId.get(hex);
  if(prior && (!isRf||prior.sources?.includes("antenna")))continue;
  byId.set(hex,{
   hex,flight:a.flight,lat:a.lat,lon:a.lon,track:a.track,
   gs:a.gs,tas:a.tas,ias:a.ias,mach:a.mach,
   alt_baro:a.alt_baro,alt_geom:a.alt_geom,baro_rate:a.baro_rate,
   geom_rate:a.geom_rate,squawk:a.squawk,rssi:isRf?a.rssi:undefined,
   seen:a.seen+elapsed,
   seen_pos:Number.isFinite(a.seen_pos)?a.seen_pos+elapsed:null,
   messages:isRf?a.messages:undefined,
   r:a.r,t:a.t,type:a.type,category:a.category,dbFlags:a.dbFlags,
   sources:a.sources,internet_providers:a.internet_providers||[]
  });
 }
 const target=tarIframeOrigin();
 if(!target || ![location.origin,"https://tihulu.github.io"].includes(target))return;
 frame.contentWindow.postMessage({type:"tihulu:tar-aircraft",
  now:Date.now()/1000,
  messages:state.connectionKind==="usb"?state.usbMessageCount:
    (Number.isFinite(state.receiverMessages)?state.receiverMessages:0),
  aircraft:[...byId.values()].slice(0,1500)},target);
}
async function resolveTarBrowserURL(){
 // Prefer the same-origin full upstream tar1090, including on GitHub Pages.
 // On native loopback it is served from the user-owned local tar1090 cache.
 try{
  const test=await fetch("./tar1090/tihulu-browser-bridge.js",
   {credentials:"omit",cache:"no-store"});
  if(test.ok)return new URL("./tar1090/index.html",location.href);
 }catch{}
 // Older native installs without the optional cache may use the exact
 // audited GitHub Pages frontend. Parent-child data only travels via
 // same-origin or the fixed HTTPS Pages origin; no receiver tokens are sent.
 if(["127.0.0.1","localhost"].includes(location.hostname)){
  notice("Local tar1090 assets unavailable; using HTTPS hosted full tar1090. Internet is required for this fallback.");
  return new URL(TRUSTED_HOSTED_TAR);
 }
 throw Error("Full tar1090 bundle is unavailable here; the main observed aircraft map remains usable.");
}
async function setBrowserTar(open){
 const shell=$("tarBrowserShell");
 tarFrameOpen=!!open;
 shell.hidden=!tarFrameOpen;
 document.body.classList.toggle("tar-open",tarFrameOpen);
 if(tarFrameOpen){
  const frame=$("fullTarFrame");
  if(!frame.getAttribute("src")){
   const query=new URLSearchParams({
    lat:state.lat.toFixed(5),lon:state.lon.toFixed(5),
    zoom:String(Math.max(3,Math.min(13,state.zoom)))
   });
   try{
    const url=await resolveTarBrowserURL();
    if(!tarFrameOpen)return;
    url.search=query.toString();
    tarTargetOrigin=url.origin;
    frame.setAttribute("src",url.toString());
   }catch(error){
    tarFrameOpen=false;shell.hidden=true;document.body.classList.remove("tar-open");
    notice("Full tar1090 is unavailable: "+String(error.message||error));
    return;
   }
  }
  publishTarBrowserSnapshot();
  notice("Full upstream tar1090 opened. Internet-only aircraft work without an SDR or readsb; RF stays optional.");
 }else{
  // Stop the nested map's timers and metadata requests on close; leave
  // all parent source settings, antenna ownership and observations intact.
  const frame=$("fullTarFrame");
  if(frame?.hasAttribute("src"))frame.removeAttribute("src");
  tarTargetOrigin=location.origin;
  $("fullTar1090").focus();
 }
}
$("fullTar1090").onclick=()=>void setBrowserTar(true);
$("openTarPrimary").onclick=()=>void setBrowserTar(true);
$("closeFullTar").onclick=()=>void setBrowserTar(false);
$("fullTarFrame").addEventListener("load",()=>publishTarBrowserSnapshot());
window.addEventListener("message",event=>{
 if(!tarFrameOpen || event.origin!==tarTargetOrigin ||
    event.source!==$("fullTarFrame").contentWindow)return;
 if(event.data?.type==="tihulu:tar-ready")publishTarBrowserSnapshot();
});
window.setInterval(()=>{if(tarFrameOpen && !document.hidden)publishTarBrowserSnapshot()},1200);
// Display-only aircraft animation; independent of real observation / RF counts.
window.setInterval(()=>{
 if(!document.hidden && state.connected && $("smoothMotion").checked)paint();
},750);
window.addEventListener("keydown",event=>{
 if(event.key==="Escape" && tarFrameOpen)void setBrowserTar(false);
});
$("legacyTar").onclick=async()=>{
 // Always offer the COMPLETE original tar1090 frontend even with no radio.
 // The external readsb-backed variant is an OPTIONAL advanced path.
 if(state.connectionKind!=="bridge"){
  await setBrowserTar(true);
  return;
 }
 let live;
 try{live=await api("/api/tar-status");}
 catch(error){
  await setBrowserTar(true);
  notice("Local decoder not available; using original tar1090 with Internet-only data.");
  return;
 }
 if(!live.available || !live.url){
  await setBrowserTar(true);
  notice("No live readsb backend; original tar1090 is using Internet-only aircraft. No antenna required.");
  return;
 }
 const raw=prompt("Verified separate tar1090 receiver URL (Cancel opens integrated full tar1090):",live.url);
 if(raw===null){await setBrowserTar(true);return;}
 try{window.open(tarFocusURL(raw),"_blank","noopener,noreferrer");}
 catch(error){notice("Invalid tar1090 URL: "+error.message);}
};
$("start").onclick=()=>control("start");
$("stop").onclick=()=>control("stop");
$("restart").onclick=()=>control("restart");
$("mode").onchange=()=>{state.autoFocused=false;refresh()};
$("focus").onclick=()=>{disableRfFollow();focusAir(true);state.moved=true;};
function chooseRegion(point,label,zoom=8){
 disableRfFollow();
 state.lat=point.lat;state.lon=point.lon;
 state.queryLat=point.lat;state.queryLon=point.lon;
 state.zoom=zoom;state.moved=true;state.autoFocused=false;
 state.centerLabel=label+" · Internet search region, not physical receiver";
 paint();
 // Do not lose a manual location choice when the previous region is loading.
 if(state.connected){
  if(state.fetching)state.startupQueryDirty=true;
  else void refresh();
 }
}
$("cologne").onclick=()=>chooseRegion(COLOGNE,"Cologne",9);
$("germany").onclick=()=>chooseRegion(GERMANY,"Germany",7);

// The Satellite Center's offline place directory and the radar share one
// location model. A saved place is a SEARCH center, never receiver GPS.
function applyPlaceToFlightRadar(place,persistBridge=true){
 if(!place||!Number.isFinite(place.lat)||!Number.isFinite(place.lon))return;
 if(Math.abs(place.lat)>90||Math.abs(place.lon)>180)return;
 const radius=Number(place.radius);
 if(![25,50,100,150,250].includes(radius))return;
 state.queryRadius=radius;
 if(persistBridge && state.connectionKind==="bridge" && state.token){
  void api("/api/search-location",{method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify(place)
  }).catch(err=>notice("Map selected, but local preference could not be saved: "+err.message));
 }
 state.tracks.clear(); // avoid carrying visible trails from an old area
 state.selected=null;$("aircraftPopup").hidden=true;
 chooseRegion({lat:place.lat,lon:place.lon},
   place.label+" · "+radius+" NM search",Number(place.zoom)||9);
 // The full original tar1090 iframe uses camera URL parameters at startup.
 // Recreate only its view; no RF process or browser receiver is restarted.
 if(tarFrameOpen){
  const frame=$("fullTarFrame");
  if(frame?.hasAttribute("src"))frame.removeAttribute("src");
  void setBrowserTar(true);
 }
 notice("Map and Internet aircraft search: "+place.label+" · "+radius+
   " NM. Physical receiver site unchanged.");
}
import("./flight_location_ui.mjs").then(mod=>{
 mod.initFlightLocationUI({
  onChoose:applyPlaceToFlightRadar,
  getCurrent:()=>({lat:state.queryLat,lon:state.queryLon,radius:state.queryRadius})
 });
 const saved=mod.readSavedPlace();
 if(saved){
  applyPlaceToFlightRadar(saved);
  $("mapLabel").textContent="Restored saved Internet search region: "+saved.label+
   " · "+saved.radius+" NM";
 }
}).catch(err=>{
 notice("Place chooser could not load: "+String(err.message||err)+
  ". Cologne, Germany, Search here and GPS controls remain available.");
 for(const id of ["placeOpen","placeTarOpen"]){
  const btn=$(id);if(btn){btn.disabled=true;btn.title="Offline place selector unavailable";}
 }
});
$("searchHere").onclick=()=>{
 disableRfFollow();
 state.queryLat=state.lat;state.queryLon=state.lon;
 state.moved=true;
 state.centerLabel="Internet search moved to map view · receiver location unchanged";
 paint();
 if(state.connected)refresh();
};
$("locate").onclick=()=>{
 if(!navigator.geolocation){notice("Browser geolocation not available.");return}
 navigator.geolocation.getCurrentPosition(p=>{
  disableRfFollow();
  state.lat=p.coords.latitude;state.lon=p.coords.longitude;
  state.queryLat=state.lat;state.queryLon=state.lon;
  state.zoom=10;state.moved=true;state.centerLabel="Explicit permitted GPS search region";
  paint();
  notice("Map and Internet search moved with your permission; SDR receiver site unchanged.");
  if(state.connected)refresh();
 },e=>notice("Browser location unavailable: "+e.message),{timeout:7000});
};
$("zoomIn").onclick=()=>{disableRfFollow();state.zoom=Math.min(12,state.zoom+1);state.moved=true;paint()};
$("zoomOut").onclick=()=>{disableRfFollow();state.zoom=Math.max(2,state.zoom-1);state.moved=true;paint()};
for(const id of selectors)$(id).onchange=()=>{
 if(id==="showTiles" && $("showTiles").checked)state.tileFailures=0;
 renderTable();paint();
};
$("bridgeUrl").value=location.hostname==="127.0.0.1"||location.hostname==="localhost"
 ? location.origin:"http://127.0.0.1:8510";
connection(false,"Not paired");
window.addEventListener("resize",resize);
resize();

// PWA caches the app shell only; never cache receiver data or map tile responses.
let pwaInstallPrompt=null;
window.addEventListener("beforeinstallprompt",event=>{
 event.preventDefault();pwaInstallPrompt=event;$("installApp").hidden=false;
});
$("installApp").onclick=async()=>{
 if(!pwaInstallPrompt)return;
 pwaInstallPrompt.prompt();
 await pwaInstallPrompt.userChoice;
 pwaInstallPrompt=null;$("installApp").hidden=true;
};
if("serviceWorker" in navigator && location.protocol==="https:"){
 window.addEventListener("load",()=>navigator.serviceWorker.register("./sw.js",{scope:"./"}).catch(()=>{}));
}
if(location.hostname==="tihulu.github.io"){
 // Both GitHub Pages sites share this source. Load public Internet flights
 // automatically in the foreground without claiming USB or opening a bridge.
 $("mode").value="internet";
 notice("Loading real adsb.lol Internet aircraft near the selected map region. Antenna remains optional.");
 const startPagesInternet=()=>{
  if(navigator.onLine===false){
   notice("Offline mode: radio/SDR and RF Timing Laboratory work without any Internet provider.");
   return;
  }
  if(state.connectionKind!=="none" || $("onlinePreset").value==="off")return;
  void connect();
 };
 if(document.hidden){
  const onFirstVisible=()=>{
   if(document.hidden)return;
   document.removeEventListener("visibilitychange",onFirstVisible);
   startPagesInternet();
  };
  document.addEventListener("visibilitychange",onFirstVisible);
 }else startPagesInternet();
 document.addEventListener("visibilitychange",()=>{
  if(!document.hidden && state.connected && state.connectionKind!=="bridge")
   void refresh();
 });
}

// An explicit ?view=tar1090 opens the real upstream interface immediately.
 // It works even before any SDR, local decoder or Internet feed is available;
 // genuine Internet contacts are injected as they arrive, never simulated.
 if(new URLSearchParams(location.search).get("view")==="tar1090"){
   window.addEventListener("load",()=>void setBrowserTar(true),{once:true});
 }
 initializeStartupLocation();
