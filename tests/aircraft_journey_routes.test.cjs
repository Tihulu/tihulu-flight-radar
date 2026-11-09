"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path");
const root=path.join(__dirname,"../tihulu_flight_radar/web");
const F=require(path.join(root,"flight_journey.js"));
const original={hex:"3c6645",flight:"DLH1234",sources:["antenna"],observations:{
 antenna:{alt_baro:"ground",seen:0,seen_pos:0,lat:50.9,lon:6.9}}};
const station=(kind,at=0)=>({
 ...original,observations:{antenna:{...original.observations.antenna,alt_baro:kind,seen:0}}
});
test("adsbdb airport route includes verified callsign and never invents times",()=>{
 const payload={response:{flightroute:{
  callsign:"DLH1234",callsign_icao:"DLH1234",
  origin:{iata_code:"CGN",icao_code:"EDDK",name:"Cologne Bonn",municipality:"Cologne"},
  destination:{iata_code:"IST",icao_code:"LTFM",municipality:"Istanbul"}
 }}};
 const route=F.fromAdsbdb(payload,"DLH1234");
 assert.equal(route.origin.code,"CGN");
 assert.equal(route.destination.code,"IST");
 assert.equal(F.shortRoute(route),"CGN → IST");
 assert.deepEqual(route.times,{});
 assert.equal(F.timeSummary(route),"Timetable unavailable");
 assert.equal(F.fromAdsbdb(payload,"THY1234"),null,"never reuse a flight with a different callsign");
 assert.equal(F.fromAdsbdb({response:{flightroute:null}},"DLH1234"),null);
});
test("only named, absolute provider schedule times are accepted; no RF times mistaken as airport schedule",()=>{
 const a={hex:"3c6645",sources:["internet"],flight:"DLH1234",observations:{
  internet:{departure:{airport:{iata_code:"CGN"},
    scheduled:"2026-11-10T13:45:00+01:00",actual:"2026-11-10T14:02:00+01:00"},
   arrival:{airport:{iata_code:"IST"},estimated:"2026-11-10T18:48:00+03:00"}}}};
 const result=F.fromProvider(a);
 assert.equal(result.origin.code,"CGN");
 assert.equal(result.destination.code,"IST");
 assert.equal(result.times.departScheduled,Date.parse("2026-11-10T13:45:00+01:00"));
 assert.equal(result.times.departActual,Date.parse("2026-11-10T14:02:00+01:00"));
 assert.equal(result.times.arriveEstimated,Date.parse("2026-11-10T18:48:00+03:00"));
 assert.match(F.timeSummary(result),/actual/);
 assert.equal(F.epoch("14:45"),null);
 assert.equal(F.epoch("2026-11-10T14:45:00"),null,"no timezone guessing");
 assert.equal(F.epoch("2026-11-10"),null);
 assert.equal(F.fromProvider(original),null,"radio-only ADS-B never supplies airport or timetable");
});
test("AirLabs fields use UTC/UNIX times without interpreting local airport clock incorrectly",()=>{
 const internet={hex:"3c6645",sources:["internet"],flight_source_fields:{
  flight_icao:"DLH1234",dep_iata:"CGN",arr_iata:"IST",
  dep_time_ts:1794307200,
  arr_estimated_utc:"2026-11-10 19:15",
  dep_time:"14:30",arr_time:"19:15"}};
 const j=F.fromProvider(internet);
 assert.equal(F.shortRoute(j),"CGN → IST");
 assert.equal(j.times.departScheduled,1794307200*1000);
 assert.equal(j.times.arriveEstimated,Date.parse("2026-11-10T19:15:00Z"));
 assert.equal(j.times.arriveScheduled,undefined,
  "local clock strings without date/timezone must not be treated as UTC");
 const js=fs.readFileSync(path.join(root,"app.js"),"utf8");
 assert.match(js,/dep_iata:a\.dep_iata,dep_icao:a\.dep_icao/);
 assert.match(js,/arr_time_ts,arr_estimated_ts,arr_actual_ts/);
});
test("explicit local radio ground-to-air state transition is observed and never an actual gate time",()=>{
 const epoch=Date.now();
 const a1=station("ground"),a2=station(3500);
 F.observeRadio([a1],epoch);
 F.observeRadio([a2],epoch+15000);
 assert.equal(F.radioInfo(a2).departure,null,"only one new state snapshot must not count");
 F.observeRadio([a2],epoch+30000);
 const r=F.radioInfo(a2);
 assert.ok(Number.isFinite(r.departure));
 assert.equal(r.arrival,null);
 // No disappearance / Internet-only feed is allowed to claim landing.
 F.observeRadio([{...a2,sources:["internet"],observations:{internet:{alt_baro:"ground",seen:0}}}],epoch+45000);
 assert.equal(F.radioInfo(a2).arrival,null);
});
test("new aircraft UI is wired to both list and mini card with no automatic bulk scraping",()=>{
 const html=fs.readFileSync(path.join(root,"index.html"),"utf8");
 const js=fs.readFileSync(path.join(root,"app.js"),"utf8");
 const ui=fs.readFileSync(path.join(root,"flight_journey_ui.js"),"utf8");
 const bridge=fs.readFileSync(path.join(__dirname,"../tihulu_flight_radar/bridge.py"),"utf8");
 const sw=fs.readFileSync(path.join(root,"sw.js"),"utf8");
 for(const id of ["popupDepartAirport","popupArriveAirport","popupDepartureTime",
  "popupArrivalTime","popupRadioJourney","popupJourneySource","popupJourneyRefresh",
  "aircraftRoutesLoad"])assert.ok(html.includes('id="'+id+'"'),id);
 assert.match(html,/flight_journey\.js/);
 assert.match(html,/flight_journey_ui\.js/);
 assert.match(sw,/flight_journey\.js/);
 assert.match(sw,/flight_journey_ui\.js/);
 assert.match(js,/TihuluJourneyUI\?\.selected/);
 assert.match(js,/TihuluJourneyUI\?\.observe/);
 assert.match(js,/TihuluJourneyUI\?\.row/);
 assert.match(bridge,/\/api\/flight-route/);
 assert.match(ui,/popupJourneyRefresh/);
 assert.match(ui,/adsbdb\.com\/v0\/callsign\//);
 assert.match(ui,/flight\(\w+\)/);
});
