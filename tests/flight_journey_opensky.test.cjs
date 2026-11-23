"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const path=require("node:path");
const F=require(path.join(__dirname,"../tihulu_flight_radar/web/flight_journey.js"));

// OpenSky flights-by-aircraft window fixture (seconds since epoch, like the API).
const DAY=Math.floor(Date.UTC(2026,10,22)/1000);
const WINDOW=[
 {icao24:"484506",firstSeen:DAY+3600,lastSeen:DAY+7200,
  estDepartureAirport:"EDDK",estArrivalAirport:"LPPT",callsign:"DLH123"},
 {icao24:"abcdef",firstSeen:DAY+10,lastSeen:DAY+20,
  estDepartureAirport:null,estArrivalAirport:null,callsign:"XXX"}
];

test("OpenSky observed times parse with icao24-exact matching",()=>{
 const j=F.fromOpenSky(WINDOW,"484506","DLH123");
 assert.ok(j);
 assert.equal(j.origin.code,"EDDK");
 assert.equal(j.destination.code,"LPPT");
 assert.equal(j.times.departEstimated,(DAY+3600)*1000);
 assert.equal(j.times.arriveEstimated,(DAY+7200)*1000);
 assert.equal(j.matchedHex,"484506");
 assert.ok(j.source.includes("icao24"));
});
test("OpenSky rows for another transponder or callsign are rejected",()=>{
 assert.equal(F.fromOpenSky(WINDOW,"abcdef","DLH123"),null); // wrong hex
 assert.equal(F.fromOpenSky(WINDOW,"484506","AUA999"),null); // callsign mismatch
 assert.equal(F.fromOpenSky([{icao24:"484506"}],"484506",null),null); // no data at all
 assert.equal(F.fromOpenSky(null,"484506",null),null);
 assert.equal(F.fromOpenSky([],"zzzzzz",null),null); // invalid hex
});
test("OpenSky entry without est airports still yields observed times",()=>{
 const j=F.fromOpenSky([{icao24:"484506",firstSeen:DAY+60,
   lastSeen:DAY+120,estDepartureAirport:null,estArrivalAirport:null,
   callsign:"DLH123"}],"484506","DLH123");
 assert.equal(j.origin,null);
 assert.equal(Number.isFinite(j.times.departEstimated),true);
});
test("Configured AirLabs schedule outranks observed times for the same phase",()=>{
 const observed=F.fromOpenSky(WINDOW,"484506","DLH123");
 const scheduled=F.fromProvider({sources:["internet"],flight:"DLH123",
  flight_source_fields:{dep_time_ts:(DAY+3660),arr_time_ts:(DAY+7260),
   dep_estimated_ts:(DAY+3700),arr_estimated_ts:(DAY+7300)}});
 const merged=F.combine(scheduled,observed);
 assert.equal(merged.times.departEstimated,(DAY+3700)*1000); // AirLabs estimate wins
 assert.equal(merged.times.departScheduled,(DAY+3660)*1000);
 assert.ok(merged.source.includes("AirLabs")||merged.source.includes("Internet flight"));
});
test("Observed times survive when only the callsign route is known",()=>{
 const observed=F.fromOpenSky(WINDOW,"484506","DLH123");
 const route=F.fromAdsbdb({response:{flightroute:{callsign:"DLH123",
  origin:{iata_code:"CGN"},destination:{iata_code:"OPO"}}}},"DLH123");
 const merged=F.combine(observed,route);
 assert.equal(merged.times.departEstimated,(DAY+3600)*1000);
 assert.equal(merged.origin.code,"EDDK"); // observed airports take precedence over the route lookup
 // combine() drops the redundant route source when the observed entry supplies both airports.
 assert.ok(merged.source.includes("OpenSky")&&!merged.source.includes("adsbdb"));
 // Without est airports the route remains visible and is credited.
 const partial=F.fromOpenSky([{icao24:"484506",firstSeen:DAY+3600,lastSeen:DAY+7200}],
  "484506","DLH123");
 const merged2=F.combine(partial,route);
 assert.equal(merged2.origin.code,"CGN"); // route fills the gap
 assert.ok(merged2.source.includes("OpenSky")&&merged2.source.includes("adsbdb"));
});
test("Summary labels OpenSky times as estimated, not actual",()=>{
 const observed=F.fromOpenSky(WINDOW,"484506","DLH123");
 assert.ok(F.timeSummary(observed).includes("estimated"));
 assert.equal(F.formatTime(observed.times.departEstimated,"UTC").endsWith(" UTC"),true);
});
