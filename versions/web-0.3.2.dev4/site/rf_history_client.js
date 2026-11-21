"use strict";
/* Explicitly started history recording; browsers use IndexedDB and native
 * desktop uses authenticated, radio-only SQLite in the local bridge.
 * No Internet positions are ever converted into RF evidence.
 */
const TihuluRFHistoryClient=(()=>{
 const DB="tihulu-rf-history-v1";
 const MAX_WINDOW_MS=48*3600000;
 const BATCH=5000;
 const MODE_IDS=["live10","liveX","best","history","historyBest"];
 const isNative=()=>Boolean(window.tihuluNativeDesktop);
 function openDb(){
  return new Promise((resolve,reject)=>{
   if(!globalThis.indexedDB){reject(Error("IndexedDB unavailable"));return;}
   const req=indexedDB.open(DB,2);
   req.onupgradeneeded=()=>{
    const db=req.result;
    if(!db.objectStoreNames.contains("fixes")){
     const fixes=db.createObjectStore("fixes",{keyPath:"id",autoIncrement:true});
     fixes.createIndex("session","session",{unique:false});
    }
    if(!db.objectStoreNames.contains("sessions"))
     db.createObjectStore("sessions",{keyPath:"id"});
   };
   req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);
  });
 }
 function client({api,verified,formatStatus,onResult,onSettled}){
  let db=null,enabled=false,session=0,viewSession=0,status={},recent=[],last=new Map();
  const newestDirectRf=new Map();
  let startedHere=false;
  let worker=null,job=0,mode="live10",hours=2,profile="balanced";
  let lastCalculation=0,calculating=false,loaded=0,currentResult=null;
  let lastHistoryKey=null,lastHistoryCount=-1,pendingHistoryKey=null,pendingHistoryCount=0;
  const notify=msg=>{if(formatStatus)formatStatus(msg);};
  async function open(){if(!db)db=await openDb();return db;}
  function remember(rows){
   const now=Date.now(),accepted=[];
   for(const row of rows||[]){
    const r=verified(row,now);
    if(!r||!TihuluRFHistoryModels.valid(r))continue;
    const hex=r.hex.toLowerCase(),previous=last.get(hex);
    // Keep a separate current-position snapshot. Stationary/slow aircraft
    // must count as current LIVE even when path-distance sampling rejects
    // a redundant archive record.
    newestDirectRf.set(hex,{...r,
     capturedAtMs:Number.isFinite(r.observationTimeMs)?
      r.observationTimeMs:r.capturedAtMs});
    if(previous){
     const decision=TihuluRFCoverage.trackSampleDecision(previous,r);
     if(!decision.keep)continue;
    }
    last.set(hex,r);recent.push(r);accepted.push(r);
   }
   const min=now-MAX_WINDOW_MS;
   if(recent.length&&recent[0].capturedAtMs<min)
    recent=recent.filter(r=>r.capturedAtMs>=min);
   return accepted;
  }
  async function ingest(rows){
   const accepted=remember(rows);
   if(!enabled||!accepted.length||isNative())return;
   try{
    await open();
    await new Promise((resolve,reject)=>{
     const tx=db.transaction("fixes","readwrite");
     const os=tx.objectStore("fixes");
     for(const r of accepted){
      // Minimal RF data only, not the original aircraft or Internet JSON.
      os.add({session,hex:r.hex,lat:r.lat,lon:r.lon,
       radiusKm:r.radiusKm,altitudeFeet:r.altitudeFeet,
       speedKt:r.speedKt,headingDeg:r.headingDeg,
       capturedAtMs:r.capturedAtMs,recorded_rf:true});
     }
     tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);
   });
   }catch(error){enabled=false;notify("Browser History recording stopped: "+error.message);}
  }
  async function statusNow(){
   if(isNative()){
    status=await api("/api/rf-history/status");enabled=!!status.recording;
    session=status.activeSessionId||0;
    return status;
   }
   await open();
   let count=0,sessions=[];
   await new Promise((resolve,reject)=>{
    const tx=db.transaction(["fixes","sessions"],"readonly");
    const c=tx.objectStore("fixes").count();
    const q=tx.objectStore("sessions").getAll();
    c.onsuccess=()=>{count=c.result;};
    q.onsuccess=()=>{sessions=q.result.sort((a,b)=>b.id-a.id).slice(0,40);};
    tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);
   });
   status={recording:enabled,activeSessionId:session,
    sessions:sessions.map(x=>({id:x.id,started_ms:x.started_ms,observations:x.observations??null})),
    observations:count,source:"verified browser SDR",diskBytes:null};
   return status;
  }
  async function recordAction(action){
   if(!["start","pause","new-session"].includes(action))throw Error("Unknown recording action");
   if(isNative()){
    status=await api("/api/rf-history/config",{
     method:"POST",headers:{"Content-Type":"application/json"},
     body:JSON.stringify({action})
    });
    enabled=!!status.recording;
    session=status.activeSessionId||0;
   }else{
    await open();
    if(action==="pause"){enabled=false;}
    else if(action==="new-session"||!startedHere||!session){
     session=Date.now();last.clear();enabled=true;startedHere=true;
     await new Promise((resolve,reject)=>{
      const tx=db.transaction("sessions","readwrite");
      tx.objectStore("sessions").put({id:session,started_ms:session});
      tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);
     });
    }else enabled=true;
   }
   notify(enabled?"History recording ON · session "+session:
    "History recording paused; stored observations retained.");
   return statusNow();
  }
  async function streamDbToWorker(send){
   await open();
   await new Promise((resolve,reject)=>{
    const tx=db.transaction("fixes","readonly");
    const index=tx.objectStore("fixes").index("session");
    const selected=viewSession||session||status.sessions?.[0]?.id||0;
    const req=index.openCursor(IDBKeyRange.only(selected));
    let batch=[];
    req.onsuccess=()=>{
     const cursor=req.result;
     if(!cursor){
      if(batch.length)send(batch);
      resolve();return;
     }
     batch.push(cursor.value);
     if(batch.length===BATCH){send(batch);batch=[];}
     cursor.continue();
    };
    req.onerror=()=>reject(req.error);
    tx.onerror=()=>reject(tx.error);
   });
  }
  async function streamNativeToWorker(send){
   const stat=await statusNow(),sid=viewSession||stat.activeSessionId||stat.sessions?.[0]?.id;
   if(!sid)return;
   let after=0,more=true,pageCount=0;
   while(more){
    const result=await api("/api/rf-history/records?session="+sid+
     "&after="+after+"&limit="+BATCH);
    if(result.records?.length)send(result.records);
    after=result.nextAfterId;
    more=!!result.hasMore;
    pageCount++;
    if(pageCount>1000000)throw Error("History pagination safety limit");
   }
  }
  function cancel(){
   job++;
   if(worker){worker.terminate();worker=null;}
   calculating=false;
  }
  async function calculate(nextMode=mode,nextHours=hours,{force=false}={}){
   if(!MODE_IDS.includes(nextMode))throw Error("Invalid RF model mode");
   mode=nextMode;hours=Math.max(1,Math.min(48,Number(nextHours)||2));
   if(calculating)return;
   if(!force&&Date.now()-lastCalculation<
     (profile==="performance"?15000:60000))return;
   if(!force&&(mode==="history"||mode==="historyBest")&&lastHistoryKey){
    try{
     const stat=await statusNow(),sid=viewSession||stat.activeSessionId||
      stat.sessions?.[0]?.id||0;
     const amount=stat.sessions?.find(r=>r.id===sid)?.observations??stat.observations;
     const key=mode+":"+sid;
     if(key===lastHistoryKey&&amount===lastHistoryCount){
      lastCalculation=Date.now();
      notify("History cache reused: "+Number(amount).toLocaleString()+
       " stored RF records unchanged; no repeat full-archive scan.");
      return;
     }
    }catch{} // If a source is unavailable, surface its normal solver error.
   }
   cancel();calculating=true;loaded=0;
   const task=job;
   notify("Calculating "+mode+" using verified RF observations…");
   try{
    const w=new Worker("./rf_history_worker.js");
    worker=w;
    w.onmessage=e=>{
     const d=e.data||{};
     if(d.job!==task)return;
     if(d.type==="batch"){loaded=d.loaded;}
     if(d.type==="progress"){
      notify("History "+d.phase+" · "+d.processed.toLocaleString()+" / "+
       d.total.toLocaleString()+" observations");
     }
     if(d.type==="error"){
      calculating=false;notify("RF solver: "+d.error);
      w.terminate();if(worker===w)worker=null;
      onSettled?.(mode,false);
     }
     if(d.type==="result"){
      calculating=false;currentResult=d.result;lastCalculation=Date.now();
      if(mode==="history"||mode==="historyBest"){
       lastHistoryKey=pendingHistoryKey;lastHistoryCount=pendingHistoryCount;
      }
      onResult?.(mode,d.result,{loaded:d.total,at:lastCalculation});
      notify("Solved "+mode+": "+d.total.toLocaleString()+" verified RF circles · "+
       d.result.status+(d.result.status==="weighted"
       ?" · weighted diagnostic, NOT GPS":""));
      w.terminate();if(worker===w)worker=null;
      onSettled?.(mode,true);
     }
    };
    w.onerror=e=>{
     calculating=false;notify("History worker error: "+e.message);
     w.terminate();if(worker===w)worker=null;
     onSettled?.(mode,false);
    };
    w.postMessage({type:"clear",job:task});
    const send=rows=>{
     if(job!==task)return;
     w.postMessage({type:"batch",job:task,records:rows});
     loaded+=rows.length;
     if(loaded>0&&loaded%BATCH===0)
      notify("Loading RF constraints: "+loaded.toLocaleString());
    };
    if(mode==="history"||mode==="historyBest"){
     const stat=await statusNow(),sid=viewSession||stat.activeSessionId||
      stat.sessions?.[0]?.id||0;
     pendingHistoryKey=mode+":"+sid;
     pendingHistoryCount=stat.sessions?.find(r=>r.id===sid)?.observations??
      stat.observations;
     if(isNative())await streamNativeToWorker(send);
     else await streamDbToWorker(send);
    }else{
     const now=Date.now(),source=recent.filter(r=>r.capturedAtMs>=
      now-(mode==="live10"?600000:hours*3600000));
     const existing=new Set(source.map(r=>[r.hex,r.observationTimeMs,
      r.lat,r.lon].join(":")));
     for(const r of newestDirectRf.values()){
      if(now-r.capturedAtMs>(mode==="live10"?600000:hours*3600000))continue;
      const key=[r.hex,r.observationTimeMs,r.lat,r.lon].join(":");
      if(!existing.has(key)){source.push(r);existing.add(key);}
     }
     for(let i=0;i<source.length;i+=BATCH)send(source.slice(i,i+BATCH));
    }
    if(job===task)w.postMessage({
     type:"solve",job:task,mode,hours,nowMs:Date.now()});
   }catch(error){
    if(job===task){
     const failedMode=mode;cancel();
     notify("History unavailable: "+String(error.message||error));
     onSettled?.(failedMode,false);
    }
   }
  }
  function settings(nextMode,nextHours,nextProfile){
   if(MODE_IDS.includes(nextMode))mode=nextMode;
   hours=Math.max(1,Math.min(48,Number(nextHours)||2));
   if(["balanced","performance","manual"].includes(nextProfile))profile=nextProfile;
  }
  function shouldRefresh(){return profile!=="manual"&&!calculating&&
   Date.now()-lastCalculation>=(profile==="performance"?15000:60000);}
  function selectSession(id){
   if(!Number.isSafeInteger(Number(id))||Number(id)<0)throw Error("Invalid History session");
   viewSession=Number(id);cancel();lastCalculation=0;currentResult=null;
  }
  function resetRecent(){
   recent=[];last.clear();newestDirectRf.clear();
   cancel();lastCalculation=0;currentResult=null;
  }
  return {ingest,recordAction,statusNow,calculate,cancel,settings,shouldRefresh,
   selectSession,resetRecent,
   state:()=>({enabled,session,viewSession,mode,hours,profile,loaded,calculating,
    lastCalculation,result:currentResult})};
 }
 return {create:client,MODES:MODE_IDS};
})();
if(typeof window!=="undefined")window.TihuluRFHistoryClient=TihuluRFHistoryClient;
if(typeof module!=="undefined"&&module.exports)module.exports=TihuluRFHistoryClient;
