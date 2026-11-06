"use strict";
// Shared static frontend: hosted by GitHub Pages or the paired local bridge.
// Never fabricates receiver observations or sends a pairing token elsewhere.
const $ = id => document.getElementById(id);
const GERMANY = {lat:51.1657, lon:10.4515};
const COLORS = {antenna:"#50dcad", internet:"#5cafe8", both:"#e6b56b"};
const canvas = $("map"), ctx = canvas.getContext("2d");
const state = {
  base:"", token:"", connected:false, data:[], mode:"auto", selected:null, 
  lat:GERMANY.lat, lon:GERMANY.lon, zoom:7, moved:false, autoFocused:false,
  pointer:null, tracks:new Map(), tiles:new Map(), fetching:false, timer:null,
  centerLabel:"Germany default view · not receiver location"
};
const selectors = ["showAntenna","showInternet","showBoth","showTracks","showTiles"];
function notice(s){$("message").textContent=s}
function isPositioned(a){
 return a && Number.isFinite(a.lat) && Number.isFinite(a.lon) &&
  a.lat >= -90 && a.lat <= 90 && a.lon >= -180 && a.lon <= 180 &&
  Number.isFinite(a.seen_pos) && a.seen_pos >= 0 && a.seen_pos <= 60;
}
function category(a){return a.sources?.length > 1 ? "both" : (a.sources?.[0] || "internet")}
function visible(a){
 const c = category(a);
 return (c==="both" && $("showBoth").checked) ||
        (c==="antenna" && $("showAntenna").checked) ||
        (c==="internet" && $("showInternet").checked);
}
function getBase(raw){
 const u=new URL(raw);
 if(u.username || u.password || u.search || u.hash || u.pathname!=="/") throw Error("Use a bridge origin without a path or credentials.");
 if(u.protocol==="http:" && !["127.0.0.1","localhost","[::1]"].includes(u.hostname))
   throw Error("Remote bridges must use HTTPS. Plain HTTP is permitted only for loopback.");
 if(u.protocol!=="https:" && u.protocol!=="http:") throw Error("Bridge URL must use HTTP(S).");
 return u.origin;
}
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
   ". An active decoder does not prove RF reception.";
 for(const id of ["start","stop","restart"])$(id).disabled=!r.control_enabled;
}
async function connect(){
 if(state.timer){clearInterval(state.timer);state.timer=null;}
 try{
  state.base=getBase($("bridgeUrl").value.trim());
  state.token=$("token").value.trim();
  if(!state.token) throw Error("Paste the session token displayed by the local bridge.");
  await checkReceiver();
  connection(true,"Paired with local bridge");
  $("token").value="";
  notice("Bridge paired. Local/online source data stays attributed separately.");
  await refresh();
  state.timer=setInterval(()=>{if(!document.hidden)refresh()},15000);
 }catch(e){
  connection(false,"Not connected");
  notice("Connection failed: "+e.message+". Verify the bridge is running, pairing token, browser local-network permission and CORS.");
  state.token="";
 }
}
function disconnect(){
 if(state.timer)clearInterval(state.timer);
 state.timer=null;state.token="";state.base="";state.data=[];
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
  (l.messages!=null?" · "+l.messages+" receiver messages":""),
  "Internet: "+(i.state||"unknown")+(i.error?" ("+i.error+")":"")+
  (i.updated_at?" · observed "+formatTime(i.updated_at):"")+
  (i.provider?" · "+i.provider+" (ODbL)":"")
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
  state.lat=GERMANY.lat;state.lon=GERMANY.lon;state.zoom=7;
  state.centerLabel="Germany default view · no fresh aircraft position";
  if(force)state.moved=false;paint();return;
 }
 const distance=a=>Math.pow(a.lat-GERMANY.lat,2)+Math.pow((a.lon-GERMANY.lon)*.6,2);
 has.sort((a,b)=>distance(a)-distance(b));
 state.lat=has[0].lat;state.lon=has[0].lon;state.zoom=9;
 state.autoFocused=true;
 if(force)state.moved=false;
 state.centerLabel="Focused on observed "+(has[0].flight||has[0].hex||"aircraft");
 paint();
}
async function refresh(){
 if(!state.connected || state.fetching)return;
 state.fetching=true;
 try{
  const args=new URLSearchParams({mode:$("mode").value,lat:state.lat.toFixed(3),
    lon:state.lon.toFixed(3),radius:"100"});
  const result=await api("/api/aircraft?"+args.toString());
  state.data=Array.isArray(result.aircraft)?result.aircraft:[];
  updateCounters(result.counts);
  feedSummary(result.sources);
  recordTracks();
  if(!state.autoFocused&&!state.moved)focusAir();
  $("lastUpdate").textContent=formatTime(result.generated_at);
  renderTable();paint();
  notice("Updated real observations from "+(result.active_sources||[]).join(" + ")+". Internet and antenna counts are independent.");
 }catch(e){
  notice("Update failed: "+e.message+" — previous positions are not treated as live.");
  state.data=[];updateCounters();renderTable();paint();
 }finally{state.fetching=false}
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
 if(old && (!old.failedAt || Date.now()-old.failedAt<90000))return old;
 if(state.tiles.size>120)state.tiles.clear();
 const img=new Image();
 const info={img,failedAt:0};
 img.crossOrigin="anonymous";
 img.onload=()=>paint();
 img.onerror=()=>{info.failedAt=Date.now();paint()};
 img.src="https://tile.openstreetmap.org/"+key+".png";
 state.tiles.set(key,info);
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
  if(t.img.complete&&t.img.naturalWidth)
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
$("fullMap").onclick=()=>{
 const raw=prompt("Full tar1090 URL (receiver must host tar1090):","http://127.0.0.1/tar1090/");
 if(raw===null)return;
 try{
  const u=new URL(raw);
  if(!["http:","https:"].includes(u.protocol) || u.username || u.password)
   throw Error("Use a valid HTTP(S) tar1090 URL without embedded credentials.");
  window.open(u.href,"_blank","noopener,noreferrer");
 }catch(e){notice("Cannot open tar1090: "+e.message)}
};
$("start").onclick=()=>control("start");
$("stop").onclick=()=>control("stop");
$("restart").onclick=()=>control("restart");
$("mode").onchange=()=>{state.autoFocused=false;refresh()};
$("focus").onclick=()=>focusAir(true);
$("germany").onclick=()=>{
 state.lat=GERMANY.lat;state.lon=GERMANY.lon;state.zoom=7;state.moved=true;
 state.centerLabel="Germany default map · not receiver location";paint();
};
$("locate").onclick=()=>{
 if(!navigator.geolocation){notice("Browser geolocation not available.");return}
 navigator.geolocation.getCurrentPosition(p=>{
  state.lat=p.coords.latitude;state.lon=p.coords.longitude;
  state.zoom=10;state.moved=true;state.centerLabel="Explicit browser GPS location";
  paint();notice("Map moved to your permitted browser location.");
 },e=>notice("Browser location unavailable: "+e.message),{timeout:7000});
};
$("zoomIn").onclick=()=>{state.zoom=Math.min(12,state.zoom+1);state.moved=true;paint()};
$("zoomOut").onclick=()=>{state.zoom=Math.max(2,state.zoom-1);state.moved=true;paint()};
for(const id of selectors)$(id).onchange=()=>{renderTable();paint()};
$("bridgeUrl").value=location.hostname==="127.0.0.1"||location.hostname==="localhost"
 ? location.origin:"http://127.0.0.1:8510";
connection(false,"Not paired");
window.addEventListener("resize",resize);
resize();
