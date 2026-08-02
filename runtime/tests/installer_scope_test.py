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
    print("PASS installer scope: none/multiple/all harnesses + CLI-only mode")
    print("PASS Git scope: projection-only repository; authority and secrets excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
