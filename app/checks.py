"""Deterministic acceptance checks.

OBJECTIVE checklist items are evaluated by code wherever a check can be
expressed as code: word count, file type/extension, required keywords or
sections, and running provided test cases in a time-limited subprocess.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .schemas import ChecklistItem, Check

CODE_TEST_TIMEOUT_SECONDS = 10
MAX_OUTPUT_CHARS = 4000

WHOLE_FILE_RE = re.compile(r"^\s*#\s*(.+?)\s*$|^\s*(.+?)\s*$", re.M)


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _human(n: int) -> str:
    return f"{n:,}"


def check_word_count(c: Check, content: str) -> tuple[bool, str]:
    n = word_count(content)
    if c.min is not None and n < c.min:
        return False, f"Word count {_human(n)} is below the required minimum of {_human(c.min)}."
    if c.max is not None and n > c.max:
        return False, f"Word count {_human(n)} exceeds the maximum of {_human(c.max)}."
    bounds = []
    if c.min is not None:
        bounds.append(f"min {c.min}")
    if c.max is not None:
        bounds.append(f"max {c.max}")
    return True, f"Word count {_human(n)} meets the requirement ({', '.join(bounds) or 'ok'})."


def check_file_type(c: Check, filename: str | None, content: str) -> tuple[bool, str]:
    exts = [e.lower() if e.startswith(".") else f".{e.lower()}"
            for e in (c.extensions or [])]
    name = filename or ""
    if not name:
        return False, "No filename was provided, so the file type cannot be verified."
    suffix = Path(name).suffix.lower()
    if not suffix:
        return False, f"File '{name}' has no extension, so the file type cannot be verified."
    if suffix in exts:
        return True, f"File type '{suffix}' is allowed ({', '.join(exts)})."
    return False, f"File type '{suffix}' is not allowed; expected one of {', '.join(exts)}."


def check_keywords(c: Check, content: str) -> tuple[bool, str]:
    values = c.values or []
    haystack = content.lower()
    missing = [v for v in values if v.lower() not in haystack]
    mode = c.mode or "all"
    if mode == "all":
        if not missing:
            return True, f"All {len(values)} required keyword(s) present."
        return False, "Missing required keyword(s): " + ", ".join(f"'{m}'" for m in missing) + "."
    # mode == "any"
    if missing and len(missing) == len(values):
        return False, "None of the accepted keyword(s) were found: " + \
            ", ".join(f"'{v}'" for v in values) + "."
    return True, "At least one accepted keyword present."


def _section_headings(content: str) -> set[str]:
    heads: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            heads.add(re.sub(r"^#+\s*", "", stripped).strip().lower())
        elif len(stripped) < 80 and not stripped.endswith((".", ":", ";")):
            # short standalone line (e.g. "Key takeaways") counts as a heading
            heads.add(stripped.lower())
    return heads


def check_sections(c: Check, content: str) -> tuple[bool, str]:
    values = c.values or []
    heads = _section_headings(content)
    lower_text = content.lower()
    missing = [v for v in values
               if v.strip().lower() not in heads and v.strip().lower() not in lower_text]
    if not missing:
        return True, f"All {len(values)} required section(s) present."
    return False, "Missing required section(s): " + \
        ", ".join(f"'{m}'" for m in missing) + "."


def run_code_tests(c: Check, code: str) -> tuple[bool, str]:
    """Run the provided test script against the submitted code in a
    time-limited subprocess (temp dir, no network assumptions)."""
    test_code = c.test_code or ""
    if not test_code.strip():
        return False, "No test cases were configured for this item."
    with tempfile.TemporaryDirectory(prefix="trustbridge_") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "solution.py").write_text(code, encoding="utf-8")
        (tmp_path / "run_tests.py").write_text(test_code, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "run_tests.py"],
                cwd=tmp_path, capture_output=True, text=True,
                timeout=CODE_TEST_TIMEOUT_SECONDS,
                env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(tmp_path)},
            )
        except subprocess.TimeoutExpired:
            return False, (f"Test run exceeded the {CODE_TEST_TIMEOUT_SECONDS}s "
                           "time limit and was stopped.")
    output = ((proc.stdout or "") + (proc.stderr or ""))[-MAX_OUTPUT_CHARS:]
    if proc.returncode == 0:
        first = next((ln for ln in (proc.stdout or "").splitlines() if ln.strip()), "all tests passed")
        return True, f"Test cases passed ({first.strip()[:160]})."
    tail = " ".join((output.strip().splitlines() or ["tests failed"])[-3:])
    return False, f"Test cases failed (exit {proc.returncode}): {tail[:300]}"


def run_deterministic(item: ChecklistItem, content: str,
                      filename: str | None) -> tuple[bool, str] | None:
    """Return (passed, reason) if this item has a codeable check, else None."""
    c = item.check
    if c is None:
        return None
    try:
        if c.type == "word_count":
            return check_word_count(c, content)
        if c.type == "file_type":
            return check_file_type(c, filename, content)
        if c.type == "keywords":
            return check_keywords(c, content)
        if c.type == "sections":
            return check_sections(c, content)
        if c.type == "code_tests":
            return run_code_tests(c, content)
    except Exception as exc:  # a crashing check must not crash the report
        return False, f"Check errored: {type(exc).__name__}: {exc}"
    return None
