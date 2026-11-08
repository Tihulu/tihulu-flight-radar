"use strict";
// Offline radio-horizon coverage constraints, NOT trilateration or time-of-flight ranging.
// Only local, positioned ADS-B radio observations are eligible. Public feeds
// (even "I/R" rows whose displayed coordinates came from the Internet) cannot
// be used to infer any physical receiver position.
const TihuluRFCoverage = (() => {
 const RAD=Math.PI/180, EARTH_KM=6371.0088, MIN_INDEPENDENT=4;
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
   // Supporting metadata of a verified RF fix, never a measured range.
   speedKt:Number.isFinite(rf.gs)?rf.gs:null,
   headingDeg:Number.isFinite(rf.track)?rf.track:
    Number.isFinite(rf.true_heading)?rf.true_heading:null,
   positionAgeSeconds:rf.seen_pos,
   // Approximate epoch of the *decoded aircraft position fix*;
   // NEVER an RF propagation delay, TX UTC timestamp or UTC-synced arrival.
   observationTimeMs:capturedAtMs-rf.seen_pos*1000,
   recorded_rf:true,capturedAtMs};
 }
 // Keep measured radio positions only. Speed and direction control adaptive
 // sampling and detect implausible jumps, NOT fake extrapolated RF fixes.
 function trackSampleDecision(previous,next){
  if(!previous)return {keep:true,reason:"first-received"};
  if(previous.hex!==next.hex||!point(previous)||!point(next)||
     !Number.isFinite(previous.capturedAtMs)||!Number.isFinite(next.capturedAtMs))
   return {keep:false,reason:"invalid-track"};
  const positionEpoch=fix=>Number.isFinite(fix.observationTimeMs)
   ?fix.observationTimeMs:
    fix.capturedAtMs-(Number.isFinite(fix.positionAgeSeconds)?fix.positionAgeSeconds:0)*1000;
  const previousT=positionEpoch(previous),nextT=positionEpoch(next);
  const dt=(nextT-previousT)/1000;
  if(!Number.isFinite(dt)||dt<=0)return {keep:false,reason:"non-monotonic"};
  const traveledKm=distanceKm(previous,next);
  const speeds=[previous.speedKt,next.speedKt].filter(x=>Number.isFinite(x)&&x>=0&&x<=1300);
  const fastestKmH=speeds.length?Math.max(...speeds)*1.852:1300;
  // Slack permits ordinary reporting jitter, changing headings and lost messages.
  if(traveledKm>Math.max(1300,fastestKmH*1.8)*dt/3600+5)
   return {keep:false,reason:"implausible-rf-jump"};
  const turning=Number.isFinite(previous.headingDeg)&&Number.isFinite(next.headingDeg)
   ?Math.abs(((next.headingDeg-previous.headingDeg+540)%360)-180)>=25:false;
  // Approx. 40 seconds' motion, bounded 5–20 km. More turns improve
  // geometric variety, so sample those at the 5 km threshold.
  const spacingKm=turning?5:Math.max(5,Math.min(20,fastestKmH*40/3600));
  return {keep:traveledKm>=spacingKm,
   reason:traveledKm>=spacingKm?"new-path-constraint":"redundant-rf-position",
   traveledKm,elapsedSeconds:dt,spacingKm};
 }
 function groupAircraftCircles(records){
  const groups=new Map();
  for(const record of records){
   let group=groups.get(record.hex);
   if(!group){group={hex:record.hex,flight:record.flight,
    samples:0,circle:record};groups.set(record.hex,group);}
   group.samples++;
  }
  return [...groups.values()].map(g=>({...g,latestAgeSeconds:g.circle.ageSeconds}));
 }
 function compute(aircraft,history=[]){
  const records=[],seen=new Set(),now=Date.now();
  for(const a of Array.isArray(aircraft)?aircraft:[]){
   if(!eligible(a) || seen.has(a.hex.toLowerCase()))continue;
   const rf=a.observations.antenna;
   const altitudeFeet=rf.alt_geom??rf.alt_baro??a.alt_geom??a.alt_baro;
   const radiusKm=horizonKm(altitudeFeet==="ground"?0:altitudeFeet);
   if(radiusKm===null)continue;
   records.push({hex:a.hex.toLowerCase(),flight:String(a.flight||a.hex).trim(),
    lat:rf.lat,lon:rf.lon,radiusKm,altitudeFeet,
    ageSeconds:Math.max(a.seen_pos,rf.seen_pos),
    observationTimeMs:now-rf.seen_pos*1000});
   seen.add(a.hex.toLowerCase());
  }
  const liveCount=records.length;
  // Optional fixed-receiver session history, gathered only after eligible().
  // Drop observations older than two hours, cap model inputs and keep their
  // historical status separate from the current aircraft map.
  for(const old of Array.isArray(history)?history.slice(-64):[]){
   if(!old||old.recorded_rf!==true||
      !/^[a-f0-9]{6}$/i.test(String(old.hex||""))||
      !point(old)||!Number.isFinite(old.radiusKm)||
      old.radiusKm<10||old.radiusKm>1600||
      !Number.isFinite(old.capturedAtMs)||
      old.capturedAtMs>now+5000||now-old.capturedAtMs>2*3600*1000)continue;
   // A single aircraft may yield several genuine geographic constraints
   // along its flight path; it still counts as only ONE independent aircraft.
   const hex=old.hex.toLowerCase();
   if(records.some(r=>r.hex===hex&&distanceKm(r,old)<8))continue;
   records.push({...old,hex,ageSeconds:(now-old.capturedAtMs)/1000,
    historic:true});
   seen.add(hex);
  }
  records.sort((a,b)=>a.ageSeconds-b.ageSeconds);
  const aircraftCircles=groupAircraftCircles(records);
  if(seen.size<MIN_INDEPENDENT)return {status:"insufficient",count:seen.size,
   liveCount,historyCount:seen.size-liveCount,required:MIN_INDEPENDENT,circles:[],aircraftCircles,region:null};
  // Bound workload: use up to 64 recent *positions* from at least four
  // independent aircraft. Multiple positions from ONE plane do not satisfy
  // the minimum. Only three circles are drawn as optional outlines.
  // First preserve one latest real observation from every independent ICAO.
  // Then add the remaining speed-spaced path samples. A busy aircraft
  // must not crowd out other received airplanes from the 64-cell solver.
  const heads=[],extras=[],usedHeads=new Set();
  for(const record of records){
   if(!usedHeads.has(record.hex)){heads.push(record);usedHeads.add(record.hex);}
   else extras.push(record);
  }
  const constraints=heads.concat(extras).slice(0,64);
  const circles=constraints.slice(0,6); // for diagnostics; UI draws only 3 optional outlines
  // The grid must NOT be anchored on the last/first airplane; use a
  // permutation-independent circular mean of ALL distinct RF aircraft.
  // Grid acceptance tests EVERY independent aircraft + RF history fix.
  const longitudeNear=(lon,anchor)=>anchor+((lon-anchor+540)%360)-180;
  const independent=heads;
  const sumSin=independent.reduce((n,p)=>n+Math.sin(p.lon*RAD),0);
  const sumCos=independent.reduce((n,p)=>n+Math.cos(p.lon*RAD),0);
  const originLon=Math.atan2(sumSin,sumCos)/RAD;
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
   status:"no_overlap",count:seen.size,liveCount,historyCount:seen.size-liveCount,
   required:MIN_INDEPENDENT,constraintsUsed:constraints.length,circles,aircraftCircles,region:null};
  const points=[];
  const STEPS=80; // finer grid reduces model-centroid quantization jitter
  for(let i=0;i<=STEPS;i++)for(let j=0;j<=STEPS;j++){
   const lat=minLat+(maxLat-minLat)*i/STEPS;
   const unwrappedLon=minLon+(maxLon-minLon)*j/STEPS;
   const p={lat,lon:((unwrappedLon+540)%360)-180};
   if(constraints.every(c=>distanceKm(p,c)<=c.radiusKm))points.push(p);
  }
  // A vanishingly small sampled overlap is not a safe coordinate estimate.
  if(points.length<3)return {status:"unresolved",count:seen.size,liveCount,historyCount:seen.size-liveCount,
   required:MIN_INDEPENDENT,constraintsUsed:constraints.length,circles,aircraftCircles,region:null};
  // Latitude/longitude grid cells have different physical areas. Correct
  // their centroid by cos(latitude); no single plane dictates the origin.
  const weighted=points.map(p=>({p,w:Math.max(.001,Math.cos(p.lat*RAD))}));
  const areaWeight=weighted.reduce((sum,v)=>sum+v.w,0);
  const centerLat=weighted.reduce((sum,v)=>sum+v.p.lat*v.w,0)/areaWeight;
  const centerUnwrappedLon=weighted.reduce((sum,v)=>
   sum+longitudeNear(v.p.lon,originLon)*v.w,0)/areaWeight;
  const center={lat:centerLat,lon:((centerUnwrappedLon+540)%360)-180};
  const extentKm=Math.max(...points.map(p=>distanceKm(center,p)));
  const aircraftDistances=independent.map(c=>({
   hex:c.hex,flight:c.flight,
   centerDistanceKm:Math.round(distanceKm(center,c)),
   horizonKm:Math.round(c.radiusKm),
   sampleCount:aircraftCircles.find(item=>item.hex===c.hex)?.samples||1
  })).sort((a,b)=>a.hex.localeCompare(b.hex));
  // This is NOT a confidence level. Even four planes can yield a very
  // broad intersection and a misleading numeric center.
  const geometryStatus=extentKm>250?"broad":extentKm>100?"coarse":"bounded-model";
  return {status:"region",count:seen.size,liveCount,historyCount:seen.size-liveCount,
   geometryStatus,aircraftDistances,
   required:MIN_INDEPENDENT,constraintsUsed:constraints.length,circles,aircraftCircles,
   region:{...center,extentKm:Math.max(10,Math.ceil(extentKm/10)*10),
    sampleCount:points.length,possibleSamples:points,
    kind:"possible-area-centroid",accuracyMeters:null,confidence:null}};
 }
 // Conditional distance envelope from *modeled* feasible receiver cells.
 // Never a measured ToA/RSSI distance; sampled grid approximates this envelope.
 function modelDistanceInterval(result,a){
  if(result?.status!=="region"||!eligible(a))return null;
  const samples=result.region?.possibleSamples;
  if(!Array.isArray(samples)||samples.length<3)return null;
  const p=a.observations.antenna;
  let minKm=Infinity,maxKm=-Infinity;
  for(const sample of samples){
   if(!point(sample))continue;
   const km=distanceKm(sample,p);
   minKm=Math.min(minKm,km);maxKm=Math.max(maxKm,km);
  }
  if(!Number.isFinite(minKm)||!Number.isFinite(maxKm))return null;
  return {minKm:Math.max(0,Math.floor(minKm/10)*10),
   maxKm:Math.ceil(maxKm/10)*10,
   kind:"model-grid-distance-interval",measured:false};
 }
 return {point,distanceKm,horizonKm,horizonPoints,eligible,recordedCircle,
  trackSampleDecision,groupAircraftCircles,compute,modelDistanceInterval,MIN_INDEPENDENT};
})();
if(typeof module!=="undefined"&&module.exports)module.exports=TihuluRFCoverage;
if(typeof window!=="undefined")window.TihuluRFCoverage=TihuluRFCoverage;
