"use strict";
/* Resizable native/browser aircraft side panel. The map keeps remaining width.
 * No pointer lock, service call or receiver side effect. */
(()=>{
 const bar=document.getElementById("aircraftSideSplitter");
 const layout=document.querySelector(".layout");
 if(!bar||!layout)return;
 const key="tihulu-flight-radar-aircraft-side-width";
 const defaultWidth=580,minimum=380;
 let width=defaultWidth,down=null;
 const viewportWidth=()=>layout.getBoundingClientRect().width||
  document.documentElement.clientWidth;
 const maxWidth=()=>Math.max(minimum,Math.min(820,viewportWidth()-360));
 const clamp=v=>Math.round(Math.max(minimum,Math.min(maxWidth(),v)));
 const set=(value,persist=false)=>{
  width=clamp(value);
  document.documentElement.style.setProperty("--flight-side-width",width+"px");
  bar.setAttribute("aria-valuemax",String(maxWidth()));
  bar.setAttribute("aria-valuenow",String(width));
  bar.setAttribute("aria-valuetext",width+" px wide");
  if(persist)try{localStorage.setItem(key,String(width));}catch{}
  // Already-registered map resize listener keeps canvas and overlay aligned.
  if(typeof window.dispatchEvent==="function"&&
     typeof Event==="function")window.dispatchEvent(new Event("resize"));
 };
 try{
  const saved=Number(localStorage.getItem(key));
  if(Number.isFinite(saved)&&saved>=minimum&&saved<=820)width=saved;
 }catch{}
 bar.addEventListener("pointerdown",e=>{
  if(e.button!==0||getComputedStyle(bar).display==="none")return;
  down={x:e.clientX,w:width,pointer:e.pointerId};
  bar.setPointerCapture?.(e.pointerId);e.preventDefault();
 });
 bar.addEventListener("pointermove",e=>{
  if(!down||e.pointerId!==down.pointer)return;
  set(down.w+down.x-e.clientX);
 });
 function finish(e){
  if(!down||e.pointerId!==down.pointer)return;
  down=null;set(width,true);
  if(bar.hasPointerCapture?.(e.pointerId))bar.releasePointerCapture(e.pointerId);
 }
 bar.addEventListener("pointerup",finish);
 bar.addEventListener("pointercancel",finish);
 bar.addEventListener("dblclick",()=>set(defaultWidth,true));
 bar.addEventListener("keydown",e=>{
  if(!["ArrowLeft","ArrowRight","Home"].includes(e.key))return;
  e.preventDefault();
  set(e.key==="Home"?defaultWidth:width+(e.key==="ArrowLeft"?30:-30),true);
 });
 window.addEventListener("resize",()=>{
  const adjusted=clamp(width);
  if(adjusted!==width){width=adjusted;
   document.documentElement.style.setProperty("--flight-side-width",width+"px");
   bar.setAttribute("aria-valuenow",String(width));}
 });
 set(width);
})();
