# TIHULU Flight Radar — Windows masaüstü 0.3.2.dev4

**Durum:** 🔨 Build bekliyor (GitHub Actions: `desktop-appimage.yml`, windows-latest)

## Kurulum (build tamamlandığında)
1. `TihuluFlightRadar-win64.zip` dosyasını indirin (GitHub Releases / Actions artifact)
2. Zip’i bir klasöre açın ( Program Files gerekmez, kullanıcı klasörü önerilir)
3. `TihuluFlightRadar.exe`’yi çalıştırın

## Gereksinimler
- Windows 10/11 x64 · Microsoft Visual C++ Redistributable (genellikle kurulu)
- RTL-SDR sürücüsü ayrıdır (WinUSB/Zadig); readsb ayrı kurulabilir
- Uygulama verileri `%APPDATA%\Tihulu\FlightRadar` altında tutulur

## Notlar
- Bu yapı PyInstaller ile üretilir; imzalı olmayan executable olarak yayınlanır
- Servis kurulumu yapmaz; kapatma yalnızca uygulamanın kendi kaynaklarını bırakır
