"""Builds the submission zip. Fails on a .env file, a key pattern, or a size over 50 MB."""
from __future__ import annotations

import os
import re
import sys
import zipfile
from pathlib import Path

OUTPUT = Path("pg-interleave.zip")
MAX_BYTES = 50 * 1024 * 1024
SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".git", ".claude"}
KEY_PATTERNS = re.compile(
    rb"sk-[A-Za-z0-9_\-]{16,}|AIza[0-9A-Za-z_\-]{20,}|ghp_[A-Za-z0-9]{20,}"
    rb"|xox[baprs]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16}"
)


def walk():
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            yield Path(root) / name


def main():
    problems, files = [], []
    for path in walk():
        if path.name == OUTPUT.name or path.name == ".DS_Store":
            continue
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            problems.append(f"{path}: env file present, move it out of the repo")
            continue
        if KEY_PATTERNS.search(path.read_bytes()):
            problems.append(f"{path}: matches a key pattern")
        files.append(path)
    if problems:
        print("zip refused:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, Path("pg-interleave") / path)
    size = OUTPUT.stat().st_size
    if size >= MAX_BYTES:
        OUTPUT.unlink()
        print(f"zip refused: {size} bytes is over the 50 MB limit", file=sys.stderr)
        return 1
    print(f"{OUTPUT}: {len(files)} files, {size / 1024 / 1024:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
