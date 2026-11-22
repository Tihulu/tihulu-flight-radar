# TIHULU Flight Radar — Raspberry Pi 5 (ARM64) 0.3.2.dev4

**Durum:** ✅ Taslak release `desktop-0.3.2.dev4-20261122-0734` (CI QEMU yapısı) / ARM kurulum yolu

## Seçenek A — Tek satır pipx kurulumu (önerilen, ARM yerel)
Raspberry Pi OS 64-bit (Bookworm+) üzerinde:
```
curl -fsSL https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/scripts/install-linux.sh | bash
```
- PySide6’nın resmi ARM64 wheel’leri vardır; ek derleme gerekmez
- Bookworm gereksinimleri: `python3-venv pipx git curl` + Qt sistem kütüphaneleri
  (install-linux.sh bunları `apt` ile kurar)
- readsb/tar1090’ı Pi’ınızda ayrıca çalıştırabilirsiniz; uygulama ona dokunmaz

## Seçenek B — ARM64 paketler (taslak release `desktop-0.3.2.dev4-20261122-0734`)
| Paket | Dosya | İndir |
|---|---|---|
| .deb (arm64) | `tihulu-flight-radar_0.3.2.dev4_arm64.deb` | [download](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-0734/tihulu-flight-radar_0.3.2.dev4_arm64.deb) |
| AppImage (aarch64) | `Tihulu_Flight_Radar-aarch64.AppImage` | [download](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-0734/Tihulu_Flight_Radar-aarch64.AppImage) |

Release sayfası: https://github.com/Tihulu/tihulu-flight-radar/releases/tag/desktop-0.3.2.dev4-20261122-0734 · Hash doğrulama: `SHA256SUMS` + `sha256sum -c --ignore-missing`.
(CI’da QEMU aarch64 emülasyonu ile üretilir; fiziksel Pi’de doğrulama gerekir.)

## Fiziksel Pi doğrulaması (sahip adımı)
- Pi 5 + Nooelec/RTL-SDR ile gerçek alım testi yapılmalı (CI bunu garanti etmez)
- readsb varsa sürücü çakışması olur; tek SDR sahibi ilkesi geçerlidir
