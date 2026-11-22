# Offline Germany / Türkiye city catalog — data attribution

The file [cities-de-tr.json](cities-de-tr.json) is a **derived database**;
it is **not** an authored list of factual coordinates and does not represent
all villages or addresses in either country.

- Upstream: [srestre/world-countries-cities-db](https://github.com/srestre/world-countries-cities-db)
- Source records: `countries/DE.json` and `countries/TR.json`
- Original derivation: `dr5hn/countries-states-cities-database`, as documented by upstream
- Data license: **Open Database License (ODbL) 1.0**
  https://opendatacommons.org/licenses/odbl/1-0/
- This transformed DE/TR dataset remains under **ODbL 1.0**.
- The app's JavaScript program and unrelated project files are not automatically
  relicensed by this database attribution.

**Transformation:** Extracted city and municipality entries in DE and TR,
retaining ISO country code, place name, first-level administrative name,
WGS84 latitude and longitude to five decimal places. Removed the source
database's phone codes, currency, administrative metadata and other countries.
The output contains 7,104 German and 980 Turkish entries (8,084 total).
Coordinates are approximate *place points* and must not be interpreted as
the user's precise GPS location.

The file is shipped with the hosted app so city suggestions work without
external geocoding queries once the static asset is loaded. The visitor's
typed name is not transmitted to an online provider unless they explicitly
request it or turn on optional online suggestions.

For searches outside this directory, users can invoke Open-Meteo Geocoding
API, based on GeoNames:
https://open-meteo.com/en/docs/geocoding-api

Open-Meteo's free endpoint is intended for non-commercial use under the
provider's terms; if the project changes to commercial use, an appropriate
commercial licence and endpoint must be obtained. Attribution shown in UI.
