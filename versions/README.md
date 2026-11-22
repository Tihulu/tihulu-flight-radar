# TIHULU Flight Radar — Versions

Bu dizin her sürümün kendi alt dizinini, kendi README’sini ve kurulum/erişim
bilgilerini tutar. En güncel sürümler ana README’de de listelenir.

## Mevcut sürümler

| Sürüm | Dizin | Durum | Kurulum / Erişim |
|---|---|---|---|
| Web 0.3.2.dev4 (canlı) | [web-0.3.2.dev4/](web-0.3.2.dev4/) | ✅ Canlı | Tarayıcı ile siteye erişim veya tek satırda lokal sunucu |
| Ubuntu / Pop!_OS masaüstü 0.3.2.dev4 | [desktop-ubuntu-popos/](desktop-ubuntu-popos/) | ✅ Taslak release (doğrulanmış) | Tek satır pipx kurulumu / .deb / AppImage |
| Windows masaüstü 0.3.2.dev4 | [desktop-windows/](desktop-windows/) | ✅ Taslak release (doğrulanmış) | İndir + çalıştır |
| macOS masaüstü 0.3.2.dev4 | [desktop-macos/](desktop-macos/) | ✅ Taslak release (doğrulanmış) | İndir + çalıştır |
| Raspberry Pi 5 (ARM64) 0.3.2.dev4 | [desktop-rpi5-arm/](desktop-rpi5-arm/) | ✅ Taslak release (CI QEMU) | Tek satır pipx kurulumu (ARM yerel) |

## İndirme (taslak release `__TAG__`)

Release sayfası: https://github.com/Tihulu/tihulu-flight-radar/releases/tag/__TAG__

| Dosya | Platform | İndir |
|---|---|---|
| `tihulu-flight-radar_0.3.2.dev4_amd64.deb` | Ubuntu/Pop!_OS x64 | [.deb](https://github.com/Tihulu/tihulu-flight-radar/releases/download/__TAG__/tihulu-flight-radar_0.3.2.dev4_amd64.deb) |
| `Tihulu_Flight_Radar-x86_64.AppImage` | Ubuntu/Pop!_OS x64 | [AppImage](https://github.com/Tihulu/tihulu-flight-radar/releases/download/__TAG__/Tihulu_Flight_Radar-x86_64.AppImage) |
| `TihuluFlightRadar-win-x64.zip` | Windows x64 | [zip](https://github.com/Tihulu/tihulu-flight-radar/releases/download/__TAG__/TihuluFlightRadar-win-x64.zip) |
| `TihuluFlightRadar-macos-arm64.zip` | macOS Apple Silicon | [zip](https://github.com/Tihulu/tihulu-flight-radar/releases/download/__TAG__/TihuluFlightRadar-macos-arm64.zip) |
| `SHA256SUMS` | tümü | [SHA256SUMS](https://github.com/Tihulu/tihulu-flight-radar/releases/download/__TAG__/SHA256SUMS) |

ARM64 (Pi 5) dosyaları aynı release'te `..._arm64.deb` ve `...-aarch64.AppImage`
olarak yer alır (CI QEMU yapısı; fiziksel Pi'de doğrulama gerekir).

Doğrulama: `sha256sum -c --ignore-missing SHA256SUMS` (indirilen dosyanın
hash'ini SHA256SUMS içeriğiyle karşılaştırır).

## Kurallar
1. Her sürüm DİZİN + README + spesifik kaynak/artefakt referansı ile birlikte eklenir.
2. Bu dizindeki sürüm kopyaları değiştirilmez; yeni sürüm için yeni tarihli dizin açılır.
3. Her README’de: exact kaynak SHA, doğrulama hash’i, kurulum komutu ve erişim adresleri bulunur.
4. Kurulumlar mevcut readsb/tar1090 servislerinize, ayarlarınıza ve kayıtlarınıza dokunmaz.
5. Public release = sürüm etiketi/YAYIN değil; bu dizin dağıtım kolaylığıdır. Ayrı onay gerekir.
