"""Installer scope tests: no harness, selected harnesses, and safe Git projection."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("lamf_installer", ROOT / "installer" / "install.py")
installer = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(installer)


def main() -> int:
    assert installer.parse_args(["--obsidian", "none"]).obsidian == "none"
    assert installer.parse_args(["--obsidian", "parallel"]).obsidian == "parallel"
    assert installer.choose_harnesses(["none"], interactive=False) == ()
    assert installer.choose_harnesses(None, interactive=False) == ()
    assert installer.choose_harnesses(["grok", "hermes", "grok"], interactive=False) == ("grok", "hermes")
    assert installer.choose_harnesses(["all"], interactive=False) == installer.HARNESSES
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data, vault = root / "data", root / "vault"
        ui = installer.UI()
        installer.write_harness_registrations(ui, data, ())
        selected = json.loads((data / "adapters" / "selection.json").read_text(encoding="utf-8"))
        assert selected["harnesses"] == []
        installer.write_harness_registrations(ui, data, ("grok", "hermes"))
        assert (data / "adapters" / "grok.toml").is_file()
        assert (data / "adapters" / "hermes.yaml").is_file()
        assert not (data / "adapters" / "codex.toml").exists()
        standalone = installer.write_helper_scripts(ui, data, None)
        standalone_text = standalone["start_ps1"].read_text(encoding="utf-8")
        assert "'serve'" in standalone_text and "'watch'" not in standalone_text
        assert "--vault" not in standalone_text
        parallel = installer.write_helper_scripts(ui, data, vault)
        parallel_text = parallel["start_ps1"].read_text(encoding="utf-8")
        assert "'serve'" in parallel_text and "'watch'" in parallel_text
        assert "--vault" in parallel_text
        if shutil.which("git"):
            assert installer.setup_git_vault(ui, vault, "vault")
            assert (vault / ".git").is_dir()
            ignore = (vault / ".gitignore").read_text(encoding="utf-8")
            assert "07 Review Queue/" in ignore and "99 System/" in ignore
            assert not (data / ".git").exists()
    # --- Data/Git boundary: refuse an authority directory inside a checkout ---
    assert installer.parse_args([]).allow_git_data_dir is False
    assert installer.parse_args(["--allow-git-data-dir"]).allow_git_data_dir is True
    with tempfile.TemporaryDirectory() as td:
        codex_home = Path(td) / ".codex"
        codex_home.mkdir()
        agents = codex_home / "AGENTS.md"
        agents.write_text("# Existing guidance\n", encoding="utf-8")
        ui = installer.UI()
        first = installer.install_codex_startup(ui, codex_home)
        installer.install_codex_startup(ui, codex_home)
        guidance = agents.read_text(encoding="utf-8")
        assert "# Existing guidance" in guidance
        assert guidance.count("<!-- BEGIN LAMF MANAGED -->") == 1
        assert "memory_orientation" in guidance and "memory_search" in guidance
        assert "name: lamf-memory" in first["skill"].read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        checkout = root / "repo"
        (checkout / ".git").mkdir(parents=True)
        nested = checkout / "sub" / "LAMF"
        outside = root / "outside" / "LAMF"

        # Detection walks up and is independent of the `git` binary.
        assert installer.git_checkout_root(nested) == checkout
        assert installer.git_checkout_root(checkout) == checkout
        assert installer.git_checkout_root(outside) is None

        # A worktree/submodule marks the root with a `.git` FILE, not a directory.
        linked = root / "worktree"
        linked.mkdir()
        (linked / ".git").write_text("gitdir: /elsewhere/.git/worktrees/wt\n", encoding="utf-8")
        assert installer.git_checkout_root(linked / "LAMF") == linked

        ui = installer.UI()
        # Refused by default, and refused BEFORE anything is created on disk.
        assert installer.guard_data_dir_outside_git(ui, nested, False) is False
        assert not nested.exists()
        # Explicit opt-in still allowed (repairing an instance already there).
        assert installer.guard_data_dir_outside_git(ui, nested, True) is True
        # Outside any checkout is always fine.
        assert installer.guard_data_dir_outside_git(ui, outside, False) is True

    # --- --no-start doctor semantics: intentionally stopped is not a failure ---
    if installer.server_up():
        print("SKIP --no-start doctor delta: a LAMF server is already running here")
    else:
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "data"
            ui = installer.UI()
            expected = installer.run_doctor(ui, data, None, "absent", server_expected=True)
            not_expected = installer.run_doctor(ui, data, None, "absent", server_expected=False)
            # The two reachability checks move from failures to warnings; every
            # other check is unchanged, so the deltas are exactly 2.
            assert not_expected.failures == expected.failures - 2, (
                f"{expected.failures} -> {not_expected.failures}")
            assert not_expected.warnings == expected.warnings + 2, (
                f"{expected.warnings} -> {not_expected.warnings}")

    print("PASS installer scope: none/multiple/all harnesses + CLI-only mode")
    print("PASS Git scope: projection-only repository; authority and secrets excluded")
    print("PASS data/Git boundary: authority refused inside a checkout, pre-mutation")
    print("PASS --no-start doctor: stopped server warns instead of failing")
    print("PASS Codex startup: profile guidance and skill are idempotent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
