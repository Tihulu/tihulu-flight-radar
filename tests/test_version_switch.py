"""Pop!_OS pinned-preview and legacy rollback contract, no real package actions."""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SWITCH = ROOT / "scripts/popos-version-switch.sh"
INSTALL = ROOT / "scripts/install-linux.sh"
LEGACY = "67280cd84feb89faec6a80f5fe2a55ce5f7b89e6"
PREVIEW = "e56a0fc890327c6a3705dcb4bde9226b7bed19b6"


def test_switcher_is_valid_bash_and_help_never_installs():
    shell = subprocess.run(["bash", "-n", str(SWITCH)],
                           capture_output=True, text=True, check=False)
    assert shell.returncode == 0, shell.stderr
    help_ = subprocess.run(["bash", str(SWITCH), "--help"],
                           capture_output=True, text=True, check=False)
    assert help_.returncode == 0, help_.stderr
    assert "preview|legacy" in help_.stdout


def test_pinned_git_sources_and_single_replacement_are_explicit():
    script = SWITCH.read_text(encoding="utf-8")
    installer = INSTALL.read_text(encoding="utf-8")
    assert LEGACY in script
    assert PREVIEW in script
    assert 'expected="0.3.2.dev4"' in script
    assert 'expected="0.3.1"' in script
    assert 'TIHULU_REF="$ref" bash "$tmp"' in script
    assert 'pipx install --force "git+https://github.com/Tihulu/tihulu-flight-radar.git@$ref"' in installer
    # User's working RF backend must never be purged or restarted by the installer.
    assert "apt-get purge" not in installer
    assert "systemctl restart readsb" not in installer
    assert "sudo systemctl stop readsb" not in installer


def test_invalid_switch_command_must_not_touch_system():
    outcome = subprocess.run(["bash", str(SWITCH), "something-not-a-version"],
                             capture_output=True, text=True, check=False)
    assert outcome.returncode == 2
    assert "preview|legacy" in outcome.stderr
