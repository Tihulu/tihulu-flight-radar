"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const path=require("node:path");
const motion=require(path.join(__dirname,"../tihulu_flight_radar/web/map_motion.js"));
function plane(){return {hex:"a00001",lat:50,lon:7,seen_pos:1,gs:450,track:90,position_source:"antenna"};}
test("Smooth map motion projects only the display and never edits the ADS-B source",()=>{
 const original=plane(),snapshot=JSON.stringify(original);
 const p=motion.displayedPosition(original,100000,105000);
 assert.equal(p.projected,true);
 assert.ok(p.lon>original.lon);
 assert.ok(Math.abs(p.lat-original.lat)<.0005);
 assert.equal(JSON.stringify(original),snapshot);
 assert.equal(original.position_source,"antenna");
});
test("No fabrication if speed or heading is unknown or invalid",()=>{
 const p=plane();
 delete p.gs;
 assert.deepEqual(motion.displayedPosition(p,100000,105000),
  {lat:50,lon:7,projected:false,ageSeconds:1});
 p.gs=450;delete p.track;
 assert.equal(motion.displayedPosition(p,100000,105000).projected,false);
});
test("Twenty-second prediction window and no motion in offline/stale gaps",()=>{
 const p=plane();
 assert.equal(motion.displayedPosition(p,100000,121000).projected,false);
 assert.equal(motion.displayedPosition(p,100000,100000-1).projected,false);
 assert.equal(motion.displayedPosition({...p,seen_pos:60},100000,100100).projected,false);
});
test("Invalid coordinates never produce a display projection",()=>{
 assert.equal(motion.displayedPosition({...plane(),lat:100},100000,105000),null);
 assert.equal(motion.displayedPosition({...plane(),lon:NaN},100000,105000),null);
});
