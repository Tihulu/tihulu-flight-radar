// Pure helpers shared by GitHub Pages, installed PWA and native-hosted web UI.
// No privileged operating system interaction or USB device claiming occurs here.
export function normalizeIqSampleBlock(block) {
  // @jtarrio/webrtlsdr@3.0.7 returns SampleBlock with an ArrayBuffer .data,
  // and older adapters may return a typed array or bare ArrayBuffer.
  const raw=block?.data ?? block;
  let bytes;
  if(raw instanceof ArrayBuffer) bytes=new Uint8Array(raw);
  else if(ArrayBuffer.isView(raw))
    bytes=new Uint8Array(raw.buffer,raw.byteOffset,raw.byteLength);
  else throw new TypeError("Invalid RTL-SDR SampleBlock: I/Q ArrayBuffer missing");
  if(bytes.byteLength<2 || bytes.byteLength%2!==0 || bytes.byteLength>2*1024*1024)
    throw new RangeError("Invalid RTL-SDR I/Q buffer length");
  if(block?.frequency!=null && Number(block.frequency)!==1090000000)
    throw new RangeError("RTL-SDR frequency changed from 1090 MHz");
  if(block?.directSampling===true)
    throw new RangeError("RTL-SDR direct sampling is not the 1090 MHz tuner");
  return bytes;
}
export function platformFamily(ua=""){
  const text=String(ua).toLowerCase();
  if(/android/.test(text))return "android";
  if(/windows/.test(text))return "windows";
  if(/macintosh|mac os/.test(text))return "mac";
  if(/linux|x11/.test(text))return "linux";
  return "unknown";
}
export function explainUsbError(error,platform=platformFamily()){
  const name=String(error?.name||"Error");
  const message=String(error?.message||error||"Unknown USB error").slice(0,300);
  const cause=String(error?.cause?.message||"").slice(0,160);
  const full=(name+" "+message+" "+cause).toLowerCase();
  const note=[
    "Browser-only connection: no additional program or pairing token is required.",
    "USB chooser permission does NOT guarantee the device can be claimed.",
  ];
  if(/no device selected|notfounderror|cancel/.test(full))
    note.push("The browser chooser was cancelled or no RTL2832U was selected. Retry Choose RTL-SDR.");
  else if(/claim|busy|could not connect|using it in another application|interface/.test(full))
    note.push("A competing SDR decoder or the Linux DVB kernel driver may own this RTL-SDR. The browser cannot seize it.");
  else if(/notallowed|securityerror|access denied|permission denied/.test(full))
    note.push("USB access was denied by the browser or operating-system permissions.");
  else note.push("USB setup failed. Check browser support, USB permissions and whether another receiver owns this stick.");
  note.push("Close any other program using THIS receiver: Flight Radar native/readsb, Satellite Center, Gqrx, welle.io, rtl_test.");
  if(platform==="linux"){
    note.push(
      "Pop!_OS, Debian, Raspberry Pi OS — only if you choose to pause your local readsb service:",
      "  sudo systemctl stop readsb.service",
      "  systemctl is-active readsb.service   # expect inactive",
      "If still blocked, inspect (read-only):",
      "  lsusb -d 0bda:2838",
      "  lsusb -t",
      "Verified Nooelec 0bda:2838 case: readsb inactive but Driver=dvb_usb_rtl28xxu owned interface 0. Explicitly unbinding only that interface made Brave work.",
      "If this driver is bound, follow the opt-in, per-device Linux recovery guide; never assume every computer uses USB path 1-4:1.0.",
      "Use the optional downloaded repository helper: bash scripts/rtl-sdr-usb-interface.sh status, then release only if you choose.",
      "After release, DO NOT unplug/replug before WebUSB: Linux may immediately bind dvb_usb_rtl28xxu again.",
      "Release the WebUSB handle with Hard stop before re-binding DVB. No website can run sudo, unbind a kernel driver, or change permissions.",
      "If Driver=[none] but claim still fails, inspect separate USB permissions/udev rules. Do not chmod 777."
    );
  }else if(platform==="windows"){
    note.push("Windows may require a one-time WinUSB-compatible driver; WebUSB cannot install drivers.");
  }else if(platform==="mac"){
    note.push("Close RTL-SDR apps and retry in a Chromium browser; Safari has no WebUSB.");
  }
  note.push("Reload this page after releasing the receiver, then select the USB device again.");
  note.push("Original error: "+name+": "+message+(cause?" (cause: "+cause+")":""));
  return note.join("\n");
}
export async function readOnlyUsbReport(usb,platform="unknown"){
  if(!usb || typeof usb.getDevices!=="function")
    return "WebUSB unavailable: try HTTPS in desktop Brave/Chrome/Edge.";
  try{
    const grants=await usb.getDevices();
    const matching=grants.filter(d=>d.vendorId===0x0bda && [0x2838,0x2832].includes(d.productId));
    return [
      "Platform: "+platform+"; secure WebUSB permission API available.",
      "Previously permitted RTL2832U devices: "+matching.length+".",
      ...matching.map(d=>"  0bda:"+d.productId.toString(16).padStart(4,"0")+" "+String(d.productName||"RTL-SDR").slice(0,80)),
      "Permissions only: no USB handle opened; claim/free status is unknown.",
      "This page cannot stop readsb, unload a driver, modify udev or bypass USB permissions."
    ].join("\n");
  }catch(error){
    return "Read-only WebUSB permission check failed: "+String(error?.message||error);
  }
}
