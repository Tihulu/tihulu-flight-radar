/* TIHULU adapter for the complete upstream tar1090 frontend, GPL-2.0-or-later.
 * Upstream is bundled, unchanged apart from adding this script after jQuery.
 * Direct WebUSB runs in parent tab; tar1090 only consumes REAL observed
 * aircraft snapshots from the same-origin parent, never owns the SDR.
 */
(() => {
  "use strict";
  const origin = location.origin;
  const isEmbedded = window.parent !== window;
  let snapshot = {now: Date.now()/1000, messages:0, aircraft:[]};
  let sources = new Map();
  let updatedAt = 0;
  let connected = false;
  const MAX_AIRCRAFT = 1500;
  const status = document.createElement("div");
  status.id = "tihulu-browser-source-status";
  status.setAttribute("role","status");
  status.style.cssText = "position:fixed;z-index:20000;left:50%;top:4px;"+
    "transform:translateX(-50%);background:#152539e8;color:#e9f6ff;"+
    "font:12px/1.4 system-ui;padding:4px 9px;border-radius:6px;"+
    "pointer-events:none;max-width:75vw;text-align:center;";
  function mountStatus(){
    if(document.body && !status.isConnected)document.body.appendChild(status);
    status.textContent = !connected
      ? "tar1090 full interface · waiting for real browser RF/Internet data"
      : "tar1090 · TIHULU WebUSB + Internet · R "+[...sources.values()].filter(s=>s.includes("antenna")).length+
        " · I "+[...sources.values()].filter(s=>s.includes("internet")).length+
        " · receiver data "+Math.round((Date.now()-updatedAt)/1000)+" s ago";
  }
  window.addEventListener("DOMContentLoaded",mountStatus);
  function sanitizeAircraft(raw){
    if(!raw || typeof raw !== "object")return null;
    const hex=String(raw.hex||"").toLowerCase();
    if(!/^[a-f0-9]{6}$/.test(hex))return null;
    let rec={hex, seen:0};
    for(const key of [
      "lat","lon","track","true_heading","gs","tas","ias","mach","alt_baro",
      "alt_geom","baro_rate","geom_rate","rssi","messages","seen","seen_pos",
      "nav_altitude_mcp","nav_heading","squawk","nic","nac_p","sil"
    ]){
      const val=raw[key];
      if(typeof val==="number" && Number.isFinite(val))rec[key]=val;
    }
    if(!Number.isFinite(rec.seen_pos) || rec.seen_pos>60) {
      delete rec.lat;delete rec.lon;
    }
    for(const key of ["flight","r","t","type","category","dbFlags","desc"]){
      const val=raw[key];
      if(typeof val==="string")rec[key]=val.slice(0,100);
    }
    if(raw.alt_baro==="ground")rec.alt_baro="ground";
    if(typeof raw.type!=="string")rec.type="adsb"; // mode, not source provenance
    return rec;
  }
  window.addEventListener("message",event=>{
    if(!isEmbedded || event.origin!==origin || event.source!==window.parent)return;
    const m=event.data;
    if(!m || m.type!=="tihulu:tar-aircraft" || !Array.isArray(m.aircraft))return;
    const aircraft=m.aircraft.slice(0,MAX_AIRCRAFT).map(sanitizeAircraft).filter(Boolean);
    const now=Number(m.now);
    if(!Number.isFinite(now) || Math.abs(Date.now()/1000-now)>120)return;
    // Distinct radio and internet records were already provenance-merged
    // by the same app that renders the regular radar.
    snapshot={now,messages:Number.isFinite(m.messages)?m.messages:0,aircraft};
    sources=new Map(aircraft.map((a,i)=>{
      const raw=m.aircraft.find(x=>String(x?.hex||"").toLowerCase()===a.hex);
      const src=Array.isArray(raw?.sources)?raw.sources.filter(x=>x==="antenna"||x==="internet"):[];
      return [a.hex,src];
    }));
    connected=true;updatedAt=Date.now();mountStatus();
    refreshBadges();
  });
  function reply(){
    if(isEmbedded)window.parent.postMessage({type:"tihulu:tar-ready"},origin);
    else {connected=false;mountStatus();}
  }
  document.addEventListener("DOMContentLoaded",reply);
  window.setInterval(reply,2000);
  window.setInterval(mountStatus,1000);
  // Supply tar1090's EXPECTED JSON over its standard AJAX interface.
  // No fake decoder service, no CORS fetch and no "grey backend" message.
  jQuery.ajaxTransport("+json", options=>{
    let url;
    try{url=new URL(options.url,location.href).pathname;}catch{return;}
    const base=url.split("/").slice(-2).join("/");
    if(!/^data\/(?:aircraft|receiver|stats|history_\d+)\.json$/.test(base))return;
    let cancelled=false;
    return {
      send(_headers,complete){
        queueMicrotask(()=>{
          if(cancelled)return;
          let response;
          if(base==="data/receiver.json")
            response={version:"TIHULU browser",readsb:false,refresh:1000,
              history:0,binCraft:false,zstd:false,dbServer:false};
          else if(base==="data/stats.json")
            response={now:Date.now()/1000,total:{messages:snapshot.messages}};
          else if(base.startsWith("data/history_"))
            response={now:Date.now()/1000,messages:0,aircraft:[]};
          else response=snapshot;
          complete(200,"success",{json:response},"Content-Type: application/json");
        });
      },
      abort(){cancelled=true;}
    };
  });
  let tagLayer=null,tagSource=null;
  function refreshBadges(){
    if(!connected)return;
    const ol=window.ol,map=window.OLMap;
    if(!ol?.layer?.Vector || !map?.addLayer || !ol?.proj?.fromLonLat)return;
    if(!tagLayer){
      tagSource=new ol.source.Vector();
      tagLayer=new ol.layer.Vector({source:tagSource,zIndex:1000,style:feature=>{
        const text=feature.get("badge");
        return new ol.style.Style({text:new ol.style.Text({
          text,font:"bold 11px sans-serif",offsetX:15,offsetY:17,
          fill:new ol.style.Fill({color:"#fff"}),
          backgroundFill:new ol.style.Fill({color:"#102b40ee"}),
          backgroundStroke:new ol.style.Stroke({color:"#9abbd6",width:1}),
          padding:[1,3,1,3]
        })});
      }});
      map.addLayer(tagLayer);
    }
    tagSource.clear();
    for(const a of snapshot.aircraft){
      if(!Number.isFinite(a.lat)||!Number.isFinite(a.lon))continue;
      const src=sources.get(a.hex)||[];
      const badge=src.includes("antenna")&&src.includes("internet")?"I/R":
        src.includes("antenna")?"R":src.includes("internet")?"I":"?";
      tagSource.addFeature(new ol.Feature({
        geometry:new ol.geom.Point(ol.proj.fromLonLat([a.lon,a.lat])),
        badge
      }));
    }
  }
  window.setInterval(refreshBadges,2200);
})();
