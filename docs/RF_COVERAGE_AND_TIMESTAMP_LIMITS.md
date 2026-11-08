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
distinct ICAO24 aircraft before displaying rings, never an arbitrary
count of online planes. The rough maximum line-of-sight radius uses
4/3 effective Earth radius, a 30-m maximum ground receiver height and an
extra 30-km allowance; this is a *demonstration bound*, not an RF
range measurement. Its grid-cell intersection is merely a possible
coverage area and may be very broad, disconnected, or wrong when the
propagation model is inaccurate. The UI NEVER declares GPS coordinates or
reports a false meter-level accuracy.

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
- Coverage checkbox and status never imply physical receiver coordinates.
- Node regression tests cover four genuine RF observations, rejected
  Internet/misprovenanced rows, timing placeholders, sample indices and UI.
- **Hardware validation is pending** for physical Nooelec NESDR SMArt v5,
  Pop!_OS COSMIC Qt window, browser USB, timestamp continuity and RF
  field accuracy. CI alone is not hardware validation.

References (technical context):
- https://streaming-docs.adsbexchange.com/guides/timestamps
- https://www.radartutorial.eu/02.basics/en/rp52.en.html
- https://www.flightaware.com/adsb/mlat/
