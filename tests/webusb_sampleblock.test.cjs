"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const {pathToFileURL}=require("node:url");
const web=path.join(__dirname,"../tihulu_flight_radar/web");
const tools=import(pathToFileURL(path.join(web,"usb_tools.mjs")).href);

test("Pinned webrtlsdr 3.0.7 SampleBlock.data is accepted and retains real IQ bytes",async()=>{
 const {normalizeIqSampleBlock:parse}=await tools;
 const original=new Uint8Array([10,20,30,40,50,60]);
 const block={frequency:1090000000,directSampling:false,data:original.buffer};
 assert.deepEqual([...parse(block)],[...original]);
 const slice=new Uint8Array(new Uint8Array([0,1,2,3,4,5]).buffer,2,4);
 assert.deepEqual([...parse({frequency:1090000000,data:slice})],[2,3,4,5]);
 assert.deepEqual([...parse(original.buffer)],[...original]);
});
test("Rejects unsupported streaming data, wrong frequency, direct sampling and broken I/Q boundaries",async()=>{
 const {normalizeIqSampleBlock:parse}=await tools;
 assert.throws(()=>parse({frequency:1090000000}),/ArrayBuffer missing/);
 assert.throws(()=>parse({frequency:1090000000,data:new Uint8Array(3).buffer}),/length/);
 assert.throws(()=>parse({frequency:100000000,data:new Uint8Array(4).buffer}),/frequency/);
 assert.throws(()=>parse({frequency:1090000000,directSampling:true,data:new Uint8Array(4).buffer}),/direct sampling/);
 assert.throws(()=>parse({data:new Uint8Array(2*1024*1024+2).buffer}),/length/);
});
test("WebUSB claim failure provides manual safe readsb steps, does not pretend to have freed USB",async()=>{
 const {explainUsbError,platformFamily}=await tools;
 assert.equal(platformFamily("Mozilla/5.0 (X11; Linux x86_64) Brave"),"linux");
 const report=explainUsbError({message:"Could not connect to the RTL-SDR stick. Are you using it in another application?"},"linux");
 assert.match(report,/readsb/);
 assert.match(report,/sudo systemctl stop readsb.service/);
 assert.match(report,/website cannot/i);
 assert.doesNotMatch(report,/chmod 777|killall|rmmod|udevadm trigger/);
});
test("Read-only USB diagnostics enumerate permission grants without opening or claiming any device",async()=>{
 const {readOnlyUsbReport}=await tools;
 let calls=0;
 const report=await readOnlyUsbReport({
  async getDevices(){calls++;return [{vendorId:0x0bda,productId:0x2838,productName:"NESDR SMArt v5"}]},
  async requestDevice(){throw Error("Never request USB during diagnostic")},
  async claimInterface(){throw Error("Never claim USB during diagnostic")}
 },"linux");
 assert.equal(calls,1);
 assert.match(report,/0bda:2838/);
 assert.match(report,/claim\/free status is unknown/);
});
test("PWA has diagnostic controls, valid module references and updated offline cache",()=>{
 const html=fs.readFileSync(path.join(web,"index.html"),"utf8");
 const usb=fs.readFileSync(path.join(web,"browser_usb.mjs"),"utf8");
 const sw=fs.readFileSync(path.join(web,"sw.js"),"utf8");
 const bridge=fs.readFileSync(path.join(__dirname,"../tihulu_flight_radar/bridge.py"),"utf8");
 for(const id of ["usbCheck","usbCopy","usbReport","usbHelp"])
  assert.match(html,new RegExp('id="'+id+'"'));
 assert.match(usb,/normalizeIqSampleBlock\(sampleBlock\)/);
 assert.match(usb,/explainUsbError\(error,platform\)/);
 assert.match(sw,/shell-v3/);
 assert.match(sw,/usb_tools\.mjs/);
 assert.match(sw,/vendor\/rtlsdr\.mjs/);
 assert.match(bridge,/usb_tools\.mjs/);
});
