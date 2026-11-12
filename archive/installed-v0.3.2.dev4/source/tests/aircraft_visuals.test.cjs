"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.join(__dirname,"../tihulu_flight_radar");
const main=fs.readFileSync(path.join(root,"web/app.js"),"utf8");
const tar=fs.readFileSync(path.join(root,"tar_overlay.py"),"utf8");
const classic=fs.readFileSync(path.join(root,"map.html"),"utf8");
const html=fs.readFileSync(path.join(root,"web/index.html"),"utf8");
const css=fs.readFileSync(path.join(root,"web/style.css"),"utf8");
function functionSource(src,name){
 const start=src.indexOf("function "+name+"(");
 if(start<0)throw Error("function not found: "+name);
 const end=src.indexOf("\n}",start);
 if(end<0)throw Error("function never closes: "+name);
 return src.slice(start,end+2);
}
const stops=src=>[...src.matchAll(/\[(0|2000|6000|10000|18000|26000|35000|40000),["'](#[0-9a-f]{6})["']\]/g)]
 .map(([,n,c])=>[Number(n),c]);
test("All airplane views share exactly the same altitude color ramp",()=>{
 const mainStops=stops(main),tarStops=stops(tar),classicStops=stops(classic);
 const expected=[0,2000,6000,10000,18000,26000,35000,40000];
 assert.deepEqual(mainStops.map(x=>x[0]),expected);
 assert.deepEqual(mainStops,tarStops);
 assert.deepEqual(mainStops,classicStops);
 assert.match(css,/linear-gradient\(to right/);
 assert.match(html,/altitude-ramp/);
});
const palette=main.match(/const ALTITUDE_STOPS = \[[\s\S]*?\];/)[0];
const altitude=vm.runInNewContext(
 palette+"\n"+functionSource(main,"aircraftAltitude")+"\n"+
 functionSource(main,"altitudeColor")+"\naltitudeColor");
const mark=vm.runInNewContext(functionSource(main,"aircraftSourceBadge")+"\naircraftSourceBadge");
test("Altitude hue is not a source category, unknown altitude stays grey",()=>{
 assert.equal(altitude({alt_baro:0}),"#f36b3e");
 assert.equal(altitude({alt_baro:26000}),"#417ded");
 assert.equal(altitude({alt_baro:40000}),"#e44bc3");
 assert.equal(altitude({alt_baro:undefined}),"#abb6c5");
 assert.equal(altitude({alt_baro:"ground"}),"#f36b3e");
 assert.equal(altitude({alt_baro:26000,sources:["antenna"]}),altitude({alt_baro:26000,sources:["internet"]}));
 assert.equal(altitude({alt_baro:26000,sources:["antenna","internet"]}),"#417ded");
 assert.equal(mark({sources:["antenna"]}),"R");
 assert.equal(mark({sources:["internet"]}),"I");
 assert.equal(mark({sources:["antenna","internet"]}),"I/R");
});
test("Main map plane silhouette and I/R badges are drawn independently",()=>{
 const paint=vm.runInNewContext(palette+"\n"+functionSource(main,"aircraftAltitude")+
  "\n"+functionSource(main,"altitudeColor")+
  "\n"+functionSource(main,"aircraftSourceBadge")+
  "\n"+functionSource(main,"paintAircraft")+"\npaintAircraft");
 for(const [sources,expected] of [
  [["antenna"],"R"],[["internet"],"I"],[["antenna","internet"],"I/R"]
 ]){
  const texts=[],fills=[],coords=[];
  const ctx={
   save(){},restore(){},translate(){},rotate(){},beginPath(){},closePath(){},
   moveTo(...v){coords.push(v);},lineTo(...v){coords.push(v);},
   stroke(){},fill(){fills.push(this.fillStyle);},fillRect(){},strokeRect(){},
   fillText(...v){texts.push(v[0]);}
  };
  paint(ctx,{alt_baro:26000,sources,track:95},100,100);
  assert.ok(coords.length>=12,"airplane has full wings and tailplane");
  assert.deepEqual(fills,["#417ded"]);
  assert.ok(texts.includes(expected));
 }
});
test("tar1090 overlays a real airplane for Internet, source badge only for native RF planes",()=>{
 const code=tar.match(/OVERLAY_JS = r"""([\s\S]*?)"""/)[1];
 const classes={};
 for(const n of ["Style","Icon","Text","Fill","Stroke"]){
  classes[n]=class {constructor(options){this.options=options;}};
 }
 class VecSource {
  constructor(){this.features=[];}
  addFeature(f){this.features.push(f);}
  clear(){this.features=[];}
  getFeatures(){return this.features;}
 }
 class VecLayer {
  constructor(options){this.options=options;this.visible=true;}
  setVisible(v){this.visible=v;}
 }
 class Feature {
  constructor(attrs){this.attrs=attrs;}
  get(k){return this.attrs[k];}
 }
 const layers=[];
 const create=()=>({style:{},children:[],isConnected:false,
  appendChild(e){this.children.push(e);},
  replaceChildren(){this.children=[];},
  setAttribute(){}});
 const ctx={
  window:{},Map,Set,Object,Array,Number,Math,Date,encodeURIComponent,
  OLMap:{addLayer:l=>layers.push(l)},
  g:{planes:{
   "3c1234":{position:[7.1,50.9],seen:2,seen_pos:2,track:90,
     alt_baro:26000,visible:true}
  }},
  ol:{
   source:{Vector:VecSource},layer:{Vector:VecLayer},Feature,
   geom:{Point:class {constructor(coords){this.coords=coords;}}},
   proj:{fromLonLat:p=>p},style:classes
  },
  document:{
   getElementById:()=>null,
   createElement:()=>create(),
   createTextNode:t=>({value:t}),
   body:{appendChild:e=>{e.isConnected=true;}}
  }
 };
 const fn=vm.runInNewContext(code,ctx);
 const result=fn({aircraft:[
  {hex:"3c1234",lat:50.9,lon:7.1,flight:"RADIO1",alt_baro:26000},
  {hex:"abcdef",lat:50.95,lon:7.2,flight:"ONLINE1",alt_baro:26000,track:180}
 ],provider:"fixture",updated_at:0});
 assert.equal(result.online,1);
 assert.equal(result.alsoLocal,1);
 assert.equal(layers.length,2,"independently togglable Internet and local R badges");
 const app=ctx.window.tihuluTarOverlay;
 const net=app.source.getFeatures()[0];
 const radio=app.localSource.getFeatures()[0];
 assert.equal(net.get("badge"),"I");
 assert.equal(radio.get("badge"),"I/R");
 const internetStyles=layers[0].options.style(net);
 const radioStyles=layers[1].options.style(radio);
 assert.ok(internetStyles.some(s=>s.options.image instanceof classes.Icon),"online airplane SVG icon");
 assert.ok(internetStyles.some(s=>s.options.text?.options.text==="I"));
 assert.equal(radioStyles.length,1,"do not duplicate tar1090's own radio airplane");
 assert.equal(radioStyles[0].options.text.options.text,"I/R");
 assert.match(internetStyles[0].options.image.options.src,/data:image\/svg\+xml/);
 ctx.g.planes["3c1234"].seen_pos=90;
 app.updateRadio();
 assert.equal(app.localSource.getFeatures().length,0,"stale radio badges disappear");
});
test("Source badge and altitude legend are visible on every main map",()=>{
 assert.match(html,/both sources/);
 assert.match(html,/Aircraft color/);
 assert.match(main,/paintAircraft\(ctx,a,x,y\)/);
 assert.match(classic,/drawRadioAircraft\(a,x,y\)/);
 assert.match(tar,/Local radio \(R\), matched \(I\/R\)/);
 assert.match(tar,/app\.updateRadio\(\)/);
});
