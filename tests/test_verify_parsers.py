import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import verify_offline


def test_vitest_counts_only_the_tests_summary_line():
    output = (
        "log: 12 skipped by business rules\n Test Files  1 passed | 1 skipped (2)\n"
        "      Tests  7 passed | 2 skipped | 1 todo (10)\n"
    )
    assert verify_offline.vitest_not_run(output) == 3
    assert verify_offline.vitest_not_run("      Tests  7 passed (7)\n") == 0
    assert verify_offline.vitest_not_run("12 skipped by business rules\n") == 0


def test_playwright_counts_only_the_final_summary():
    output = "  ok 1 skipped by business rules\n  7 passed (3.5s)\n  2 skipped\n"
    assert verify_offline.playwright_not_run(output) == 2
    assert verify_offline.playwright_not_run("  7 passed (3.5s)\n") == 0
    assert verify_offline.playwright_not_run("log 12 skipped by business rules\n") == 0
