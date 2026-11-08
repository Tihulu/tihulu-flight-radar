/*
 * Browser-only 1090 MHz Mode S/ADS-B receiver (experimental).
 * Real 2 Msps unsigned 8-bit interleaved RTL-SDR IQ input. We accept only
 * DF17/DF18 messages with a valid 24-bit Mode S CRC; no parity correction.
 * Compatible with a pinned WebUSB RTL2832U client, no local server needed.
 * No fabricated flight positions: airborne CPR needs genuine, recent even
 * AND odd position transmissions from the same ICAO.
 *
 * This is not a replacement for readsb's robust 2.4 Msps DSP or tar1090.
 * Web Worker only: never access navigator.usb or device handles here.
 */
export const SAMPLE_RATE=2000000;
const CRC_POLY=0xFFF409;
const AIRCRAFT_TTL_MS=60000;
const CPR_PAIR_MS=10000;
const CALL_CHARS="#ABCDEFGHIJKLMNOPQRSTUVWXYZ#####_###############0123456789######";

export function crcValid(frame){
 if(!(frame instanceof Uint8Array) || frame.length!==14) return false;
 if(![17,18].includes(frame[0]>>3))return false;
 let crc=0;
 for(let i=0;i<112;i++){
  const bit=(frame[i>>3]>>(7-(i&7)))&1;
  const upper=(crc>>23)&1;
  crc=((crc<<1)|bit)&0xffffff;
  if(upper)crc^=CRC_POLY;
 }
 return crc===0;
}
const safeMod=(x,y)=>((x%y)+y)%y;
export function cprNL(lat){
 const a=Math.abs(lat);
 if(a<1e-9)return 59;
 if(a>=87)return 1;
 const ratio=(1-Math.cos(Math.PI/30))/(Math.cos(a*Math.PI/180)**2);
 const arg=Math.max(-1,Math.min(1,1-ratio));
 return Math.max(1,Math.floor(2*Math.PI/Math.acos(arg)));
}
export function decodeGlobalCPR(even,odd){
 if(!even || !odd || Math.abs(even.time-odd.time)>CPR_PAIR_MS)return null;
 const latEven=even.lat/131072,latOdd=odd.lat/131072;
 const j=Math.floor(59*latEven-60*latOdd+0.5);
 let a=(360/60)*(safeMod(j,60)+latEven);
 let b=(360/59)*(safeMod(j,59)+latOdd);
 if(a>=270)a-=360;
 if(b>=270)b-=360;
 if(Math.abs(a)>90 || Math.abs(b)>90 || cprNL(a)!==cprNL(b))return null;
 const useEven=even.time>=odd.time;
 const latitude=useEven?a:b, nl=cprNL(latitude);
 const ni=Math.max(1,nl-(useEven?0:1));
 const m=Math.floor((even.lon*(nl-1)-odd.lon*nl)/131072+0.5);
 let longitude=(360/ni)*(safeMod(m,ni)+(useEven?even.lon:odd.lon)/131072);
 if(longitude>=180)longitude-=360;
 if(!Number.isFinite(latitude)||!Number.isFinite(longitude))return null;
 if(Math.abs(latitude)>90||Math.abs(longitude)>180)return null;
 return {lat:latitude,lon:longitude};
}
function callsign(frame){
 let out="";
 for(let n=0;n<8;n++){
  const offset=40+6*n;
  let code=0;
  for(let b=0;b<6;b++){
   const bitIndex=offset+b;
   code=(code<<1)|((frame[bitIndex>>3]>>(7-(bitIndex&7)))&1);
  }
  out+=CALL_CHARS[code]||"";
 }
 return out.replaceAll("#","").replaceAll("_"," ").trim()||null;
}
export function decodeFrame(frame,time=Date.now()){
 if(!crcValid(frame))return null;
 const df=frame[0]>>3;
 if(df!==17 && df!==18)return null;
 const hex=Array.from(frame.subarray(1,4),b=>b.toString(16).padStart(2,"0")).join("");
 const tc=frame[4]>>3;
 const row={hex,seen:0,time};
 if(tc>=1&&tc<=4) row.flight=callsign(frame);
 if(tc>=9&&tc<=18){
  const rawAltitude=(frame[5]<<4)|(frame[6]>>4);
  if(rawAltitude&0x10){
   const n=((rawAltitude&0xfe0)>>1)|(rawAltitude&0x0f);
   row.alt_baro=n*25-1000;
  }
  row.cpr={
   odd:!!(frame[6]&4),
   lat:((frame[6]&3)<<15)|(frame[7]<<7)|(frame[8]>>1),
   lon:((frame[8]&1)<<16)|(frame[9]<<8)|frame[10],
   time
  };
 }
 return row;
}

function magnitude(bytes){
 const mag=new Uint16Array(Math.floor(bytes.length/2));
 for(let i=0,j=0;i+1<bytes.length;i+=2,j++){
  const a=bytes[i]-127.5,b=bytes[i+1]-127.5;
  mag[j]=Math.min(65535,Math.round(a*a+b*b));
 }
 return mag;
}
export function extractFrameCandidates(raw){
 const samples=raw instanceof Uint8Array?raw:new Uint8Array(raw);
 const mag=magnitude(samples), messages=[];
 // 8 us preamble = 16 magnitude samples at 2 Msps.
 // 112 bits follow: first or second half-microsecond has higher power.
 for(let j=0;j+240<mag.length;j++){
  const hi=mag[j]+mag[j+2]+mag[j+7]+mag[j+9];
  const lo=mag[j+1]+mag[j+3]+mag[j+4]+mag[j+5]+mag[j+6]+
            mag[j+8]+mag[j+10]+mag[j+11]+mag[j+12]+mag[j+13]+mag[j+14];
  if(hi<500 || hi*11<lo*12)continue;
  if(mag[j]<mag[j+1]*1.5 || mag[j+2]<mag[j+3]*1.5 ||
     mag[j+7]<mag[j+8]*1.5 || mag[j+9]<mag[j+10]*1.5)continue;
  const frame=new Uint8Array(14);
  let confident=true;
  for(let b=0;b<112;b++){
   const one=mag[j+16+2*b], zero=mag[j+17+2*b];
   if(Math.abs(one-zero)<20){confident=false;break;}
   if(one>zero)frame[b>>3]|=1<<(7-(b&7));
  }
  if(confident && (frame[0]>>3===17 || frame[0]>>3===18) && crcValid(frame)){
   messages.push({frame,sampleOffset:j});
   j+=240;
  }
 }
 return messages;
}
// Preserve the original external API used by existing browser regression tests.
export function extractFrames(raw){return extractFrameCandidates(raw).map(v=>v.frame)}
export class BrowserAircraftStore {
 constructor(){this.rows=new Map();this.messages=0;}
 ingest(frame,time=Date.now(),rfTiming=null){
  const m=decodeFrame(frame,time);
  if(!m)return false;
  let item=this.rows.get(m.hex);
  if(!item){item={hex:m.hex,firstSeen:time,updated:time};this.rows.set(m.hex,item)}
  item.updated=time;
  if(rfTiming)item.rfTiming=rfTiming;
  this.messages++;
  if(m.flight)item.flight=m.flight;
  if(Number.isFinite(m.alt_baro))item.alt_baro=m.alt_baro;
  if(m.cpr){
   item[m.cpr.odd?"odd":"even"]=m.cpr;
   const pos=decodeGlobalCPR(item.even,item.odd);
   if(pos){
    // CPR global coordinates need both actual frames and freshness.
    item.lat=pos.lat;item.lon=pos.lon;
    item.positionTime=time;
   }
  }
  return true;
 }
 snapshot(now=Date.now()){
  for(const [id,a] of this.rows)if(now-a.updated>AIRCRAFT_TTL_MS)this.rows.delete(id);
  // Guard against RAM buildup when hundreds of ICAO addresses are heard.
  if(this.rows.size>1500){
   const ordered=[...this.rows.entries()].sort((a,b)=>a[1].updated-b[1].updated);
   for(const [id] of ordered.slice(0,this.rows.size-1500))this.rows.delete(id);
  }
  return [...this.rows.values()].map(a=>{
   const row={hex:a.hex,flight:a.flight||undefined,alt_baro:a.alt_baro,
     seen:Math.max(0,(now-a.updated)/1000)};
   if(a.rfTiming)row.rf_timing={...a.rfTiming};
   if(Number.isFinite(a.positionTime) && now-a.positionTime<60000){
    row.lat=a.lat;row.lon=a.lon;
    row.seen_pos=Math.max(0,(now-a.positionTime)/1000);
   }
   return row;
  });
 }
}
let store,tail=new Uint8Array(0),bytes=0,lastPublish=0,totalSamples=0,lastFrameSample=-1;
function onIQ(buffer){
 if(!store)store=new BrowserAircraftStore();
 const incoming=new Uint8Array(buffer);
 if(incoming.byteLength<2 || incoming.byteLength>2*1024*1024)return;
 const joined=new Uint8Array(tail.byteLength+incoming.byteLength);
 joined.set(tail,0);joined.set(incoming,tail.byteLength);
 const messages=extractFrameCandidates(joined);
 const now=Date.now();
 // Real ADC sample offsets in sequential WebUSB chunks, nominal 2 Msps.
 // USB completion and JS Date.now() are NOT an absolute RF arrival timestamp.
 // An RTL2832U does not supply GPS-synchronized UTC timestamps here.
 const firstSample=totalSamples-tail.byteLength/2;
 for(const m of messages){
  const absoluteIndex=firstSample+m.sampleOffset;
  if(absoluteIndex<0 || absoluteIndex<=lastFrameSample)continue;
  lastFrameSample=absoluteIndex; // prevent double-counting a frame also present in the overlap tail
  store.ingest(m.frame,now,{
   arrival_sample_index:absoluteIndex,
   sample_period_us:1e6/SAMPLE_RATE,
   decoder_observed_unix_ms:now,
   transmit_timestamp_utc:null,
   receiver_hardware_utc:null,
   timing_clock:"unsynchronized RTL-SDR sample counter",
   timestamp_accuracy:"sample-index quantization only; UTC accuracy unknown"
  });
 }
 totalSamples+=incoming.byteLength/2;
 // Keep 256 IQ samples, enough to reconstruct a packet crossing chunks.
 tail=joined.slice(Math.max(0,joined.length-512));
 bytes+=incoming.byteLength;
 if(now-lastPublish>=1000){
  lastPublish=now;
  self.postMessage({type:"snapshot",aircraft:store.snapshot(now),
    messages:store.messages,receivedBytes:bytes,updatedAt:now});
 }
 self.postMessage({type:"ack"});
}
if(typeof self!=="undefined" && typeof self.addEventListener==="function"){
 self.addEventListener("message",event=>{
  const msg=event.data||{};
  if(msg.type==="iq" && msg.buffer instanceof ArrayBuffer){
   try{onIQ(msg.buffer);}
   catch(error){
    // Never strand the USB reader waiting for an ACK if one IQ block fails.
    self.postMessage({type:"error",message:String(error?.message||error).slice(0,160)});
    self.postMessage({type:"ack"});
   }
  }
  if(msg.type==="reset"){store=new BrowserAircraftStore();tail=new Uint8Array(0);bytes=0;lastPublish=0;totalSamples=0;lastFrameSample=-1;}
 });
}
