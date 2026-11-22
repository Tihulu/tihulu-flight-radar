# TIHULU Flight Radar — macOS masaüstü 0.3.2.dev4

**Durum:** ✅ Taslak release `desktop-0.3.2.dev4-20261122-0734` (GitHub Actions: `desktop-versions-build.yml`, macos-latest)

## Kurulum
1. [`TihuluFlightRadar-macos-arm64.zip`](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-0734/TihuluFlightRadar-macos-arm64.zip) dosyasını indirin
   (Apple Silicon arm64 yapısı · [release sayfası](https://github.com/Tihulu/tihulu-flight-radar/releases/tag/desktop-0.3.2.dev4-20261122-0734) · hash: `SHA256SUMS`)
2. `TihuluFlightRadar.app` klasörünü `/Applications` (veya kullanıcı klasörü) içine sürükleyin
3. İlk açılışta Gatekeeper uyarısı çıkabilir: sağ tık → Aç (imzasız yapı için beklenen davranış)

## Gereksinimler
- macOS 12+ (Intel veya Apple Silicon)
- RTL-SDR sürücüsü ayrıdır; readsb ayrı kurulabilir
- Veriler `~/Library/Application Support/Tihulu/FlightRadar` altında tutulur

## Notlar
- Bu yapı PyInstaller ile üretilir; Apple notarization/imzası YOK — yayın öncesi ayrı onay gerekir
- Kod imzalama/notarization eklenmeden yaygın dağıtım önerilmez (PUBLIC RELEASE HOLD)
