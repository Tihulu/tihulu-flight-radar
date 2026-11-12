/* Map camera logic. Uses only actual fresh aircraft positions.
   No fallback coordinates, no inferred receiver coordinates. */
(function(root, factory) {
  const helpers = factory();
  if (typeof module === "object" && module.exports) module.exports = helpers;
  root.TihuluMapFocus = helpers;
})(typeof globalThis !== "undefined" ? globalThis : this, function() {
  "use strict";

  function point(value) {
    if (!value || typeof value !== "object") return null;
    const lat = value.lat, lon = value.lon;
    if (typeof lat !== "number" || typeof lon !== "number" ||
        !Number.isFinite(lat) || !Number.isFinite(lon) ||
        Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
    return {lat, lon};
  }

  function validAircraft(aircraft) {
    if (!point(aircraft)) return false;
    return typeof aircraft.seen === "number" &&
      Number.isFinite(aircraft.seen) && aircraft.seen >= 0 && aircraft.seen <= 60 &&
      typeof aircraft.seen_pos === "number" &&
      Number.isFinite(aircraft.seen_pos) &&
      aircraft.seen_pos >= 0 && aircraft.seen_pos <= 60;
  }

  function distanceKm(a, b) {
    const pa = point(a), pb = point(b);
    if (!pa || !pb) return Infinity;
    const rad = Math.PI / 180;
    const dLat = (pb.lat - pa.lat) * rad;
    const dLon = (pb.lon - pa.lon) * rad;
    const h = Math.sin(dLat / 2) ** 2 +
      Math.cos(pa.lat * rad) * Math.cos(pb.lat * rad) *
      Math.sin(dLon / 2) ** 2;
    return 6371.0088 * 2 * Math.asin(Math.min(1, Math.sqrt(Math.max(0, h))));
  }

  function chooseFocus(aircraft, receiver) {
    if (!Array.isArray(aircraft)) return null;
    const located = aircraft.filter(validAircraft);
    if (!located.length) return null;

    // When the receiver or browser position is explicitly known, pick
    // the genuinely closest aircraft, not whichever is first in the feed.
    if (point(receiver)) {
      let best = located[0], bestDistance = distanceKm(best, receiver);
      for (const item of located.slice(1)) {
        const distance = distanceKm(item, receiver);
        if (distance < bestDistance) {
          best = item; bestDistance = distance;
        }
      }
      return {aircraft: best, method: "nearest", distanceKm: bestDistance};
    }

    // With no receiver location, "nearest to the user" is unknowable.
    // Prefer the medoid (a REAL received aircraft) so a distant outlier
    // does not drag the opening map to another continent.
    // Sample cap bounds quadratic effort on large receiver feeds.
    const sample = located.slice(0, 256);
    let best = sample[0], bestScore = Infinity;
    for (const a of sample) {
      let score = 0;
      for (const b of sample) score += distanceKm(a, b);
      if (score < bestScore) { best = a; bestScore = score; }
    }
    return {aircraft: best, method: "cluster", distanceKm: null};
  }

  return {point, validAircraft, distanceKm, chooseFocus};
});
