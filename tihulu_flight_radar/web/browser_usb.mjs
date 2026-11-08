import {normalizeIqSampleBlock, platformFamily, explainUsbError, readOnlyUsbReport, probeUsbInterface} from "./usb_tools.mjs";
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
let claimProbeRunning=false;
const $=id=>document.getElementById(id);
const platform=platformFamily(navigator.userAgent||"");
let reportText="No USB diagnostic recorded.";
function showDiagnostic(text){
 reportText=String(text);
 const report=$("usbReport");
 if(report)report.textContent=reportText;
 const section=$("usbHelp");
 if(section)section.open=true;
}
$("usbCheck")?.addEventListener("click",async()=>{
 const status=await readOnlyUsbReport(navigator.usb,platform);
 showDiagnostic(status);
});
$("usbClaimTest")?.addEventListener("click",async()=>{
 if(device || chosenDevice || readLoop){
  tell("Stop this tab's SDR capture before running the separate USB interface-claim test.",true);
  return;
 }
 claimProbeRunning=true;
 $("usbClaimTest").disabled=true;
 $("usbStart").disabled=true;
 try{
  const result=await probeUsbInterface(navigator.usb);
  const line=result.ok
   ? result.summary
   : "USB test failed at "+result.stage+": "+result.errorName+": "+result.errorMessage;
  const extra=result.cleanupErrors?.length
   ? "\nRelease warning: "+result.cleanupErrors.join("; "):"";
  showDiagnostic(line+extra+(result.ok?"":"\n\n"+
    explainUsbError({name:result.errorName,message:result.errorMessage},platform)));
  tell(line,!result.ok);
 }finally{
  claimProbeRunning=false;
  $("usbClaimTest").disabled=false;
  $("usbStart").disabled=!Driver || !!device || !!readLoop;
 }
});
$("usbCopy")?.addEventListener("click",async()=>{
 try{
  await navigator.clipboard.writeText(reportText);
  tell("USB diagnostic copied; no USB serial numbers or raw IQ included.");
 }catch(error){tell("Clipboard unavailable: "+String(error?.message||error),true);}
});
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
 const report=explainUsbError(error,platform);
 showDiagnostic(report);
 return report.split("\n").slice(0,4).join(" ");
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
  window.tihuluTimingBatch?.(msg.timing_events||[],msg.timing_stats||null);
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
 if($("usbClaimTest"))$("usbClaimTest").disabled=false;
}
async function read(){
 let terminalError=null;
 try{
  while(!stopRequested && device){
   // @jtarrio/webrtlsdr 3.0.7 returns SampleBlock {frequency,
   // directSampling, data:ArrayBuffer}, NOT a bare ArrayBuffer.
   // The previous reader rejected every successful sample transfer!
   const hostStart=performance.now();
   const sampleBlock=await device.readSamples(65536);
   const hostReadMs=Math.max(0,performance.now()-hostStart);
   if(stopRequested)break;
   const view=normalizeIqSampleBlock(sampleBlock);
   if(view.byteLength>2*1024*1024)throw Error("WebUSB block exceeded safe 2 MiB bound.");
   const own=view.slice();
   bytes+=own.byteLength;
   // Worker signals ACK for backpressure; never queue unbounded IQ buffers.
   const accepted=new Promise(resolve=>ackResolve=resolve);
   worker.postMessage({type:"iq",buffer:own.buffer,host_read_ms:hostReadMs},[own.buffer]);
   await accepted;
  }
 }catch(error){
  if(!stopRequested){
   terminalError=error;
   tell("USB read failed: "+usbError(error),true);
  }
 }finally{
  await cleanup();
  window.tihuluUsbStopped?.();
  if(!terminalError && !alreadyReported){
   tell("Direct WebUSB receiver stopped; this tab released its device.");
   alreadyReported=true;
  }
 }
}
async function start(){
 if(!Driver || device || readLoop || !isUsable() || claimProbeRunning)return;
 if(window.tihuluUsbCanStart && !window.tihuluUsbCanStart()){
  tell("Disconnect the paired readsb bridge before choosing direct WebUSB. One SDR cannot be owned by two receivers.",true);
  return;
 }
 stopRequested=false;alreadyReported=false;
 $("usbStart").disabled=true;$("usbStop").disabled=false;
 if($('usbClaimTest'))$('usbClaimTest').disabled=true;
 try{
  // Keep navigator.usb.requestDevice within the click's user activation.
  const provider=new Driver({webusb:{
    requestDevice:async options=>{
      chosenDevice=await navigator.usb.requestDevice(options);
      return chosenDevice;
    }
  }});
  device=await provider.get();
  if(document.hidden || stopRequested){
   throw Error("Tab was hidden or stopped while opening USB; releasing this tab's device.");
  }
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
  const explanation=usbError(error);
  await cleanup();
  window.tihuluUsbStopped?.();
  tell(explanation,true);  // Do not overwrite the actual error with Stop.
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
window.tihuluTimingRecord=enabled=>worker?.postMessage({type:"timing_record",enabled:enabled===true});
window.tihuluTimingClear=()=>worker?.postMessage({type:"timing_clear"});
navigator.usb?.addEventListener("disconnect",()=>{
 if(device||chosenDevice)void stop();
});
// Give other SDR programs their dongle back when browsing away or hiding
// this tab; no background capture or device handle is intentionally retained.
document.addEventListener("visibilitychange",()=>{if(document.hidden && device)void stop()});
window.addEventListener("pagehide",()=>{if(device||chosenDevice)void stop()});
void preload();
