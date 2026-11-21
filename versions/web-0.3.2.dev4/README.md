# TIHULU Flight Radar — Web 0.3.2.dev4

**Frozen:** 2026-11-21 · **Kaynak:** main `75edc0efe478ca96febc5bb7b2721400a42889c2`
(app.js SHA256 `f99fbcfb700c…`, canlı origin ile birebir) · **Kopya:** `site/` (47 MB, 31 dosya)

## Canlı erişim (önerilen)
- Standalone: https://tihulu.github.io/tihulu-flight-radar/
- TEXT CENTER yansıması: https://tihulu.github.io/TIHULU-TEXT-CENTER/flight_radar/

Her iki origin aynı kaynaktan derlenir; `source-revision.json` aynı `source_sha`’yı
göstermelidir. Ayna sitesi periyodik senkronize edilir (birkaç dakika gecikme olabilir).

## Tek satırda lokal sunucu (bu kopyadan)
```
git clone --depth 1 https://github.com/Tihulu/tihulu-flight-radar.git tfr && \
cd tfr/versions/web-0.3.2.dev4/site && python3 -m http.server 8811
# Tarayıcı: http://localhost:8811/
```
Internet uçakları çalışır; USB alıcı için HTTPS gerektirir (localhost hariç WebUSB
çalışmaz — bu beklenen bir tarayıcı güvenlik kuralıdır).

## İçerik
- RF area/circles ve beş katmanlı RF history modeli (rf_history_*)
- Show BEST on map + LIVE kartları · flight journey · map motion
- Yeniden boyutlandırılabilir uçak paneli · kaynak bazlı yükleme (Load · Radio / Load · Internet)
- Zengin uçak detay/çoklu seçim arayüzü · tam upstream tar1090 (GPL, paket içinde)

## Doğrulama
```
curl -sS https://tihulu.github.io/tihulu-flight-radar/app.js | sha256sum   # f99fbcfb700c...
```
