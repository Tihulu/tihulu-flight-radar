"use strict";
/* TIHULU shared Germany/Türkiye offline place selector.
 * Both same-origin JSON catalogs are checked into this repository; no external
 * geocoding service, IP-location lookup or implicit GPS permission is needed.
 */
const TihuluPlaces=(()=>{
  const FILES=Object.freeze({DE:"./places/de.json",TR:"./places/tr.json"});
  const LABELS=Object.freeze({
    DE:{country:"Germany",region:"Bundesland",district:"Landkreis / district",place:"City / town"},
    TR:{country:"Türkiye",region:"İl / province",district:"İlçe / district",place:"District centre"}
  });
  const STORE_KEY="tihulu-flight-radar:search-home:v1";
  const cache=new Map();
  const validPoint=p=>p&&Number.isFinite(p.lat)&&Number.isFinite(p.lon)&&
    p.lat>=-90&&p.lat<=90&&p.lon>=-180&&p.lon<=180;
  const validRadius=r=>Number.isInteger(r)&&r>=10&&r<=250;
  function validateSaved(saved){
    if(!saved||typeof saved!=="object"||!Object.prototype.hasOwnProperty.call(FILES,saved.country)||
       !validPoint(saved)||!validRadius(saved.radius))return null;
    if(typeof saved.region!=="string"||saved.region.length>120 ||
       typeof saved.district!=="string"||saved.district.length>140 ||
       typeof saved.place!=="string"||saved.place.length>140)return null;
    return {country:saved.country,region:saved.region,district:saved.district,
      place:saved.place,lat:saved.lat,lon:saved.lon,radius:saved.radius};
  }
  function readSaved(storage){
    try{return validateSaved(JSON.parse((storage??window.localStorage).getItem(STORE_KEY)));}
    catch{return null}
  }
  function save(saved,storage){
    const value=validateSaved(saved);
    if(!value)throw Error("Invalid saved region.");
    (storage??window.localStorage).setItem(STORE_KEY,JSON.stringify(value));
    return value;
  }
  function clear(storage){try{(storage??window.localStorage).removeItem(STORE_KEY);}catch{}}
  function checkCatalog(data,code){
    if(!data||data.country!==code||!Array.isArray(data.regions) ||
       !data.regions.length||data.regions.length>300)throw Error("Invalid local place catalog.");
    for(const reg of data.regions){
      if(typeof reg.name!=="string"||!validPoint(reg)||
         !Array.isArray(reg.districts)||!reg.districts.length)throw Error("Invalid state/province data.");
      for(const district of reg.districts){
        if(typeof district.name!=="string"||!validPoint(district))throw Error("Invalid district data.");
        if(district.places && (!Array.isArray(district.places)||
          district.places.some(p=>!Array.isArray(p)||typeof p[0]!=="string"||
            !validPoint({lat:p[1],lon:p[2]}))))throw Error("Invalid city data.");
      }
    }
    return data;
  }
  async function load(code,fetchImpl){
    if(!Object.prototype.hasOwnProperty.call(FILES,code))throw Error("Unsupported country.");
    if(cache.has(code))return cache.get(code);
    const request=(async()=>{
      const response=await (fetchImpl||fetch)(FILES[code],{
        credentials:"same-origin",cache:"default"});
      if(!response.ok)throw Error("Place catalog unavailable: HTTP "+response.status);
      return checkCatalog(await response.json(),code);
    })();
    cache.set(code,request);
    try{return await request;}
    catch(e){cache.delete(code);throw e}
  }
  function locate(catalog,regionName="",districtName="",cityName=""){
    const region=catalog.regions.find(r=>r.name===regionName);
    if(!region)return null;
    const district=districtName?
      region.districts.find(d=>d.name===districtName):null;
    if(districtName&&!district)return null;
    const place=cityName && district?.places?.find(p=>p[0]===cityName);
    if(cityName&&!place)return null;
    const point=place?{lat:place[1],lon:place[2]}:(district||region);
    const names=[region.name,district?.name,place?.[0]].filter(Boolean);
    return {country:catalog.country,region:region.name,
      district:district?.name||"",place:place?.[0]||"",
      lat:point.lat,lon:point.lon,label:names.reverse().join(", ")};
  }
  function label(saved){
    const place=saved?.place||saved?.district||saved?.region||"Unknown region";
    return place+" · "+(saved?.country==="TR"?"Türkiye":"Germany");
  }
  return {FILES,LABELS,STORE_KEY,validateSaved,readSaved,save,clear,
    checkCatalog,load,locate,label};
})();
if(typeof window!=="undefined")window.TihuluPlaces=TihuluPlaces;
if(typeof module!=="undefined"&&module.exports)module.exports=TihuluPlaces;
