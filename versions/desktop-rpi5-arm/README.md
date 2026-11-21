# TIHULU Flight Radar — Raspberry Pi 5 (ARM64) 0.3.2.dev4

**Durum:** 🔨 Build bekliyor / ARM kurulum yolu

## Seçenek A — Tek satır pipx kurulumu (önerilen, ARM yerel)
Raspberry Pi OS 64-bit (Bookworm+) üzerinde:
```
curl -fsSL https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/scripts/install-linux.sh | bash
```
- PySide6’nın resmi ARM64 wheel’leri vardır; ek derleme gerekmez
- Bookworm gereksinimleri: `python3-venv pipx git curl` + Qt sistem kütüphaneleri
  (install-linux.sh bunları `apt` ile kurar)
- readsb/tar1090’ı Pi’ınızda ayrıca çalıştırabilirsiniz; uygulama ona dokunmaz

## Seçenek B — ARM64 AppImage (build tamamlandığında)
`Tihulu_Flight_Radar-aarch64.AppImage` indir → `chmod +x` → çalıştır.
(CI’da QEMU aarch64 emülasyonu ile üretilir; fiziksel Pi’de doğrulama gerekir.)

## Fiziksel Pi doğrulaması (sahip adımı)
- Pi 5 + Nooelec/RTL-SDR ile gerçek alım testi yapılmalı (CI bunu garanti etmez)
- readsb varsa sürücü çakışması olur; tek SDR sahibi ilkesi geçerlidir
