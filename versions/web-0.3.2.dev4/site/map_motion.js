"use strict";
// Display-only short-term ground-track projection between real ADS-B updates.
// Never writes predicted coordinates into aircraft records, network snapshots,
// RF provenance, tracks, location estimates, or exported data.
const TihuluMapMotion=(()=>{
 const RAD=Math.PI/180,EARTH_KM=6371.0088;
 function displayedPosition(a,receivedAtMs,nowMs=Date.now()){
  if(!a||!Number.isFinite(a.lat)||!Number.isFinite(a.lon)||
     !Number.isFinite(a.seen_pos)||a.seen_pos<0||
     Math.abs(a.lat)>85||Math.abs(a.lon)>180)
   return null;
  const measured={lat:a.lat,lon:a.lon,projected:false,ageSeconds:a.seen_pos};
  const gs=a.gs,heading=Number.isFinite(a.track)?a.track:a.true_heading;
  if(!Number.isFinite(gs)||gs<=5||gs>1250||
     !Number.isFinite(heading)||!Number.isFinite(receivedAtMs)||
     !Number.isFinite(nowMs)||nowMs<receivedAtMs)return measured;
  const age=Math.max(0,a.seen_pos+(nowMs-receivedAtMs)/1000);
  // Do not move old/stale traffic or infer movement in prolonged outages.
  if(age<=0||age>20)return {...measured,ageSeconds:age};
  const distanceKm=gs*1.852*(age/3600);
  if(distanceKm<=0)return {...measured,ageSeconds:age};
  const angular=distanceKm/EARTH_KM,lat=a.lat*RAD,lon=a.lon*RAD,bearing=heading*RAD;
  const nextLat=Math.asin(Math.sin(lat)*Math.cos(angular)+
   Math.cos(lat)*Math.sin(angular)*Math.cos(bearing));
  const nextLon=lon+Math.atan2(Math.sin(bearing)*Math.sin(angular)*Math.cos(lat),
   Math.cos(angular)-Math.sin(lat)*Math.sin(nextLat));
  return {lat:nextLat/RAD,lon:((nextLon/RAD+540)%360)-180,
   projected:true,ageSeconds:age};
 }
 return {displayedPosition};
})();
if(typeof module!=="undefined"&&module.exports)module.exports=TihuluMapMotion;
if(typeof window!=="undefined")window.TihuluMapMotion=TihuluMapMotion;
