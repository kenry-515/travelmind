#!/usr/bin/env python3
"""
Fix hard-coded light-color Tailwind classes in frontend src for dark mode.

Scans .tsx / .ts files under frontend/src, detects className strings that
contain classes like bg-white / text-slate-900 / border-slate-300 without
a matching dark: variant, and inserts the dark: counterpart right after
the light-class token so that both themes render properly.

Safe, regex-based; rewrites files in place with minimal diffs.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"

# Mapping: light class prefix -> dark class prefix (matched by starts-with).
# Handles variants like bg-white/90, text-slate-800, hover:text-slate-600 etc.
# The dark class is inserted immediately after the light-class token.
_PREFIX_MAPPING: Dict[str, str] = {
    "bg-white": "dark:bg-slate-900",
    "bg-slate-50": "dark:bg-slate-800",
    "bg-slate-100": "dark:bg-slate-800",
    "text-slate-900": "dark:text-slate-100",
    "text-slate-800": "dark:text-slate-200",
    "text-slate-700": "dark:text-slate-300",
    "text-slate-600": "dark:text-slate-400",
    "text-slate-500": "dark:text-slate-400",
    "text-slate-400": "dark:text-slate-500",
    "border-slate-300": "dark:border-slate-700",
    "border-slate-200": "dark:border-slate-700",
    "border-slate-100": "dark:border-slate-800",
}

# Suffix variants (after a prefix like hover:, focus:, placeholder:)
_SUFFIX_MAPPING: Dict[str, str] = {
    "hover:bg-slate-50": "dark:hover:bg-slate-800",
    "hover:text-slate-800": "dark:hover:text-slate-100",
    "hover:text-slate-600": "dark:hover:text-slate-300",
    "placeholder:text-slate-400": "dark:placeholder:text-slate-500",
    "focus:bg-white": "dark:focus:bg-slate-900",
    "focus:text-slate-800": "dark:focus:text-slate-100",
    "focus:text-slate-600": "dark:focus:text-slate-300",
    "focus:text-slate-900": "dark:focus:text-slate-100",
    "focus:text-slate-700": "dark:focus:text-slate-200",
}


def _match_any_prefix(token: str) -> Optional[str]:
    """Return the mapped dark class if token starts with a known light prefix."""
    # Try exact suffix variants first (hover:, focus:, placeholder: ...)
    for light, dark in _SUFFIX_MAPPING.items():
        if token == light or token.startswith(light + "/"):
            return dark
    # Then base prefixes (possibly with opacity like /70)
    for light, dark in _PREFIX_MAPPING.items():
        if token == light or token.startswith(light + "/"):
            return dark
    return None


# Regex captures a Tailwind class token.  Matches e.g.
#   bg-white  bg-white/70  text-slate-900  hover:bg-slate-50
_TAILWIND_TOKEN_RE = re.compile(
    r"\b"                          # word boundary
    r"(?:[\w-]+:)?"                # optional prefix like hover: focus: placeholder:
    r"(?:bg|text|border)"          # category
    r"[\w-]+"                      # color / shade
    r"(?:/\d+)?"                   # optional opacity like /70
    r"(?!-)"                       # not followed by another token connector
)


def fix_file(path: Path) -> Tuple[int, List[str]]:
    raw = path.read_text(encoding="utf-8")
    changed = 0
    diffs: List[str] = []

    def _replace(match: re.Match) -> str:
        nonlocal changed
        token = match.group(0)
        dark_variant = _match_any_prefix(token)
        if not dark_variant:
            return token
        # Avoid duplicate insertion: if the very next chars already contain
        # the dark variant or any dark: class, skip.
        tail = raw[match.end():match.end() + 50]
        if re.search(r"\bdark:", tail):
            return token
        changed += 1
        diffs.append(f"  +{dark_variant}  after '{token}'")
        return f"{token} {dark_variant}"

    new = _TAILWIND_TOKEN_RE.sub(_replace, raw)
    if new != raw:
        path.write_text(new, encoding="utf-8")
    return changed, diffs


def main() -> int:
    files: List[Path] = []
    for ext in ("*.tsx", "*.ts", "*.css"):
        files.extend(FRONTEND.rglob(ext))

    total_files = 0
    total_changes = 0
    for f in files:
        changes, diffs = fix_file(f)
        if changes:
            total_files += 1
            total_changes += changes
            print(f"\n[{f}] {changes} insertion(s)")
            for d in diffs[:5]:
                print(d)
            if len(diffs) > 5:
                print(f"  ... +{len(diffs) - 5} more")

    print(f"\n=== Summary ===")
    print(f"Touched files  : {total_files}")
    print(f"Insertions     : {total_changes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
