"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const html = fs.readFileSync(path.join(__dirname, "../tihulu_flight_radar/map.html"), "utf8");

test("embedded map JavaScript is syntactically valid", () => {
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
  const inline = scripts.map(match => match[1]).filter(s => s.trim());
  assert.ok(inline.length > 0);
  for (const code of inline) {
    assert.doesNotThrow(() => new vm.Script(code, { filename: "map.html inline script" }));
  }
});

test("receiver location provides map fallback without inventing aircraft", () => {
  assert.match(html, /function centerOnReference\(force=false\)/);
  assert.match(html, /if\(reference\)centerOnReference\(\)/);
  assert.match(html, /if\(reference\)centerOnReference\(force\)/);
  assert.match(html, /if\(!aircraftFocused&&positioned\.length&&!userMoved\)focusNearest\(\)/);
  assert.match(html, /No fresh aircraft position/);
});

test("the OSM layer is usable before aircraft positions arrive if location is known", () => {
  assert.match(html, /id="tiles" checked/);
  assert.match(html, /if\(!centered\)/);
  assert.match(html, /grid\(\);\s*if\(tileSwitch\.checked\)/);
  assert.doesNotMatch(html, /let lat=0,lon=0/);
});


test("Germany is the explicit map fallback, never a synthetic aircraft", () => {
  assert.match(html, /const GERMANY_DEFAULT=\{lat:51\.1657,lon:10\.4515\}/);
  assert.match(html, /centerOnGermany\(\)/);
  assert.match(html, /id="germany"/);
  assert.match(html, /id="receiver"/);
  assert.match(html, /id="refocus"/);
  assert.match(html, /id="locate"/);
  assert.match(html, /id="manualLocation"/);
  assert.match(html, /reference\|\|GERMANY_DEFAULT/);
  assert.match(html, /not receiver location/);
  assert.match(html, /if\(!aircraftFocused&&positioned\.length&&!userMoved\)focusNearest\(\)/);
});
