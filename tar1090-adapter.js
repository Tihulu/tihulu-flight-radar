/* TIHULU adapter for the complete upstream tar1090 frontend, GPL-2.0-or-later.
 * Upstream is bundled, unchanged apart from adding this script after jQuery.
 * Direct WebUSB runs in parent tab; tar1090 only consumes REAL observed
 * aircraft snapshots from the same-origin parent, never owns the SDR.
 */
(() => {
  "use strict";
  const origin = location.origin;
  const isEmbedded = window.parent !== window;
  // A packaged native Qt parent uses private localhost while its fallback
  // full tar1090 iframe can be hosted on official HTTPS Pages. Only these
  // two explicitly verified origins may send aircraft, never arbitrary sites.
  const allowedParent = raw => {
    try{
      const url=new URL(raw);
      return url.origin===origin || (url.protocol==="http:" &&
        ["localhost","127.0.0.1"].includes(url.hostname) &&
        Number.isInteger(Number(url.port)) && Number(url.port)>0);
    }catch{return false;}
  };
  let parentOrigin = null;
  const show = {internet:true,antenna:true,matched:true};
  let snapshot = {now: Date.now()/1000, messages:0, aircraft:[]};
  let sources = new Map();
  let updatedAt = 0;
  let connected = false;
  const MAX_AIRCRAFT = 1500;
  // Pinned upstream tar1090 declares 'let OLMap' at global lexical scope.
  // It is not window.OLMap. Use that actual map for genuine I/R badge layer.
  function originalMap(){
    return typeof OLMap !== "undefined" && OLMap ? OLMap : window.OLMap;
  }
  function originalPlanes(){return typeof g !== "undefined" && g ? g : window.g;}
  function originalOl(){return typeof ol !== "undefined" && ol ? ol : window.ol;}
  function updateUpstreamTable(){
    const tar=typeof TAR !== "undefined" ? TAR : window.TAR;
    if(tar?.planeMan?.refresh)tar.planeMan.refresh();
    originalMap()?.render?.();
  }
  // tar1090 retains aircraft models after a JSON row disappears.
  // Filtering transport JSON alone therefore cannot disable a map layer.
  // Remove only excluded objects using upstream's own reaper pattern.
  function reconcileSourceVisibility(){
    if(!connected)return;
    const group=originalPlanes();
    if(!group || !Array.isArray(group.planesOrdered) || !group.planes)return;
    const permitted=new Set(visibleAircraft().map(a=>a.hex));
    let removed=0;
    for(const plane of [...group.planesOrdered]){
      if(!plane || permitted.has(String(plane.icao||"").toLowerCase()))continue;
      if(plane.selected && typeof deselectAllPlanes==="function")deselectAllPlanes();
      delete group.planes[plane.icao];
      const i=group.planesOrdered.indexOf(plane);
      if(i!==-1)group.planesOrdered.splice(i,1);
      if(typeof plane.destroy==="function")plane.destroy();
      removed++;
    }
    if(removed)updateUpstreamTable();
  }
  function visibleAircraft(){
    const elapsed=Math.max(0,(Date.now()-updatedAt)/1000);
    return snapshot.aircraft.filter(a=>{
      const src=sources.get(a.hex)||[];
      if(src.includes("antenna")&&src.includes("internet"))return show.matched;
      return src.includes("antenna")?show.antenna:show.internet;
    }).map(a=>{
      const row={...a};
      if(Number.isFinite(row.seen))row.seen+=elapsed;
      if(Number.isFinite(row.seen_pos))row.seen_pos+=elapsed;
      if(!Number.isFinite(row.seen_pos)||row.seen_pos>60){
        delete row.lat;delete row.lon;
      }
      return row;
    }).filter(a=>Number.isFinite(a.seen)&&a.seen<=60);
  }
  function liveSnapshot(){
    // A static browser page is NOT a radio decoder: only actual radio
    // counters reported by the parent can be sent as such.
    return {now:Date.now()/1000,messages:snapshot.messages,
      aircraft:visibleAircraft()};
  }
  function mountSourceLayers(){
    if(typeof document.getElementById!=="function")return;
    const map=document.getElementById("map_container");
    if(!map || document.getElementById("tihulu-source-layers"))return;
    const panel=document.createElement("div");
    panel.id="tihulu-source-layers";
    panel.style.cssText="position:absolute;top:64px;left:12px;z-index:20010;"+
      "background:#101c2be9;color:#edf7ff;border:1px solid #496983;"+
      "border-radius:8px;padding:9px 12px;font:12px/1.4 system-ui;"+
      "box-shadow:0 4px 14px #08162799;max-width:min(360px,90%);";
    const header=document.createElement("div");
    header.textContent="TIHULU aircraft sources — original tar1090";
    header.style.cssText="font-weight:700;margin-bottom:6px";
    panel.appendChild(header);
    for(const [key,name] of [
      ["internet","Internet planes (I)"],["antenna","Local radio (R)"],
      ["matched","Both Internet + radio (I/R)"]
    ]){
      const label=document.createElement("label");
      label.style.cssText="display:block;margin:3px 0;cursor:pointer";
      const checkbox=document.createElement("input");
      checkbox.type="checkbox";checkbox.checked=show[key];
      checkbox.setAttribute("aria-label","Show "+name);
      checkbox.onchange=()=>{
        show[key]=checkbox.checked;
        reconcileSourceVisibility(); // remove already-drawn markers and table rows
        refreshBadges();
      };
      label.appendChild(checkbox);
      label.appendChild(document.createTextNode(" "+name));
      panel.appendChild(label);
    }
    const message=document.createElement("div");
    message.id="tihulu-sources-detail";
    message.style.cssText="color:#a8cddd;margin-top:6px;font-size:11px";
    panel.appendChild(message);
    map.appendChild(panel);
    window.tihuluTarSourcePanel=panel;
    // Restore the legacy selected-aircraft-safe layout. In tar1090 the
    // selected_info block is a SIBLING of map_container and floats above it,
    // so an unconditional top-left legend obscures the aircraft details.
    const layout=()=>{
      const host=document.getElementById("map_container");
      const side=document.getElementById("sidebar_container");
      const selected=document.getElementById("selected_infoblock");
      if(!host || !host.getBoundingClientRect)return;
      const bounds=host.getBoundingClientRect();
      if(bounds.width<1 || bounds.height<1)return;
      const selectedRect=selected?.getBoundingClientRect?.();
      const selectedStyle=selected && window.getComputedStyle?.(selected);
      const infoblockVisible=!!(selectedRect && selectedStyle?.display!=="none" &&
        selectedStyle?.visibility!=="hidden" &&
        selectedRect.width>30 && selectedRect.height>30 &&
        selectedRect.right>bounds.left && selectedRect.left<bounds.right);
      const safeLeft=infoblockVisible
        ? Math.max(12,Math.ceil(selectedRect.right-bounds.left)+12):12;
      const remaining=Math.max(0,Math.floor(bounds.width-safeLeft-12));
      const sideBounds=side?.getBoundingClientRect?.();
      const dockToSidebar=infoblockVisible && remaining<190 &&
        sideBounds?.width>240 && sideBounds?.height>200;
      if(dockToSidebar){
        if(panel.parentElement!==side)side.insertBefore(panel,side.firstChild);
        panel.style.position="relative";panel.style.left="auto";panel.style.top="auto";
        panel.style.width="auto";panel.style.maxWidth="calc(100% - 12px)";
        panel.style.margin="6px";panel.style.flexShrink="0";
      }else{
        if(panel.parentElement!==host)host.appendChild(panel);
        panel.style.position="absolute";panel.style.left=safeLeft+"px";
        panel.style.top="64px";panel.style.width="max-content";
        panel.style.maxWidth=Math.max(70,remaining)+"px";
        panel.style.margin="0";panel.style.flexShrink="";
      }
      // The original tar1090 altitude ramp is up to 800px wide and stays
      // on the map bottom. Narrow the ramp when a selected plane's detail
      // pane occupies the left side; never let ramp and details intersect.
      const chart=document.getElementById("altitude_chart");
      if(chart){
        const right=Math.min(85,Math.max(12,Math.round(bounds.width*.06)));
        const space=Math.max(0,Math.floor(bounds.width-right-(infoblockVisible?safeLeft:12)-12));
        const width=Math.min(800,space);
        chart.style.right=right+"px";
        chart.style.width=width+"px";
        chart.style.maxWidth=width+"px";
        chart.style.visibility=space<125?"hidden":"";
      }
    };
    window.tihuluTarLayout=layout;
    window.addEventListener("resize",layout);
    if(typeof ResizeObserver!=="undefined"){
      const obs=new ResizeObserver(layout);
      obs.observe(map);
      const sel=document.getElementById("selected_infoblock");
      if(sel)obs.observe(sel);
      window.tihuluTarLayoutResizeObserver=obs;
    }
    if(typeof MutationObserver!=="undefined"){
      const sel=document.getElementById("selected_infoblock");
      if(sel){
        const obs=new MutationObserver(layout);
        obs.observe(sel,{attributes:true,attributeFilter:["style","class","hidden"]});
        window.tihuluTarLayoutMutationObserver=obs;
      }
    }
    layout();
    mountStatus();
  }
  const status = document.createElement("div");
  status.id = "tihulu-browser-source-status";
  status.setAttribute("role","status");
  status.style.cssText = "position:fixed;z-index:20000;left:50%;top:4px;"+
    "transform:translateX(-50%);background:#152539e8;color:#e9f6ff;"+
    "font:12px/1.4 system-ui;padding:4px 9px;border-radius:6px;"+
    "pointer-events:none;max-width:75vw;text-align:center;";
  function mountStatus(){
    if(document.body && !status.isConnected)document.body.appendChild(status);
    const radio=[...sources.values()].filter(s=>s.includes("antenna")).length;
    const internet=[...sources.values()].filter(s=>s.includes("internet")).length;
    const matched=[...sources.values()].filter(s=>s.includes("antenna")&&s.includes("internet")).length;
    const age=Math.round((Date.now()-updatedAt)/1000);
    const descriptor=connected?(radio?"Antenna + Internet":"Internet-only · no antenna required"):
      "Awaiting real Internet or antenna observations";
    status.textContent="tar1090 · "+descriptor+" · R "+radio+" · I "+internet+
      " · I/R "+matched+(connected?" · update "+age+"s ago":"");
    const detail=document.getElementById?.("tihulu-sources-detail");
    if(detail)detail.textContent=internet+" Internet · "+radio+" radio · "+matched+
      " matched (single ICAO marker) · "+Math.max(0,age)+"s ago";
  }
  window.addEventListener("DOMContentLoaded",()=>{
    mountStatus();
    mountSourceLayers();
  });
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
    if(!isEmbedded || !allowedParent(event.origin) || event.source!==window.parent)return;
    const m=event.data;
    if(!m || m.type!=="tihulu:tar-aircraft" || !Array.isArray(m.aircraft))return;
    if(!allowedParent(event.origin))return;
    if(parentOrigin && event.origin!==parentOrigin)return;
    parentOrigin=event.origin;
    const unique=new Map(),observations=new Map();
    for(const raw of m.aircraft.slice(0,MAX_AIRCRAFT)){
      const a=sanitizeAircraft(raw);
      if(!a)continue;
      const src=Array.isArray(raw?.sources)?
        raw.sources.filter(x=>x==="antenna"||x==="internet"):[];
      const previous=unique.get(a.hex);
      const oldSources=observations.get(a.hex)||[];
      observations.set(a.hex,[...new Set([...oldSources,...src])]);
      if(!previous || (src.includes("antenna")&&!oldSources.includes("antenna")) ||
          (Number.isFinite(a.seen_pos)&&a.seen_pos<(previous.seen_pos??Infinity)))
        unique.set(a.hex,a);
    }
    const aircraft=[...unique.values()];
    const now=Number(m.now);
    if(!Number.isFinite(now) || Math.abs(Date.now()/1000-now)>120)return;
    // Distinct radio and internet records were already provenance-merged
    // by the same app that renders the regular radar.
    snapshot={now,messages:Number.isFinite(m.messages)?m.messages:0,aircraft};
    sources=observations;
    connected=true;updatedAt=Date.now();mountStatus();
    reconcileSourceVisibility();
    refreshBadges();
  });
  function reply(){
    // The greeting contains no aircraft, secrets or personal coordinates.
    // Parent will authenticate this iframe by event.source + event.origin.
    if(isEmbedded)window.parent.postMessage(
      {type:"tihulu:tar-ready"},parentOrigin||"*");
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
          else response=liveSnapshot();
          complete(200,"success",{json:response},"Content-Type: application/json");
        });
      },
      abort(){cancelled=true;}
    };
  });
  let tagLayer=null,tagSource=null;
  function refreshBadges(){
    if(!connected)return;
    const ol=originalOl(),map=originalMap();
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
    for(const a of visibleAircraft()){
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
  window.setInterval(()=>{
    reconcileSourceVisibility();
    refreshBadges();
    window.tihuluTarLayout?.();
  },2200);
})();
