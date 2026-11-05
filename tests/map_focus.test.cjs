"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const focus = require("../tihulu_flight_radar/map_focus.js");

const live = (hex, lat, lon) => ({hex, lat, lon, seen: 2, seen_pos: 2});

test("nearest selection uses receiver coordinates instead of first plane", () => {
  const list = [live("us", 40.7128, -74.0060), live("de", 50.9029, 6.7383)];
  const picked = focus.chooseFocus(list, {lat: 50.9, lon: 6.7});
  assert.equal(picked.aircraft.hex, "de");
  assert.equal(picked.method, "nearest");
  assert.ok(picked.distanceKm < 5);
});

test("without reference choose a real aircraft in dominant cluster, not US outlier", () => {
  const planes = [
    live("us", 39.0, -77.0),
    live("de1", 50.9, 6.7),
    live("de2", 50.92, 6.8),
    live("de3", 50.95, 6.74),
  ];
  const result = focus.chooseFocus(planes, null);
  assert.ok(result.aircraft.hex.startsWith("de"));
  assert.equal(result.method, "cluster");
  assert.equal(result.distanceKm, null);
});

test("no valid aircraft means no automatic map coordinate", () => {
  assert.equal(focus.chooseFocus([], {lat: 50.9, lon: 6.7}), null);
  assert.equal(focus.chooseFocus([{hex: "only-mode-s"}], null), null);
  assert.equal(focus.chooseFocus([live("stale", 50, 6)], {lat: 50, lon: 6}).method, "nearest");
});

test("stale and malformed coordinate reports never enter the map", () => {
  assert.equal(focus.validAircraft({...live("old", 50, 6), seen_pos: 120}), false);
  assert.equal(focus.validAircraft({...live("bad", 150, 6)}), false);
  assert.equal(focus.validAircraft({...live("nan", NaN, 6)}), false);
  assert.equal(focus.validAircraft({...live("missing", 50, 6), lon: undefined}), false);
});

test("distances are geographic and robust across the antimeridian", () => {
  assert.ok(focus.distanceKm({lat: 0, lon: 179.9}, {lat: 0, lon: -179.9}) < 25);
  assert.equal(focus.distanceKm({lat: 50, lon: 7}, {lat: 50, lon: 7}), 0);
});

test("one valid plane is used even if all other aircraft lack position", () => {
  const result = focus.chooseFocus([{hex: "mode-s"}, live("only-real", 50.9, 6.7)], null);
  assert.equal(result.aircraft.hex, "only-real");
});
