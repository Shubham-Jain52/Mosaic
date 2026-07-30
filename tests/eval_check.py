#!/usr/bin/env python3
"""
Small eval harness for mosaic check (no network required for trivial paths).

Usage:
  python tests/eval_check.py

For a full LLM eyeball on a real corpus:
  mosaic check
  # or: git diff main | mosaic check --stdin
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.diff_parser import is_trivial_diff, parse_unified_diff
from pipeline.check_runner import run_check


EMPTY = ""
WHITESPACE = """\
diff --git a/x.txt b/x.txt
--- a/x.txt
+++ b/x.txt
@@ -1 +1 @@
-
+  
"""

REALISH = """\
diff --git a/core/config.py b/core/config.py
index aaa..bbb 100644
--- a/core/config.py
+++ b/core/config.py
@@ -10,6 +10,9 @@ def load_config() -> None:
     load_dotenv(ENV_PATH)
+
+def unused_helper():
+    return 42
"""


def main() -> int:
    failures = 0

    cases = [
        ("empty", EMPTY, True),
        ("whitespace", WHITESPACE, True),
        ("realish", REALISH, False),
    ]
    for name, diff, expect_trivial in cases:
        got = is_trivial_diff(diff)
        ok = got == expect_trivial
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] trivial/{name}: expected={expect_trivial} got={got}")
        if not ok:
            failures += 1

    hunks = parse_unified_diff(REALISH)
    ok = len(hunks) == 1 and hunks[0].file_path == "core/config.py"
    print(f"[{'PASS' if ok else 'FAIL'}] parse realish hunk")
    if not ok:
        failures += 1

    # Trivial path must not need embedder/chat
    result = run_check(EMPTY)
    ok = result.trivial and result.llm_call_count == 0
    print(f"[{'PASS' if ok else 'FAIL'}] run_check empty → trivial, 0 LLM calls")
    if not ok:
        failures += 1

    print()
    if failures:
        print(f"{failures} failure(s)")
        return 1
    print("All cheap eval checks passed.")
    print("Manual: run `mosaic check` in a repo with mosaic.db + .mosaic/ + CHAT_API_KEY.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
