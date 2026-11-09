"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const root=path.join(__dirname,"../tihulu_flight_radar/web");
const model=require(path.join(root,"receiver_coverage.js"));
const read=name=>fs.readFileSync(path.join(root,name),"utf8");
function plane(hex,lat,lon){
 const a={hex,lat,lon,seen:1,seen_pos:1,alt_baro:30000,gs:480,track:90,
  position_source:"antenna",sources:["antenna"]};
 a.observations={antenna:{...a}};
 return a;
}
test("Recorded RF samples preserve speed/course but never create projected constraints",()=>{
 const record=model.recordedCircle(plane("a00001",50,7),100000);
 assert.equal(record.speedKt,480);
 assert.equal(record.headingDeg,90);
 assert.equal(record.lat,50);
 assert.equal(record.lon,7);
 assert.equal(record.recorded_rf,true);
 assert.equal(Object.hasOwn(record,"projected"),false);
});
test("Speed-adaptive sampler rejects duplicates, invalid chronology and impossible jumps",()=>{
 const a={...model.recordedCircle(plane("a00001",50,7),100000),positionAgeSeconds:1};
 const near={...a,lon:7.012,capturedAtMs:150000,observationTimeMs:149000};
 const next={...a,lon:7.15,capturedAtMs:150000,observationTimeMs:149000};
 assert.equal(model.trackSampleDecision(null,a).keep,true);
 assert.equal(model.trackSampleDecision(a,near).keep,false);
 assert.equal(model.trackSampleDecision(a,next).keep,true);
 assert.equal(model.trackSampleDecision(a,{...next,capturedAtMs:90000,observationTimeMs:89000}).reason,"non-monotonic");
 assert.equal(model.trackSampleDecision(a,{...next,lon:16,capturedAtMs:105000,observationTimeMs:104000}).reason,"implausible-rf-jump");
});
test("Independent aircraft count is not inflated by along-track samples",()=>{
 const rows=[plane("a00001",50.7,6.7),plane("a00002",50.2,7.5),
  plane("a00003",51.1,6.2),plane("a00004",50.6,7.9)];
 const initial=model.compute(rows.slice(0,3));
 assert.equal(initial.status,"insufficient");
 assert.equal(initial.aircraftCircles.length,3);
 const rec=model.recordedCircle(rows[0]);
 const past={...rec,lon:rec.lon+.26,capturedAtMs:Date.now()-45000};
 const result=model.compute(rows,[past]);
 assert.equal(result.count,4);
 assert.equal(result.status,"region");
 assert.equal(result.aircraftCircles.length,4);
 assert.equal(result.aircraftCircles.find(x=>x.hex==="a00001").samples,2);
 assert.equal(result.region.confidence,null);
 assert.equal(result.region.accuracyMeters,null);
});
test("RF model visuals expose independent live-follow and per-aircraft toggles",()=>{
 const html=read("index.html"),js=read("app.js"),css=read("style.css");
 for(const id of ["rfFollow","rfFill","rfHatch","rfModelCircle","rfModelPin",
  "rfAircraftLayers","rfAllPlanes","rfNoPlanes","rfProgress"]){
  assert.match(html,new RegExp('id="'+id+'"'));
 }
 assert.match(js,/function disableRfFollow\(\)/);
 assert.match(js,/function rfFeasibleHull\(result\)/);
 assert.match(js,/function rfDrawRing\(ring,color/);
 assert.match(js,/rfSelectedPlanes\.has\(item\.hex\)/);
 assert.match(js,/function rfPlaneColor\(hex\)/);
 assert.match(js,/rfLastFollowModel===result/);
 assert.match(js,/ctx\.clip\(\)/);
 assert.match(css,/\.rf-aircraft-layer/);
 assert.match(html,/NOT a statistical accuracy\/error circle/);
 assert.doesNotMatch(read("receiver_coverage.js"),/navigator\.geolocation|\bfetch\s*\(/);
});

test("RF camera follows new model revisions and keeps zoom after first focus",()=>{
 const js=read("app.js");
 const source=js.match(/function focusRfModelWhenReady\(result\)\{[\s\S]*?\n\}/)?.[0];
 assert.ok(source,"RF focus function exists");
 const state={lat:50,lon:7,zoom:9,moved:false,autoFocused:false,centerLabel:""};
 const first={status:"region",region:{lat:50.9,lon:7.2,extentKm:120}};
 const second={status:"region",region:{lat:51.1,lon:7.8,extentKm:70}};
 const ctx={state,first,second,Math};
 vm.runInNewContext([
  "let rfLocatorActive=true,rfLocatorFocused=false,rfFollowCenter=true,rfLastFollowModel=null,rfUserZoomed=false;",
  source,
  "focusRfModelWhenReady(first);",
  "const oldZoom=state.zoom;",
  "focusRfModelWhenReady(second);",
  "if(state.zoom!==oldZoom)throw Error('follow unexpectedly changed zoom');"
 ].join("\n"),ctx);
 assert.equal(state.lat,second.region.lat);
 assert.equal(state.lon,second.region.lon);
 assert.match(state.centerLabel,/NOT GPS/);
});

test("Mixed Internet metadata never supplies a missing local RF speed",()=>{
 const a=plane("a00011",50,7);
 delete a.observations.antenna.gs;
 delete a.observations.antenna.track;
 a.sources.push("internet");
 a.gs=999;a.track=180;
 const item=model.recordedCircle(a);
 assert.equal(item.speedKt,null);
 assert.equal(item.headingDeg,null);
});
test("Solver still uses distinct aircraft after high-density one-aircraft track history",()=>{
 const rows=[plane("a00001",50.7,6.7),plane("a00002",50.2,7.5),
  plane("a00003",51.1,6.2),plane("a00004",50.6,7.9)];
 const base=model.recordedCircle(rows[0]);
 const history=Array.from({length:60},(_,i)=>({
  ...base,lat:base.lat+.001*i,lon:base.lon+.26+.02*i,
  capturedAtMs:Date.now()-(i+1)*25000
 }));
 const out=model.compute(rows,history);
 assert.equal(out.status,"region");
 assert.equal(out.count,4);
 assert.equal(out.constraintsUsed<=64,true);
 assert.equal(out.aircraftCircles.length,4);
});

test("Plus/minus and wheel zoom preserve four-aircraft RF follow and user scale",()=>{
 const js=read("app.js");
 const zoomSource=js.match(/function adjustMapZoom\(delta\)\{[\s\S]*?\n\}/)?.[0];
 const focusSource=js.match(/function focusRfModelWhenReady\(result\)\{[\s\S]*?\n\}/)?.[0];
 assert.ok(zoomSource&&focusSource);
 const state={lat:50,lon:7,zoom:6,moved:false,autoFocused:false,centerLabel:""};
 const first={status:"region",region:{lat:50.9,lon:7.2,extentKm:350}};
 const second={status:"region",region:{lat:51.1,lon:7.8,extentKm:290}};
 const ctx={state,first,second,Math,paint:()=>{}};
 const result=vm.runInNewContext([
  "let rfLocatorActive=true,rfLocatorFocused=false,rfFollowCenter=true,rfLastFollowModel=null,rfUserZoomed=false;",
  zoomSource,focusSource,
  "focusRfModelWhenReady(first);",
  "const fitZoom=state.zoom;",
  "adjustMapZoom(1);",
  "adjustMapZoom(1);",
  "const selectedZoom=state.zoom;",
  "focusRfModelWhenReady(second);",
  "({fitZoom,selectedZoom,afterZoom:state.zoom,following:rfFollowCenter,",
  "  lat:state.lat,lon:state.lon,zoomUserAdjusted:rfUserZoomed})"
 ].join("\n"),ctx);
 assert.equal(result.selectedZoom,result.fitZoom+2);
 assert.equal(result.afterZoom,result.selectedZoom);
 assert.equal(result.following,true);
 assert.equal(result.zoomUserAdjusted,true);
 assert.equal(result.lat,second.region.lat);
 assert.equal(result.lon,second.region.lon);
 assert.match(js,/\$\("zoomIn"\)\.onclick=\(\)=>adjustMapZoom\(1\)/);
 assert.match(js,/\$\("zoomOut"\)\.onclick=\(\)=>adjustMapZoom\(-1\)/);
 assert.match(js,/canvas\.addEventListener\("wheel",e=>\{\s*e\.preventDefault\(\);\s*adjustMapZoom/);
 const wheel=js.match(/canvas\.addEventListener\("wheel",e=>\{[\s\S]*?\},\{passive:false\}\);/)?.[0];
 assert.ok(wheel);
 assert.doesNotMatch(wheel,/disableRfFollow/);
});
test("Zoom set before first four-aircraft model remains selected on initial RF focus",()=>{
 const js=read("app.js");
 const zoomSource=js.match(/function adjustMapZoom\(delta\)\{[\s\S]*?\n\}/)?.[0];
 const focusSource=js.match(/function focusRfModelWhenReady\(result\)\{[\s\S]*?\n\}/)?.[0];
 assert.ok(zoomSource&&focusSource);
 const state={lat:50,lon:7,zoom:7,moved:false,autoFocused:false,centerLabel:""};
 const first={status:"region",region:{lat:50.9,lon:7.2,extentKm:350}};
 const ctx={state,first,Math,paint:()=>{}};
 const r=vm.runInNewContext([
  "let rfLocatorActive=true,rfLocatorFocused=false,rfFollowCenter=true,rfLastFollowModel=null,rfUserZoomed=false;",
  zoomSource,focusSource,
  "adjustMapZoom(1);",
  "const chosen=state.zoom;",
  "focusRfModelWhenReady(first);",
  "({chosen,zoom:state.zoom,lat:state.lat,lon:state.lon,rfFollowCenter})"
 ].join("\n"),ctx);
 assert.equal(r.zoom,r.chosen);
 assert.equal(r.rfFollowCenter,true);
 assert.equal(r.lat,first.region.lat);
 assert.equal(r.lon,first.region.lon);
});

test("Gaussian horizon PSF is an assumed radial edge shape, not a calibrated distance",()=>{
 const R=330,sigma=20;
 const band=model.gaussianHorizonBand(R,sigma);
 assert.equal(band.innerKm,310);
 assert.equal(band.outerKm,350);
 assert.equal(band.sigmaKm,20);
 assert.equal(band.calibrated,false);
 assert.equal(band.measuredRange,false);
 assert.equal(band.credibleInterval,false);
 assert.equal(model.gaussianHorizonPsf(R,sigma,R),1);
 assert.ok(Math.abs(model.gaussianHorizonPsf(R,sigma,R+sigma)-Math.exp(-.5))<1e-12);
 assert.ok(Math.abs(model.gaussianHorizonPsf(R,sigma,R-sigma)-Math.exp(-.5))<1e-12);
 assert.equal(model.gaussianHorizonPsf(R,0,R),null);
 assert.equal(model.gaussianHorizonBand(330,-1),null);
 const normal=model.compute([plane("a00001",50.7,6.7),
  plane("a00002",50.2,7.5),plane("a00003",51.1,6.2),plane("a00004",50.6,7.9)]);
 assert.equal(normal.status,"region");
 assert.equal(normal.region.accuracyMeters,null);
 assert.equal(normal.region.confidence,null);
 assert.ok(normal.region.rawExtentKm<=normal.region.extentKm);
});
test("Gaussian 1-sigma option uses individual radio-plane toggles; pointer jitter does not uncheck RF following",()=>{
 const html=read("index.html"),js=read("app.js");
 assert.match(html,/id="rfGaussianBand"/);
 assert.match(html,/id="rfSigmaKm"/);
 assert.match(html,/Assumed σ \(km\)/);
 assert.match(html,/NOT measured accuracy/);
 assert.match(js,/function rfDrawGaussianBand\(ring,color,sigmaKm\)/);
 assert.match(js,/gaussianHorizonPsf\(ring\.radiusKm,sigmaKm,middle\)/);
 assert.match(js,/ctx\.fill\("evenodd"\)/);
 assert.match(js,/if\(\$\("rfGaussianBand"\)\.checked\)/);
 assert.match(js,/rfSelectedPlanes\.has\(item\.hex\)/);
 assert.match(js,/rfAutoSelectNewPlanes=mode==="all"/);
 assert.match(js,/if\(!p\[4\]&&Math\.hypot\(e\.clientX-p\[0\],e\.clientY-p\[1\]\)<7\)return/);
 const wheel=js.slice(js.indexOf('canvas.addEventListener("wheel"'),js.indexOf('// Provider selection',js.indexOf('canvas.addEventListener("wheel"')));
 assert.doesNotMatch(wheel,/disableRfFollow/);
});
test("Best session RF model updates at the unrounded spread and is independent of zoom",()=>{
 const js=read("app.js");
 const source=js.match(/function updateRfBest\(result,nowMs=Date\.now\(\)\)\{[\s\S]*?\n\}/)?.[0];
 assert.ok(source,"RF best update helper exists");
 const run=vm.runInNewContext([
  "let rfBest=null,rfBestComparedModel=null,rfBestImprovedThisUpdate=false;",
  source,
  'const first={status:"region",count:4,constraintsUsed:4,region:{lat:50.9,lon:7.1,rawExtentKm:110.8,extentKm:120}};',
  'const tighter={status:"region",count:5,constraintsUsed:6,region:{lat:50.91,lon:7.13,rawExtentKm:109.7,extentKm:110}};',
  'const worse={status:"region",count:6,constraintsUsed:8,region:{lat:50.92,lon:7.2,rawExtentKm:130.2,extentKm:140}};',
  'const one=updateRfBest(first,10000);',
  'const repeated=updateRfBest(first,11000);',
  'const two=updateRfBest(tighter,12000);',
  'const three=updateRfBest(worse,13000);',
  '({one,repeated,two,three,best:rfBest})'
 ].join("\n"));
 assert.equal(run.one,true);
 assert.equal(run.repeated,false);
 assert.equal(run.two,true);
 assert.equal(run.three,false);
 assert.equal(run.best.rawExtentKm,109.7);
 assert.equal(run.best.aircraftCount,5);
 assert.equal(run.best.updatedAtMs,12000);
 assert.match(js,/rfBestPin/);
 assert.match(js,/CURRENT MODEL spread/);
 assert.match(js,/BEST SESSION spread/);
 assert.match(js,/rfUserZoomed=true/);
});

test("Live and best RF model centers display geographic coordinates and update on new RF revisions",()=>{
 const js=read("app.js"),html=read("index.html"),css=read("style.css");
 for(const id of ["rfMapCoordinates","rfCoordinateReadout","rfCurrentCoordinates","rfBestCoordinates"])
  assert.match(html,new RegExp('id="'+id+'"'));
 const format=js.match(/function rfCoordinateText\(point\)\{[\s\S]*?\n\}/)?.[0];
 const render=js.match(/function renderRfCoordinateReadouts\(result\)\{[\s\S]*?\n\}/)?.[0];
 assert.ok(format&&render);
 const values=vm.runInNewContext([
  "const els={rfCurrentCoordinates:{textContent:''},rfBestCoordinates:{textContent:''},rfMapCoordinates:{textContent:''}};",
  "const $=id=>els[id];",
  "let rfBest=null,rfLocatorActive=true;",
  format,render,
  "const before=rfCoordinateText({lat:-4.5,lon:-74.2});",
  "renderRfCoordinateReadouts({status:'insufficient',count:2});",
  "const empty=els.rfMapCoordinates.textContent;",
  "const first={status:'region',count:4,region:{lat:50.938,lon:6.9601}};",
  "renderRfCoordinateReadouts(first);",
  "const initial=els.rfCurrentCoordinates.textContent;",
  "rfBest={lat:50.9421,lon:6.97201};",
  "renderRfCoordinateReadouts({status:'region',count:5,region:{lat:50.94322,lon:6.98111}});",
  "const live=els.rfCurrentCoordinates.textContent;",
  "const best=els.rfBestCoordinates.textContent;",
  "const footer=els.rfMapCoordinates.textContent;",
  "renderRfCoordinateReadouts({status:'insufficient',count:1});",
  "({before,empty,initial,live,best,footer,unavailable:els.rfCurrentCoordinates.textContent,retained:els.rfBestCoordinates.textContent})"
 ].join("\n"));
 assert.equal(values.before,"4.50000° S, 74.20000° W");
 assert.match(values.empty,/unavailable/);
 assert.match(values.initial,/50\.93800° N, 6\.96010° E/);
 assert.match(values.live,/50\.94322° N, 6\.98111° E/);
 assert.match(values.best,/50\.94210° N, 6\.97201° E/);
 assert.match(values.footer,/RF LIVE .* BEST .*NOT GPS/);
 assert.match(values.unavailable,/unavailable/);
 assert.match(values.retained,/50\.94210° N, 6\.97201° E/);
 assert.match(js,/paintRfMapLabel\("live"/);
 assert.match(js,/paintRfMapLabel\("best"/);
 assert.match(js,/\$\("rfPopupCoordinates"\)\.textContent=rfCoordinateText\(model\)/);
 assert.match(css,/\.rf-coordinate-readout/);
 assert.match(css,/\.rf-map-coordinates/);
});
