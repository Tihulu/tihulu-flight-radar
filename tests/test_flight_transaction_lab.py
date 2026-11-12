"""Adversarial transaction laboratory tests, confined to disposable fake CI roots."""
from pathlib import Path
import hashlib
import json
import os
import sys
import pytest

# Security fixture is deliberately POSIX/Linux-only; import collection on Windows
# must succeed without weakening any Linux assertions.
pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux-only transaction lab')

from tools.flight_transaction_lab import TransactionLab


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    return TransactionLab(tmp_path / "flight-transaction-lab" / "scenario")


def test_is_not_executable_as_real_workstation_install(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    with pytest.raises(RuntimeError, match="CI-only"):
        TransactionLab(tmp_path / "flight-transaction-lab" / "scenario")


def test_rejects_path_outside_runner_temp(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    with pytest.raises(RuntimeError, match="direct child"):
        TransactionLab(tmp_path / "home" / "app")


def test_stage_then_activate_without_destroying_prior_release(lab):
    lab.stage_fixture("old", b"v0.3.1")
    lab.stage_fixture("new", b"v0.3.2.dev4")
    lab.switch("old")
    assert lab.status()["active"] == "old"
    lab.switch("new")
    assert lab.status() == {
        "owner": "TIHULU_FLIGHT_TRANSACTION_LAB_V1",
        "active": "new", "previous": "old",
    }
    assert (lab.releases / "old" / "image.bin").read_bytes() == b"v0.3.1"
    assert (lab.releases / "new" / "image.bin").read_bytes() == b"v0.3.2.dev4"


def test_rollback_only_switches_pointer_preserves_both_releases(lab):
    lab.stage_fixture("v1", b"one")
    lab.stage_fixture("v2", b"two")
    lab.switch("v1")
    lab.switch("v2")
    lab.rollback()
    assert lab.status()["active"] == "v1"
    assert {x.name for x in lab.releases.iterdir()} == {"v1", "v2"}


def test_deactivation_preserves_all_fixtures(lab):
    lab.stage_fixture("v1", b"one")
    lab.switch("v1")
    lab.switch(None)
    assert lab.status()["active"] is None
    assert not lab.current.is_symlink()
    assert (lab.releases / "v1" / "image.bin").read_bytes() == b"one"


@pytest.mark.parametrize("fault", ["after_journal", "after_pointer", "after_state"])
def test_recovery_undoes_partial_activation(lab, fault):
    lab.stage_fixture("v1", b"one")
    lab.stage_fixture("v2", b"two")
    lab.switch("v1")
    with pytest.raises(RuntimeError, match="Injected fault"):
        lab.switch("v2", fault=fault)
    with pytest.raises(RuntimeError, match="recover"):
        lab.status()
    lab.recover()
    assert lab.status()["active"] == "v1"
    assert (lab.releases / "v2" / "image.bin").read_bytes() == b"two"


def test_rejects_same_name_without_overwriting(lab):
    lab.stage_fixture("only", b"keep")
    with pytest.raises(RuntimeError, match="already exists"):
        lab.stage_fixture("only", b"replace")
    assert (lab.releases / "only" / "image.bin").read_bytes() == b"keep"


def test_corrupt_release_refuses_switch(lab):
    lab.stage_fixture("v1", b"initial")
    lab.stage_fixture("v2", b"other")
    (lab.releases / "v2" / "image.bin").write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="manifest"):
        lab.switch("v2")
    assert lab.status()["active"] is None


def test_symlink_root_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    parent = tmp_path / "flight-transaction-lab"
    parent.mkdir()
    external = tmp_path / "other"
    external.mkdir()
    (parent / "scenario").symlink_to(external, target_is_directory=True)
    with pytest.raises(RuntimeError, match="Symlink"):
        TransactionLab(parent / "scenario")


def test_does_not_touch_preexisting_fake_pipx_or_system_configuration(lab):
    fake_home = lab.root.parent.parent / "user-home"
    app = fake_home / ".local/share/pipx/venvs/tihulu-flight-radar"
    app.mkdir(parents=True)
    secret = app / "owner-install-marker"
    secret.write_bytes(b"unchanged")
    lab.stage_fixture("v1", b"test")
    lab.switch("v1")
    lab.switch(None)
    assert secret.read_bytes() == b"unchanged"
    assert set(lab.root.iterdir()) == {
        lab.releases, lab.current.parent / "lab.lock", lab.state_path
    }


def test_rejects_wrong_release_marker_owner(lab):
    lab.stage_fixture("v1", b"valid")
    marker = lab.releases / "v1" / "manifest.json"
    record = json.loads(marker.read_text(encoding="utf-8"))
    record["owner"] = "FOREIGN"
    marker.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(RuntimeError, match="manifest"):
        lab.switch("v1")
