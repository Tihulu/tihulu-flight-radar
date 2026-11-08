"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),
 fs=require("node:fs"),path=require("node:path"),url=require("node:url");
const root=path.join(__dirname,".."),web=path.join(root,"tihulu_flight_radar/web");
const catalog=JSON.parse(fs.readFileSync(path.join(web,"cities-de-tr.json"),"utf8"));
const src=fs.readFileSync(path.join(web,"app.js"),"utf8");
const html=fs.readFileSync(path.join(web,"index.html"),"utf8");
const bridge=fs.readFileSync(path.join(root,"tihulu_flight_radar/bridge.py"),"utf8");
const pkg=fs.readFileSync(path.join(root,"pyproject.toml"),"utf8");
const sw=fs.readFileSync(path.join(web,"sw.js"),"utf8");
const modulePath=name=>url.pathToFileURL(path.join(web,name)).href;
const getHelpers=()=>Promise.all([import(modulePath("flight_location_ui.mjs")),
 import(modulePath("location_search.mjs"))]);

test("Offline Satellite Center DE/TR place list is complete, licensed and WGS84",async()=>{
 const data=catalog.places;
 assert.equal(data.length,8084);
 assert.equal(data.filter(r=>r[0]==="DE").length,7104);
 assert.equal(data.filter(r=>r[0]==="TR").length,980);
 const [f,s]=await getHelpers();
 assert.equal(f.regionsFromPlaces(data,"DE").length,16);
 assert.equal(f.regionsFromPlaces(data,"TR").length,81);
 assert.ok(f.regionsFromPlaces(data,"DE").includes("North Rhine-Westphalia"));
 assert.ok(f.regionsFromPlaces(data,"TR").includes("İzmir"));
 const n=f.localitiesForRegion(data,"DE","North Rhine-Westphalia");
 assert.ok(n.some(x=>x.name==="Köln"));
 assert.ok(n.some(x=>x.name==="Hürth"));
 const tr=f.localitiesForRegion(data,"TR","İzmir");
 assert.ok(tr.some(x=>x.name==="Karaburun"));
 assert.ok(tr.some(x=>x.name==="Bornova"));
 assert.deepEqual(f.localitiesForRegion(data,"DE","İzmir"),[]);
 assert.equal(s.offlineCityMatches(data,"Koln","DE")[0].name,"Köln");
 assert.equal(s.offlineCityMatches(data,"karaburun","TR")[0].region,"İzmir");
 assert.match(fs.readFileSync(path.join(web,"CITY_DATA_LICENSE.md"),"utf8"),/ODbL 1.0/);
});
test("Saved search region works across relaunch without leaking or changing SDR",async()=>{
 const [f]=await getHelpers();
 const storage={x:null,getItem(){return this.x},setItem(_k,x){this.x=x},removeItem(){this.x=null}};
 const a={lat:38.6364,lon:26.51094,radius:150,label:"Karaburun · İzmir · Türkiye",
   name:"Karaburun",region:"İzmir",country:"TR",provider:"offline"};
 assert.equal(f.saveSelectedPlace(a,storage),true);
 assert.equal(f.readSavedPlace(storage).country,"TR");
 assert.equal(f.readSavedPlace(storage).radius,150);
 storage.x='{"lat":250,"lon":4,"radius":100,"label":"Invalid"}';
 assert.equal(f.readSavedPlace(storage),null);
 assert.equal(f.validSearchPlace({...a,radius:123}),false);
 assert.equal(f.validSearchPlace({...a,lon:Infinity}),false);
 assert.equal(f.clearSelectedPlace(storage),true);
 assert.equal(f.readSavedPlace(storage),null);
});
test("Picker is accessible from BOTH full original tar1090 and compact live radar",()=>{
 for(const id of ["placeOpen","placeTarOpen","locationPicker","placeCountry",
  "placeRegion","placeTown","placeQuery","placeSuggestions","placeLatitude",
  "placeLongitude","placeRadius","placeApply","placeGps","placeOnline","placeClose"])
  assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(html,/role="dialog" aria-modal="true"/);
 assert.match(src,/import\("\.\/flight_location_ui\.mjs"\)/);
 assert.match(src,/state\.queryRadius=radius/);
 assert.match(src,/if\(tarFrameOpen\)\{/);
 assert.match(src,/frame\.removeAttribute\("src"\)/);
 assert.match(src,/void setBrowserTar\(true\)/);
 assert.match(src,/Physical receiver site unchanged/);
 assert.match(src,/state\.moved=true;state\.autoFocused=false/);
 assert.match(html,/Satellite Center/);
});
test("Native loopback serves, package distributes, PWA caches all offline selector files",()=>{
 for(const asset of ["flight_location_ui.mjs","location_search.mjs","cities-de-tr.json","CITY_DATA_LICENSE.md"])
  assert.match(bridge,new RegExp('"\\/'+asset.replace(".","\\.")+'"'));
 assert.match(bridge,/"application\/json" if name\.endswith\("\.json"\)/);
 assert.match(pkg,/web\/\*\.json/);
 assert.match(pkg,/web\/\*\.md/);
 for(const asset of ["flight_location_ui.mjs","location_search.mjs","cities-de-tr.json"])
  assert.ok(sw.includes('"./'+asset+'"'));
 assert.match(sw,/shell-v20/);
 assert.doesNotMatch(src,/fetch\(["']https?:\/\/.*cities-de-tr/);
});
test("No auto GPS permission prompt and worldwide lookup is explicitly user-initiated",async()=>{
 const [f]=await getHelpers();
 assert.match(src,/navigator\.permissions\.query\(\{name:"geolocation"\}\)/);
 const locationUI=fs.readFileSync(path.join(web,"flight_location_ui.mjs"),"utf8");
 assert.match(locationUI,/\$\("placeGps"\)\.addEventListener\("click"/);
 assert.match(locationUI,/\$\("placeOnline"\)\.addEventListener\("click"/);
 assert.match(locationUI,/https:\/\/geocoding-api\.open-meteo\.com\/v1\/search/);
 assert.match(locationUI,/fetch\("\.\/cities-de-tr\.json",\{cache:"force-cache"\}\)/);
 assert.equal(f.regionsFromPlaces(catalog.places,"all").length,0);
});
