"""Non-invasive source-attributed Internet aircraft overlay for embedded tar1090.

Uses the existing OpenLayers map object exposed by tar1090 in Qt WebEngine
MainWorld. Does NOT modify tar1090 files, its own receiver data or systemd.
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView

from .bridge import DataProvider
from .core import recently_seen, position_is_fresh

# tar1090 (wiedehopf) defines the lexical OLMap map in html/script.js.
MAP_CENTER_JS = r"""(() => {
  if (typeof OLMap === 'undefined' || !OLMap || typeof ol === 'undefined')
    return null;
  // These are view-only changes. Do not mutate SiteLat/SiteLon or tar1090's
  // receiver location: doing so produces a fake center dot and range rings.
  if (typeof siteCircleLayer !== 'undefined' && siteCircleLayer)
    siteCircleLayer.setVisible(false);
  if (typeof locationDotLayer !== 'undefined' && locationDotLayer)
    locationDotLayer.setVisible(false);
  if (!window.tihuluTarCameraApplied) {
    const params = new URLSearchParams(location.search);
    const a = Number(params.get('tihuluFocusLat'));
    const b = Number(params.get('tihuluFocusLon'));
    if (params.has('tihuluFocusLat') && params.has('tihuluFocusLon') &&
        Number.isFinite(a) && Number.isFinite(b) &&
        Math.abs(a)<=90 && Math.abs(b)<=180) {
      OLMap.getView().setCenter(ol.proj.fromLonLat([b,a]));
      OLMap.getView().setZoom(Number(params.get('zoom')) || 9);
    }
    window.tihuluTarCameraApplied = true;
  }
  const p = ol.proj.toLonLat(OLMap.getView().getCenter());
  if (!p || !isFinite(p[0]) || !isFinite(p[1])) return null;
  return {lon:p[0],lat:p[1]};
})()"""

# Even when tar1090 fails to initialize its OpenLayers map, show a visible
# diagnostic instead of an invisible Internet layer. This does not modify tar.
BOOTSTRAP_JS = r"""(() => {
  if (document.getElementById('tihulu-tar-overlay-panel')) return;
  const panel = document.createElement('div');
  panel.id='tihulu-tar-overlay-panel';
  panel.style.cssText='position:fixed;bottom:16px;right:15px;z-index:2147483000;'+
    'background:#101d2aef;color:#eaf7ff;padding:9px;border:1px solid #407391;'+
    'border-radius:8px;font:12px system-ui;max-width:260px';
  panel.textContent='Internet overlay: waiting for tar1090 map…';
  document.body.appendChild(panel);
})()"""

# Delivered from the native application into the local tar1090 WebEngine page.
# It does NOT fetch remotely or expose a pairing token into tar1090.
# Aircraft with matching ICAO already visible in tar1090 are skipped.
OVERLAY_JS = r"""(function(input){
  if (typeof OLMap === 'undefined' || !OLMap || typeof ol === 'undefined')
    return 'tar1090 OpenLayers map not ready';
  const app = window.tihuluTarOverlay || {};
  if (!app.layer) {
    app.source = new ol.source.Vector();
    app.layer = new ol.layer.Vector({
      source: app.source,
      zIndex: 1000,
      style: feature => new ol.style.Style({
        image: new ol.style.Circle({
          radius: 6,
          fill: new ol.style.Fill({color: '#53b1ff'}),
          stroke: new ol.style.Stroke({color:'#102537',width:2})
        }),
        text: new ol.style.Text({
          text: 'NET ' + (feature.get('flight') || feature.get('hex') || ''),
          font: '11px sans-serif',
          offsetY: -15,
          fill: new ol.style.Fill({color:'#b9e5ff'}),
          stroke: new ol.style.Stroke({color:'#0d2433',width:3})
        })
      })
    });
    OLMap.addLayer(app.layer);
    const panel = document.getElementById('tihulu-tar-overlay-panel')
       || document.createElement('div');
    panel.replaceChildren();
    panel.id='tihulu-tar-overlay-panel';
    panel.style.cssText = 'position:fixed;bottom:16px;right:15px;z-index:2147483000;'+
      'background:#101d2aef;color:#eaf7ff;padding:9px;border:1px solid #407391;'+
      'border-radius:8px;font:12px system-ui;max-width:230px';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox'; checkbox.checked = true;
    checkbox.setAttribute('aria-label','Show Internet aircraft overlay');
    checkbox.onchange=()=>{app.layer.setVisible(checkbox.checked)};
    const label=document.createElement('label');
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(' Internet aircraft (blue)'));
    panel.appendChild(label);
    const status=document.createElement('div');
    status.id='tihulu-tar-overlay-status';
    status.style.cssText='color:#a5c4d8;margin-top:4px';
    panel.appendChild(status);
    if (!panel.isConnected) document.body.appendChild(panel);
    app.status=status;
    window.tihuluTarOverlay=app;
  }
  app.source.clear();
  const local=(typeof g==='object' && g.planes) ? g.planes : {};
  let plotted=0, overlapped=0;
  for (const a of input.aircraft) {
    if (a.hex && Object.prototype.hasOwnProperty.call(local,a.hex.toLowerCase())) {
      overlapped++;continue;
    }
    const f=new ol.Feature({
      geometry:new ol.geom.Point(ol.proj.fromLonLat([a.lon,a.lat])),
      hex:a.hex || null,
      flight:a.flight || null,
      source:'internet'
    });
    app.source.addFeature(f);
    plotted++;
  }
  const when=Number.isFinite(input.updated_at)
    ? (' · updated '+new Date(input.updated_at*1000).toLocaleTimeString()) : '';
  app.status.textContent=plotted+' online · '+overlapped+' also local | '+input.provider+
    when+(input.error ? ' | ERROR: '+input.error : '');
  app.status.style.color=input.error?'#ffb3a5':'#a5c4d8';
  return {online:plotted,alsoLocal:overlapped};
})"""  # supplied data is serialized separately below; not interpolated from URLs


class TarOverlayView(QWebEngineView):
    """Native Qt tar1090 viewer with an independent blue network data layer."""

    def __init__(self, parent=None, provider=None, assume_tar=False):
        super().__init__(parent)
        self._provider = provider if provider is not None else DataProvider()
        self._assume_tar = bool(assume_tar)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tihulu-tar")
        self._pending = None
        self._active = False
        self._generation = 0
        self._timer = QTimer(self)
        self._timer.setInterval(2500)
        self._timer.timeout.connect(self._poll)
        self.loadFinished.connect(self._loaded)
        self.destroyed.connect(lambda *_: self._pool.shutdown(wait=False, cancel_futures=True))

    def _loaded(self, ok):
        from ipaddress import ip_address
        host=self.url().host().lower()
        allowed=host in ("localhost", "127.0.0.1") or host.endswith((".lan", ".local"))
        if not allowed:
            try:
                allowed=ip_address(host).is_private
            except ValueError:
                allowed=False
        self._active = bool(ok and allowed
                            and (self._assume_tar or "/tar1090" in self.url().path))
        self._generation += 1
        if self._active:
            self.page().runJavaScript(BOOTSTRAP_JS)
            self._timer.start()
        else:
            self._timer.stop()

    def _poll(self):
        if not self._active or not self.isVisible():
            return
        if self._pending is not None:
            if self._pending.done():
                f, generation=self._pending, self._generation
                self._pending=None
                try:
                    aircraft, status=f.result()
                    actual=[]
                    for a in aircraft:
                        if (isinstance(a,dict) and recently_seen(a)
                                and position_is_fresh(a)):
                            actual.append({
                                "lat":a["lat"],"lon":a["lon"],
                                "hex":a.get("hex") if isinstance(a.get("hex"),str) else None,
                                "flight":str(a.get("flight") or "").strip()[:12]
                            })
                    if self._active and generation==self._generation:
                        self._draw_overlay(
                            actual[:1200], status.get("provider") or "Internet",
                            status.get("error") or "", status.get("updated_at")
                        )
                except Exception as exc:
                    if self._active:
                        self._draw_overlay([], "Internet", str(exc)[:160])
            return
        # Fetch only every ~15 seconds; DataProvider also enforces a shared
        # cooldown, including provider backoff after HTTP 429.
        from time import monotonic
        if monotonic()<getattr(self, "_next_poll", 0):
            return
        self.page().runJavaScript(MAP_CENTER_JS,self._got_center)

    def _got_center(self, value):
        if not self._active or not isinstance(value,dict):
            return
        lat,lon=value.get("lat"),value.get("lon")
        if not (isinstance(lat,(int,float)) and isinstance(lon,(int,float))
                and math.isfinite(lat) and math.isfinite(lon)
                and -90<=lat<=90 and -180<=lon<=180):
            return
        from time import monotonic
        self._next_poll=monotonic()+16
        self._pending=self._pool.submit(self._provider.fetch,float(lat),float(lon),100)
        if not getattr(self, "_overlay_bootstrapped", False):
            self._overlay_bootstrapped=True
            self._draw_overlay([], "Connecting to Internet feed", "")

    def _draw_overlay(self, aircraft, provider, error="", updated_at=None):
        if not self._active:
            return
        payload=json.dumps({
            "aircraft":aircraft,
            "provider":provider,
            "error":error,
            "updated_at":updated_at
        }, ensure_ascii=False)
        self.page().runJavaScript(OVERLAY_JS+"("+payload+")")

    def closeEvent(self, event):
        self._timer.stop()
        self._active=False
        self._generation+=1
        self._pool.shutdown(wait=False,cancel_futures=True)
        super().closeEvent(event)
