"""Sandbox-only regression tests of preflight. Never touch user HOME or services."""
import os
import stat
from pathlib import Path

import pytest

from tools.flight_safe_preflight import check, SAFE_NAME


def _tree(base):
    return sorted(str(p.relative_to(base)) for p in base.rglob("*"))


def test_empty_home_preflight_is_read_only(tmp_path):
    policy = tmp_path.parent / ("no-policy-" + tmp_path.name)
    before = _tree(tmp_path)
    result = check(tmp_path, policy)
    after = _tree(tmp_path)
    assert before == after == []
    assert result["ready_for_installer_qa"]
    assert not result["ready_for_installation"]
    assert result["candidate"] == SAFE_NAME
    assert result["check_mode"] == "read-only-no-side-effects"


def test_live_pipx_and_other_version_are_protected_not_replaced(tmp_path):
    pipx = tmp_path / ".local/share/pipx/venvs/tihulu-flight-radar"
    pipx.mkdir(parents=True)
    launcher = tmp_path / ".local/bin/tihulu-flight-radar"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("protected content", encoding="utf-8")
    before = launcher.read_bytes()
    result = check(tmp_path, tmp_path.parent / ("no-policy-" + tmp_path.name))
    assert result["existing_protected_names"]["installed_pipx"]["present"]
    assert result["existing_protected_names"]["installed_launcher"]["present"]
    assert result["ready_for_installer_qa"]
    assert launcher.read_bytes() == before


def test_future_launcher_conflict_is_refused(tmp_path):
    launcher = tmp_path / ".local/bin" / SAFE_NAME
    launcher.parent.mkdir(parents=True)
    launcher.write_text("someone else's launcher", encoding="utf-8")
    result = check(tmp_path, tmp_path.parent / ("no-policy-" + tmp_path.name))
    assert not result["ready_for_installer_qa"]
    assert any("launcher name already occupied" in s for s in result["blockers"])
    assert launcher.read_text(encoding="utf-8") == "someone else's launcher"


def test_symlink_ancestor_is_blocked_without_following(tmp_path):
    external = tmp_path.parent / ("outside-" + tmp_path.name)
    external.mkdir()
    (tmp_path / ".local").symlink_to(external, target_is_directory=True)
    before = _tree(external)
    result = check(tmp_path, tmp_path.parent / ("no-policy-" + tmp_path.name))
    assert not result["ready_for_installer_qa"]
    assert any("Symlink ancestor" in s for s in result["blockers"])
    assert _tree(external) == before


def test_old_sudoers_policy_metadata_blocks_installer_qa(tmp_path):
    policy = tmp_path.parent / ("legacy-policy-" + tmp_path.name)
    policy.write_text("fake policy test only", encoding="utf-8")
    before = policy.read_bytes()
    result = check(tmp_path, policy)
    assert result["sudoers_policy_present"]
    assert not result["ready_for_installer_qa"]
    assert any("Historical sudoers" in s for s in result["blockers"])
    assert policy.read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="Posix mode bits only")
def test_world_writable_parent_is_blocked_without_chmod(tmp_path):
    path = tmp_path / ".local"
    path.mkdir()
    path.chmod(0o777)
    try:
        result = check(tmp_path, tmp_path.parent / ("no-policy-" + tmp_path.name))
        assert any("Group/other-writable ancestor" in s for s in result["blockers"])
        assert stat.S_IMODE(path.stat().st_mode) == 0o777
    finally:
        path.chmod(0o700)


def test_home_must_be_absolute(tmp_path):
    with pytest.raises(ValueError, match="absolute"):
        check(Path("relative"), tmp_path / "nothing")


def test_zero_hidden_changes_during_preflight(tmp_path):
    (tmp_path / ".config").mkdir()
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".local/share").mkdir(parents=True)
    baseline = _tree(tmp_path)
    for _ in range(3):
        result = check(tmp_path, tmp_path.parent / ("no-policy-" + tmp_path.name))
        assert result["ready_for_installer_qa"]
    assert _tree(tmp_path) == baseline
