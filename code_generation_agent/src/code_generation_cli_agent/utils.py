from __future__ import annotations

import re
from pathlib import Path


def ensure_repo_path(repo: str) -> Path:
    p = Path(repo).resolve()

    # Create the repo directory if it does not exist.
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)

    if not p.is_dir():
        raise SystemExit(f"Invalid repo path (not a directory): {repo}")

    return p


def strip_code_fences(text: str) -> str:
    if not text:
        return ""

    s = text.strip()
    s = re.sub(r"^\s*Here is the code:\s*", "", s, flags=re.IGNORECASE)
    lines = s.splitlines()

    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].lstrip().startswith("```"):
        lines = lines[:-1]

    return "\n".join(lines).strip()