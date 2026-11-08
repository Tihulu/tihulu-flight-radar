"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const root=path.join(__dirname,"../tihulu_flight_radar/web");
const rf=require(path.join(root,"receiver_coverage.js"));
const js=fs.readFileSync(path.join(root,"app.js"),"utf8");
function plane(hex,lat,lon,source="antenna"){
 const a={hex,lat,lon,alt_baro:30000,seen:1,seen_pos:1,
  sources:[source],position_source:source,gs:460,track:90};
 a.observations={[source]:{...a}};
 return a;
}
const four=()=>[
 plane("a10101",51.2,7.0),
 plane("a10102",49.8,7.0),
 plane("a10103",50.5,6.0),
 plane("a10104",50.5,8.0)
];
test("A 4-aircraft RF center is not the last airplane or a one-airplane position",()=>{
 const all=four(),r=rf.compute(all);
 assert.equal(r.status,"region");
 assert.equal(r.count,4);
 assert.equal(r.aircraftDistances.length,4);
 assert.equal(r.constraintsUsed,4);
 for(const p of all)
  assert.ok(rf.distanceKm(r.region,p)>30,"not a fake single-plane center");
 assert.ok(rf.distanceKm(r.region,{lat:50.5,lon:7})<20);
 assert.equal(r.geometryStatus===undefined,false);
 assert.equal(r.region.accuracyMeters,null);
 assert.equal(r.region.confidence,null);
 assert.equal(rf.compute([all[3]]).status,"insufficient");
});
test("RF feasibility centroid is order-independent and ignores online airplanes",()=>{
 const all=four(),r=rf.compute(all);
 const reversed=rf.compute(all.slice().reverse());
 const rotated=rf.compute([all[2],all[0],all[3],all[1]]);
 assert.equal(r.status,"region");
 assert.equal(reversed.status,"region");
 assert.ok(rf.distanceKm(r.region,reversed.region)<1.5);
 assert.ok(rf.distanceKm(r.region,rotated.region)<1.5);
 const internet=plane("a20202",50.5,7.5,"internet");
 const mixed=rf.compute([...all,internet]);
 assert.ok(rf.distanceKm(r.region,mixed.region)<1.5);
 assert.equal(mixed.count,4);
});
test("RF observation age gives only approximate trajectory epoch, never ToF",()=>{
 const a=four()[0];a.observations.antenna.seen_pos=2.5;
 const snapshotMs=1710000000000;
 const fix=rf.recordedCircle(a,snapshotMs);
 assert.equal(fix.observationTimeMs,snapshotMs-2500);
 assert.equal(fix.lat,a.lat);
 assert.equal(fix.lon,a.lon);
 assert.equal(Object.hasOwn(fix,"propagationDelayMs"),false);
 assert.equal(Object.hasOwn(fix,"receiverGPS"),false);
});
test("Startup, airplane selection and receiver-model follow are distinct",()=>{
 assert.match(js,/Map startup is NEVER a one-plane RF receiver site estimate/);
 assert.match(js,/return \{lat:COLOGNE\.lat,lon:COLOGNE\.lon,zoom:9,rank:1,source:"cologne"\}/);
 assert.match(js,/let rfFollowCenter=true/);
 assert.match(js,/tr\.onclick=\(\)=>choose\(a,\{center:!rfFollowCenter\}\)/);
 assert.match(js,/MULTI-AIRCRAFT RF MODEL/);
 assert.match(js,/independent aircraft \/ /);
});
