/* Shared Satellite Center location catalog, adapted to Flight Radar.
 * 8,084 offline DE/TR WGS84 place points; not a cadastral Kreis/ilçe registry.
 * Offline city selection NEVER transmits the typed query.
 * GPS and Open-Meteo are user-triggered only.
 * Physical receiver location is NEVER changed by the map search selector.
 */
import {foldCityName,offlineCityMatches,onlineCityMatches,validStationCoordinates} from "./location_search.mjs";

export const STORAGE_KEY="tihulu-flight-radar-search-place-v1";
const RADIUSES=Object.freeze([25,50,100,150,250]);
const LABELS=Object.freeze({DE:"Germany",TR:"Türkiye"});
let catalogPromise=null;

export function regionsFromPlaces(rows,country){
 if(!Array.isArray(rows)||!["DE","TR"].includes(country))return [];
 return [...new Set(rows.filter(r=>Array.isArray(r)&&r[0]===country &&
  typeof r[2]==="string"&&r[2].trim()).map(r=>r[2]))]
  .sort((a,b)=>a.localeCompare(b,country==="TR"?"tr":"de"));
}
export function localitiesForRegion(rows,country,region){
 if(!Array.isArray(rows)||!region)return [];
 return rows.filter(r=>Array.isArray(r)&&r[0]===country&&r[2]===region&&
  validStationCoordinates(Number(r[3]),Number(r[4])))
  .map(r=>({country:r[0],name:r[1],region:r[2],lat:Number(r[3]),
   lon:Number(r[4]),provider:"offline"}))
  .sort((a,b)=>a.name.localeCompare(b.name,country==="TR"?"tr":"de") ||
    a.lat-b.lat||a.lon-b.lon);
}
export function validSearchPlace(p){
 return p && validStationCoordinates(p.lat,p.lon) &&
  typeof p.label==="string" && p.label.length>0 && p.label.length<=190 &&
  RADIUSES.includes(p.radius);
}
export function readSavedPlace(storage=globalThis?.localStorage){
 try{
  const p=JSON.parse(storage?.getItem(STORAGE_KEY)||"null");
  return validSearchPlace(p)?p:null;
 }catch{return null;}
}
export function saveSelectedPlace(p,storage=globalThis?.localStorage){
 if(!validSearchPlace(p))throw Error("Invalid Flight Radar search location.");
 try{storage?.setItem(STORAGE_KEY,JSON.stringify(p));return true;}
 catch{return false;}
}
export function clearSelectedPlace(storage=globalThis?.localStorage){
 try{storage?.removeItem(STORAGE_KEY);return true;}catch{return false;}
}
async function loadPlaces(){
 if(!catalogPromise){
  catalogPromise=fetch("./cities-de-tr.json",{cache:"force-cache"})
   .then(async res=>{
    if(!res.ok)throw Error("Offline city directory HTTP "+res.status);
    const data=await res.json();
    if(!Array.isArray(data?.places)||data.places.length!==8084)
     throw Error("The DE/TR city directory is incomplete.");
    return data.places;
   }).catch(err=>{catalogPromise=null;throw err;});
 }
 return catalogPromise;
}
function displayName(row){
 return [row.name,row.region,LABELS[row.country]||row.country]
  .filter(Boolean).join(" · ");
}
export function initFlightLocationUI({onChoose,getCurrent}){
 const $=id=>document.getElementById(id);
 const root=$("locationPicker"),country=$("placeCountry"),region=$("placeRegion");
 const town=$("placeTown"),query=$("placeQuery"),suggestions=$("placeSuggestions");
 const lat=$("placeLatitude"),lon=$("placeLongitude"),radius=$("placeRadius");
 const status=$("placeStatus"),selection=$("placeSelection");
 let cities=[],localities=[],activePlace=null,requestId=0,manualChanged=false;
 const say=value=>{status.textContent=String(value)};
 const option=(value,title)=>{
  const el=document.createElement("option");el.value=value;el.textContent=title;return el;
 };
 function showSelection(row){
  if(!row||!validStationCoordinates(row.lat,row.lon))return;
  manualChanged=false;activePlace={...row};lat.value=Number(row.lat).toFixed(5);
  lon.value=Number(row.lon).toFixed(5);
  selection.textContent=displayName(row)+" · "+lat.value+", "+lon.value+" (map search point)";
  suggestions.replaceChildren();suggestions.hidden=true;
 }
 function refreshTownList(){
  const reg=region.value,cc=country.value;
  localities=localitiesForRegion(cities,cc,reg);
  town.replaceChildren(option("","Select a city, town or district / municipality"));
  for(let i=0;i<localities.length;i++){
   const r=localities[i];
   town.append(option(String(i),r.name));
  }
  town.disabled=localities.length===0;
  town.value="";
  say(reg
   ?localities.length+" offline places available in "+reg+
      ". Select a place or type to search. Entries are municipality/place points, not complete administrative district boundaries."
   :"Choose a state or province, then a city/town/district.");
 }
 function refreshRegions(){
  region.replaceChildren(option("","Select state / province"));
  for(const r of regionsFromPlaces(cities,country.value))
   region.append(option(r,r));
  region.value="";
  refreshTownList();
  suggestions.replaceChildren();suggestions.hidden=true;
 }
 function listSuggestions(rows){
  suggestions.replaceChildren();
  suggestions.hidden=!rows.length;
  for(const row of rows.slice(0,12)){
   const btn=document.createElement("button");
   btn.type="button";btn.setAttribute("role","option");
   btn.className="place-result";btn.textContent=displayName(row);
   btn.addEventListener("click",()=>{showSelection(row);query.value=row.name;});
   suggestions.append(btn);
  }
 }
 async function showPicker(){
  root.hidden=false;
  const saved=readSavedPlace();
  const now=getCurrent();
  radius.value=String(saved?.radius||now.radius||100);
  lat.value=String(saved?.lat??now.lat);
  lon.value=String(saved?.lon??now.lon);
  selection.textContent=saved?.label||"Choose a place to change the online aircraft search center.";
  activePlace=null;manualChanged=false;
  query.value="";
  country.value=saved?.country==="TR"?"TR":saved?.country==="all"?"all":"DE";
  say("Loading Satellite Center's offline Germany/Türkiye directory...");
  try{
   cities=await loadPlaces();
   if(root.hidden)return;
   refreshRegions();
   if(saved?.region && regionsFromPlaces(cities,country.value).includes(saved.region)){
    region.value=saved.region;refreshTownList();
    const index=localities.findIndex(x=>x.name===saved.name &&
     Math.abs(x.lat-saved.lat)<0.0001&&Math.abs(x.lon-saved.lon)<0.0001);
    if(index>=0)town.value=String(index);
   }
   if(saved)activePlace={country:saved.country,name:saved.name||saved.label,
    region:saved.region||"",lat:saved.lat,lon:saved.lon,provider:saved.provider||"saved"};
   say("Offline DE/TR directory ready: 7,104 Germany and 980 Türkiye locations. No search text leaves your device.");
  }catch(err){say("Offline directory unavailable: "+err.message+
    ". Enter latitude and longitude manually or use explicit GPS/online search.");}
  query.focus();
 }
 const close=()=>{root.hidden=true;suggestions.replaceChildren();};
 const apply=(row,source)=>{
  const nlat=Number(row.lat),nlon=Number(row.lon);
  if(!validStationCoordinates(nlat,nlon)){say("Invalid coordinates. Map unchanged.");return;}
  const r=Number(radius.value);
  if(!RADIUSES.includes(r)){say("Select a valid search radius.");return;}
  const label=displayName(row)||"Custom coordinates";
  const place={lat:nlat,lon:nlon,zoom:9,radius:r,label,
    name:row.name||"",region:row.region||"",country:row.country||"",
    provider:source||row.provider||"offline"};
  saveSelectedPlace(place);
  close();
  onChoose(place);
 };
 $("placeOpen").addEventListener("click",()=>void showPicker());
 $("placeTarOpen").addEventListener("click",()=>void showPicker());
 $("placeClose").addEventListener("click",close);
 root.addEventListener("click",e=>{if(e.target===root)close();});
 root.addEventListener("keydown",e=>{if(e.key==="Escape"){e.preventDefault();e.stopPropagation();close();}});
 country.addEventListener("change",()=>{query.value="";activePlace=null;manualChanged=false;refreshRegions();});
 region.addEventListener("change",()=>{query.value="";activePlace=null;manualChanged=false;refreshTownList();});
 town.addEventListener("change",()=>{
  const row=localities[Number(town.value)];
  if(row)showSelection(row);
 });
 query.addEventListener("input",()=>{
  activePlace=null;manualChanged=false;
  const text=query.value.trim();
  if(foldCityName(text).length<2){listSuggestions([]);return;}
  const subset=region.value
   ?cities.filter(x=>x[0]===country.value&&x[2]===region.value)
   :cities;
  const matches=offlineCityMatches(subset,text,country.value,12);
  listSuggestions(matches);
  say(matches.length
   ?matches.length+" matching offline places. Select a result; typing does not change your map."
   :"No offline place found. Use a different spelling, online search or manual coordinates.");
 });
 for(const el of [lat,lon]){
  el.addEventListener("input",()=>{
   activePlace=null;manualChanged=true;
   selection.textContent="Manual WGS84 coordinates · map search point only; not SDR location.";
  });
 }
 $("placeApply").addEventListener("click",()=>{
  if(activePlace){apply(activePlace,activePlace.provider);return;}
  if(!manualChanged){say("Choose a listed city/district or edit coordinates before applying.");return;}
  if(lat.value.trim()===""||lon.value.trim()===""){
   say("Enter both latitude and longitude or select an offline place.");return;
  }
  const a=Number(lat.value),b=Number(lon.value);
  if(!validStationCoordinates(a,b)){say("Latitude must be −90…90, longitude −180…180.");return;}
  apply({lat:a,lon:b,name:"Custom coordinates",country:"",region:"",provider:"manual"},"manual");
 });
 $("placeGps").addEventListener("click",()=>{
  if(!window.isSecureContext||!navigator.geolocation){
   say("GPS unavailable. Use manual coordinates or HTTPS.");return;
  }
  const btn=$("placeGps");btn.disabled=true;
  say("Requesting device location by your explicit action...");
  navigator.geolocation.getCurrentPosition(pos=>{
   btn.disabled=false;
   const a=pos.coords.latitude,b=pos.coords.longitude;
   if(!validStationCoordinates(a,b)){say("GPS returned invalid coordinates.");return;}
   apply({lat:a,lon:b,name:"Device location",country:"",region:"",provider:"gps"},"gps");
  },err=>{btn.disabled=false;say("Device location unavailable: "+String(err.message||err.code));},
   {enableHighAccuracy:true,timeout:12000,maximumAge:0});
 });
 $("placeOnline").addEventListener("click",async()=>{
  const typed=query.value.trim();
  if(typed.length<2){say("Enter at least two characters to search worldwide.");return;}
  const token=++requestId,btn=$("placeOnline");
  btn.disabled=true;say("Searching Open-Meteo/GeoNames on demand; the typed place name is sent to their server.");
  const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),9000);
  try{
   const url=new URL("https://geocoding-api.open-meteo.com/v1/search");
   url.searchParams.set("name",typed);url.searchParams.set("count","10");
   url.searchParams.set("format","json");url.searchParams.set("language","en");
   if(country.value==="TR"||country.value==="DE")url.searchParams.set("countryCode",country.value);
   const res=await fetch(url,{mode:"cors",signal:abort.signal,credentials:"omit"});
   if(!res.ok)throw Error("HTTP "+res.status);
   const results=onlineCityMatches(await res.json(),country.value).map(x=>({
    ...x,provider:"open-meteo"}));
   if(requestId!==token||root.hidden)return;
   listSuggestions(results);
   say(results.length
    ?"Choose one of "+results.length+" online geocoding suggestions. Actual aircraft will still use selected providers."
    :"No matching places found online.");
  }catch(err){if(err.name!=="AbortError")say("Online search unavailable: "+err.message);}
  finally{clearTimeout(timeout);btn.disabled=false;}
 });
 let lastAddressRequest=0;
 $("placeAddressOnline").addEventListener("click",async()=>{
  const typed=query.value.trim();
  if(typed.length<3||typed.length>180){
   say("Enter a street, district, landmark or address (3–180 characters).");return;
  }
  if(Date.now()-lastAddressRequest<1200){
   say("Please avoid rapid repeated searches of the public Photon server.");return;
  }
  lastAddressRequest=Date.now();
  const token=++requestId,button=$("placeAddressOnline");
  button.disabled=true;
  say("Searching Photon/OSM on demand: your entered address is sent to photon.komoot.io.");
  const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),9000);
  try{
   const url=new URL("https://photon.komoot.io/api/");
   url.searchParams.set("q",typed);url.searchParams.set("limit","10");
   url.searchParams.set("lang","en");
   const res=await fetch(url,{mode:"cors",credentials:"omit",
    cache:"no-store",signal:abort.signal});
   if(!res.ok)throw Error("HTTP "+res.status);
   const body=await res.json();
   if(!Array.isArray(body?.features))throw Error("Invalid Photon search response.");
   const rows=body.features.slice(0,10).map(feature=>{
    const p=feature?.properties||{},coords=feature?.geometry?.coordinates;
    const a=Number(coords?.[1]),b=Number(coords?.[0]);
    if(!validStationCoordinates(a,b))return null;
    const countryCode=String(p.countrycode||"").toUpperCase();
    if(country.value!=="all"&&countryCode!==country.value)return null;
    const address=[p.name,p.street,p.housenumber,p.city||p.town||p.village,
      p.postcode].filter(v=>typeof v==="string"||typeof v==="number")
     .map(String).filter(Boolean);
    return {name:[...new Set(address)].join(", ").slice(0,160)||
      "Unknown Photon place",region:String(p.state||p.county||"").slice(0,80),
     country:countryCode,lat:a,lon:b,provider:"photon"};
   }).filter(Boolean);
   if(requestId!==token||root.hidden)return;
   listSuggestions(rows);
   say(rows.length?rows.length+" Photon/OSM address results. Select a "+
    "result to use its coordinates as the map search center. The antenna "+
    "location is unchanged.":"No matching address found; try another spelling.");
  }catch(err){
   if(err.name!=="AbortError")say("Address search unavailable: "+err.message+
    ". Offline towns and manual coordinates remain usable.");
  }finally{clearTimeout(timeout);button.disabled=false;}
 });
 return {open:showPicker,close,loadPlaces,readSavedPlace};
}
