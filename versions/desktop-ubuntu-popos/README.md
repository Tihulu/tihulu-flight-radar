# TIHULU Flight Radar — Ubuntu / Pop!_OS masaüstü 0.3.2.dev4

**Durum:** ✅ Taslak release `desktop-0.3.2.dev4-20261122-0734` (GitHub Actions: `desktop-versions-build.yml`) · **Kaynak:** main (parity merge sonrası)

## Tek satır kurulum (önerilen — pipx, mevcut kurulumunuza dokunmaz)
```
curl -fsSL https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/scripts/install-linux.sh | bash
```
- Debian 12 / Ubuntu 22.04+ / Pop!_OS desteklenir
- Mevcut readsb/tar1090 servisleriniz, alıcı ayarlarınız ve kayıtlarınız değişmez
- Sürümü pinellemek için: `TIHULU_REF=<commit-sha> bash -s` (install-linux.sh `TIHULU_REF` kabul eder)

## İndirilebilir paketler (taslak release `desktop-0.3.2.dev4-20261122-0734`)
| Paket | Dosya | İndir | Not |
|---|---|---|---|
| .deb | `tihulu-flight-radar_0.3.2.dev4_amd64.deb` | [download](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-0734/tihulu-flight-radar_0.3.2.dev4_amd64.deb) | `sudo dpkg -i` ile kurulur |
| AppImage | `Tihulu_Flight_Radar-x86_64.AppImage` | [download](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-0734/Tihulu_Flight_Radar-x86_64.AppImage) | `chmod +x` ile çalışır, kurulum gerektirmez |

Release sayfası: https://github.com/Tihulu/tihulu-flight-radar/releases/tag/desktop-0.3.2.dev4-20261122-0734 · Hash doğrulama: `SHA256SUMS` dosyasını indirip
`sha256sum -c --ignore-missing SHA256SUMS` komutuyla karşılaştırın.

## Mevcut kurulumunuz
Kurulu sürüm 0.3.2.dev4 · pipx venv · ~/.local/bin/tihulu-flight-radar symlink.
Rollback yolu: legacy/v0.3.1 @ 67280cd84feb89faec6a80f5fe2a55ce5f7b89e6.
