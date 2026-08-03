"""Installer scope tests: no harness, selected harnesses, and safe Git projection."""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

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
        regular_checkout = root / "regular-checkout"
        (regular_checkout / ".git").mkdir(parents=True)
        regular_data = regular_checkout / "not-created" / "private-data"
        assert installer.git_checkout_root(regular_data) == regular_checkout.resolve()

        linked_checkout = root / "linked-worktree"
        linked_checkout.mkdir()
        (linked_checkout / ".git").write_text("gitdir: ../metadata\n", encoding="utf-8")
        linked_data = linked_checkout / "private-secret-token-123"
        assert installer.git_checkout_root(linked_data) == linked_checkout.resolve()

        safe_data = root / "private-data"
        assert installer.git_checkout_root(safe_data) is None
        nested_checkout = safe_data / "nested-project" / ".git"
        nested_checkout.mkdir(parents=True)
        assert installer.git_checkout_root(safe_data) is None

        output = io.StringIO()
        with redirect_stdout(output):
            assert not installer.validate_data_dir_location(installer.UI(), linked_data)
        diagnostic = output.getvalue()
        assert "inside a Git checkout" in diagnostic
        assert "outside every Git checkout" in diagnostic
        assert "private-secret-token-123" not in diagnostic
        assert str(linked_checkout) not in diagnostic
        assert installer.validate_data_dir_location(installer.UI(), safe_data)

        previous_data_dir = installer.os.environ.get("LAMF_DATA_DIR")
        output = io.StringIO()
        with mock.patch.object(installer, "registered_paths", return_value=(None, None)):
            with redirect_stdout(output):
                result = installer.main([
                    "--data-dir", str(linked_data),
                    "--obsidian", "none",
                    "--harness", "none",
                    "--no-start",
                ])
        assert result == 2
        assert not linked_data.exists()
        assert "private-secret-token-123" not in output.getvalue()
        assert installer.os.environ.get("LAMF_DATA_DIR") == previous_data_dir

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
    print("PASS data scope: Git checkout paths rejected without disclosing selected paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
