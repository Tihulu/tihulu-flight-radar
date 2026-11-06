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
  lastFreshAt:0, lastData:[],
  usbSnapshot:{aircraft:[],messages:0,updatedAt:0},internetSnapshot:null,
  usbMessageCount:0,
  pointer:null, tracks:new Map(), tiles:new Map(), tileFailures:0, fetching:false, timer:null,
  centerLabel:"Cologne startup fallback · awaiting location permission / radio aircraft"
};
const selectors = ["showAntenna","showInternet","showBoth","showTracks","showTiles"];
function notice(s){$("message").textContent=s}
function isPositioned(a){
 return a && Number.isFinite(a.lat) && Number.isFinite(a.lon) &&
  a.lat >= -90 && a.lat <= 90 && a.lon >= -180 && a.lon <= 180 &&
  Number.isFinite(a.seen_pos) && a.seen_pos >= 0 && a.seen_pos <= 60;
}
// Pure startup choice; only the radio-sourced position qualifies as RF.
// A merged aircraft whose position came from the Internet is not radio GPS.
function chooseStartupTarget(geo, aircraft){
 const valid=p=>p && Number.isFinite(p.lat) && Number.isFinite(p.lon) &&
   Math.abs(p.lat)<=90 && Math.abs(p.lon)<=180;
 if(valid(geo))return {lat:geo.lat,lon:geo.lon,zoom:10,rank:3,source:"location"};
 const available=(Array.isArray(aircraft)?aircraft:[]).filter(a=>
  valid(a) && a.position_source==="antenna" &&
  a.sources?.includes("antenna") && Number.isFinite(a.seen) && a.seen<=60 &&
  Number.isFinite(a.seen_pos) && a.seen_pos<=60);
 const square=a=>{
  const dx=(a.lon-COLOGNE.lon)*Math.cos(COLOGNE.lat*Math.PI/180);
  const dy=a.lat-COLOGNE.lat;return dx*dx+dy*dy;
 };
 available.sort((a,b)=>square(a)-square(b));
 if(available.length)return {lat:available[0].lat,lon:available[0].lon,
   zoom:10,rank:2,source:"antenna",flight:available[0].flight||available[0].hex};
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
   : "Nearest actual radio aircraft "+(selected.flight||"")+" · startup";
 state.startupQueryDirty=state.connected;
 paint();
}
function initializeStartupLocation(){
 if(!navigator.geolocation){
  state.startupLocationPending=false;applyStartupPriority();return;
 }
 navigator.geolocation.getCurrentPosition(
  fix=>{
   const p=fix?.coords;
   if(p && Number.isFinite(p.latitude) && Number.isFinite(p.longitude)){
    state.startupGeo={lat:p.latitude,lon:p.longitude};
   }
   state.startupLocationPending=false;applyStartupPriority();
   if(state.startupQueryDirty && !state.fetching && state.connected){
    state.startupQueryDirty=false;refresh();
   }
  },
  ()=>{state.startupLocationPending=false;applyStartupPriority();},
  {enableHighAccuracy:false,timeout:6500,maximumAge:300000}
 );
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
 else if(provider==="adsblol-relay")url=ADSBLOL_PUBLIC_RELAY;
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
   if(!isPositioned(exists)&&isPositioned(a)){
    exists.lat=a.lat;exists.lon=a.lon;exists.seen_pos=a.seen_pos;
    exists.position_source="internet";
   }
   if(!exists.flight&&a.flight)exists.flight=a.flight;
   if(!Number.isFinite(exists.alt_baro)&&Number.isFinite(a.alt_baro))exists.alt_baro=a.alt_baro;
  }else{
   const row={...a,hex:id,sources:["internet"],
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
      updated_at:state.internetSnapshot?.sources?.internet?.updated_at}
  }
 };
}
function displayUsbSnapshot(){
 if(state.connectionKind!=="usb")return;
 const result=browserSourceResult();
 state.data=result.aircraft;
 updateCounters(result.counts);feedSummary(result.sources);recordTracks();
 applyStartupPriority();
 renderTable();paint();
 $("receiverStatus").textContent="Direct WebUSB 1090 MHz receiver · "+
   state.usbMessageCount+" CRC-verified Mode S messages. RF access is held only by this browser tab.";
 $("lastUpdate").textContent=formatTime(result.generated_at);
 $("sourceCredits").textContent=result.sources.internet.attribution;
}
window.tihuluUsbCanStart=()=>state.connectionKind!=="bridge";
window.tihuluUsbStarted=()=>{
 state.usbSnapshot={aircraft:[],messages:0,updatedAt:Date.now()};
 state.usbMessageCount=0;state.connectionKind="usb";state.connected=true;
 let networkSetupError=null;
 try{state.onlineFeed=configuredOnlineFeed();}
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
};
// Called only by our packaged Qt WebEngine wrapper after the trusted local
// page is loaded. The token is never placed in a URL, cookies or storage.
window.tihuluNativeConnect=async function(base, token){
 document.documentElement.classList.add("native");
 document.querySelector(".bridge-advanced").open=true;
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
 $("receiverStatus").textContent=(r.active?"Decoder active — ":"Decoder inactive — ")+r.detail+
   (r.control_enabled?" · controls enabled":" · controls read-only")+
   (r.startup_error ? " · START FAILED: "+r.startup_error : "")+
   ". An active decoder does not prove RF reception.";
 for(const id of ["start","stop","restart"])$(id).disabled=!r.control_enabled;
}
async function connect(){
 if(state.timer){clearInterval(state.timer);state.timer=null;}
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
  state.onlineFeed=configuredOnlineFeed();
   state.internetBackoffUntil=0;state.airlabsLastFetch=0;
  const token=$("token").value.trim();
  if(token){
   state.base=getBase($("bridgeUrl").value.trim());
   state.token=token;state.connectionKind="bridge";
   await checkReceiver();
  }else if(state.onlineFeed){
   state.base="";state.token="";state.connectionKind="internet";
   $("receiverStatus").textContent="Internet-only: no local hardware connected. Pair a bridge for antenna data.";
   for(const id of ["start","stop","restart"])$(id).disabled=true;
  }else{
   throw Error("For antenna data enter a local pairing token; for Internet only enter an HTTPS Internet feed URL.");
  }
  state.connected=true;
  await refresh(true);
  connection(true,state.connectionKind==="bridge"?"Paired with local bridge":"Internet feed connected");
  $("token").value="";
  state.timer=setInterval(()=>{if(!document.hidden)refresh()},15000);
 }catch(e){
  if(state.connectionKind==="usb"){
   // A bad optional network key/URL must not disconnect healthy WebUSB
   // or permanently cancel the already-running RF refresh timer.
   state.connected=true;displayUsbSnapshot();
   if(!state.timer)state.timer=setInterval(()=>{if(!document.hidden)refresh()},15000);
   notice("Optional Internet feed failed; direct WebUSB remains connected: "+e.message);
  }else{
   state.connected=false;state.token="";state.connectionKind="none";
   connection(false,"Not connected");
   notice("Connection failed: "+e.message+". Check bridge pairing or feed CORS/availability.");
  }
 }
}
function disconnect(){
 if(state.connectionKind==="usb")void window.tihuluStopUsb?.();
 if(state.timer)clearInterval(state.timer);
 state.timer=null;state.token="";state.base="";state.onlineFeed="";state.connectionKind="none";state.data=[];state.lastData=[];state.lastFreshAt=0;
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
function renderTable(){
 const rows=$("aircraftRows"); rows.replaceChildren();
 const displayed=state.data.filter(visible);
 $("visibleCount").textContent=displayed.length;
 for(const a of displayed.slice(0,400)){
  const tr=document.createElement("tr");
  if(state.selected && a.hex===state.selected)tr.className="selected";
  for(const [index,value] of [
   (a.flight||"—").trim()+" / "+(a.hex||"—"),
   a.alt_baro??a.alt_geom??"—",a.gs??"—",
   aircraftSourceBadge(a)+" · "+category(a)
  ].entries()){
   const td=document.createElement("td");
   td.textContent=String(value);
   if(index===3)td.className="tag "+category(a);
   if(index===1)td.style.color=altitudeColor(a);
   tr.append(td);
  }
  tr.onclick=()=>choose(a);
  rows.append(tr);
 }
 if(state.selected){
  const found=state.data.find(a=>a.hex===state.selected);
  if(!found)$("details").textContent="Selected aircraft no longer in the latest snapshot.";
 }
}
function choose(a){
 state.selected=a.hex||null;
 $("details").textContent=JSON.stringify({
  callsign:a.flight||null,icao24:a.hex||null,sources:a.sources,
  displayed_position_source:a.position_source,observations:a.observations
 },null,2);
 if(isPositioned(a)){
  state.lat=a.lat;state.lon=a.lon;state.zoom=Math.max(state.zoom,9);
  state.moved=true;state.centerLabel="Selected "+(a.flight||a.hex||"aircraft");
 }
 renderTable();paint();
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
  state.lastData=state.data.map(a=>({...a}));
  state.lastFreshAt=Date.now();
  updateCounters(result.counts);feedSummary(result.sources);recordTracks();
  applyStartupPriority();
  const providerTime=result.sources?.internet?.updated_at;
  $("lastUpdate").textContent=formatTime(providerTime ?? result.generated_at);
  $("sourceCredits").textContent=result.sources?.internet?.attribution ||
     "Antenna only (no Internet source)";
  renderTable();paint();
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
  updateCounters({antenna:state.data.filter(a=>a.sources?.includes("antenna")).length,
                  internet:state.data.filter(a=>a.sources?.includes("internet")).length,
                  combined:state.data.length});
  renderTable();paint();
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
function paint(){
 const w=canvas.clientWidth,h=canvas.clientHeight;
 if(!w||!h)return;
 ctx.clearRect(0,0,w,h);ctx.fillStyle="#102231";ctx.fillRect(0,0,w,h);
 tiles();grid();
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
  const [x,y]=xy(a.lat,a.lon);
  if(x< -15||x>w+15||y< -15||y>h+15)continue;
  markers++;
  paintAircraft(ctx,a,x,y);
  ctx.font="12px system-ui";ctx.fillStyle="#fff";
  ctx.shadowColor="#102030";ctx.shadowBlur=3;
  ctx.fillText((a.flight||a.hex||"Aircraft").trim(),x+19,y-10);
  ctx.shadowBlur=0;
 }
 if(!markers){
  ctx.fillStyle="rgba(13,23,33,.9)";ctx.fillRect(12,12,Math.min(420,w-24),38);
  ctx.fillStyle="#d6e7f7";ctx.font="13px system-ui";
  ctx.fillText("No fresh aircraft positions in selected layers",22,36);
 }
 $("mapLabel").textContent=state.centerLabel;
}
canvas.addEventListener("pointerdown",e=>{
 state.pointer=[e.clientX,e.clientY,state.lon,state.lat];
 canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener("pointermove",e=>{
 if(!state.pointer)return;
 const p=state.pointer,state_zoom=2**state.zoom*256;
 state.moved=true;state.lon=p[2]-(e.clientX-p[0])/state_zoom*360;
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
  const [x,y]=xy(a.lat,a.lon);
  const d=Math.hypot(x-(e.clientX-canvas.getBoundingClientRect().left),y-(e.clientY-canvas.getBoundingClientRect().top));
  if(d<bestD){bestD=d;best=a}
 }
 if(best)choose(best);
});
canvas.addEventListener("wheel",e=>{
 e.preventDefault();state.moved=true;state.zoom=Math.max(2,Math.min(12,state.zoom+(e.deltaY<0?1:-1)));paint();
},{passive:false});
// Provider selection is explicit and never creates a hidden proxy/key.
const preset=$("onlinePreset");
const customFeed=$("onlineFeedUrl");
function showProviderChoice(){
 customFeed.disabled=preset.value!=="custom";
 $("airlabsKeyField").hidden=preset.value!=="airlabs";
 customFeed.title=customFeed.disabled
  ?"Select Custom HTTPS/CORS ADS-B feed to enter a URL."
  :"Only trusted /api/aircraft endpoints with documented CORS and source attribution.";
}
preset.onchange=()=>{
 showProviderChoice();
 if(state.connectionKind==="usb"||state.connectionKind==="internet"){
  state.internetSnapshot=null;state.internetBackoffUntil=0;state.airlabsLastFetch=0;
  if(preset.value==="off"&&state.connectionKind==="internet")disconnect();
  else void connect();
 }
};
showProviderChoice();
$("networkApply").onclick=()=>{
 if(state.connectionKind==="bridge"){
  notice("The paired readsb bridge manages its own network source. To configure a browser Internet provider, disconnect the bridge first; this will not stop your readsb service.");
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
function publishTarBrowserSnapshot(){
 const frame=$("fullTarFrame");
 if(!tarFrameOpen||!frame?.contentWindow)return;
 const aircraft=(state.data||[]).filter(a=>a && Number.isFinite(a.seen) && a.seen>=0 && a.seen<=60)
  .slice(0,1500).map(a=>({
    hex:a.hex,flight:a.flight,lat:a.lat,lon:a.lon,track:a.track,
    gs:a.gs,tas:a.tas,ias:a.ias,mach:a.mach,
    alt_baro:a.alt_baro,alt_geom:a.alt_geom,baro_rate:a.baro_rate,
    geom_rate:a.geom_rate,squawk:a.squawk,rssi:a.rssi,
    seen:a.seen,seen_pos:a.seen_pos,messages:a.messages,
    r:a.r,t:a.t,type:a.type,category:a.category,dbFlags:a.dbFlags,
    sources:a.sources
  }));
 frame.contentWindow.postMessage({type:"tihulu:tar-aircraft",
  now:Date.now()/1000,
  messages:state.connectionKind==="usb"?state.usbMessageCount:
    (Number.isFinite(state.receiverMessages)?state.receiverMessages:0),
  aircraft},location.origin);
}
function setBrowserTar(open){
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
   frame.setAttribute("src","./tar1090/index.html?"+query.toString());
  }
  publishTarBrowserSnapshot();
  notice("Full upstream tar1090 frontend opened with this tab's real aircraft. No separate readsb service or USB claim.");
 }else{
  // Tear down upstream tar1090 intervals/map listeners when its window closes.
  // The parent WebUSB receiver stays active and owns the dongle as before.
  const frame=$("fullTarFrame");
  if(frame?.hasAttribute("src"))frame.removeAttribute("src");
  $("fullTar1090").focus();
 }
}
$("fullTar1090").onclick=()=>setBrowserTar(true);
$("closeFullTar").onclick=()=>setBrowserTar(false);
$("fullTarFrame").addEventListener("load",()=>publishTarBrowserSnapshot());
window.addEventListener("message",event=>{
 if(event.origin!==location.origin || event.source!==$("fullTarFrame").contentWindow)return;
 if(event.data?.type==="tihulu:tar-ready")publishTarBrowserSnapshot();
});
window.setInterval(()=>{if(tarFrameOpen && !document.hidden)publishTarBrowserSnapshot()},1200);
window.addEventListener("keydown",event=>{
 if(event.key==="Escape" && tarFrameOpen)setBrowserTar(false);
});
$("legacyTar").onclick=async()=>{
 if(state.connectionKind==="usb"){
  // Do not direct a user with one USB dongle to a dead readsb JSON server.
  setRadarExpanded(true);
  notice("tar1090 needs a separate live readsb JSON backend. Your SDR is owned by this WebUSB tab, so use this full browser map. Stop WebUSB before switching the same antenna to readsb.");
  return;
 }
 // A running readsb process is not proof that tar1090 has fresh JSON.
 // GitHub Pages cannot share this tab's WebUSB receiver with tar1090.
 if(state.connectionKind!=="bridge"){
  setRadarExpanded(true);
  notice("No independently verified tar1090 decoder. This full browser map retains genuine WebUSB aircraft and Internet layers.");
  return;
 }
 let live;
 try{live=await api("/api/tar-status");}
 catch(error){
  setRadarExpanded(true);
  notice("Unable to verify tar1090 aircraft.json: "+String(error.message||error)+". Showing the working integrated radar.");
  return;
 }
 if(!live.available || !live.url){
  setRadarExpanded(true);
  notice(live.reason||"tar1090 has no fresh readsb aircraft.json; use this full radar.");
  return;
 }
 const raw=prompt("Verified separate tar1090 receiver URL:",live.url);
 if(raw===null)return;
 try{window.open(tarFocusURL(raw),"_blank","noopener,noreferrer");}
 catch(error){notice("Invalid tar1090 URL: "+error.message);}
};
$("start").onclick=()=>control("start");
$("stop").onclick=()=>control("stop");
$("restart").onclick=()=>control("restart");
$("mode").onchange=()=>{state.autoFocused=false;refresh()};
$("focus").onclick=()=>{focusAir(true);state.moved=true;};
function chooseRegion(point,label,zoom=8){
 state.lat=point.lat;state.lon=point.lon;
 state.queryLat=point.lat;state.queryLon=point.lon;
 state.zoom=zoom;state.moved=true;state.autoFocused=false;
 state.centerLabel=label+" · Internet search region, not physical receiver";
 paint();
 if(state.connected)refresh();
}
$("cologne").onclick=()=>chooseRegion(COLOGNE,"Cologne",9);
$("germany").onclick=()=>chooseRegion(GERMANY,"Germany",7);
$("searchHere").onclick=()=>{
 state.queryLat=state.lat;state.queryLon=state.lon;
 state.moved=true;
 state.centerLabel="Internet search moved to map view · receiver location unchanged";
 paint();
 if(state.connected)refresh();
};
$("locate").onclick=()=>{
 if(!navigator.geolocation){notice("Browser geolocation not available.");return}
 navigator.geolocation.getCurrentPosition(p=>{
  state.lat=p.coords.latitude;state.lon=p.coords.longitude;
  state.queryLat=state.lat;state.queryLon=state.lon;
  state.zoom=10;state.moved=true;state.centerLabel="Explicit permitted GPS search region";
  paint();
  notice("Map and Internet search moved with your permission; SDR receiver site unchanged.");
  if(state.connected)refresh();
 },e=>notice("Browser location unavailable: "+e.message),{timeout:7000});
};
$("zoomIn").onclick=()=>{state.zoom=Math.min(12,state.zoom+1);state.moved=true;paint()};
$("zoomOut").onclick=()=>{state.zoom=Math.max(2,state.zoom-1);state.moved=true;paint()};
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
 $("mode").value="auto";
 notice("GitHub Pages ready. Start Direct WebUSB for actual 1090 MHz ADS-B, or configure an Internet feed. No local app is required.");
}

initializeStartupLocation();
