"use strict";
/* RF Geolocation v2 UI integration. Shared native, paired and PWA frontend.
 * Explicit History Recorder starts OFF, never auto-enables SDR or uploads RF.
 */
(()=>{
 const $=id=>document.getElementById(id);
 const labels={live10:"LIVE · 10 min",liveX:"X-hour LIVE",best:"BEST Fit · session",
  history:"HISTORY · all",historyBest:"HISTORY BEST · weighted"};
 let mode="live10",latest=null,latestMode=null,calculated=0;
 const modelCache=new Map(),modelInfo=new Map();
 const layerCheckboxes={live10:"rfLayerLive10",liveX:"rfLayerLiveX",
  best:"rfBestCircle",history:"rfLayerHistory",
  historyBest:"rfLayerHistoryBest"};
 const layerOrder=["live10","liveX","best","history","historyBest"];
 const taskQueue=[];
 let activeTask=null;
 const enabled=id=>!!$(layerCheckboxes[id])?.checked;
 const keyFor=id=>id==="liveX"?"liveX:"+$("rfHours").value:
  id==="history"||id==="historyBest"?
   id+":session:"+$("rfHistorySession").value:id;
 const interval=()=>$("rfHistorySpeed").value==="performance"?15000:60000;
 function layerState(){
  const on=layerOrder.filter(enabled);
  const calculated=on.filter(id=>id==="best"?
   !!rfBest:!!modelCache.get(id)&&modelInfo.get(id)?.key===keyFor(id)&&
    ["region","weighted"].includes(modelCache.get(id)?.status));
  $("rfCircleLayerStatus").textContent=
   on.length+" selected · "+calculated.length+" model(s) available"+
   (activeTask?" · calculating "+(labels[activeTask]||activeTask):"")+
   (on.some(id=>id==="historyBest")?
    " · HISTORY BEST is a point only, NOT a radius":"");
 }
 function stopTasks(){
  taskQueue.length=0;activeTask=null;client.cancel();
 }
 function pump(){
  if(!rfLocatorActive||activeTask||client.state().calculating)return;
  const next=taskQueue.shift();
  if(!next){layerState();return;}
  activeTask=next;
  client.settings(next,$("rfHours").value,$("rfHistorySpeed").value);
  layerState();
  void client.calculate(next,Number($("rfHours").value),{force:true})
   .catch(error=>{
    activeTask=null;
    $("rfModeCalculation").textContent="RF layer: "+String(error.message||error);
    pump();
   });
 }
 function enqueue(id,force=false){
  if(!rfLocatorActive||id==="best"||!layerOrder.includes(id))return;
  const info=modelInfo.get(id),key=keyFor(id);
  if(!force&&info?.key===key&&
      Date.now()-info.at<interval())return;
  if(activeTask===id||taskQueue.includes(id))return;
  taskQueue.push(id);pump();
 }
 function calculateVisible(force=false){
  if(!rfLocatorActive)return;
  // Active model is computed even if the corresponding map circle is hidden;
  // display-only layer toggles never change what the solver measures.
  enqueue(mode,force);
  for(const id of layerOrder)
   if(id!==mode&&enabled(id))enqueue(id,force);
  layerState();
 }
 const client=TihuluRFHistoryClient.create({
  api:(url,options)=>api(url,options),
  verified:(row,now)=>TihuluRFCoverage.recordedCircle(row,now),
  formatStatus:msg=>{$("rfModeCalculation").textContent=msg;},
  onResult:(kind,result,meta)=>{
   modelCache.set(kind,result);
   modelInfo.set(kind,{at:meta.at,key:keyFor(kind)});
   if(kind===mode){
    latest=result;latestMode=kind;calculated=meta.at;show(result);
   }
   paint();
  },
  onSettled:(kind,ok)=>{
   if(activeTask===kind)activeTask=null;
   if(!ok)modelInfo.set(kind,{at:Date.now(),key:keyFor(kind)});
   layerState();pump();
  }
 });
 function display(legacy){
  if(!rfLocatorActive)return {status:"disabled",count:0,
   constraintsUsed:0,region:null,aircraftCircles:[]};
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
  if(mode==="best"){show(display());paint();}
  else enqueue(mode,force);
  calculateVisible(force);
 }
 function switchMode(){
  mode=$("rfMode").value;stopTasks();
  const cached=modelCache.get(mode),info=modelInfo.get(mode);
  latest=info?.key===keyFor(mode)?cached:null;
  latestMode=latest?mode:null;calculated=info?.at||0;
  show(display());calculate(true);paint();
 }
 $("rfMode").addEventListener("change",switchMode);
 $("rfHours").addEventListener("change",()=>{
  stopTasks();modelCache.delete("liveX");modelInfo.delete("liveX");
  if(mode==="liveX"){latest=null;latestMode=null;}
  show(display());calculateVisible(true);paint();
 });
 $("rfHistorySpeed").addEventListener("change",()=>{
  if(!activeTask)
   client.settings(mode,$("rfHours").value,$("rfHistorySpeed").value);
  $("rfModeCalculation").textContent=
   "Processing profile: "+$("rfHistorySpeed").selectedOptions[0].textContent;
 });
 $("rfRecalculate").addEventListener("click",()=>{
  stopTasks();calculateVisible(true);
 });
 for(const id of layerOrder){
  $(layerCheckboxes[id]).addEventListener("change",()=>{
   if(id!=="best"&&enabled(id))enqueue(id,false);
   layerState();paint();
  });
 }
 $("rfLayerAll").addEventListener("click",()=>{
  for(const id of layerOrder)$(layerCheckboxes[id]).checked=true;
  persistRfViewPreferences();calculateVisible(false);paint();
 });
 $("rfLayerNone").addEventListener("click",()=>{
  for(const id of layerOrder)$(layerCheckboxes[id]).checked=false;
  persistRfViewPreferences();layerState();paint();
 });
 $("rfLayerRefresh").addEventListener("click",()=>{
  stopTasks();calculateVisible(true);paint();
 });
 $("rfRecorderToggle").addEventListener("click",async()=>{
  const button=$("rfRecorderToggle");button.disabled=true;
  try{
   const stat=await client.statusNow();
   archiveStatus(await client.recordAction(stat.recording?"pause":"start"));
   if(mode==="history"||mode==="historyBest"||
      enabled("history")||enabled("historyBest")){
    stopTasks();modelCache.delete("history");modelCache.delete("historyBest");
    modelInfo.delete("history");modelInfo.delete("historyBest");
    latest=null;latestMode=null;calculateVisible(true);
   }
  }catch(err){$("rfArchiveStatus").textContent="Recorder: "+String(err.message||err);}
  finally{button.disabled=false;}
 });
 $("rfHistorySession").addEventListener("change",()=>{
  try{
   stopTasks();client.selectSession(Number($("rfHistorySession").value));
   modelCache.delete("history");modelCache.delete("historyBest");
   modelInfo.delete("history");modelInfo.delete("historyBest");
   $("rfCompareModels").checked=false;
   if(mode==="history"||mode==="historyBest"){latest=null;latestMode=null;}
   calculateVisible(true);show(display());paint();
  }catch(err){$("rfArchiveStatus").textContent="Session selection: "+err.message;}
 });
 $("rfCompareModels").addEventListener("change",()=>paint());
 $("rfNewSession").addEventListener("click",async()=>{
  if(!window.confirm("Start a NEW physical receiver History session? Old RF records remain stored but will not be mixed with the new antenna location."))return;
  try{archiveStatus(await client.recordAction("new-session"));
   stopTasks();client.selectSession(0);client.resetRecent();
   // Prevent old antenna geometry and previous BEST from leaking into a
   // different physical receiver location after an explicit new session.
   rfHistory.clear();rfHistoryRevision++;clearRfBest();
   modelCache.clear();modelInfo.clear();
   $("rfCompareModels").checked=false;
   $("rfHistorySession").value="0";
   latest=null;latestMode=null;calculateVisible(true);
  }catch(err){$("rfArchiveStatus").textContent="New session: "+String(err.message||err);}
 });
 async function ingest(rows){
  await client.ingest(rows);
  if(rfLocatorActive&&$("rfHistorySpeed").value!=="manual")
   calculateVisible(false);
 }
 function tick(){
  if(document.hidden||!state.connected||!rfLocatorActive)return;
  if($("rfHistorySpeed").value!=="manual")calculateVisible(false);
 }
 function comparisons(){
  return layerOrder.filter(id=>enabled(id)&&id!=="best"&&id!==mode)
   .flatMap(id=>{
    const result=modelCache.get(id),info=modelInfo.get(id);
    return info?.key===keyFor(id)&&
     ["region","weighted"].includes(result?.status)&&result.region?
      [{id,result}]:[];
   });
 }
 function layerModel(id){
  if(id==="best")return rfBest;
  const info=modelInfo.get(id);
  return info?.key===keyFor(id)?modelCache.get(id):null;
 }
 window.TihuluRFV2={display,show,ingest,tick,comparisons,layerModel,
  layerEnabled:enabled,getMode:()=>mode,client};
 show(display());layerState();
 calculateVisible(false);
 void client.statusNow().then(archiveStatus).catch(err=>{
  $("rfArchiveStatus").textContent="Recorder not yet connected: "+err.message;
 });
 window.setInterval(tick,5000);
 window.setInterval(()=>{
  if(!document.hidden&&state.connected)
   void client.statusNow().then(archiveStatus).catch(()=>{});
 },30000);
})();
