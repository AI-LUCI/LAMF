#!/usr/bin/env python3
"""Static regression checks for the local web workspace accessibility contract."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "runtime" / "lamf" / "web"


def main() -> int:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")

    for required in (
        'class="skip-link" href="#main-content"',
        'id="main-content" tabindex="-1"',
        'id="search-title"',
        'aria-labelledby="search-title"',
        'aria-current="page"',
        'aria-pressed="true"',
        'aria-label="Filter memory library"',
        'id="search-results" class="search-results" aria-live="polite"',
        'id="auth-error" class="error" role="alert"',
        'aria-label="Close search"',
    ):
        assert required in html, required
    assert ":focus-visible" in css
    assert ".count[hidden]{display:none}" in css
    assert ".skip-link:focus" in css
    assert "prefers-reduced-motion:reduce" in css
    assert "setAttribute('aria-current','page')" in js
    assert "setAttribute('aria-pressed','true')" in js
    assert "setAttribute('aria-busy','false')" in js
    assert "document.getElementById(`${name}-title`)?.focus()" in js
    print("PASS web accessibility: focus, state, labels, and live-region contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
