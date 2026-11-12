/** Optional, owner-deployed HTTPS relay for the static GitHub Pages app.
 * No API keys, no RTL-SDR access, no local aircraft uploads, no storage.
 * Publish only after confirming adsb.lol's terms/rate limits and your hosting quotas.
 * Allowed browser origin is restricted to the Tihulu GitHub Pages site.
 */
const ORIGIN = "https://tihulu.github.io";
const SOURCE = "https://api.adsb.lol";
const TTL_SECONDS = 30;

function json(value, status=200, cache=false, extra={}) {
  return new Response(JSON.stringify(value), {
    status, headers: {
      "Content-Type":"application/json; charset=utf-8",
      "Access-Control-Allow-Origin":ORIGIN,
      "Vary":"Origin",
      "Cache-Control":cache ? "public, max-age=30" : "no-store",
      "X-Content-Type-Options":"nosniff",
      ...extra
    }
  });
}
function clampCoordinate(value, low, high) {
  const n=Number(value);
  return value !== null && value !== "" && Number.isFinite(n) && n>=low && n<=high ? n : null;
}
export default {
 async fetch(request, env, ctx){
  const origin=request.headers.get("Origin");
  if(origin!==ORIGIN) return new Response("Forbidden", {status:403});
  if(request.method==="OPTIONS") return new Response(null,{
   status:204,headers:{
    "Access-Control-Allow-Origin":ORIGIN,
    "Access-Control-Allow-Methods":"GET, OPTIONS",
    "Access-Control-Allow-Headers":"Content-Type",
    "Access-Control-Max-Age":"600","Vary":"Origin"
   }
  });
  if(request.method!=="GET")return json({error:"Only GET is permitted."},405);
  const url=new URL(request.url);
  if(url.pathname!=="/api/aircraft")return json({error:"Unknown API route."},404);
  const lat=clampCoordinate(url.searchParams.get("lat"),-90,90);
  const lon=clampCoordinate(url.searchParams.get("lon"),-180,180);
  const radius=clampCoordinate(url.searchParams.get("radius"),10,250);
  if(lat===null||lon===null||radius===null)return json({error:"Invalid bounded center/radius."},400);
  // Coarsening mitigates abuse through arbitrary viewport-key variations.
  const a=(Math.round(lat*5)/5).toFixed(1);
  const b=(Math.round(lon*5)/5).toFixed(1);
  const r=Math.max(25,Math.min(250,Math.round(radius/25)*25));
  const key=new Request(new URL("/api/aircraft?lat="+a+"&lon="+b+"&radius="+r,url.origin).href);
  const cache=typeof caches!=="undefined"?caches.default:null;
  if(cache){
    const hit=await cache.match(key);
    if(hit)return hit;
  }
  const abort=new AbortController();
  const timeout=setTimeout(()=>abort.abort(),7000);
  try{
   const target=SOURCE+"/v2/point/"+a+"/"+b+"/"+r;
   const upstream=await fetch(target,{headers:{
    "Accept":"application/json",
    "User-Agent":"TihuluFlightRadarFeed/0.1 (+https://github.com/Tihulu/tihulu-flight-radar)"
   },signal:abort.signal});
   if(!upstream.ok){
    return json({error:"Aircraft provider returned HTTP "+upstream.status},503,false,
      upstream.status===429?{"Retry-After":upstream.headers.get("Retry-After")||"90"}:{});
   }
   const length=Number(upstream.headers.get("Content-Length"));
   if(Number.isFinite(length)&&length>4_194_304)
    return json({error:"Provider response too large."},502);
   const body=await upstream.text();
   if(body.length>4_194_304) return json({error:"Provider response too large."},502);
   const result=JSON.parse(body);
   if(!result||!Array.isArray(result.ac))return json({error:"Unexpected provider JSON."},502);
   const planes=result.ac.slice(0,10000).filter(a=>
     a&&typeof a==="object"&&Number.isFinite(a.seen)&&a.seen>=0&&a.seen<=60
   );
   const payload=json({
    generated_at:Date.now()/1000,
    provider:"adsb.lol",
    attribution:"adsb.lol (ODbL 1.0)",
    aircraft:planes
   },200,true);
   if(cache)ctx.waitUntil(cache.put(key,payload.clone()));
   return payload;
  }catch(error){
   return json({error:"Upstream feed timeout, CORS gateway outage or invalid response."},503);
  }finally{clearTimeout(timeout)}
 }
};
