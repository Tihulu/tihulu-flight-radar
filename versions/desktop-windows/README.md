# TIHULU Flight Radar — Windows masaüstü 0.3.2.dev4

**Durum:** ✅ Taslak release `desktop-0.3.2.dev4-20261122-0734` (GitHub Actions: `desktop-versions-build.yml`, windows-latest)

## Kurulum
1. [`TihuluFlightRadar-win-x64.zip`](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-0734/TihuluFlightRadar-win-x64.zip) dosyasını indirin
   ([release sayfası](https://github.com/Tihulu/tihulu-flight-radar/releases/tag/desktop-0.3.2.dev4-20261122-0734) · hash: `SHA256SUMS`)
2. Zip’i bir klasöre açın ( Program Files gerekmez, kullanıcı klasörü önerilir)
3. `TihuluFlightRadar.exe`’yi çalıştırın

## Gereksinimler
- Windows 10/11 x64 · Microsoft Visual C++ Redistributable (genellikle kurulu)
- RTL-SDR sürücüsü ayrıdır (WinUSB/Zadig); readsb ayrı kurulabilir
- Uygulama verileri `%APPDATA%\Tihulu\FlightRadar` altında tutulur

## Notlar
- Bu yapı PyInstaller ile üretilir; imzalı olmayan executable olarak yayınlanır
- Servis kurulumu yapmaz; kapatma yalnızca uygulamanın kendi kaynaklarını bırakır
