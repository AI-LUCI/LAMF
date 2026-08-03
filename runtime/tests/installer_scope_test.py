"""Installer scope tests: no harness, selected harnesses, and safe Git projection."""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("lamf_installer", ROOT / "installer" / "install.py")
installer = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(installer)

report_spec = importlib.util.spec_from_file_location(
    "lamf_issue_report", ROOT / "installer" / "collect_issue_report.py"
)
issue_report = importlib.util.module_from_spec(report_spec)
assert report_spec.loader
report_spec.loader.exec_module(issue_report)


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

        adversarial_root = root / "Users" / "alice" / "private-project"
        (adversarial_root / "runtime" / "lamf").mkdir(parents=True)
        (adversarial_root / "VERSION").write_text(
            "C:/Users/alice/operator.token\n", encoding="utf-8"
        )
        forbidden = {
            "lamf.db": "private memory content",
            "operator.token": "github_pat_DO_NOT_COLLECT",
            "instance.key": "PRIVATE KEY",
            "events.jsonl": "payload text",
            "memory.log": "personal fact",
            "vault.md": "private vault",
            "backup.lamf": "private export",
        }
        for name, content in forbidden.items():
            (adversarial_root / name).write_text(content, encoding="utf-8")
        with mock.patch.object(issue_report.platform, "release", return_value="C:/Users/alice/private"):
            with mock.patch.object(issue_report.platform, "machine", return_value="secret machine name"):
                report = issue_report.build_report(
                    package_root=adversarial_root,
                    profile="controlled",
                    mode="core",
                    harnesses=["codex", "generic", "codex"],
                )
        encoded_report = json.dumps(report, sort_keys=True)
        assert report["schema"] == "lamf-public-issue-report-1"
        assert report["lamf_version"] == "unknown"
        assert report["platform"]["release"] == "redacted"
        assert report["platform"]["machine"] == "redacted"
        assert report["public_configuration"]["harnesses"] == ["codex", "generic"]
        assert report["privacy"] == {
            "collection_policy": "allowlist-only",
            "data_directory_accessed": False,
            "personal_paths_included": False,
            "memory_content_included": False,
        }
        for forbidden_value in (*forbidden, *forbidden.values(), "C:/Users", str(adversarial_root)):
            assert forbidden_value not in encoded_report
        for refused_args in (
            ["--data-dir", str(adversarial_root)],
            ["--diagnostic", "private memory content"],
        ):
            with redirect_stderr(io.StringIO()):
                try:
                    issue_report.build_parser().parse_args(refused_args)
                except SystemExit as exc:
                    assert exc.code == 2
                else:
                    raise AssertionError(f"private input option was accepted: {refused_args[0]}")

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
    print("PASS issue report: allowlist-only output excludes adversarial private artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
