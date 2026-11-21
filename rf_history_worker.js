"use strict";
/* Separate CPU worker for expensive uncapped RF history calculations.
 * The UI remains responsive. Data is sent in bounded 5k batches.
 */
importScripts("./rf_history_models.js");
let records=[];
self.onmessage=event=>{
 const d=event.data||{};
 if(d.type==="clear"){records=[];self.postMessage({type:"cleared",job:d.job});return;}
 if(d.type==="batch"){
  if(Array.isArray(d.records))for(const r of d.records)
   if(TihuluRFHistoryModels.valid(r))records.push(r);
  self.postMessage({type:"batch",job:d.job,loaded:records.length});
  return;
 }
 if(d.type==="solve"){
  const mode=d.mode==="historyBest"?"historyBest":d.mode==="live10"?"live10":
   d.mode==="liveX"?"liveX":"history";
  try{
   const result=TihuluRFHistoryModels.solve(records,{
    mode,hours:d.hours||2,nowMs:d.nowMs||Date.now(),
    onProgress:detail=>self.postMessage({type:"progress",job:d.job,...detail})
   });
   self.postMessage({type:"result",job:d.job,mode,result,total:records.length});
  }catch(error){
   self.postMessage({type:"error",job:d.job,error:String(error.message||error)});
  }finally{records=[];}
 }
};
