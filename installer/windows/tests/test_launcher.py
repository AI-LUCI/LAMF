"""Unit tests for the LAMF Windows launcher command derivation.

These tests exercise the pure-Python reimplementation in
``installer/windows/build_launcher.py`` and inspect ``launcher.rs`` to ensure
the Rust source mirrors the same rules.  They do not require a compiled EXE.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the parent package importable regardless of cwd.
INSTALLER_WINDOWS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INSTALLER_WINDOWS))

from build_launcher import derive_command, parse_rustc_version  # noqa: E402
from build_config import RUSTC_VERSION  # noqa: E402


def _expected_env(data_dir: str) -> dict[str, str]:
    """Return the environment additions the launcher must inject."""
    return {
        "LAMF_DATA_DIR": data_dir,
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }


def _rust_source() -> str:
    return (INSTALLER_WINDOWS / "launcher.rs").read_text(encoding="utf-8")


def test_parse_rustc_version():
    assert parse_rustc_version("rustc 1.95.0 (59807616e 2026-04-14)") == "1.95.0"
    assert parse_rustc_version("rustc 1.2.3") == "1.2.3"


def test_parse_rustc_version_invalid():
    try:
        parse_rustc_version("not rustc output")
    except ValueError as exc:
        assert "cannot parse" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_lamf_command_with_args():
    exe = Path("C:/Program Files/LAMF/lamf.exe")
    state = {"data_dir": "C:/Users/Alice/AppData/Local/LAMF/data"}
    python, args, env = derive_command(exe, state, [str(exe), "status"])

    assert python == Path("C:/Program Files/LAMF/python/pythonw.exe")
    assert args == ["-m", "lamf.cli", "status"]
    assert env == _expected_env("C:/Users/Alice/AppData/Local/LAMF/data")


def test_lamf_command_no_args():
    exe = Path("C:/LAMF/lamf.exe")
    state = {"data_dir": "D:/lamf-data"}
    python, args, env = derive_command(exe, state, [str(exe)])

    assert python == Path("C:/LAMF/python/pythonw.exe")
    assert args == ["-m", "lamf.cli"]
    assert env == _expected_env("D:/lamf-data")


def test_lamf_control_command():
    exe = Path("C:/Program Files/LAMF/lamf-control.exe")
    state = {"data_dir": "C:/Users/Alice/AppData/Local/LAMF/data"}
    python, args, env = derive_command(exe, state, [str(exe)])

    assert python == Path("C:/Program Files/LAMF/python/pythonw.exe")
    assert args == [
        "-m",
        "lamf.cli",
        "serve",
        "--data-dir",
        "C:/Users/Alice/AppData/Local/LAMF/data",
    ]
    assert env == _expected_env("C:/Users/Alice/AppData/Local/LAMF/data")


def test_lamf_control_ignores_case_and_extra_args():
    exe = Path("C:/LAMF/LAMF-CONTROL.EXE")
    state = {"data_dir": "C:/data"}
    python, args, env = derive_command(exe, state, [str(exe), "--port", "9000"])

    assert python == Path("C:/LAMF/python/pythonw.exe")
    assert args == [
        "-m",
        "lamf.cli",
        "serve",
        "--data-dir",
        "C:/data",
        "--port",
        "9000",
    ]


def test_missing_data_dir_raises():
    exe = Path("C:/LAMF/lamf.exe")
    try:
        derive_command(exe, {}, [str(exe)])
    except ValueError as exc:
        assert "data_dir missing" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_empty_data_dir_raises():
    exe = Path("C:/LAMF/lamf.exe")
    try:
        derive_command(exe, {"data_dir": ""}, [str(exe)])
    except ValueError as exc:
        assert "data_dir missing" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_pinned_rustc_matches_environment():
    """The pinned version must match the rustc available in this environment.

    This is a guard against stale pins; a real build host must install the
    matching toolchain.
    """
    import subprocess

    result = subprocess.run(["rustc", "--version"], capture_output=True, text=True, check=True)
    installed = parse_rustc_version(result.stdout.strip())
    assert installed == RUSTC_VERSION, f"rustc {installed} != pinned {RUSTC_VERSION}"


def test_rust_source_reads_install_state():
    source = _rust_source()
    assert 'install-state.json' in source
    assert 'json_string_field' in source
    assert '"data_dir"' in source


def test_rust_source_sets_lamf_data_dir():
    source = _rust_source()
    assert 'LAMF_DATA_DIR' in source


def test_rust_source_uses_pythonw():
    source = _rust_source()
    assert 'pythonw.exe' in source


def test_rust_source_branching_by_base_name():
    source = _rust_source()
    assert 'lamf-control' in source
    assert '"serve"' in source
    assert '"--data-dir"' in source


def test_rust_source_uninstall_uses_module():
    """The native uninstall launcher must run the helper as a package module."""
    source = _rust_source()
    assert '-m").arg("installer.windows.uninstall_helper"' in source
    assert 'PYTHONPATH' in source
    assert '/APP_DIR' in source
    assert '/DATA_DIR' in source


def _function_source(source: str, name: str) -> str:
    """Return the body of a Rust fn *name* from *source*."""
    start = source.find(f"fn {name}(")
    assert start != -1, f"function {name} not found"
    # Find the opening brace of the function body.
    brace = source.find("{", start)
    depth = 0
    for i in range(brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[brace:i + 1]
    raise AssertionError(f"could not find end of function {name}")


def _uninstall_branch_source() -> str:
    """Return the Rust source between the uninstall branch and its else."""
    source = _rust_source()
    start = source.find('if base == "uninstall"')
    assert start != -1, "uninstall branch not found in launcher.rs"
    end = source.find('} else {', start)
    assert end != -1, "end of uninstall branch not found in launcher.rs"
    return source[start:end]


def test_rust_source_uninstall_nulls_stdio():
    """uninstall.exe must null stdio to survive invalid inherited handles."""
    source = _rust_source()
    branch = _uninstall_branch_source()
    assert 'configure_uninstall_stdio(&mut cmd)' in branch
    # The helper function itself applies Stdio::null() to all three streams.
    helper = _function_source(source, "configure_uninstall_stdio")
    assert helper.count('Stdio::null()') == 3


def test_rust_source_lamf_branches_do_not_null_stdio():
    """lamf.exe and lamf-control.exe must keep inherited console/agent stdio."""
    source = _rust_source()
    start = source.find('} else {')
    assert start != -1
    # Exclude the configure_uninstall_stdio helper function, which is declared
    # before main; only inspect the else branch and the lamf-control block.
    after_else = source[start:source.find("fn configure_uninstall_stdio")]
    assert 'configure_uninstall_stdio(&mut cmd)' not in after_else
    assert 'Stdio::null()' not in after_else


def test_rust_source_windows_only_guard():
    source = _rust_source()
    assert '#[cfg(windows)]' in source
    assert '#[cfg(not(windows))]' in source
    assert "LAMF launcher is Windows-only" in source


def test_rust_source_no_external_dependencies():
    source = _rust_source()
    # No Cargo.toml exists, and the source only uses stdlib.
    assert "extern crate" not in source
    assert "use " in source  # stdlib imports are present


def test_install_state_round_trip_with_spaces():
    """Paths containing spaces survive a JSON round-trip through the model."""
    exe = Path("C:/Users/Alice Liddell/LAMF/lamf.exe")
    data = "C:/Users/Alice Liddell/AppData/Local/LAMF/data"
    state = {"data_dir": data}
    text = json.dumps(state)
    loaded = json.loads(text)
    python, args, env = derive_command(exe, loaded, [str(exe), "doctor"])

    assert python == Path("C:/Users/Alice Liddell/LAMF/python/pythonw.exe")
    assert env == _expected_env(data)
    assert "doctor" in args


def test_install_state_round_trip_with_unicode_omega():
    """JSON-escaped Unicode (e.g. Ω as \\u03a9) is decoded to the real path."""
    exe = Path("C:/tmp/LAMF Install Ω/Application/lamf.exe")
    data = "C:/tmp/LAMF Install Ω/Private Memory"
    state = {"data_dir": data}
    text = json.dumps(state, ensure_ascii=True)
    loaded = json.loads(text)
    python, args, env = derive_command(exe, loaded, [str(exe), "doctor"])

    assert python == Path("C:/tmp/LAMF Install Ω/Application/python/pythonw.exe")
    assert env == _expected_env(data)


def test_install_state_round_trip_with_non_bmp_emoji():
    """Non-BMP Unicode decoded from a surrogate pair survives the model."""
    exe = Path("C:/tmp/LAMF 😀/Application/lamf.exe")
    data = "C:/tmp/LAMF 😀/Private Memory"
    state = {"data_dir": data}
    text = json.dumps(state, ensure_ascii=True)
    loaded = json.loads(text)
    python, args, env = derive_command(exe, loaded, [str(exe), "doctor"])

    assert python == Path("C:/tmp/LAMF 😀/Application/python/pythonw.exe")
    assert env == _expected_env(data)


def test_launcher_forces_utf8_env():
    """The launcher must inject UTF-8 mode flags for the embedded interpreter."""
    exe = Path("C:/tmp/LAMF Ω 😀/lamf.exe")
    data = "C:/tmp/LAMF Ω 😀/Private Memory"
    state = {"data_dir": data}
    _python, args, env = derive_command(exe, state, [str(exe), "status"])

    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    # Caller arguments and data path are preserved as well.
    assert env["LAMF_DATA_DIR"] == data
    assert "status" in args


def test_uninstall_command_uses_module_execution():
    """uninstall.exe must run the helper as a module so relative imports work."""
    exe = Path("C:/Program Files/LAMF/uninstall.exe")
    data = "C:/Users/Alice/AppData/Local/LAMF/data"
    state = {"data_dir": data}
    python, args, env = derive_command(exe, state, [str(exe)])

    assert python == Path("C:/Program Files/LAMF/python/pythonw.exe")
    assert args[:2] == ["-m", "installer.windows.uninstall_helper"]
    assert "/APP_DIR" in args
    assert Path(args[args.index("/APP_DIR") + 1]) == exe.parent
    assert "/DATA_DIR" in args
    assert args[args.index("/DATA_DIR") + 1] == data
    assert "PYTHONPATH" in env
    assert str(exe.parent / "app") in env["PYTHONPATH"]
    assert "PYTHONUTF8" in env
    assert "PYTHONIOENCODING" in env
    # LAMF_DATA_DIR is passed explicitly via /DATA_DIR, not via the environment.
    assert "LAMF_DATA_DIR" not in env


def test_uninstall_command_forwards_caller_args():
    """Additional arguments passed to uninstall.exe must be forwarded."""
    exe = Path("C:/LAMF/uninstall.exe")
    state = {"data_dir": "C:/lamf-data"}
    _python, args, _env = derive_command(
        exe, state, [str(exe), "/FORCE", "/SILENT"]
    )

    assert "installer.windows.uninstall_helper" in args
    assert "/FORCE" in args
    assert "/SILENT" in args


def test_uninstall_command_preserves_existing_pythonpath():
    """PYTHONPATH additions must not clobber an existing value."""
    exe = Path("C:/LAMF/uninstall.exe")
    state = {"data_dir": "C:/lamf-data"}
    import os
    original = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = "C:/existing/path"
    try:
        _python, _args, env = derive_command(exe, state, [str(exe)])
        assert str(exe.parent / "app") in env["PYTHONPATH"]
        assert "C:/existing/path" in env["PYTHONPATH"]
    finally:
        if original is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = original


def test_rust_source_sets_env():
    source = _rust_source()
    assert 'LAMF_DATA_DIR' in source
    assert 'PYTHONUTF8' in source
    assert 'PYTHONIOENCODING' in source


def test_rust_unit_tests_pass():
    """The Rust launcher unit tests (including JSON unescaping) must pass."""
    import subprocess

    source = INSTALLER_WINDOWS / "launcher.rs"
    test_exe = INSTALLER_WINDOWS / "build" / "launcher-test"
    subprocess.run(
        ["rustc", "--test", "-o", str(test_exe), str(source)],
        capture_output=True, text=True, check=True,
    )
    result = subprocess.run([str(test_exe)], capture_output=True, text=True, check=True)
    assert "test result: ok" in result.stdout


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
