"use strict";
/* Five RF geolocation model modes. Radio-horizon circles are geometric UPPER
 * BOUNDS, never measured range, GPS positions or statistical accuracy.
 * Every accepted record is examined; no 64-sample solver truncation.
 * Functions are pure and work in Web Workers, Node and Qt WebEngine.
 */
const TihuluRFHistoryModels=(()=>{
 const EARTH=6371.0088,DEG=Math.PI/180,MIN=4;
 const MODES=Object.freeze(["live10","liveX","best","history","historyBest"]);
 function valid(r){
  return r?.recorded_rf===true && /^[0-9a-f]{6}$/i.test(String(r.hex||""))&&
   Number.isFinite(r.lat)&&Math.abs(r.lat)<=85&&
   Number.isFinite(r.lon)&&Math.abs(r.lon)<=180&&
   Number.isFinite(r.radiusKm)&&r.radiusKm>=10&&r.radiusKm<=1600&&
   Number.isFinite(r.capturedAtMs)&&r.capturedAtMs>0;
 }
 function lonNear(lon,base){return base+((lon-base+540)%360)-180;}
 function km(a,b){
  const dp=(b.lat-a.lat)*DEG,dl=(b.lon-a.lon)*DEG;
  const q=Math.sin(dp/2)**2+Math.cos(a.lat*DEG)*Math.cos(b.lat*DEG)*Math.sin(dl/2)**2;
  return 2*EARTH*Math.asin(Math.min(1,Math.sqrt(Math.max(0,q))));
 }
 function filter(records,{mode="history",hours=2,nowMs=Date.now()}={}){
  const cutoff=mode==="live10"?nowMs-600000:
   mode==="liveX"?nowMs-Math.max(1,Math.min(48,Number(hours)||2))*3600000:-Infinity;
  return (Array.isArray(records)?records:[]).filter(r=>
   valid(r)&&r.capturedAtMs>=cutoff&&r.capturedAtMs<=nowMs+5000);
 }
 function empty(status,rows,extra={}){
  const identities=new Set(rows.map(x=>x.hex.toLowerCase()));
  return {status,count:identities.size,liveCount:0,historyCount:identities.size,
   constraintsUsed:rows.length,required:MIN,circles:[],aircraftCircles:[],
   region:null,accuracyMeters:null,confidence:null,...extra};
 }
 function hard(records,opt={}){
  const rows=filter(records,opt),identities=new Set(rows.map(r=>r.hex.toLowerCase()));
  if(identities.size<MIN)return empty("insufficient",rows);
  // Broad and safe geodetic bounding boxes; all records constrain these bounds.
  // One epoch's longitude (not arbitrary first-array order) is the anchor.
  const anchor=rows.reduce((prev,r)=>r.capturedAtMs>prev.capturedAtMs?r:prev,rows[0]).lon;
  let minLat=-85,maxLat=85,minLon=anchor-180,maxLon=anchor+180;
  let n=0;
  for(const r of rows){
   const spread=r.radiusKm/110.5;
   const edge=Math.min(84.9,Math.abs(r.lat)+spread);
   const dlon=r.radiusKm/(111.2*Math.max(.05,Math.cos(edge*DEG)));
   const x=lonNear(r.lon,anchor);
   minLat=Math.max(minLat,r.lat-spread);
   maxLat=Math.min(maxLat,r.lat+spread);
   minLon=Math.max(minLon,x-dlon);
   maxLon=Math.min(maxLon,x+dlon);
   n++;
   if(n%5000===0)opt.onProgress?.({phase:"bounds",processed:n,total:rows.length});
  }
  if(minLat>=maxLat||minLon>=maxLon)return empty("no_overlap",rows,{reason:"No common geographic bounds"});
  // 81×81 candidate grid, pruned against EVERY stored RF circle. Processing
  // a 5k batch does not discard remaining records. Grid is an approximation.
  const STEPS=80,alive=[];
  for(let i=0;i<=STEPS;i++)for(let j=0;j<=STEPS;j++)
   alive.push({lat:minLat+(maxLat-minLat)*i/STEPS,
    lon:((minLon+(maxLon-minLon)*j/STEPS+540)%360)-180});
  let remaining=alive;
  for(let k=0;k<rows.length;k++){
   const r=rows[k],next=[];
   for(const p of remaining)if(km(p,r)<=r.radiusKm+1e-7)next.push(p);
   remaining=next;
   if(k%5000===4999||k===rows.length-1)
    opt.onProgress?.({phase:"intersection",processed:k+1,total:rows.length,
     candidates:remaining.length});
   if(remaining.length===0)return empty("unresolved",rows,{
    reason:"No feasible sampled cells; area may be empty or below grid resolution",
    checkedConstraints:k+1});
  }
  if(remaining.length<3)return empty("unresolved",rows,{
   reason:"Fewer than three feasible grid cells"});
  let sw=0,slat=0,slon=0;
  for(const p of remaining){
   const w=Math.max(.001,Math.cos(p.lat*DEG));
   sw+=w;slat+=p.lat*w;slon+=lonNear(p.lon,anchor)*w;
  }
  const center={lat:slat/sw,lon:((slon/sw+540)%360)-180};
  const rawExtentKm=remaining.reduce((max,p)=>Math.max(max,km(center,p)),0);
  const colors=[],distinct=new Set();
  for(const r of rows){
   const hex=r.hex.toLowerCase();
   if(distinct.has(hex))continue;
   distinct.add(hex);
   if(colors.length<12)colors.push({hex,flight:r.flight||hex,samples:rows.filter(v=>v.hex.toLowerCase()===hex).length,
    circle:{lat:r.lat,lon:r.lon,radiusKm:r.radiusKm}});
  }
  return {status:"region",count:identities.size,liveCount:0,
   historyCount:identities.size,constraintsUsed:rows.length,required:MIN,
   geometryStatus:rawExtentKm>250?"broad":rawExtentKm>100?"coarse":"bounded-model",
   circles:[],aircraftCircles:colors,accuracyMeters:null,confidence:null,
   region:{...center,rawExtentKm,
    extentKm:Math.max(10,Math.ceil(rawExtentKm/10)*10),
    possibleSamples:remaining,sampleCount:remaining.length,
    kind:"historical-radio-horizon-intersection",accuracyMeters:null,confidence:null}};
 }
 function weighted(records,opt={}){
  const rows=filter(records,opt),ids=new Set(rows.map(r=>r.hex.toLowerCase()));
  if(ids.size<MIN)return empty("insufficient",rows);
  const perPlane=new Map();
  for(const r of rows){const key=r.hex.toLowerCase();perPlane.set(key,(perPlane.get(key)||0)+1);}
  // Weight smaller radio-horizon UPPER bounds more strongly, with ICAO-level
  // normalization so thousands of reports from one airplane cannot dominate.
  // This is a heuristic violation minimizer, NOT a likelihood or ranging model.
  const earthCenter={lat:rows.reduce((s,r)=>s+r.lat/rows.length,0),
   lon:Math.atan2(rows.reduce((s,r)=>s+Math.sin(r.lon*DEG),0),
    rows.reduce((s,r)=>s+Math.cos(r.lon*DEG),0))/DEG};
  const angularOrigin=earthCenter.lon;
  let x=0,y=0,wSum=0;
  const anchors=[];
  for(const r of rows){
   const xx=lonNear(r.lon,angularOrigin)*Math.cos(earthCenter.lat*DEG)*111.2;
   const yy=r.lat*110.5;
   const weight=Math.pow(180/Math.max(35,r.radiusKm),1.5)/perPlane.get(r.hex.toLowerCase());
   anchors.push({x:xx,y:yy,r:r.radiusKm,weight});
   x+=xx*weight;y+=yy*weight;wSum+=weight;
  }
  x/=wSum;y/=wSum;
  // Smooth convex hinge outside the allowed disc. Every record contributes
  // to each optimization pass (no newest-N truncation).
  let lastCost=Infinity;
  for(let pass=0;pass<45;pass++){
   let gx=0,gy=0,cost=0,violated=0;
   for(const a of anchors){
    const dx=x-a.x,dy=y-a.y,d=Math.hypot(dx,dy);
    const excess=Math.max(0,d-a.r);
    if(excess>0){violated++;cost+=a.weight*excess*excess;
     if(d>1e-8){gx+=2*a.weight*excess*dx/d;gy+=2*a.weight*excess*dy/d;}}
   }
   // A tie within the common feasible area is NOT localization evidence.
   if(cost<1e-6)break;
   const norm=Math.hypot(gx,gy);
   if(norm<1e-6)break;
   let step=Math.max(.1,Math.min(30,Math.sqrt(cost/wSum)*.5));
   let nextCost=Infinity,nx=x,ny=y;
   for(let tries=0;tries<12;tries++){
    nx=x-step*gx/norm;ny=y-step*gy/norm;nextCost=0;
    for(const a of anchors){
     const ex=Math.max(0,Math.hypot(nx-a.x,ny-a.y)-a.r);
     nextCost+=a.weight*ex*ex;
    }
    if(nextCost<=cost)break;
    step/=2;
   }
   if(nextCost>=cost||Math.abs(lastCost-nextCost)<1e-6)break;
   x=nx;y=ny;lastCost=nextCost;
   opt.onProgress?.({phase:"weighted",processed:Math.round((pass+1)/45*rows.length),
    total:rows.length,pass:pass+1});
  }
  const lat=y/110.5,lon=((x/(111.2*Math.cos(earthCenter.lat*DEG))+540)%360)-180;
  const location={lat,lon};
  let nFailed=0,sumSquared=0,maximumResidual=0;
  for(const r of rows){
   const e=Math.max(0,km(location,r)-r.radiusKm);
   if(e>0.1)nFailed++;
   maximumResidual=Math.max(maximumResidual,e);sumSquared+=e*e;
  }
  opt.onProgress?.({phase:"complete",processed:rows.length,total:rows.length});
  return {status:"weighted",count:ids.size,liveCount:0,historyCount:ids.size,
   constraintsUsed:rows.length,required:MIN,geometryStatus:"weighted-heuristic",
   violatedConstraints:nFailed,satisfiedConstraints:rows.length-nFailed,
   maxViolationKm:maximumResidual,rmsViolationKm:Math.sqrt(sumSquared/rows.length),
   circles:[],aircraftCircles:[],accuracyMeters:null,confidence:null,
   region:{lat,lon,extentKm:null,rawExtentKm:null,possibleSamples:[],
    kind:"weighted-soft-constraint-center",accuracyMeters:null,confidence:null},
   note:"Weighted minimizer of RF horizon-bound violations, NOT GPS accuracy or a feasible-area confidence circle."};
 }
 function solve(records,opt={}){
  return opt.mode==="historyBest"?weighted(records,opt):hard(records,opt);
 }
 return {MODES,valid,filter,hard,weighted,solve,km};
})();
if(typeof module!=="undefined"&&module.exports)module.exports=TihuluRFHistoryModels;
if(typeof self!=="undefined")self.TihuluRFHistoryModels=TihuluRFHistoryModels;
