"use strict";
const fs=require("node:fs");
const path=require("node:path");
const test=require("node:test");
const assert=require("node:assert/strict");
const vm=require("node:vm");

const root=path.join(__dirname,"..");
const js=fs.readFileSync(path.join(root,"tihulu_flight_radar/web/app.js"),"utf8");
function extract(name){
 const m=js.match(new RegExp("function "+name+"\\([^)]*\\)\\{[\\s\\S]*?\\n\\}"));
 if(!m)throw Error("missing "+name);
 return m[0];
}

test("Full tar1090 map starts near genuine local aircraft and retains other planes",()=>{
 const state={lat:50.9,lon:7.1,zoom:10,startupSource:"antenna",moved:false,data:[
  {hex:"3c1234",lat:50.9,lon:7.1,seen:1,seen_pos:1,sources:["antenna"],position_source:"antenna"},
  {hex:"abcdef",lat:36.2,lon:-100,seen:1,seen_pos:1,sources:["internet"]}
 ]};
 const sandbox={URL,state,visible:()=>true,isPositioned:a=>a.seen_pos<=60};
 const fn=vm.runInNewContext(extract("tarFocusURL")+"\ntarFocusURL",sandbox);
 const parsed=new URL(fn("http://127.0.0.1/tar1090/"));
 assert.equal(parsed.searchParams.get("icao"),"3c1234");
 assert.equal(parsed.searchParams.get("tihuluFocusLat"),"50.900000");
 assert.equal(parsed.searchParams.has("SiteLat"),false);
 assert.equal(parsed.searchParams.get("rangeRings"),"0");
 assert.equal(parsed.searchParams.get("tihuluFocusLon"),"7.100000");
 assert.equal(parsed.searchParams.has("SiteLon"),false);
 assert.equal(parsed.searchParams.has("centerReceiver"),false);
 assert.equal(parsed.searchParams.get("noIsolation"),"");
});

test("Tar1090 defaults Germany if no live aircraft, no imposed USA coordinates",()=>{
 const state={lat:50.938,lon:6.960,zoom:9,startupSource:"cologne",moved:false,data:[]};
 const sandbox={URL,state,visible:()=>true,isPositioned:()=>false};
 const fn=vm.runInNewContext(extract("tarFocusURL")+"\ntarFocusURL",sandbox);
 const p=new URL(fn("http://localhost:8504/?zoom=5&SiteLon=-98&SiteLat=37"));
 assert.equal(p.searchParams.get("tihuluFocusLat"),"50.938000");
 assert.equal(p.searchParams.has("SiteLat"),false);
 assert.equal(p.searchParams.get("tihuluFocusLon"),"6.960000");
 assert.equal(p.searchParams.has("SiteLon"),false);
 assert.equal(p.searchParams.get("zoom"),"9");
});

test("Pages PWA has standalone manifest, scoped worker and no aircraft API caching",()=>{
 const manifest=JSON.parse(fs.readFileSync(path.join(root,"tihulu_flight_radar/web/manifest.webmanifest"),"utf8"));
 const sw=fs.readFileSync(path.join(root,"tihulu_flight_radar/web/sw.js"),"utf8");
 assert.equal(manifest.display,"standalone");
 assert.equal(manifest.start_url,"./");
 assert.ok(!sw.includes("/api/aircraft"));
 assert.ok(!sw.includes("tile.openstreetmap.org"));
});

test("Embedded tar overlay uses OpenLayers source and exposes a source-specific toggle",()=>{
 const py=fs.readFileSync(path.join(root,"tihulu_flight_radar/tar_overlay.py"),"utf8");
 const m=py.match(/OVERLAY_JS = r"""([\s\S]*?)"""/);
 assert.ok(m,"tar JavaScript not present");
 assert.match(m[1],/ol\.layer\.Vector/);
 assert.match(m[1],/source:'internet'/);
 assert.match(m[1],/Show Internet aircraft overlay/);
 assert.match(py,/siteCircleLayer\.setVisible\(false\)/);
 assert.match(py,/locationDotLayer\.setVisible\(false\)/);
 new vm.Script(m[1]+"({aircraft:[],provider:'test'})");
});

test("Internet feed URL requires trusted HTTPS endpoint without keys in query",()=>{
 const fn=vm.runInNewContext(extract("getFeedURL")+"\ngetFeedURL",{URL});
 assert.equal(fn("https://feed.example/api/aircraft"),"https://feed.example/api/aircraft");
 assert.throws(()=>fn("http://feed.example/api/aircraft"),/HTTPS/);
 assert.throws(()=>fn("https://feed.example/api/aircraft?key=foo"),/without embedded keys/);
});


test("Auto focus respects the chosen Internet search region, not Germany center",()=>{
 const state={moved:false,autoFocused:false,zoom:7,
  queryLat:50.938,queryLon:6.96,lat:51.1657,lon:10.4515,
  data:[
   {hex:"123456",lat:50.95,lon:6.96,seen:2,seen_pos:2,sources:["internet"]},
   {hex:"abcdef",lat:51.1657,lon:10.4515,seen:2,seen_pos:2,sources:["internet"]}
  ]};
 let painted=0;
 const fn=vm.runInNewContext(extract("focusAir")+"\nfocusAir", {
  state,visible:()=>true,isPositioned:a=>a.seen_pos<=60,paint:()=>{painted++},
  GERMANY:{lat:51.1657,lon:10.4515},Math
 });
 fn(true);
 assert.equal(state.lat,50.95);
 assert.equal(state.lon,6.96);
 assert.equal(state.autoFocused,true);
 assert.ok(painted);
});

test("Camera movement cannot silently retarget the online API's search area",()=>{
 assert.match(js,/queryLat:initialCenter\.lat/);
 assert.match(js,/lat:state\.queryLat\.toFixed\(3\)/);
 assert.match(js,/lon:state\.queryLon\.toFixed\(3\)/);
 assert.match(js,/searchHere/);
 assert.match(js,/queryLat=state\.lat/);
 const html=fs.readFileSync(path.join(root,"tihulu_flight_radar/web/index.html"),"utf8");
 assert.match(html,/id="cologne"/);
 assert.match(html,/id="searchHere"/);
 assert.match(html,/id="sourceCredits"/);
});

test("Qt's tar1090 MainWorld script probes OpenLayers and hides receiver overlays",()=>{
 const py=fs.readFileSync(path.join(root,"tihulu_flight_radar/tar_overlay.py"),"utf8");
 const m=py.match(/MAP_CENTER_JS = r"""([\s\S]*?)"""/);
 assert.ok(m);
 const script=m[1];
 new vm.Script(script);
 let center=[-74,40],zoom=4;
 const layers=[];
 const view={getCenter:()=>center,setCenter:x=>{center=x},setZoom:z=>{zoom=z}};
 const ctx={
  URLSearchParams,location:{search:"?tihuluFocusLat=50.938&tihuluFocusLon=6.960&zoom=9"},
  window:{},OLMap:{getView:()=>view},ol:{proj:{fromLonLat:x=>x,toLonLat:x=>x}},
  siteCircleLayer:{setVisible:b=>layers.push(["circle",b])},
  locationDotLayer:{setVisible:b=>layers.push(["dot",b])},
 };
 const raw=vm.runInNewContext(script,ctx);
 assert.equal(typeof raw,"string","Qt needs a JSON-serializable primitive, not JS Object");
 const result=JSON.parse(raw);
 assert.equal(result.ready,true);
 assert.equal(result.lat,50.938);
 assert.equal(result.lon,6.960);
 assert.equal(zoom,9);
 assert.deepEqual(layers,[["circle",false],["dot",false]]);
 assert.equal(ctx.window.tihuluTarCameraApplied,true);
});


test("Tar1090 probe returns a JSON string even before OpenLayers is ready",()=>{
 const py=fs.readFileSync(path.join(root,"tihulu_flight_radar/tar_overlay.py"),"utf8");
 const m=py.match(/MAP_CENTER_JS = r"""([\s\S]*?)"""/);
 assert.ok(m);
 const result=vm.runInNewContext(m[1],{
  URLSearchParams, location:{search:""}, window:{}
 });
 const value=JSON.parse(result);
 assert.equal(value.ready,false);
 assert.match(value.reason,/OpenLayers/);
 assert.match(py,/isinstance\(value, str\)/);
 assert.match(py,/self\._initial_focus\(\)/);
 assert.match(py,/runJavaScript\(MAP_CENTER_JS, 0/);
});

test("Embedded tar Internet map overlays report OpenLayers drawing errors",()=>{
 const py=fs.readFileSync(path.join(root,"tihulu_flight_radar/tar_overlay.py"),"utf8");
 const m=py.match(/OVERLAY_JS = r"""([\s\S]*?)"""/);
 assert.ok(m);
 assert.match(py,/def _overlay_result\(self, value\)/);
 assert.match(py,/JSON\.stringify\(/);
 assert.match(m[1],/Internet aircraft \(blue\)/);
});


test("Startup priority: consented location, then nearest genuine radio plane, then Cologne",()=>{
 const COLOGNE={lat:50.938,lon:6.960};
 const choose=vm.runInNewContext(extract("chooseStartupTarget")+"\nchooseStartupTarget",{COLOGNE,Math,Number,Array});
 const radioFar={hex:"123456",lat:51.9,lon:9.8,seen:2,seen_pos:2,sources:["antenna"],position_source:"antenna"};
 const radioNear={hex:"654321",lat:50.94,lon:7.05,seen:1,seen_pos:1,sources:["antenna","internet"],position_source:"antenna"};
 const internetNear={hex:"abcdef",lat:50.938,lon:6.961,seen:1,seen_pos:1,sources:["internet"],position_source:"internet"};
 const internetPositionOnRf={hex:"fedcba",lat:50.937,lon:6.962,seen:1,seen_pos:1,sources:["antenna","internet"],position_source:"internet"};
 assert.equal(choose(null,[]).source,"cologne");
 assert.equal(choose(null,[internetNear,internetPositionOnRf]).source,"cologne");
 const target=choose(null,[radioFar,radioNear,internetNear,internetPositionOnRf]);
 assert.equal(target.source,"antenna");
 assert.equal(target.lat,radioNear.lat);
 assert.equal(target.lon,radioNear.lon);
 const gps=choose({lat:38.4,lon:27.1},[radioNear]);
 assert.equal(gps.source,"location");
 assert.equal(gps.lat,38.4);
 assert.equal(gps.lon,27.1);
});

test("Radio startup focus upgrades to location if granted later, but manual map wins",()=>{
 const COLOGNE={lat:50.938,lon:6.960};
 const state={
   moved:false,startupLocationPending:false,startupGeo:null,startupRank:1,
   startupSource:"cologne",connected:true,startupQueryDirty:false,
   lat:COLOGNE.lat,lon:COLOGNE.lon,zoom:9,
   queryLat:COLOGNE.lat,queryLon:COLOGNE.lon,
   data:[{hex:"3c1234",lat:50.96,lon:7.2,seen:1,seen_pos:1,
          sources:["antenna"],position_source:"antenna"}]
 };
 let painted=0;
 const ctx={state,COLOGNE,Math,Number,Array,paint:()=>painted++};
 const fn=vm.runInNewContext(
   extract("chooseStartupTarget")+"\n"+extract("applyStartupPriority")+"\napplyStartupPriority",ctx);
 fn();
 assert.equal(state.startupSource,"antenna");
 assert.equal(state.queryLon,7.2);
 assert.equal(state.startupQueryDirty,true);
 state.startupQueryDirty=false;
 state.startupGeo={lat:39.9,lon:32.9};
 fn();
 assert.equal(state.startupSource,"location");
 assert.equal(state.queryLon,32.9);
 assert.equal(state.startupRank,3);
 state.moved=true;state.startupGeo={lat:48,lon:11};
 fn();
 assert.equal(state.lat,39.9);
 assert.equal(painted,2);
});

test("Location requires explicit Qt permission, and never silently asks for a receiver position",()=>{
 const native=fs.readFileSync(path.join(root,"tihulu_flight_radar/native.py"),"utf8");
 assert.match(native,/permissionRequested\.connect\(self\._location_permission_requested\)/);
 assert.match(native,/QWebEnginePermission\.PermissionType\.Geolocation/);
 assert.match(native,/QMessageBox\.question/);
 assert.match(native,/permission\.grant\(\)/);
 assert.match(native,/permission\.deny\(\)/);
 assert.match(js,/navigator\.geolocation\.getCurrentPosition/);
 assert.match(js,/position_source==="antenna"/);
});


test("tar1090 inherits permitted location over a nearby radio plane",()=>{
 const state={lat:38.4,lon:27.1,zoom:10,moved:false,startupSource:"location",
   selected:null,data:[
    {hex:"3c1234",lat:50.9,lon:7.1,seen:1,seen_pos:1,
     sources:["antenna"],position_source:"antenna"}
   ]};
 const sandbox={URL,state,visible:()=>true,isPositioned:a=>a.seen_pos<=60};
 const fn=vm.runInNewContext(extract("tarFocusURL")+"\ntarFocusURL",sandbox);
 const params=new URL(fn("http://localhost/tar1090/")).searchParams;
 assert.equal(params.get("tihuluFocusLat"),"38.400000");
 assert.equal(params.get("tihuluFocusLon"),"27.100000");
 assert.equal(params.has("icao"),false);
});
