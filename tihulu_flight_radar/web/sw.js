"use strict";
// Only same-origin, immutable app-shell assets are cached for offline UI use.
// Never cache ADS-B data, third-party tiles, pairing tokens or API responses.
const CACHE="tihulu-flight-radar-shell-v27";
const SHELL=["./","./index.html","./install.html","./style.css","./app.js","./receiver_coverage.js","./map_motion.js","./rf_timing_lab.js","./multi_sources.js","./flight_location_ui.mjs","./location_search.mjs","./cities-de-tr.json","./manifest.webmanifest","./icon.svg","./browser_usb.mjs","./adsb_worker.mjs","./usb_tools.mjs","./vendor/rtlsdr.mjs"];
self.addEventListener("install",event=>{
 event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting()));
});
self.addEventListener("activate",event=>{
 event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith("tihulu-flight-radar-shell-")&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener("fetch",event=>{
 if(event.request.method!=="GET")return;
 const u=new URL(event.request.url);
 if(u.origin!==self.location.origin)return;
 const path=u.pathname;
 const eligible=SHELL.some(asset=>new URL(asset,self.registration.scope).pathname===path);
 if(!eligible)return;
 event.respondWith(
  fetch(event.request).then(response=>{
   if(response.ok){
    const copy=response.clone();
    event.waitUntil(caches.open(CACHE).then(cache=>cache.put(event.request,copy)));
   }
   return response;
  }).catch(()=>caches.match(event.request))
 );
});
