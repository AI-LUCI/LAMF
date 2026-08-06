"""Tests for installer/windows/acquire.py.

All tests use local fixture files and a temporary cache directory.  They never
hit the public internet.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acquire import (  # noqa: E402
    Artifact,
    _download,
    _is_pinned_url,
    acquire_all,
    ensure_artifact,
    load_provenance,
    write_provenance,
)


def _make_artifact(cache_dir: Path, name: str, content: bytes,
                   url_path: str = "file.txt") -> Artifact:
    """Create a local file-based artifact for testing."""
    src = cache_dir / "source"
    src.mkdir(parents=True, exist_ok=True)
    src_file = src / url_path
    src_file.write_bytes(content)
    return Artifact(
        name=name,
        url=src_file.as_uri(),
        filename=f"{name}.bin",
        sha256=hashlib.sha256(content).hexdigest(),
    )


def test_is_pinned_url_rejects_latest():
    assert _is_pinned_url("https://example.com/python-3.11.9.zip") is True
    assert _is_pinned_url("https://example.com/latest/python.zip") is False
    assert _is_pinned_url("https://example.com/LATEST/download.exe") is False


def test_ensure_artifact_downloads_when_missing():
    with tempfile.TemporaryDirectory() as td:
        cache_dir = Path(td) / "cache"
        content = b"pinned artifact content"
        artifact = _make_artifact(Path(td), "sample", content)
        path, status = ensure_artifact(artifact, cache_dir)
        assert status == "downloaded"
        assert path == cache_dir / "sample.bin"
        assert path.read_bytes() == content


def test_ensure_artifact_uses_cache_on_hash_match():
    with tempfile.TemporaryDirectory() as td:
        cache_dir = Path(td) / "cache"
        content = b"cached artifact content"
        artifact = _make_artifact(Path(td), "sample", content)
        path1, status1 = ensure_artifact(artifact, cache_dir)
        assert status1 == "downloaded"
        path2, status2 = ensure_artifact(artifact, cache_dir)
        assert status2 == "cached"
        assert path1 == path2


def test_ensure_artifact_detects_tampered_cache():
    with tempfile.TemporaryDirectory() as td:
        cache_dir = Path(td) / "cache"
        content = b"original"
        artifact = _make_artifact(Path(td), "sample", content)
        ensure_artifact(artifact, cache_dir)
        (cache_dir / "sample.bin").write_bytes(b"tampered")
        try:
            ensure_artifact(artifact, cache_dir)
        except RuntimeError as exc:
            assert "SHA-256 mismatch" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for tampered cache")


def test_ensure_artifact_refuses_mutable_url():
    with tempfile.TemporaryDirectory() as td:
        artifact = Artifact(
            name="bad",
            url="https://example.com/latest.zip",
            filename="bad.zip",
            sha256="0" * 64,
        )
        try:
            ensure_artifact(artifact, Path(td) / "cache")
        except ValueError as exc:
            assert "refusing mutable URL" in str(exc)
        else:
            raise AssertionError("expected ValueError for mutable URL")


def test_write_provenance_records_all_artifacts():
    with tempfile.TemporaryDirectory() as td:
        cache_dir = Path(td) / "cache"
        artifacts = [
            Artifact(name="a", url="https://x/a.zip", filename="a.zip",
                     sha256="0" * 64),
            Artifact(name="b", url="https://x/b.whl", filename="b.whl",
                     sha256="1" * 64),
        ]
        statuses = {"a": "cached", "b": "downloaded"}
        path = write_provenance(artifacts, cache_dir, statuses=statuses)
        assert path == cache_dir / "provenance.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
        assert len(data["artifacts"]) == 2
        names = {a["name"] for a in data["artifacts"]}
        assert names == {"a", "b"}
        for entry in data["artifacts"]:
            assert "url" in entry
            assert "sha256" in entry
            assert "status" in entry
            assert "cached_at" in entry


def test_load_provenance_returns_empty_stub_when_missing():
    with tempfile.TemporaryDirectory() as td:
        data = load_provenance(Path(td) / "cache")
        assert data["schema_version"] == 1
        assert data["artifacts"] == []


def test_acquire_all_returns_paths_and_writes_provenance():
    with tempfile.TemporaryDirectory() as td:
        cache_dir = Path(td) / "cache"
        content = b"wheel content"
        artifact = _make_artifact(Path(td), "wheel", content)
        paths = acquire_all(cache_dir, artifacts=[artifact])
        assert "wheel" in paths
        assert paths["wheel"].read_bytes() == content
        provenance = load_provenance(cache_dir)
        assert len(provenance["artifacts"]) == 1


def test_download_preserves_binary_content():
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "source.bin"
        content = bytes(range(256))
        src.write_bytes(content)
        dest = Path(td) / "dest.bin"
        _download(src.as_uri(), dest)
        assert dest.read_bytes() == content
