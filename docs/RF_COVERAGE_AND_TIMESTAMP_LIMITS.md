# Experimental RF coverage and ADS-B time provenance

Scope: the same Flight Radar `web/index.html` and `web/app.js` are delivered
by GitHub Pages and by the PySide6/Qt desktop loopback bridge. These views
must never turn an Internet aircraft into an independently measured radio
signal or guess the receiver's position.

## What is measured

- Browser WebUSB RTL-SDR is tuned to 1090 MHz at **2,000,000 complex
  samples/s**. On each CRC-verified DF17/DF18 message, the decoder now stores
  the **preamble's sample offset** in the sequential received I/Q stream
  (`rf_timing.arrival_sample_index`). The nominal ADC sample step is
  **0.5 microseconds**. This quantizes relative sample positions; it is **not
  a calibrated 0.5 microsecond UTC arrival-time accuracy**.
- The worker also records `decoder_observed_unix_ms` from the browser
  system clock. This occurs after USB buffering/transfer/decoding and is
  **not the propagation-corrected RF arrival instant**. USB host/queue
  delays, clock drift, sample drops and epoch alignment remain unmeasured.
- Native `readsb` `aircraft.json` usually supplies `seen` and
  `seen_pos` relative ages, **not raw sample timing or UTC transmit time**.
  Missing precision data is represented as missing, never fabricated.
- ADS-B/1090ES airborne position messages **do not carry an exact UTC
  transmission timestamp**. Time-of-applicability and a UTC synchronization
  flag, when present, are not equivalent to measured RF emission time.
- Therefore **TX - RX propagation delay, distance-by-time-of-flight, and
  precise receiver position are unavailable** with this unsynchronized
  single-dongle feed. Never label a WebUSB sample-index timestamp as a
  GPS-synchronized TOA measurement or use `now - seen` as a send time.

## The optional rings

Only rows with `position_source="antenna"`, independently positioned
`observations.antenna`, valid fresh age fields and plausible aircraft
altitude enter the conservative radio-horizon model. It requires **four**
distinct independently positioned ICAO24 aircraft before displaying
model constraints, never an arbitrary count of online planes. The rough maximum line-of-sight radius uses
4/3 effective Earth radius, a 30-m maximum ground receiver height and an
extra 30-km allowance; this is a *demonstration bound*, not an RF
range measurement. Its grid-cell intersection is merely a possible
coverage area and may be very broad, disconnected, or wrong when the
propagation model is inaccurate. The default-on **RF area**
control computes a centroid of those possible grid cells without taking
a receiver latitude/longitude, GPS permission, or public aircraft data.
The value shown is a **model-dependent plausible-area center**, not an
inferred measured location or a GPS fix. The displayed extent in kilometers
describes the area sampled by the model, **not statistical confidence** or
a measured receiver error bound. This center is independently drawable even
when the optional rings are hidden. No real receiver accuracy is claimed.

## What a true ToA / reverse-position estimator requires

A receiver-site solve from aircraft beacons needs independently verified
TX epochs **or** precisely synchronized geographically separated
receivers with real calibrated hardware timestamps. Standard MLAT solves
**aircraft** location from arrival-time differences of the **same**
transmission at independent sites; four aircraft received at one SDR is
not the same measurement geometry.

If a later receiver backend provides GNSS-disciplined arrival timestamps
with uncertainty and an authenticated transmission-time model, add an
explicit, separately validated solver with residuals and an error
ellipse. Do not enable it from ordinary `aircraft.json`, external
aggregator `now`/age fields, browser `Date.now` or `performance.now`.

## UI / acceptance

- Aircraft table: **Altitude (ft), Speed (kt)**; switch to **m / km/h**.
- Marker and row selection: a nonmodal, closeable popover, while the
  expandable raw JSON view is preserved.
- RF timing disclosure displays actual sample indices, decoder time and
  missing TX time separately.
- **RF area ON/OFF** is the only master control for the four-aircraft
  receiver-location solver. OFF skips both the solver and RF history sampling;
  normal ADS-B reception, Internet overlays, flight details and map remain
  operational. Existing session BEST is retained, not recomputed or displayed
  while OFF. Reenable to resume valid real RF model calculations.
- **Circles dropdown**, beside RF area ON/OFF, controls visual layers
  independently of the solver: LIVE Fit circle (default ON), BEST Fit
  circle (default OFF), LIVE feasible area (default ON), and individual
  aircraft horizons (default hidden, Selected or All). Gaussian PSF remains
  display-only on explicitly selected aircraft horizons; enabling Gaussian
  never auto-enables unwanted aircraft circles. LIVE and BEST center pins
  are also independently controlled in the advanced RF panel.
- The **LIVE Fit circle** is centered at the current four-aircraft
  feasible-grid area centroid with the rounded maximum sampled radial spread;
  its cyan outline is not a confidence interval or GPS accuracy estimate.
  The **BEST Fit circle** is centered at the stored session model with
  the smallest *unrounded* sampled spread. It has a distinct purple outline
  and remains visible when LIVE later becomes insufficient, provided RF
  locator ON is still enabled. Smaller sampled spread does not prove a more
  accurate receiver position.
- Source browser and bundled Qt desktop use the **same** JavaScript/CSS
  and preferences; best model and raw RF history remain session-only.
  Preferences persist when the engine permits localStorage. Offline
  PWA shell cache is versioned so upgraded controls replace old copies.
- The optional centroid marker and its displayed coordinates are labeled
  model outputs, never actual measured receiver coordinates.
- Node regression tests cover four genuine RF observations, rejected
  Internet/misprovenanced rows, timing placeholders, sample indices and UI.
- **Hardware validation is pending** for physical Nooelec NESDR SMArt v5,
  Pop!_OS COSMIC Qt window, browser USB, timestamp continuity and RF
  field accuracy. CI alone is not hardware validation.

References (technical context):
- https://streaming-docs.adsbexchange.com/guides/timestamps
- https://www.radartutorial.eu/02.basics/en/rp52.en.html
- https://www.flightaware.com/adsb/mlat/

## Offline RF Timing Laboratory (November 2026)

The shared radar UI now contains a native/browser RF Timing Laboratory. It
works without public ADS-B providers when an actual radio feed is available,
and it can open a previously exported session with **no antenna and no
Internet**. All analysis is local: there is no background uploader, geolocation
API call, artificial aircraft, remote time server or hidden service dependency.

**Direct browser receiver (Brave/Chrome/Edge with permitted WebUSB):**
- No second RTL-SDR owner: the worker piggybacks on the **existing** 2 Msps
  I/Q stream, recording a capped batch of CRC-verified Mode S frames.
- Per record: ICAO24, DF, type code, original 112-bit frame hex, receiver ADC
  sample index, worker decoder processing UTC, and a segment marker for
  explicit pauses/resumes. The per-frame **0.5 µs nominal sample period** is
  not a calibrated UTC accuracy.
- Statistics: total accepted timing records, distinct aircraft, same-ICAO
  interarrival median, median absolute deviation (MAD), number of segment
  interruptions, host USB read duration (last/mean/max), and possible slow
  host-read windows. Slow host reads and UI records dropped due to a cap are
  not proof of lost radio samples or an estimate of propagation time.
- Bounded memory: maximum 4,000 retained frames in the frontend, maximum 512
  queued decoder events per publication interval. Oldest frontend records
  are evicted; recording can be paused and cleared explicitly.
- Exports: user-initiated JSON session (schema
  `tihulu.rf-timing-lab.v1`) and CSV. Offline import validates format, field
  types, ascending sample indices and size (4 MiB maximum), and **never**
  injects replayed frames into the live radar or RF aircraft counts.
- After first installation/cache fill, the service worker caches UI,
  decoder, USB drivers and analysis code for offline operation. WebUSB still
  requires a supported Chromium browser, a working local USB device and
  operating-system permissions. Cached map tiles are not guaranteed.

**Qt desktop + readsb backend:**
- Same timing-lab UI is included, and JSON/CSV exports open an OS-local
  save dialog through Qt WebEngine.
- `readsb` `aircraft.json` contains aircraft message age estimates but **not**
  calibrated per-message ADC arrival timestamps. Thus no fine-grained
  interarrival record is fabricated for this receiver backend. It can still
  display and export a previous local WebUSB recording, and the genuine
  `readsb` aircraft contribute to the RF horizon constraints.
- For a future native high-precision mode, integrate a verified raw readsb
  Beast/timestamp source with explicit clock origin, sample loss and time
  uncertainty, without claiming the SDR a second time.

**RF coverage and accumulating aircraft:**
- The receiver is assumed stationary *only when the user leaves the fixed-site
  history checkbox on*. The browser retains up to 64 individually
  **antenna-verified** aircraft position constraints for at most two hours
  in the current session; historical records are explicitly labeled as
  historical rather than passed back as fresh live plane positions.
- More RF aircraft can shrink the **model-dependent feasible region**. The
  map draws at most three pale-blue optional horizon outlines (OFF by default), while up to 64
  genuine position observations from at least four independent aircraft constrain the feasible area. Multiple positions of a single aircraft never inflate the independent-aircraft threshold.
- Increasing aircraft count does **not guarantee increasing geolocation
  accuracy**. Radio-horizon ranges are assumptions, not time-of-flight
  distances, so this version never returns a receiver GPS fix or accuracy
  figure. Clear the history when moving the receiver.

Physical SDR reception, driver stability, offline first-load setup and Qt
download dialogs require testing on the target computer. CI simulation is not
a substitute for hardware calibration.


## Offline RF possible-area locator (4+ aircraft; default-on)

The cyan feasible-area overlay is enabled by default, independently of the
optional outer radio-horizon outlines. **Focus RF area** recenters the map
only when explicitly clicked; discovering new radio planes does not hijack
the user's manual map position. The model requires at least **four distinct
independently positioned local RF aircraft**, with source provenance and fresh
ages verified, before an area is produced. The total 'Local aircraft' counter
can be larger because Mode S detections do not all include coordinates.

With the stationary-receiver history option enabled (session-only), multiple
genuinely received positions along an aircraft's trajectory are recorded when
separated by meaningful distance or time. They give additional *constraints*,
but a single aircraft never counts as several independent aircraft. Up to
64 observations over two hours are used. Clear history whenever the receiver
or antenna changes site. No Internet, GPS, manually entered receiver position,
or external tiles are required for this experiment.

The translucent cyan polygon approximates the **intersection of feasible
radio-horizon regions**. Its marker is the **model-dependent sample centroid**
and its extent is **not** a GPS fix, measured RF range, statistical
confidence interval, or validated accuracy. The horizon model can be
incorrect under obstructed or anomalous propagation. This is not TDOA/MLAT
trilateration; there is no exact transmission epoch in ordinary 1090ES.
If insufficient distinct local aircraft or incompatible constraints are
present, no receiver location is asserted.

When a valid modeled region exists, a selected genuinely RF-positioned
aircraft can display a **conditional approximate distance interval**. It is
the minimum/maximum distance from the aircraft's genuine received coordinates
to sampled cells of the receiver's modeled feasible region, rounded outwards
to tens of kilometers. This is not a measured slant range, radio propagation
time, RF RSSI distance, GPS position or statistical confidence bound; it is
not shown for Internet-only aircraft or insufficient RF model inputs.

The normal aircraft map now opt-out animates *display-only* short-horizon
motion using actual received position, speed and heading. A dashed halo
distinguishes the projected icon, which is never used for RF coverage,
provenance, tracks or exports. Native `readsb` RSSI, if present, is displayed
as an uncalibrated relative signal indicator in the aircraft timing panel,
never converted to fictional kilometers. The RF Timing Laboratory may show
zero calibrated sample-index frames while the native readsb feed still
contains genuine positioned RF aircraft.

Independent tests enforce these rules in `tests/aircraft_popup_rf_coverage.test.cjs`
and `tests/map_motion.test.cjs`. Hardware validation with the user's SDR is
still pending; GitHub Actions do not confirm real RF reception.


## 8 November 2026 — cumulative RF flight paths and live map layers

The session-only stationary receiver model now uses actual received trajectories.
`recordedCircle()` records true RF-sourced aircraft positions plus reported
ground speed and direction (when available). `trackSampleDecision()` compares
the elapsed time, measured movement and plausible speed envelope, rejecting
duplicate geographic fixes and implausible jumps. Heading changes allow
denser sampling at turns. No synthetic or interpolated aircraft position can
be fed to the RF model. The separate smooth radar animation still remains
*display only*. A two-hour, 64-observation cap applies; when trimming, retain
independently identified aircraft before old redundant observations from one
aircraft. Multiple observations from the same ICAO add constraints, but
never count as multiple independent aircraft.

RF possible-area cells are sampled on a finer 80×80 grid when four or more
independent positioned RF aircraft are present. A *model center* is the
centroid of compatible sampled cells, with an approximate *model spread
circle* extending to the furthest sampled feasible cell (rounded outward).
This is **NOT** a statistical confidence circle, known GPS error margin,
measured antenna position or actual measured signal range. The model may
remain broad, move or become invalid as verified constraints arrive.
The on-screen narrowing/widening and center-shift readouts describe **model
changes**, not improving physical geolocation accuracy.

Map controls:
- **Focus RF area**: one-shot recenter to the currently modeled region.
- **Follow RF center**: opt-in continuous camera follow on each changed RF
  model result. Manual map drag, zoom, search region or aircraft focus
  cancels follow. Existing zoom is maintained during subsequent updates.
- **Feasible area**: transparent cyan model polygon (default ON).
- **Hatched area**: clipped diagonal texture within that polygon (optional).
- **Model spread circle**: explicit optional white dashed modeled upper
  spread from the model centroid (default ON); **Center pin** is independent
  and may be hidden (default ON).
- **Individual aircraft horizon circles**: generated from each independent
  aircraft's most recent genuinely received radio position, available as
  separate color-coded checkboxes with Show all / Hide all. They are only
  propagation upper-bound outlines; they are **not** measurements of the
  receiver-to-plane distance. They can be displayed even before enough
  independent aircraft are available to derive a feasible model area.
- Optional legacy **RF horizon outlines** retain three faint diagnostic rings
  as a convenience control. All overlay colors are distinct from the live
  altitude color scheme.

These controls do not require Internet or device geolocation. All RF
observations remain source-verified; the displayed model is never silently
fed into the actual receiver location, map search region, aircraft records
or exports. Validation tests are in `tests/rf_trajectory_layers.test.cjs`,
`tests/aircraft_popup_rf_coverage.test.cjs`, and the cross-platform CI
workflows. Actual SDR/Pop!_OS receiver tests remain required before merging.


## 8 November 2026 — single-aircraft focus regression and time alignment correction

**Verified root cause:** the radar's startup `chooseStartupTarget()`
previously centered the map on the nearest **single** genuinely radio-received
aircraft before a four-aircraft RF model existed. Clicking an aircraft row
also recentered the map even while `Follow RF center` was active. These two
camera paths were separate from the RF model and made a plane's last position
appear to be the inferred receiver location.

The startup map now stays at the ordinary fallback or explicitly permitted
device location until **four distinct RF-positioned airplanes** yield a
compatible RF-feasible region. Four-aircraft RF follow is default ON, fits
the initial model spread once, and updates center without resetting zoom.
While following the model, clicking an aircraft in the table selects it
without changing the map center. An explicit `Center aircraft` action
disables RF follow and moves to that aircraft. Any lost/invalid model is
marked as unresolved rather than labeling a retained camera position as
a current estimated receiver site.

**Geometry and timing:** the grid longitude reference is the circular mean
of the independently received RF aircraft, not the first/newest airplane.
The feasible-cell centroid is area weighted, and every accepted local radio
position constraint is tested geodesically. The evidence panel lists the
independent ICAO aircraft, their contributions, backend-reported positional
age, native RF speed when present, and model-derived center-to-plane versus
radio-horizon distances. These are not measured ranges or GPS accuracy.
Permutation tests verify that changing which airplane is last does not
change the model center, including with Internet-only aircraft in the feed.

For a real native readsb snapshot, the provisional observation epoch used
to time-order recorded fixes is `snapshot_capture_ms - seen_pos * 1000`.
The original radio aircraft lat/lon is stored at that approximate epoch.
Reported RF speed and heading validate plausible movement between *real*
position fixes and control sampling density. We must **not** turn elapsed
JavaScript polling delay, JSON age, ADS-B decoding latency or receiver USB
buffering into a propagation time or geometric range: no calibrated
transmission-time epoch is present. Nor do we fabricate additional RF
aircraft coordinates by projecting positions forward.

The dedicated `tests/rf_multiaircraft_center_regression.test.cjs` protects
the multi-aircraft center against input ordering and the old one-plane
auto-focus behavior. This was checked by automated CI with synthetic
fixtures; a real multi-aircraft local SDR capture is still needed to
validate actual feasibility and effective receiver position uncertainty.


## 8 November 2026 — zoom-follow fix, best-model history, hypothetical Gaussian PSF

A `+`/`−` click or wheel zoom **must never** turn off `Follow 4+ RF model
center`. The user's chosen zoom remains the active zoom through later live
RF model revisions. Only a real map drag, explicit aircraft focus, or a
different manually selected map region may switch the follow checkbox off.
Pointer movement under seven pixels from the initial press is considered
click jitter, not a deliberate pan; it will not cancel following. Camera
following pans to new RF model center coordinates but does not refit each
time. This is separate from the display-only aircraft motion interpolation.

The *current* feasible model center, current sampled model spread, and
*best session* (smallest raw sampled model spread) are tracked separately.
The best-center pin is violet and can be turned off independently of the
cyan current-model center pin. Comparisons use the unrounded sampled
spread in km, while the large dashed map circle remains rounded upwards.
A model can be re-estimated when a new actual antenna aircraft appears
or real trajectory constraint is recorded. Even the smallest spread in
the session is **not** a GPS fix, measured receiver error, calibrated RF
accuracy or a statistical confidence region. It is only the best model
geometry produced from the session's available radio-horizon constraints.

**Optional Gaussian/PSF 1σ ring edge**: the `Gaussian PSF · ±1σ`
checkbox and an *assumed sigma* selector (5–150 km, default 20 km)
draw a soft annulus around each individually selected RF aircraft's
radio-horizon circle. For radius `R` and manually chosen sigma `σ`,
the illustrative edge profile is

`w(d) = exp[-0.5 ((d-R)/σ)^2]`.

The highlighted one-sigma interval is `[max(0,R-σ),R+σ]`;
the profile reaches `exp(-0.5)` of its peak at either boundary.
This is **not** a valid probabilistic RF range likelihood: the original
circle is a broad *maximum line-of-sight horizon*, not a range
measurement. We have no empirical standard deviation or independently
calibrated propagation model. In particular **68.3% statistical coverage**
of the receiver position is **NOT** implied. The Gaussian visualization
is never fed into RF model intersection/centroid calculations, receiver
distance estimates or raw observations. Users can tick each plane's
separate checkbox or choose Show all. If PSF is first enabled when no
aircraft outline is selected, the current and newly appearing genuine
RF aircraft are automatically selected until overridden by a manual
per-plane choice or Hide all.

CI regression tests cover zoom before and after valid 4+ aircraft model
updates, camera jitter, best unrounded spread selection, the per-plane
Gaussian function at ±1σ, and the no-GPS/no-calibrated-range assertions.

## 2026-11-09: Independent LIVE / BEST / aircraft Circles controls

The LIVE and BEST circle overlays **do not alter** `compute()` in
`receiver_coverage.js`: that solver still accepts only genuine local
antenna-origin aircraft positions, with four distinct ICAO24 identifiers,
real recorded trajectory points and no fabricated range, TOA or GPS fix.
The optional Gaussian ±1σ display has NO weighting in model selection.

The UI exposes separate `rfModelCircle`, `rfBestCircle`, `rfFill`,
`rfAircraftCircleMode` and original per-aircraft selection controls
from a top `Circles` dropdown. Existing `rfHatch`,
`rfModelPin`, `rfBestPin`, `rfGaussianBand` and `rfSigmaKm`
remain in the advanced RF panel. No duplicate controls/element IDs.
Normal 1090 MHz antenna reception and Internet display continue
when the RF *locator* is OFF. The solver/remember-history functions
short-circuit immediately in that mode; user settings and the previous
session BEST record are kept for later use.

The initial visual default is LIVE circle + feasible-area fill,
BEST circle OFF, individual aircraft horizons hidden and Gaussian OFF.
The BEST pin and BEST ring use stored session data even when current LIVE
is unavailable, so an RF history shortage does not erase a valid
earlier session model. Neither circle represents measured error.
Zoom-in/out and live map follow remain independent of layer choices.
Cross-platform regression `tests/rf_circles_layers.test.cjs` exercises
actual function behavior for model gating, independent drawings, selected
aircraft and session BEST retention. The same UI assets ship in
Linux/Pop!_OS, Windows, macOS and Raspberry Pi packages; no new
native dependency or second SDR owner was added. Real RF and Qt GUI
acceptance tests remain necessary.
