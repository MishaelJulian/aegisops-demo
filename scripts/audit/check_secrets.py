"""Scans repository files for accidental real secrets, .env files, and local SQLite DBs.

Allows explicitly marked synthetic dev templates (.env.example, simulator/fixtures/).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_FILENAMES = {
    ".env",
    ".env.local",
}

FORBIDDEN_EXTENSIONS = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}

IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
}

SKIP_CONTENT_PATHS = {
    ".env.example",
    "simulator/fixtures/sample_raw_events.json",
    "scripts/audit/check_secrets.py",
    "scripts/audit/verify_contracts.py",
}

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Private Key Block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub Personal Access Token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{24,}\b")),
    ("OpenAI / Anthropic Style API Key", re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b")),
    ("Generic Bearer Real Token", re.compile(r"Authorization:\s*Bearer\s+(?!<|dev-|example)[A-Za-z0-9._-]{24,}")),
]


def scan_repository() -> tuple[bool, list[str]]:
    import subprocess

    findings: list[str] = []

    # Check tracked + staged + non-ignored untracked files via git when inside a repo
    # so gitignored local runtime SQLite databases in collector/data/ or backend/data/
    # do not block pushes while running dev servers, yet any tracked/staged .db or .env ALWAYS fails.
    candidate_paths: list[Path] = []
    proc = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            rel_str = line.strip()
            if rel_str:
                p = REPO_ROOT / rel_str
                if p.is_file():
                    candidate_paths.append(p)
    else:
        for p in REPO_ROOT.rglob("*"):
            if not any(part in IGNORED_DIRS for part in p.parts) and p.is_file():
                candidate_paths.append(p)

    for path in candidate_paths:
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue

        rel = path.relative_to(REPO_ROOT).as_posix()

        if path.name in FORBIDDEN_FILENAMES:
            findings.append(f"Forbidden environment file present: {rel}")
            continue
        if path.suffix.lower() in FORBIDDEN_EXTENSIONS:
            findings.append(f"Forbidden secret/database artifact present: {rel}")
            continue
        if rel in SKIP_CONTENT_PATHS or path.suffix.lower() in {".pdf", ".png", ".jpg", ".ico", ".woff2"}:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"Potential secret ({label}) detected in {rel}")

    return len(findings) == 0, findings


def main() -> int:
    ok, findings = scan_repository()
    if ok:
        print("[PASS] Secret scan passed: zero leaked secrets, .env files, or local DB artifacts.")
        return 0
    print("[FAIL] Secret scan detected issues:")
    for item in findings:
        print(f"  - {item}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
