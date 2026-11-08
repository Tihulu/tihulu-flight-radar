"use strict";
// Radio-horizon coverage constraints, NOT trilateration or time-of-flight ranging.
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
 function compute(aircraft){
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
  records.sort((a,b)=>a.ageSeconds-b.ageSeconds);
  if(records.length<4)return {status:"insufficient",count:records.length,circles:[],region:null};
  // Bound workload: choose newest independent RF aircraft, max 6 rings.
  // Apply more genuinely independent RF constraints as aircraft count grows;
  // only draw six circles to avoid visual clutter. This is not true accuracy.
  const constraints=records.slice(0,64);
  const circles=constraints.slice(0,6);
  // Equirectangular bounds only choose a candidate search grid; actual cell
  // acceptance always checks geodesic distances to every ring.
  const minLat=Math.max(...constraints.map(c=>c.lat-c.radiusKm/110.5));
  const maxLat=Math.min(...circles.map(c=>c.lat+c.radiusKm/110.5));
  const minLon=Math.max(...circles.map(c=>c.lon-c.radiusKm/(111.2*Math.max(0.2,Math.cos(c.lat*RAD)))));
  const maxLon=Math.min(...circles.map(c=>c.lon+c.radiusKm/(111.2*Math.max(0.2,Math.cos(c.lat*RAD)))));
  if(minLat>=maxLat||minLon>=maxLon)return {status:"no_overlap",count:records.length,constraintsUsed:constraints.length,circles,region:null};
  const points=[];
  for(let i=0;i<=40;i++)for(let j=0;j<=40;j++){
   const p={lat:minLat+(maxLat-minLat)*i/40,lon:minLon+(maxLon-minLon)*j/40};
   if(constraints.every(c=>distanceKm(p,c)<=c.radiusKm))points.push(p);
  }
  if(!points.length)return {status:"unresolved",count:records.length,constraintsUsed:constraints.length,circles,region:null};
  // Centre of *geometric possibility area*, not a receiver coordinate fix.
  const center={lat:points.reduce((s,p)=>s+p.lat,0)/points.length,
   lon:points.reduce((s,p)=>s+p.lon,0)/points.length};
  const extentKm=Math.max(...points.map(p=>distanceKm(center,p)));
  return {status:"region",count:records.length,constraintsUsed:constraints.length,circles,
   region:{...center,extentKm:Math.ceil(extentKm/10)*10,
    sampleCount:points.length,possibleSamples:points}};
 }
 return {point,distanceKm,horizonKm,horizonPoints,eligible,compute};
})();
if(typeof module!=="undefined"&&module.exports)module.exports=TihuluRFCoverage;
if(typeof window!=="undefined")window.TihuluRFCoverage=TihuluRFCoverage;
