# TIHULU Flight Radar — macOS masaüstü 0.3.2.dev4

**Durum:** 🔨 Build bekliyor (GitHub Actions: `desktop-appimage.yml`, macos-latest)

## Kurulum (build tamamlandığında)
1. `TihuluFlightRadar-macos.zip` dosyasını indirin (Universal veya arm64)
2. `TihuluFlightRadar.app` klasörünü `/Applications` (veya kullanıcı klasörü) içine sürükleyin
3. İlk açılışta Gatekeeper uyarısı çıkabilir: sağ tık → Aç (imzasız yapı için beklenen davranış)

## Gereksinimler
- macOS 12+ (Intel veya Apple Silicon)
- RTL-SDR sürücüsü ayrıdır; readsb ayrı kurulabilir
- Veriler `~/Library/Application Support/Tihulu/FlightRadar` altında tutulur

## Notlar
- Bu yapı PyInstaller ile üretilir; Apple notarization/imzası YOK — yayın öncesi ayrı onay gerekir
- Kod imzalama/notarization eklenmeden yaygın dağıtım önerilmez (PUBLIC RELEASE HOLD)
