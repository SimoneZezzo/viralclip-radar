from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _bash():
    if os.name == "nt" and (git := shutil.which("git")):
        git_bash = Path(git).parent.parent / "bin" / "bash.exe"
        if git_bash.is_file():
            return str(git_bash)
    if bash := shutil.which("bash"):
        return bash
    pytest.skip("Bash is required to exercise the production preflight runbook")


@pytest.mark.parametrize(
    ("gta_v", "gta_vi", "v_status", "vi_status"),
    [
        (0, 0, "HEALTHY", "HEALTHY"),
        (1, 0, "DEGRADED", "HEALTHY"),
        (2, 0, "FAILED", "HEALTHY"),
        (0, 1, "HEALTHY", "DEGRADED"),
        (0, 2, "HEALTHY", "FAILED"),
        (2, 1, "FAILED", "DEGRADED"),
        (1, 2, "DEGRADED", "FAILED"),
        (2, 2, "FAILED", "FAILED"),
        (127, 0, "FAILED", "HEALTHY"),
    ],
)
def test_health_preflight_reports_both_results_under_errexit(gta_v, gta_vi, v_status, vi_status):
    script = Path(__file__).resolve().parents[1] / "deploy/dual-collector-health.sh"
    fixture = r"""
set -eu
sudo() {
    [[ $1 == -u && ${!#} == health ]] || return 125
    printf 'checked %s\n' "$2"
    case $2 in
        viralclip) return GTA_V_RC ;;
        viralclip-gta-vi) return GTA_VI_RC ;;
        *) return 125 ;;
    esac
}
""".replace("GTA_V_RC", str(gta_v)).replace("GTA_VI_RC", str(gta_vi))
    result = subprocess.run(
        [_bash(), "-s"],
        input=fixture + script.read_text(encoding="utf-8"),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.stdout.splitlines()[:2] == ["checked viralclip", "checked viralclip-gta-vi"]
    assert f"GTA V: {v_status} (exit {gta_v})" in result.stdout
    assert f"GTA VI: {vi_status} (exit {gta_vi})" in result.stdout
    assert result.returncode == int(bool(gta_v or gta_vi))
