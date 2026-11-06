/*
 * Device-owned browser RTL-SDR loop. No Python, readsb or companion server.
 * WebUSB permission is requested only from the explicit button click.
 * Driver is pinned to the same release used by Tihulu Satellite Center.
 * Worker receives raw IQ locally; the SDR bytes are NEVER uploaded.
 */
// Bundled by GitHub Actions from pinned Apache-2.0 @jtarrio/webrtlsdr 3.0.7.
// No third-party JavaScript executes from a runtime CDN on the public site.
const LIBRARY="./vendor/rtlsdr.mjs";
let Driver=null, device=null, chosenDevice=null, worker=null;
let stopRequested=false,readLoop=null,ackResolve=null,bytes=0,alreadyReported=false;
const $=id=>document.getElementById(id);
const tell=(message,error=false)=>{
 const el=$("usbStatus");
 if(el){el.textContent=String(message);el.dataset.error=error?"true":"false";}
 if(error)window.tihuluUsbError?.(String(message));
};
const isUsable=()=>!!(window.isSecureContext && navigator.usb);
async function preload(){
 if(!isUsable()){
  tell("WebUSB unavailable: use HTTPS with desktop Brave/Chrome/Edge. Firefox and Safari cannot access RTL-SDR USB.");
  return;
 }
 tell("Loading pinned browser RTL-SDR driver; no desktop installation is needed.");
 try{
  const mod=await import(LIBRARY);
  if(typeof mod.RTL2832U_Provider!=="function")throw Error("Missing RTL-SDR library export");
  Driver=mod.RTL2832U_Provider;
  $("usbStart").disabled=false;
  tell("WebUSB ready. Stop readsb/Gqrx/welle.io if they own your only RTL-SDR before choosing USB.");
 }catch(error){
  tell("Browser RTL-SDR driver could not load: "+error.message+
       ". The static GitHub Pages WebUSB bundle may be missing. No USB device was opened.",true);
 }
}
function usbError(error){
 const message=String(error?.message||error);
 if(/connect|claim|busy|permission|denied|interface/i.test(message)){
  return "USB could not be claimed: "+message+
    ". Another application (readsb/Gqrx/welle.io), the Linux DVB driver or USB permissions may own it. "+
    "The website cannot override OS permissions or stop other processes.";
 }
 return message;
}
function ack(){if(ackResolve){const callback=ackResolve;ackResolve=null;callback();}}
function processMessage(msg){
 if(msg.type==="ack"){ack();return;}
 if(msg.type==="error"){
  tell("In-browser Mode S decoder error: "+String(msg.message||"unknown"),true);
  void stop();
  return;
 }
 if(msg.type==="snapshot"){
  window.tihuluUsbSnapshot?.(msg);
  const count=Number(msg.messages)||0;
  tell("WebUSB 1090 MHz · "+count+" CRC-verified Mode S frames · "+
    (Number(msg.receivedBytes)/1048576).toFixed(1)+" MiB of real I/Q read. "+
    "Position appears only after a verified airborne CPR pair.");
 }
}
async function cleanup(){
 stopRequested=true;ack();
 const owned=device;
 device=null;
 if(owned){
  try{await owned.close();}catch(error){tell("USB close warning: "+error.message,true);}
 }else if(chosenDevice?.opened){
  try{await chosenDevice.close();}catch{/* only this tab's acquired device */}
 }
 chosenDevice=null;
 if(worker){worker.terminate();worker=null;}
 $("usbStop").disabled=true;
 $("usbStart").disabled=!Driver;
}
async function read(){
 try{
  while(!stopRequested && device){
   const raw=await device.readSamples(65536);
   if(stopRequested)break;
   const view=raw instanceof ArrayBuffer?new Uint8Array(raw):
     ArrayBuffer.isView(raw)?new Uint8Array(raw.buffer,raw.byteOffset,raw.byteLength):null;
   if(!view || view.byteLength<2)throw Error("No usable unsigned 8-bit interleaved I/Q samples returned.");
   if(view.byteLength>2*1024*1024)throw Error("WebUSB block exceeded safe 2 MiB bound.");
   const own=view.slice();
   bytes+=own.byteLength;
   // Worker signals ACK for backpressure; never queue unbounded IQ buffers.
   const accepted=new Promise(resolve=>ackResolve=resolve);
   worker.postMessage({type:"iq",buffer:own.buffer},[own.buffer]);
   await accepted;
  }
 }catch(error){
  if(!stopRequested)tell("USB read failed: "+usbError(error),true);
 }finally{
  await cleanup();
  window.tihuluUsbStopped?.();
  if(!alreadyReported){tell("Direct WebUSB receiver stopped; this tab released its device.");alreadyReported=true;}
 }
}
async function start(){
 if(!Driver || device || readLoop || !isUsable())return;
 if(window.tihuluUsbCanStart && !window.tihuluUsbCanStart()){
  tell("Disconnect the paired readsb bridge before choosing direct WebUSB. One SDR cannot be owned by two receivers.",true);
  return;
 }
 stopRequested=false;alreadyReported=false;
 $("usbStart").disabled=true;$("usbStop").disabled=false;
 try{
  // Keep navigator.usb.requestDevice within the click's user activation.
  const provider=new Driver({webusb:{
    requestDevice:async options=>{
      chosenDevice=await navigator.usb.requestDevice(options);
      return chosenDevice;
    }
  }});
  device=await provider.get();
  // Never tune to a frequency other than the public ADS-B receive channel.
  await device.setSampleRate(2000000);
  await device.setCenterFrequency(1090000000);
  await device.setGain(null);
  await device.resetBuffer();
  worker=new Worker("./adsb_worker.mjs",{type:"module",name:"tihulu-mode-s"});
  worker.addEventListener("message",event=>processMessage(event.data||{}));
  worker.addEventListener("error",event=>{
   tell("In-browser ADS-B decoder worker failed: "+event.message,true);
   stop();
  });
  worker.postMessage({type:"reset"});
  bytes=0;
  window.tihuluUsbStarted?.();
  tell("WebUSB active at 1090 MHz · scanning genuine IQ for CRC-verified ADS-B.");
  readLoop=read().finally(()=>{readLoop=null;});
 }catch(error){
  tell(usbError(error),true);
  await cleanup();
  window.tihuluUsbStopped?.();
 }
}
async function stop(){
 stopRequested=true;
 ack();
 // Closing first interrupts any pending USB transfer; cleanup is idempotent.
 const owned=device;
 if(owned){try{await owned.close();}catch{/* read() will also cleanup */}}
 if(readLoop){await Promise.race([readLoop,new Promise(resolve=>setTimeout(resolve,700))]);}
 await cleanup();
 window.tihuluUsbStopped?.();
 tell("WebUSB stopped and this tab's RTL-SDR device released.");
}
$("usbStart").disabled=true;
$("usbStop").disabled=true;
$("usbStart").addEventListener("click",()=>{void start()});
$("usbStop").addEventListener("click",()=>{void stop()});
window.tihuluStopUsb=stop;
navigator.usb?.addEventListener("disconnect",()=>{
 if(device||chosenDevice)void stop();
});
// Give other SDR programs their dongle back when browsing away or hiding
// this tab; no background capture or device handle is intentionally retained.
document.addEventListener("visibilitychange",()=>{if(document.hidden && device)void stop()});
window.addEventListener("pagehide",()=>{if(device||chosenDevice)void stop()});
void preload();
