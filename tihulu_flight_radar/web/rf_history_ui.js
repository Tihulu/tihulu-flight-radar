"use strict";
/* RF Geolocation v2 UI integration. Shared native, paired and PWA frontend.
 * Explicit History Recorder starts OFF, never auto-enables SDR or uploads RF.
 */
(()=>{
 const $=id=>document.getElementById(id);
 const labels={live10:"LIVE · 10 min",liveX:"X-hour LIVE",best:"BEST Fit · session",
  history:"HISTORY · all",historyBest:"HISTORY BEST · weighted"};
 let mode="live10",latest=null,latestMode=null,calculated=0;
 const modelCache=new Map();
 const client=TihuluRFHistoryClient.create({
  api:(url,options)=>api(url,options),
  verified:(row,now)=>TihuluRFCoverage.recordedCircle(row,now),
  formatStatus:msg=>{$("rfModeCalculation").textContent=msg;},
  onResult:(kind,result,meta)=>{
   if(kind!==mode)return;
   latest=result;latestMode=kind;calculated=meta.at;
   modelCache.set(kind,result);show(result);paint();
  }
 });
 function display(legacy){
  if(mode==="best"){
   if(!rfBest)return {status:"insufficient",count:0,
    constraintsUsed:0,region:null,aircraftCircles:[]};
   return {status:"region",count:rfBest.aircraftCount||0,
    constraintsUsed:rfBest.constraintsUsed||0,
    liveCount:rfBest.liveCount,historyCount:rfBest.historyCount,
    geometryStatus:rfBest.geometryStatus,aircraftCircles:[],
    region:{lat:rfBest.lat,lon:rfBest.lon,
     extentKm:rfBest.displayedExtentKm,rawExtentKm:rfBest.rawExtentKm,
     kind:"session-best-model",possibleSamples:[],
     sampleCount:rfBest.sampleCount||0}};
  }
  return latestMode===mode&&latest?latest:
   {status:"insufficient",count:0,constraintsUsed:0,
    region:null,aircraftCircles:[],reason:"Waiting for model calculation"};
 }
 function show(model=display()){
  const current=labels[mode]||mode;
  $("rfModeLabel").textContent=current;
  $("rfHoursWrap").hidden=mode!=="liveX";
  const note=mode==="live10"?"Only RF observations from the last 10 minutes.":
   mode==="liveX"?"Only RF observations from the last "+$("rfHours").value+" hours.":
   mode==="best"?"The tightest saved legacy session model (may be older than live).":
   mode==="history"?"All verified RF constraints from the selected recording session.":
   "All verified historical constraints with extra weight for narrow radio horizons.";
  $("rfModeDescription").textContent=note;
  $("rfModeAircraft").textContent=String(model.count||0);
  $("rfModeFixes").textContent=String(model.constraintsUsed||0);
  $("rfModeSpread").textContent=
   model.status==="weighted"?
    "Weighted center · no calibrated spread":
   model.status==="region"&&Number.isFinite(model.region?.extentKm)?
    model.region.extentKm.toFixed(1)+" km · model":
   model.status==="no_overlap"?"No common area":
   model.status==="unresolved"?"Area unresolved":"—";
  if(mode==="historyBest"&&Number.isFinite(model.rmsViolationKm))
   $("rfModeCalculation").textContent=
    "Weighted all-circle violation RMS "+model.rmsViolationKm.toFixed(1)+
    " km · "+model.violatedConstraints+" violated bounds; NOT GPS or accuracy.";
 }
 function archiveStatus(stat){
  const picker=$("rfHistorySession"),prior=picker.value||"0";
  picker.replaceChildren();
  const auto=document.createElement("option");auto.value="0";
  auto.textContent="Latest session (automatic)";picker.append(auto);
  for(const row of stat.sessions||[]){
   const option=document.createElement("option");
   option.value=String(row.id);
   option.textContent="#"+row.id+" · "+new Date(row.started_ms).toLocaleString()+
    (Number.isFinite(row.observations)?" · "+row.observations+" fixes":"");
   picker.append(option);
  }
  picker.value=[...picker.options].some(o=>o.value===prior)?prior:"0";
  $("rfRecorderToggle").textContent=stat.recording?"Pause recording":"Start recording";
  $("rfArchiveStatus").textContent=(stat.recording?"Recording ON":"Recorder OFF")+
   " · session "+(stat.activeSessionId||stat.sessions?.[0]?.id||"none")+
   " · "+Number(stat.observations||0).toLocaleString()+" total saved observations";
  $("rfArchiveWarning").textContent=stat.warning||
   "No fixed 64-record or 2-hour cap. Native SQLite pauses if under 2 GiB free.";
 }
 function calculate(force=false){
  if(!rfLocatorActive)return;
  if(mode==="best"){show(display());paint();return;}
  client.settings(mode,$("rfHours").value,$("rfHistorySpeed").value);
  void client.calculate(mode,Number($("rfHours").value),{force});
 }
 function switchMode(){
  mode=$("rfMode").value;
  latest=null;latestMode=null;calculated=0;
  client.cancel();
  show(display());
  calculate(true);paint();
 }
 $("rfMode").addEventListener("change",switchMode);
 $("rfHours").addEventListener("change",()=>{
  if(mode==="liveX"){client.cancel();latest=null;latestMode=null;calculate(true);}
  show(display());paint();
 });
 $("rfHistorySpeed").addEventListener("change",()=>{
  client.settings(mode,$("rfHours").value,$("rfHistorySpeed").value);
  $("rfModeCalculation").textContent=
   "Processing profile: "+$("rfHistorySpeed").selectedOptions[0].textContent;
 });
 $("rfRecalculate").addEventListener("click",()=>{
  client.cancel();calculate(true);
 });
 $("rfRecorderToggle").addEventListener("click",async()=>{
  const button=$("rfRecorderToggle");button.disabled=true;
  try{
   const stat=await client.statusNow();
   archiveStatus(await client.recordAction(stat.recording?"pause":"start"));
   if(mode==="history"||mode==="historyBest"){
    client.cancel();latest=null;latestMode=null;calculate(true);
   }
  }catch(err){$("rfArchiveStatus").textContent="Recorder: "+String(err.message||err);}
  finally{button.disabled=false;}
 });
 $("rfHistorySession").addEventListener("change",()=>{
  try{
   client.selectSession(Number($("rfHistorySession").value));
   latest=null;latestMode=null;
   if(mode==="history"||mode==="historyBest")calculate(true);
   show(display());paint();
  }catch(err){$("rfArchiveStatus").textContent="Session selection: "+err.message;}
 });
 $("rfCompareModels").addEventListener("change",()=>paint());
 $("rfNewSession").addEventListener("click",async()=>{
  if(!window.confirm("Start a NEW physical receiver History session? Old RF records remain stored but will not be mixed with the new antenna location."))return;
  try{archiveStatus(await client.recordAction("new-session"));
   client.selectSession(0);
   $("rfHistorySession").value="0";
   latest=null;latestMode=null;calculate(true);
  }catch(err){$("rfArchiveStatus").textContent="New session: "+String(err.message||err);}
 });
 async function ingest(rows){
  await client.ingest(rows);
  if(rfLocatorActive&&mode!=="best"&&client.shouldRefresh())calculate();
 }
 function tick(){
  if(document.hidden||!state.connected||!rfLocatorActive)return;
  if(mode!=="best"&&client.shouldRefresh())calculate();
 }
 function comparisons(){
  if(!$("rfCompareModels").checked)return [];
  return [...modelCache.entries()].filter(([id,r])=>
   id!==mode&&r?.status==="region"&&Number.isFinite(r.region?.extentKm))
   .map(([id,result])=>({id,result}));
 }
 window.TihuluRFV2={display,show,ingest,tick,comparisons,getMode:()=>mode,client};
 show(display());
 void client.statusNow().then(archiveStatus).catch(err=>{
  $("rfArchiveStatus").textContent="Recorder not yet connected: "+err.message;
 });
 window.setInterval(tick,5000);
 window.setInterval(()=>{
  if(!document.hidden&&state.connected)
   void client.statusNow().then(archiveStatus).catch(()=>{});
 },30000);
})();
