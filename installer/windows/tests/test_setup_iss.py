"""Static contract tests for installer/windows/setup.iss.

These tests inspect the Inno Setup source and enforce UI behavior contracts
(e.g. silent installs must not block on a MsgBox).
"""

from __future__ import annotations

import re
from pathlib import Path


SETUP_ISS = Path(__file__).resolve().parents[1] / "setup.iss"


def _run_post_install_body() -> str:
    text = SETUP_ISS.read_text(encoding="utf-8")
    match = re.search(r"^function RunPostInstall[\s\S]*?^end;", text, re.S | re.M)
    if not match:
        raise AssertionError("could not locate RunPostInstall in setup.iss")
    return match.group(0)


def test_run_post_install_logs_in_silent_mode():
    """Failure in silent/very-silent mode must log, not show MsgBox."""
    body = _run_post_install_body()
    # Every MsgBox in RunPostInstall must be in an else branch guarded by
    # WizardSilent.  We track whether the current line lives inside such a
    # branch by looking for "else" on the immediately preceding non-empty line.
    prev_stripped = ""
    for raw in body.splitlines():
        stripped = raw.strip().lower()
        if not stripped:
            continue
        if "msgbox(" in stripped:
            assert "else" in prev_stripped, (
                f"RunPostInstall shows an unconditional MsgBox: {raw.strip()}"
            )
        prev_stripped = stripped


def test_run_post_install_has_silent_branch():
    """RunPostInstall must contain a WizardSilent branch for each failure path."""
    body = _run_post_install_body()
    assert "if WizardSilent then" in body, "missing WizardSilent guard in RunPostInstall"
    assert "Log(" in body, "missing Log() calls for silent-mode failure reporting"


def _cur_uninstall_step_changed_body() -> str:
    text = SETUP_ISS.read_text(encoding="utf-8")
    match = re.search(r"^procedure CurUninstallStepChanged[\s\S]*?^end;", text, re.S | re.M)
    if not match:
        raise AssertionError("could not locate CurUninstallStepChanged in setup.iss")
    return match.group(0)


def test_cur_uninstall_step_changed_uses_inno_mode():
    """The uninstall helper must be invoked in /INNO_MODE (not the legacy /INNO)."""
    body = _cur_uninstall_step_changed_body()
    assert "/INNO_MODE" in body, "setup.iss must invoke uninstall helper with /INNO_MODE"
    assert "/INNO /SILENT" not in body, "setup.iss must not use the legacy /INNO switch"


def test_cur_uninstall_step_changed_checks_exec_and_aborts():
    """Exec failure or a nonzero exit code must both abort the uninstall."""
    body = _cur_uninstall_step_changed_body()
    assert "Exec(" in body, "CurUninstallStepChanged must call Exec"
    assert "if not Exec(" in body, "Exec result must be checked"
    assert "Abort" in body, "CurUninstallStepChanged must call Abort on failure"
    # Count Abort calls: one for Exec failure, one for nonzero ResultCode.
    abort_count = body.count("Abort;")
    assert abort_count >= 2, (
        f"expected at least two Abort calls (Exec failure + nonzero exit), found {abort_count}"
    )
    assert "ResultCode <> 0" in body, "nonzero ResultCode must trigger Abort"


def test_cur_uninstall_step_changed_passes_log_file():
    """Inno Setup must pass a quoted /LOG_FILE path for diagnostic capture."""
    body = _cur_uninstall_step_changed_body()
    assert "/LOG_FILE=" in body, "setup.iss must pass /LOG_FILE to the uninstall helper"
    assert "uninstall-helper.log" in body, "expected default uninstall-helper.log path"
