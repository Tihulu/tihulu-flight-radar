"""Mocked end-to-end Linux installer regression (never uses real sudo/pipx/apt)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest


INSTALLER = Path(__file__).resolve().parents[1] / "scripts" / "install-linux.sh"


def _stub(path: Path, content: str):
    path.write_text("#!/bin/sh\n" + content, encoding="utf-8")
    path.chmod(0o755)


@pytest.mark.skipif(sys.platform != "linux" or getattr(os, "geteuid", lambda: 0)() == 0,
                    reason="Linux Debian/Ubuntu/Pop!_OS installer only; refuses root")
def test_one_line_upgrade_creates_both_application_shortcuts(tmp_path):
    home = tmp_path / "test-home"
    tools = tmp_path / "mock-bin"
    home.mkdir()
    tools.mkdir()
    _stub(tools / "sudo", "exit 0\n")
    _stub(tools / "pipx", """
mkdir -p "$HOME/.local/bin"
printf '#!/bin/sh\\nexit 0\\n' > "$HOME/.local/bin/tihulu-flight-radar"
printf '#!/bin/sh\\nexit 0\\n' > "$HOME/.local/bin/tihulu-flight-bridge"
printf '#!/bin/sh\\nexit 0\\n' > "$HOME/.local/bin/tihulu-flight-radar-classic"
chmod +x "$HOME/.local/bin/tihulu-flight-radar" "$HOME/.local/bin/tihulu-flight-bridge" "$HOME/.local/bin/tihulu-flight-radar-classic"
exit 0
""")
    _stub(tools / "curl", """
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then
    shift
    printf '<svg xmlns="http://www.w3.org/2000/svg"></svg>\\n' > "$1"
    exit 0
  fi
  shift
done
exit 1
""")
    _stub(tools / "dpkg", "exit 1\n")
    # The optional tar1090 static cache is not necessary to validate base
    # pipx replacement, and must not make mocked CI download 40 MiB.
    _stub(tools / "git", "exit 1\n")
    # Installer must preserve the user's unrelated local resources.
    preserved = home / ".local/share/important-data"
    preserved.parent.mkdir(parents=True)
    preserved.write_text("do not remove", encoding="utf-8")
    appdir = home / ".local/share/applications"
    appdir.mkdir(parents=True)
    (appdir / "tihulu-adsb-radar.desktop").write_text("old shortcut")
    env = dict(os.environ, HOME=str(home), PATH=str(tools)+os.pathsep+os.environ["PATH"],
               TIHULU_REF="feature/github-pages-local-bridge-2026-11-06")
    result = subprocess.run(["bash", str(INSTALLER)], env=env, text=True,
                            capture_output=True, timeout=35, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    qt = (appdir / "tihulu-flight-radar.desktop").read_text(encoding="utf-8")
    web = (appdir / "tihulu-flight-radar-web.desktop").read_text(encoding="utf-8")
    assert "Name=Tihulu Flight Radar\n" in qt
    assert 'Exec="'+str(home)+"/.local/bin/tihulu-flight-radar"+'"' in qt
    assert "Terminal=false" in qt
    assert "Name=Tihulu Flight Radar Live" in web
    assert 'Exec="'+str(home)+"/.local/bin/tihulu-flight-radar"+'"' in web
    assert "Terminal=false" in web
    classic = (appdir / "tihulu-flight-radar-classic.desktop").read_text()
    assert 'Exec="'+str(home)+"/.local/bin/tihulu-flight-radar-classic"+'"' in classic
    assert preserved.read_text() == "do not remove"
    assert not (appdir / "tihulu-adsb-radar.desktop").exists()
    assert (home / ".local/share/icons/hicolor/scalable/apps/tihulu-flight-radar.svg").exists()


@pytest.mark.skipif(sys.platform != "linux",
                    reason="Linux-only installer syntax checked on Linux CI")
def test_installer_shell_syntax():
    result = subprocess.run(["bash", "-n", str(INSTALLER)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
