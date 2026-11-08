"use strict";
// Offline radio-horizon coverage constraints, NOT trilateration or time-of-flight ranging.
// Only local, positioned ADS-B radio observations are eligible. Public feeds
// (even "I/R" rows whose displayed coordinates came from the Internet) cannot
// be used to infer any physical receiver position.
const TihuluRFCoverage = (() => {
 const RAD=Math.PI/180, EARTH_KM=6371.0088;
 function point(p){
  return p && Number.isFinite(p.lat) && Number.isFinite(p.lon) &&
   Math.abs(p.lat)<=85 && Math.abs(p.lon)<=180;
 }
 function distanceKm(a,b){
  const dlat=(b.lat-a.lat)*RAD,dlon=(b.lon-a.lon)*RAD;
  const q=Math.sin(dlat/2)**2+Math.cos(a.lat*RAD)*Math.cos(b.lat*RAD)*Math.sin(dlon/2)**2;
  return 2*EARTH_KM*Math.asin(Math.min(1,Math.sqrt(Math.max(0,q))));
 }
 // A generous radio-line-of-sight ceiling for a near-ground (<=30 m) receiver:
 // 4/3 effective-earth-radius standard refraction, plus a 30 km uncertainty
 // allowance for altitude, refraction and antenna elevation. This is an
 // upper-bound *model*, never a measured path length or an accuracy estimate.
 function horizonKm(altitudeFeet){
  if(!Number.isFinite(altitudeFeet)||altitudeFeet<1000||altitudeFeet>65000)return null;
  const r=EARTH_KM*4/3, h=altitudeFeet*0.0003048, receiverH=0.03;
  return Math.sqrt(2*r*h+h*h)+Math.sqrt(2*r*receiverH+receiverH*receiverH)+30;
 }
 function eligible(a){
  const radio=a?.observations?.antenna;
  return a?.position_source==="antenna" &&
   Array.isArray(a.sources)&&a.sources.includes("antenna") &&
   /^[a-f0-9]{6}$/i.test(String(a.hex||"")) &&
   point(radio) && point(a) &&
   Number.isFinite(a.seen)&&a.seen>=0&&a.seen<=60 &&
   Number.isFinite(a.seen_pos)&&a.seen_pos>=0&&a.seen_pos<=60 &&
   Number.isFinite(radio.seen)&&radio.seen>=0&&radio.seen<=60 &&
   Number.isFinite(radio.seen_pos)&&radio.seen_pos>=0&&radio.seen_pos<=60 &&
   distanceKm(radio,a)<1; // the displayed position must be genuinely from RF
 }
 function horizonPoints(circle,segments=72){
  const lat=circle.lat*RAD,lon=circle.lon*RAD,d=circle.radiusKm/EARTH_KM;
  const samples=[];
  for(let i=0;i<=segments;i++){
   const angle=2*Math.PI*i/segments;
   const nextLat=Math.asin(Math.sin(lat)*Math.cos(d)+Math.cos(lat)*Math.sin(d)*Math.cos(angle));
   const nextLon=lon+Math.atan2(Math.sin(angle)*Math.sin(d)*Math.cos(lat),
    Math.cos(d)-Math.sin(lat)*Math.sin(nextLat));
   samples.push({lat:nextLat/RAD,lon:((nextLon/RAD+540)%360)-180});
  }
  return samples;
 }
 // Store only an already verified direct-antenna position constraint.
 // A historical observation is *not* a fresh plane or a measured range.
 function recordedCircle(a,capturedAtMs=Date.now()){
  if(!eligible(a)||!Number.isFinite(capturedAtMs))return null;
  const rf=a.observations.antenna;
  const altitudeFeet=rf.alt_geom??rf.alt_baro??a.alt_geom??a.alt_baro;
  const radiusKm=horizonKm(altitudeFeet==="ground"?0:altitudeFeet);
  if(radiusKm===null)return null;
  return {hex:a.hex.toLowerCase(),flight:String(a.flight||a.hex).trim(),
   lat:rf.lat,lon:rf.lon,radiusKm,altitudeFeet,
   recorded_rf:true,capturedAtMs};
 }
 function compute(aircraft,history=[]){
  const records=[],seen=new Set();
  for(const a of Array.isArray(aircraft)?aircraft:[]){
   if(!eligible(a) || seen.has(a.hex.toLowerCase()))continue;
   const rf=a.observations.antenna;
   const altitudeFeet=rf.alt_geom??rf.alt_baro??a.alt_geom??a.alt_baro;
   const radiusKm=horizonKm(altitudeFeet==="ground"?0:altitudeFeet);
   if(radiusKm===null)continue;
   records.push({hex:a.hex.toLowerCase(),flight:String(a.flight||a.hex).trim(),
    lat:rf.lat,lon:rf.lon,radiusKm,altitudeFeet,
    ageSeconds:Math.max(a.seen_pos,rf.seen_pos)});
   seen.add(a.hex.toLowerCase());
  }
  // Optional fixed-receiver session history, gathered only after eligible().
  // Drop observations older than two hours, cap model inputs and keep their
  // historical status separate from the current aircraft map.
  const now=Date.now();
  for(const old of Array.isArray(history)?history.slice(-64):[]){
   if(!old||old.recorded_rf!==true||
      !/^[a-f0-9]{6}$/i.test(String(old.hex||""))||seen.has(old.hex)||
      !point(old)||!Number.isFinite(old.radiusKm)||
      old.radiusKm<10||old.radiusKm>1600||
      !Number.isFinite(old.capturedAtMs)||
      old.capturedAtMs>now+5000||now-old.capturedAtMs>2*3600*1000)continue;
   records.push({...old,ageSeconds:(now-old.capturedAtMs)/1000,
    historic:true});
   seen.add(old.hex);
  }
  records.sort((a,b)=>a.ageSeconds-b.ageSeconds);
  if(records.length<3)return {status:"insufficient",count:records.length,circles:[],region:null};
  // Bound workload: choose newest independent RF aircraft, max 6 rings.
  // Apply more genuinely independent RF constraints as aircraft count grows;
  // only draw six circles to avoid visual clutter. This is not true accuracy.
  const constraints=records.slice(0,64);
  const circles=constraints.slice(0,6);
  // No receiver latitude/longitude is an input. Unwrap longitude only to
  // build the intersection grid (crossing the date line is supported).
  // Actual acceptance remains a geodesic distance test for EVERY verified RF
  // aircraft. Each circle is an upper-bound reception constraint, not a
  // measured range. The resulting centroid is *not* a receiver location fix.
  const longitudeNear=(lon,anchor)=>anchor+((lon-anchor+540)%360)-180;
  const originLon=constraints[0].lon;
  const bounds=constraints.map(c=>{
   const spreadLat=c.radiusKm/110.5;
   // Conservative longitude envelope uses the smallest cosine at the
   // northern/southern edge, not only at the aircraft latitude.
   const edge=Math.min(84.9,Math.abs(c.lat)+spreadLat);
   const spreadLon=c.radiusKm/(111.2*Math.max(.05,Math.cos(edge*RAD)));
   const lon=longitudeNear(c.lon,originLon);
   return {south:Math.max(-85,c.lat-spreadLat),
    north:Math.min(85,c.lat+spreadLat),
    west:lon-spreadLon,east:lon+spreadLon};
  });
  const minLat=Math.max(...bounds.map(b=>b.south));
  const maxLat=Math.min(...bounds.map(b=>b.north));
  const minLon=Math.max(...bounds.map(b=>b.west));
  const maxLon=Math.min(...bounds.map(b=>b.east));
  if(minLat>=maxLat||minLon>=maxLon)return {
   status:"no_overlap",count:records.length,constraintsUsed:constraints.length,circles,region:null};
  const points=[];
  const STEPS=48;
  for(let i=0;i<=STEPS;i++)for(let j=0;j<=STEPS;j++){
   const lat=minLat+(maxLat-minLat)*i/STEPS;
   const unwrappedLon=minLon+(maxLon-minLon)*j/STEPS;
   const p={lat,lon:((unwrappedLon+540)%360)-180};
   if(constraints.every(c=>distanceKm(p,c)<=c.radiusKm))points.push(p);
  }
  // A vanishingly small sampled overlap is not a safe coordinate estimate.
  if(points.length<3)return {status:"unresolved",count:records.length,
   constraintsUsed:constraints.length,circles,region:null};
  const centerLat=points.reduce((sum,p)=>sum+p.lat,0)/points.length;
  const centerUnwrappedLon=points.reduce((sum,p)=>
   sum+longitudeNear(p.lon,originLon),0)/points.length;
  const center={lat:centerLat,lon:((centerUnwrappedLon+540)%360)-180};
  const extentKm=Math.max(...points.map(p=>distanceKm(center,p)));
  return {status:"region",count:records.length,constraintsUsed:constraints.length,circles,
   region:{...center,extentKm:Math.max(10,Math.ceil(extentKm/10)*10),
    sampleCount:points.length,possibleSamples:points,
    kind:"possible-area-centroid",accuracyMeters:null,confidence:null}};
 }
 return {point,distanceKm,horizonKm,horizonPoints,eligible,recordedCircle,compute};
})();
if(typeof module!=="undefined"&&module.exports)module.exports=TihuluRFCoverage;
if(typeof window!=="undefined")window.TihuluRFCoverage=TihuluRFCoverage;
