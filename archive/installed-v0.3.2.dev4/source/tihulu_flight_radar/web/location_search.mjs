/* Satellite Center location selector.
 * Local DE/TR city search never sends queries to a server.
 * Browser geolocation is accessed only on explicit button click.
 * Optional worldwide online suggestions use Open-Meteo Geocoding (non-commercial API).
 * All coordinate calculations remain client-side.
 */
export function foldCityName(value){
  return String(value??"").trim().toLocaleLowerCase("en-US")
   .replace(/ı/g,"i").replace(/ß/g,"ss").normalize("NFD")
   .replace(/[\u0300-\u036f]/g,"").replace(/æ/g,"ae").replace(/œ/g,"oe")
   .replace(/[^a-z0-9\s-]/g," ").replace(/\s+/g," ").trim();
}
export function validStationCoordinates(lat,lon){
  return Number.isFinite(lat)&&Number.isFinite(lon)&&lat>=-90&&lat<=90&&lon>=-180&&lon<=180;
}
const aliasNames=Object.freeze({
  "cologne":"köln","koln":"köln","munich":"münchen",
  "nuremberg":"nürnberg","izmir":"izmir","istanbul":"istanbul",
  "eskisehir":"eskişehir","sanliurfa":"şanlıurfa","antep":"gaziantep",
  "huerth":"hürth","hurth":"hürth","duesseldorf":"düsseldorf","dusseldorf":"düsseldorf"
});
export function offlineCityMatches(rows,query,country="all",limit=12){
  if(!Array.isArray(rows))return [];
  const raw=foldCityName(query);
  if(raw.length<2)return [];
  const key=foldCityName(aliasNames[raw]||raw);
  const terms=key.split(/[\s,]+/).filter(Boolean);
  const found=[];
  for(const row of rows){
    if(!Array.isArray(row)||row.length<5)continue;
    const [cc,name,region,lat,lon]=row;
    if(country!=="all"&&cc!==country)continue;
    if(!validStationCoordinates(Number(lat),Number(lon)))continue;
    const n=foldCityName(name),r=foldCityName(region);
    let rank;
    if(n===key)rank=0;
    else if(n.startsWith(key))rank=1;
    else if(n.split(" ").some(word=>word.startsWith(key)))rank=2;
    else if(n.includes(key))rank=3;
    else if(terms.length>1&&terms.every(t=>(n+" "+r).includes(t)))rank=4;
    else continue;
    found.push({country:cc,name,region,lat:Number(lat),lon:Number(lon),rank,provider:"offline"});
  }
  found.sort((a,b)=>a.rank-b.rank||a.name.length-b.name.length||
    a.name.localeCompare(b.name,"en")||a.region.localeCompare(b.region,"en"));
  return found.slice(0,Math.max(1,Math.min(20,limit)));
}
export function onlineCityMatches(payload,country="all"){
  const results=Array.isArray(payload?.results)?payload.results:[];
  return results.filter(r=>
    typeof r.name==="string"&&r.name.length>0&&
    validStationCoordinates(Number(r.latitude),Number(r.longitude))&&
    (country==="all"||r.country_code===country)
  ).slice(0,10).map(r=>({
    country:r.country_code||"",
    name:r.name.slice(0,100),
    region:String(r.admin1||"").slice(0,100),
    countryName:String(r.country||"").slice(0,100),
    lat:Number(r.latitude),lon:Number(r.longitude),
    provider:"open-meteo"
  }));
}
export function initStationLocationUI({onStationChanged,log=()=>{},ids={}}={}){
 const $=id=>document.getElementById(ids[id]||id);
 const query=$("city-query"),suggestions=$("city-suggestions");
 const status=$("location-status"),country=$("city-country");
 const select=$("city"),lat=$("lat"),lon=$("lon");
 const gpsBtn=$("location-gps"),onlineBtn=$("city-online-search");
 const onlineToggle=$("city-online-toggle");
 let cities=[],citiesPromise=null,choices=[],active=-1;
 let typingTimer=null,inFlight=null,lastRemoteAt=0;
 const cache=new Map();
 let latestSearchToken=0;
 let internalApply=false;
 const say=text=>{status.textContent=String(text)};
 const countryName=c=>c==="DE"?"Germany":c==="TR"?"Türkiye":c||"Unknown";
 const label=row=>[row.name,row.region,row.countryName||countryName(row.country)].filter(Boolean).join(" · ");
 function clearOptions(){
   suggestions.replaceChildren();choices=[];active=-1;
   suggestions.hidden=true;query.setAttribute("aria-expanded","false");
   query.removeAttribute("aria-activedescendant");
 }
 function activate(index){
   if(!choices.length)return;
   active=(index+choices.length)%choices.length;
   suggestions.querySelectorAll('[role="option"]').forEach((el,i)=>{
     el.classList.toggle("active",i===active);
     el.setAttribute("aria-selected",i===active?"true":"false");
     if(i===active){query.setAttribute("aria-activedescendant",el.id);el.scrollIntoView({block:"nearest"});}
   });
 }
 function applyStation(row,mode,more=""){
   const nlat=Number(row.lat),nlon=Number(row.lon);
   if(!validStationCoordinates(nlat,nlon)){say("Invalid coordinates; station unchanged.");return;}
   const oldLat=Number(lat.value),oldLon=Number(lon.value);
   lat.value=nlat.toFixed(5);lon.value=nlon.toFixed(5);
   select.value=mode;
   if(mode==="city-search")query.value=row.name;
   clearOptions();
   const summary=label(row)+(more?" · "+more:"");
   say("Station set: "+summary+" · "+nlat.toFixed(5)+"°, "+nlon.toFixed(5)+"°."+
       " Recalculate passes for this location.");
   if(!Number.isFinite(oldLat)||!Number.isFinite(oldLon)||Math.abs(oldLat-nlat)>1e-9||Math.abs(oldLon-nlon)>1e-9){
     internalApply=true;
     try{lat.dispatchEvent(new Event("change",{bubbles:true}));}
     finally{internalApply=false;}
   }
   if(typeof onStationChanged==="function")onStationChanged({...row,mode});
   log("Ground station chosen: "+row.provider+" · "+row.name+". Orbital geometry will use the new coordinates.");
 }
 function show(rows){
   choices=rows.slice(0,12);active=-1;
   suggestions.replaceChildren();
   if(!choices.length){clearOptions();return;}
   const fragment=document.createDocumentFragment();
   choices.forEach((row,i)=>{
     const button=document.createElement("button");
     button.id="city-choice-"+i;button.type="button";
     button.className="city-option";button.setAttribute("role","option");
     button.setAttribute("aria-selected","false");
     button.textContent=label(row)+(row.provider==="open-meteo"?" · Online":" · Offline");
     button.addEventListener("pointerdown",event=>event.preventDefault());
     button.addEventListener("click",()=>applyStation(row,"city-search",row.provider==="offline"?"offline directory":"Open-Meteo online lookup"));
     fragment.append(button);
   });
   suggestions.append(fragment);
   suggestions.hidden=false;
   query.setAttribute("aria-expanded","true");
 }
 async function loadCities(){
   if(citiesPromise)return citiesPromise;
   citiesPromise=(async()=>{
     const res=await fetch("./cities-de-tr.json",{cache:"force-cache"});
     if(!res.ok)throw Error("Could not load bundled DE/TR city directory (HTTP "+res.status+")");
     const data=await res.json();
     if(!Array.isArray(data?.places)||data.places.length<1000)throw Error("Invalid offline city database");
     cities=data.places;
     return cities;
   })();
   try{return await citiesPromise;}catch(e){citiesPromise=null;throw e;}
 }
 async function localSuggest(){
   const typed=query.value.trim();if(!typed){clearOptions();return;}
   try{
     await loadCities();
     if(query.value.trim()!==typed)return;
     const rows=offlineCityMatches(cities,typed,country.value);
     show(rows);
     if(!rows.length){
       say("No offline city matches. Try another spelling, use Search worldwide online, or enter custom coordinates.");
     }else{
       say(rows.length+" matching city/town suggestions from 8,084 bundled Germany/Türkiye records. "+
           "Select a result to update your station; typing alone does not change coordinates.");
     }
   }catch(e){
     say("Offline city directory unavailable: "+e.message+". Presets and manual coordinates remain available.");
     clearOptions();
   }
 }
 async function remoteSuggest({automatic=false}={}){
   const typed=query.value.trim();
   if(typed.length<(automatic?3:2))return;
   // Manual action or explicit opt-in to online autocomplete only.
   if(automatic&&!onlineToggle.checked)return;
   if(inFlight){inFlight.abort();inFlight=null;}
   const countryCode=country.value;
   const key=typed.toLocaleLowerCase()+"|"+countryCode;
   const token=++latestSearchToken;
   if(cache.has(key)){
     const cached=cache.get(key);if(typed!==query.value.trim())return;
     show(cached);say(cached.length?"Online city results (cached in this tab). Select a location.":"No online cities found for this search.");return;
   }
   const elapsed=Date.now()-lastRemoteAt;
   if(automatic&&elapsed<1800)return; // fair-use: avoid sending each keystroke
   lastRemoteAt=Date.now();
   onlineBtn.disabled=true;
   say("Searching worldwide places through Open-Meteo (your typed query is sent to their server)...");
   const controller=new AbortController();inFlight=controller;
   const watchdog=setTimeout(()=>controller.abort(),9000);
   try{
     const url=new URL("https://geocoding-api.open-meteo.com/v1/search");
     url.searchParams.set("name",typed);url.searchParams.set("count","10");
     url.searchParams.set("language","en");url.searchParams.set("format","json");
     if(countryCode!=="all")url.searchParams.set("countryCode",countryCode);
     const resp=await fetch(url.href,{mode:"cors",signal:controller.signal,cache:"default"});
     if(!resp.ok)throw Error("HTTP "+resp.status);
     const data=await resp.json();
     if(data?.error)throw Error(String(data.reason||"Provider error"));
     const rows=onlineCityMatches(data,countryCode);
     if(cache.size>=30)cache.delete(cache.keys().next().value);
     cache.set(key,rows);
     if(token!==latestSearchToken||typed!==query.value.trim())return;
     show(rows);
     say(rows.length?rows.length+" results from Open-Meteo/GeoNames. Select the correct city and region.":"Online search returned no matches. You can always enter custom coordinates.");
   }catch(err){
     if(err.name!=="AbortError")say("Online search failed: "+err.message+". Offline suggestions and custom coordinates are still available.");
   }finally{
     clearTimeout(watchdog);if(inFlight===controller)inFlight=null;
     onlineBtn.disabled=false;
   }
 }
 async function refreshSuggestions(){
   ++latestSearchToken;
   if(inFlight){inFlight.abort();inFlight=null;}
   await localSuggest();
   if(onlineToggle.checked&&foldCityName(query.value).length>=3){
     clearTimeout(typingTimer);
     typingTimer=setTimeout(()=>{void remoteSuggest({automatic:true});},850);
   }
 }
 query.addEventListener("focus",()=>{if(query.value.trim().length>=2)void localSuggest();else void loadCities().catch(()=>{});});
 query.addEventListener("input",()=>{
   select.value="city-search";
   clearTimeout(typingTimer);
   void refreshSuggestions();
 });
 query.addEventListener("keydown",event=>{
   if(event.key==="ArrowDown"||event.key==="ArrowUp"){
     if(choices.length){event.preventDefault();activate(active<0?(event.key==="ArrowDown"?0:choices.length-1):active+(event.key==="ArrowDown"?1:-1));}
   }else if(event.key==="Enter"){
     if(choices.length){event.preventDefault();applyStation(choices[active<0?0:active],"city-search");}
     else if(query.value.trim().length>=2){event.preventDefault();void remoteSuggest();}
   }else if(event.key==="Escape"){clearOptions();}
 });
 country.addEventListener("change",()=>{if(query.value.trim())void refreshSuggestions();});
 onlineToggle.addEventListener("change",()=>{
   clearTimeout(typingTimer);if(onlineToggle.checked&&query.value.trim().length>=3)void remoteSuggest({automatic:true});
 });
 onlineBtn.addEventListener("click",()=>{void remoteSuggest();});
 document.addEventListener("pointerdown",e=>{
   if(!query.contains(e.target)&&!suggestions.contains(e.target))clearOptions();
 });
 gpsBtn.addEventListener("click",()=>{
   if(!window.isSecureContext || !navigator.geolocation){
     say("Browser geolocation unavailable. Use HTTPS or enter coordinates manually.");return;
   }
   gpsBtn.disabled=true;
   say("Requesting your browser's device location. You can deny permission; no location is uploaded by this page.");
   navigator.geolocation.getCurrentPosition(pos=>{
     gpsBtn.disabled=false;
     const {latitude,longitude,accuracy}=pos.coords;
     if(!validStationCoordinates(latitude,longitude)){
       say("Browser returned invalid coordinates. Ground station unchanged.");return;
     }
     applyStation({name:"Device location",region:"",country:"",countryName:"",
       lat:latitude,lon:longitude,provider:"browser-geolocation"},"gps",
       "estimated accuracy ±"+Math.round(accuracy)+" m");
   },error=>{
     gpsBtn.disabled=false;
     const details={1:"Permission denied",2:"Position unavailable",3:"Timed out"};
     say("Could not obtain device location: "+(details[error.code]||error.message||"Unknown error")+
       ". Search a city or enter coordinates manually. No inferred location is substituted.");
   },{enableHighAccuracy:true,timeout:12000,maximumAge:0});
 });
 for(const el of [lat,lon]){
   el.addEventListener("input",()=>{
     select.value="Custom";clearOptions();
     say("Manual coordinate entry. Edit both latitude and longitude; pass predictions use these values when recalculated.");
   });
   el.addEventListener("change",()=>{
     if(internalApply)return;
     const a=Number(lat.value),b=Number(lon.value);
     if(!validStationCoordinates(a,b)||lat.value.trim()===""||lon.value.trim()===""){
       say("Invalid custom coordinates: latitude must be −90…90 and longitude −180…180.");
       return;
     }
     if(typeof onStationChanged==="function")onStationChanged({
       name:"Custom coordinates",provider:"manual",lat:a,lon:b,mode:"Custom"});
     say("Custom station: "+a.toFixed(5)+"°, "+b.toFixed(5)+"°. Recalculate passes to use it.");
   });
 }
 select.addEventListener("change",()=>{
   if(select.value==="city-search"){
     query.focus();void loadCities().catch(()=>{});
   }else if(select.value==="gps"){
     say("Press Use device location below to request permission; no location access happens automatically.");
   }else if(select.value==="Custom"){
     say("Custom station mode. Enter any latitude and longitude, including outside Germany or Türkiye.");
   } // legacy city presets handled in main browser.js
 });
 say("Current station coordinates are editable. Search Germany/Türkiye offline, request device location, or use fully custom coordinates.");
 return {loadCities,refreshSuggestions,applyStation};
}
