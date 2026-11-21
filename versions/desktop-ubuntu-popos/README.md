# TIHULU Flight Radar — Ubuntu / Pop!_OS masaüstü 0.3.2.dev4

**Durum:** 🔨 Build bekliyor (GitHub Actions: `desktop-appimage.yml`) · **Kaynak:** main (parity merge sonrası)

## Tek satır kurulum (önerilen — pipx, mevcut kurulumunuza dokunmaz)
```
curl -fsSL https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/scripts/install-linux.sh | bash
```
- Debian 12 / Ubuntu 22.04+ / Pop!_OS desteklenir
- Mevcut readsb/tar1090 servisleriniz, alıcı ayarlarınız ve kayıtlarınız değişmez
- Sürümü pinellemek için: `TIHULU_REF=<commit-sha> bash -s` (install-linux.sh `TIHULU_REF` kabul eder)

## İndirilebilir paketler (Actions build’i tamamlandığında)
| Paket | Dosya | Not |
|---|---|---|
| .deb | `tihulu-flight-radar_0.3.2.dev4_amd64.deb` | `sudo dpkg -i` ile kurulur |
| AppImage | `Tihulu_Flight_Radar-x86_64.AppImage` | `chmod +x` ile çalışır, kurulum gerektirmez |

Paketler GitHub Releases sayfasındaki “Desktop builds” sürümünde yayınlanır
(ya da ilgili Actions run’ının artifact olarak indirilir). Hash’ler `SHA256SUMS`
dosyasında yayınlanır.

## Mevcut kurulumunuz
Kurulu sürüm 0.3.2.dev4 · pipx venv · ~/.local/bin/tihulu-flight-radar symlink.
Rollback yolu: legacy/v0.3.1 @ 67280cd84feb89faec6a80f5fe2a55ce5f7b89e6.
