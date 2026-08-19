"""Static guards keeping provider secrets out of the repo and out of HTTP responses.

These are deliberately dumb string checks over the source tree rather than behavioural
tests. They catch the class of regression that is cheap to introduce and expensive to
notice: someone builds a URL by hand, adds a debug print, or hands a raw provider
exception back to a client. HANDOFF.md records that an API-key-in-logs bug already
happened once in this project.

Scope note: only backend/app/ is scanned. backend/scripts/ legitimately prints (it is a
CLI migration tool) and backend/tests/ legitimately contains sentinel key literals.
"""
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = REPO_ROOT / "backend" / "app"
APP_PY_FILES = sorted(APP_DIR.rglob("*.py"))

_INTERPOLATED_KEY_RE = re.compile(r"""(?:apikey|api_key)\s*=\s*["']?\{|f["'][^"']*apikey=\{""")
_PRINT_RE = re.compile(r"^\s*print\(", re.MULTILINE)
_PLACEHOLDER_RE = re.compile(r"^your_[a-z_]*key_here$")


def test_app_sources_exist_to_scan():
    """Guard against the guards silently passing because the glob found nothing."""
    assert len(APP_PY_FILES) >= 5, APP_PY_FILES


def test_no_api_key_is_interpolated_into_a_string():
    offenders = [p.name for p in APP_PY_FILES if _INTERPOLATED_KEY_RE.search(p.read_text())]
    assert offenders == [], f"build requests with params={{...}}, not string interpolation: {offenders}"


def test_no_print_calls_in_backend_app():
    offenders = [p.name for p in APP_PY_FILES if _PRINT_RE.search(p.read_text())]
    assert offenders == [], f"use no output at all rather than print(): {offenders}"


def test_main_never_returns_a_raw_exception_string():
    text = (APP_DIR / "main.py").read_text()
    assert "detail=str(e)" not in text, (
        "httpx embeds the full request URL in its error messages, and OMDb's key is a "
        "query parameter -- passing the raw exception through unredacted would leak "
        "OMDB_API_KEY into the response body"
    )
    assert text.count("detail=redact_secrets(str(e))") >= 2


def test_env_example_documents_both_keys_as_placeholders_only():
    lines = (REPO_ROOT / "backend" / ".env.example").read_text().splitlines()
    pairs = dict(
        line.split("=", 1) for line in lines
        if "=" in line and not line.strip().startswith("#")
    )
    assert "TMDB_API_KEY" in pairs and "OMDB_API_KEY" in pairs, pairs
    for name, value in pairs.items():
        assert _PLACEHOLDER_RE.match(value.strip()), f"{name} looks like a real value"


def test_gitignore_excludes_secrets_and_the_derived_cache():
    text = (REPO_ROOT / ".gitignore").read_text()
    assert "backend/.env" in text
    assert "backend/data/api_cache.json" in text


def test_no_env_file_is_tracked_by_git():
    result = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT,
                            capture_output=True, text=True, check=False)
    tracked = set(result.stdout.split())
    assert "backend/.env" not in tracked
    assert ".env" not in tracked
