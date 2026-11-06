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
const canvas = $("map"), ctx = canvas.getContext("2d");
const state = {
  base:"", token:"", onlineFeed:"", connectionKind:"none", connected:false, data:[], mode:"auto", selected:null, 
  lat:initialCenter.lat, lon:initialCenter.lon, zoom:9, moved:false, autoFocused:false,
  startupLocationPending:true, startupGeo:null, startupRank:1, startupSource:"cologne",
  startupQueryDirty:false,
  // Camera movement must not change the API search key during feed cooldown.
  queryLat:initialCenter.lat, queryLon:initialCenter.lon, queryRadius:100,
  lastFreshAt:0, lastData:[],
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
async function fetchInternetFeed(){
 const u=new URL(state.onlineFeed);
 u.searchParams.set("lat",state.queryLat.toFixed(3));
 u.searchParams.set("lon",state.queryLon.toFixed(3));
 u.searchParams.set("radius",String(state.queryRadius));
 const abort=new AbortController(), timeout=setTimeout(()=>abort.abort(),10000);
 try{
  const response=await fetch(u.href,{mode:"cors",credentials:"omit",cache:"no-store",signal:abort.signal});
  if(!response.ok)throw Error("Internet feed returned HTTP "+response.status);
  const text=await response.text();
  if(text.length>4*1024*1024)throw Error("Internet feed exceeds size limit.");
  const result=JSON.parse(text);
  if(!Array.isArray(result.aircraft))throw Error("Internet feed did not return aircraft.");
  const receivedAt=Number(result.generated_at);
  const age=Date.now()/1000-receivedAt;
  if(!Number.isFinite(age) || age< -10 || age>90)
   throw Error("Internet snapshot is stale or missing an observation timestamp.");
  const safe=result.aircraft.slice(0,10000).filter(a=>a&&typeof a==="object").map(a=>{
   const own={...a};
   if(typeof own.seen==="number")own.seen+=Math.max(0,age);
   if(typeof own.seen_pos==="number")own.seen_pos+=Math.max(0,age);
   own.sources=["internet"];
   own.position_source=isPositioned(own)?"internet":null;
   own.observations={internet:a};
   return own;
  }).filter(a=>Number.isFinite(a.seen)&&a.seen>=0&&a.seen<=60);
  return {
    generated_at:receivedAt,active_sources:["internet"],aircraft:safe,
    counts:{antenna:0,internet:safe.length,combined:safe.length},
    sources:{antenna:{state:"unavailable",error:"Requires paired local bridge"},
             internet:{state:"available",provider:result.provider||"Configured Internet feed",
                       attribution:result.attribution||"See Internet feed provider terms",
                       updated_at:receivedAt}}
  };
 }finally{clearTimeout(timeout)}
}
// Called only by our packaged Qt WebEngine wrapper after the trusted local
// page is loaded. The token is never placed in a URL, cookies or storage.
window.tihuluNativeConnect=async function(base, token){
 document.documentElement.classList.add("native");
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
  state.onlineFeed=getFeedURL($("onlineFeedUrl").value);
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
  state.connected=false;state.token="";state.connectionKind="none";
  connection(false,"Not connected");
  notice("Connection failed: "+e.message+". Check bridge pairing or feed CORS/availability.");
 }
}
function disconnect(){
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
  for(const value of [
   (a.flight||"—").trim()+" / "+(a.hex||"—"),
   a.alt_baro??a.alt_geom??"—",a.gs??"—",category(a)
  ]){
   const td=document.createElement("td");
   td.textContent=String(value);
   if(value===category(a)){td.className="tag "+category(a)}
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
  (i.attribution?" · "+i.attribution:"")
 ];
 $("feedStatus").textContent=details.join("\n");
 $("feedStatus").style.whiteSpace="pre-line";
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
   throw Error("Antenna-only mode requires a paired local bridge.");
  const args=new URLSearchParams({mode,lat:state.queryLat.toFixed(3),lon:state.queryLon.toFixed(3),radius:String(state.queryRadius)});
  const result=state.connectionKind==="bridge"
    ? await api("/api/aircraft?"+args.toString())
    : await fetchInternetFeed();
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
   ctx.strokeStyle=COLORS[category(a)];ctx.globalAlpha=.5;ctx.lineWidth=2;
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
  ctx.save();ctx.translate(x,y);ctx.rotate((Number(a.track)||0)*Math.PI/180);
  ctx.fillStyle=COLORS[category(a)];ctx.beginPath();
  ctx.moveTo(0,-13);ctx.lineTo(7,9);ctx.lineTo(0,4);ctx.lineTo(-7,9);
  ctx.closePath();ctx.fill();ctx.restore();
  ctx.font="12px system-ui";ctx.fillStyle="#fff";
  ctx.fillText((a.flight||a.hex||"Aircraft").trim(),x+12,y-8);
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
$("connect").onclick=connect;
$("disconnect").onclick=disconnect;
$("refresh").onclick=refresh;
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
$("fullMap").onclick=()=>{
 const raw=prompt("Full tar1090 URL (receiver must host tar1090):","http://127.0.0.1/tar1090/");
 if(raw===null)return;
 try{
  window.open(tarFocusURL(raw),"_blank","noopener,noreferrer");
 }catch(e){notice("Cannot open tar1090: "+e.message)}
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
 $("mode").value="internet";
 notice("GitHub Pages ready. Enter a trusted HTTPS Internet feed URL or pair a local bridge for antenna data.");
}

initializeStartupLocation();
