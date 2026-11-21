# TIHULU Flight Radar — Versions

Bu dizin her sürümün kendi alt dizinini, kendi README’sini ve kurulum/erişim
bilgilerini tutar. En güncel sürümler ana README’de de listelenir.

## Mevcut sürümler

| Sürüm | Dizin | Durum | Kurulum / Erişim |
|---|---|---|---|
| Web 0.3.2.dev4 (canlı) | [web-0.3.2.dev4/](web-0.3.2.dev4/) | ✅ Canlı | Tarayıcı ile siteye erişim veya tek satırda lokal sunucu |
| Ubuntu / Pop!_OS masaüstü 0.3.2.dev4 | [desktop-ubuntu-popos/](desktop-ubuntu-popos/) | 🔨 Build bekliyor | Tek satır pipx kurulumu / .deb / AppImage |
| Windows masaüstü 0.3.2.dev4 | [desktop-windows/](desktop-windows/) | 🔨 Build bekliyor | İndir + çalıştır |
| macOS masaüstü 0.3.2.dev4 | [desktop-macos/](desktop-macos/) | 🔨 Build bekliyor | İndir + çalıştır |
| Raspberry Pi 5 (ARM64) 0.3.2.dev4 | [desktop-rpi5-arm/](desktop-rpi5-arm/) | 🔨 Build bekliyor | Tek satır pipx kurulumu (ARM yerel) |

## Kurallar
1. Her sürüm DİZİN + README + spesifik kaynak/artefakt referansı ile birlikte eklenir.
2. Bu dizindeki sürüm kopyaları değiştirilmez; yeni sürüm için yeni tarihli dizin açılır.
3. Her README’de: exact kaynak SHA, doğrulama hash’i, kurulum komutu ve erişim adresleri bulunur.
4. Kurulumlar mevcut readsb/tar1090 servislerinize, ayarlarınıza ve kayıtlarınıza dokunmaz.
5. Public release = sürüm etiketi/YAYIN değil; bu dizin dağıtım kolaylığıdır. Ayrı onay gerekir.
