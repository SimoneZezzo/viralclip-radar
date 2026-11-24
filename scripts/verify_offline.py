"""Run the repository checks with synthetic fixtures and print one status per check."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from package_release import git, package_release

ROOT = Path(__file__).resolve().parents[1]
PASS, FAIL, SKIP, UNKNOWN = "PASS", "FAIL", "SKIP", "UNKNOWN"
POWERSHELL_PARSER = r"""
param([string]$Manifest)
$ErrorActionPreference = 'Stop'
$count = 0
$failed = $false
foreach ($source in (Get-Content -Raw -Encoding utf8 -LiteralPath $Manifest | ConvertFrom-Json)) {
    $text = [IO.File]::ReadAllText($source)
    $snippets = if ($source.EndsWith('.ps1')) { ,$text } else {
        foreach ($block in [regex]::Matches($text, '(?ms)^ *`{3}(?:powershell|pwsh|ps1)[ 	]*\r?\n(.*?)^ *`{3}')) {
            $block.Groups[1].Value
        }
    }
    foreach ($snippet in $snippets) {
        $count++
        $tokens = $null
        $errors = $null
        $null = [Management.Automation.Language.Parser]::ParseInput($snippet, [ref]$tokens, [ref]$errors)
        foreach ($errorInfo in $errors) {
            $failed = $true
            [Console]::Error.WriteLine("$source snippet line $($errorInfo.Extent.StartLineNumber): $($errorInfo.ErrorId)")
        }
    }
}
Write-Output "$count scripts or fenced blocks parsed"
if ($failed) { exit 1 }
exit 0
"""


def offline_env(scratch: Path) -> dict[str, str]:
    os_keys = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "SYSTEMDRIVE",
        "COMSPEC",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "LANG",
        "LC_ALL",
    }
    return {
        **{key: os.environ[key] for key in os.environ if key.upper() in os_keys},
        "TMP": str(scratch),
        "TEMP": str(scratch),
        "TMPDIR": str(scratch),
        "PYTHON_DOTENV_DISABLED": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "VIRALCLIP_DB_PATH": str(scratch / "synthetic.sqlite3"),
        "GIT_TERMINAL_PROMPT": "0",
    }


def run(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )


def details(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join((result.stdout + result.stderr).strip().splitlines()[-30:])


def command_check(command: list[str], env: dict[str, str] | None, success: str) -> tuple[str, str]:
    result = run(command, env)
    if result.returncode:
        return FAIL, f"exit {result.returncode}\n{details(result)}"
    return PASS, success or details(result)


def pytest_check(scratch: Path, env: dict[str, str]) -> tuple[str, str]:
    if importlib.util.find_spec("pytest") is None:
        return UNKNOWN, "pytest unavailable. Run uv sync --locked."
    xml = scratch / "pytest.xml"
    result = run(
        [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "pytest",
            "-q",
            "-ra",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(scratch / "pytest"),
            "--junitxml",
            str(xml),
        ],
        env,
    )
    if not xml.is_file():
        return UNKNOWN, f"No pytest report (exit {result.returncode})\n{details(result)}"
    cases = list(ET.parse(xml).iter("testcase"))
    failed = sum(
        case.find("failure") is not None or case.find("error") is not None for case in cases
    )
    skipped = sum(case.find("skipped") is not None for case in cases)
    counts = f"{len(cases) - failed - skipped} passed, {failed} failed/errors, {skipped} skipped"
    if result.returncode or failed or not cases:
        return FAIL, f"{counts} (exit {result.returncode})\n{details(result)}"
    if skipped:
        return SKIP, f"{counts}\n{details(result)}"
    return PASS, counts


def ruff_check(arguments: list[str], env: dict[str, str]) -> tuple[str, str]:
    if importlib.util.find_spec("ruff") is None:
        return UNKNOWN, "Ruff unavailable. Run uv sync --locked."
    return command_check(
        [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "ruff",
            *arguments,
            "--no-cache",
            "src",
            "tests",
            "scripts",
        ],
        env,
        "",
    )


def git_check() -> tuple[str, str]:
    for command, arguments in (
        ("diff", []),
        ("diff", ["--cached"]),
        ("show", ["--format=", "--diff-merges=first-parent", "HEAD"]),
    ):
        status, message = command_check(
            [
                "git",
                "--no-optional-locks",
                command,
                "--check",
                "--no-ext-diff",
                "--no-textconv",
                *arguments,
            ],
            None,
            "",
        )
        if status != PASS:
            return status, message
    ignored = git(ROOT, "ls-files", "-ci", "--exclude-standard", "-z")
    if ignored:
        return FAIL, f"{ignored.count(bytes(1))} tracked paths match ignore rules"
    return (
        PASS,
        "Whitespace checked in unstaged, staged and HEAD changes. No tracked ignored paths.",
    )


def source_paths(*patterns: str) -> list[str]:
    paths = git(
        ROOT, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *patterns
    )
    # A tracked file deleted from the working tree, but not yet staged, has nothing to parse.
    files = sorted(
        path
        for path in {os.fsdecode(path) for path in paths.split(b"\0") if path}
        if (ROOT / path).is_symlink() or (ROOT / path).exists()
    )
    for path in files:
        if (ROOT / path).is_symlink():
            raise ValueError(f"Syntax input is a symlink: {path}")
    return files


def bash_check(env: dict[str, str]) -> tuple[str, str]:
    bash = shutil.which("bash")
    if os.name == "nt" and (git_exe := shutil.which("git")):
        bundled = Path(git_exe).parent.parent / "bin" / "bash.exe"
        if bundled.is_file():
            bash = str(bundled)
    if bash is None:
        return SKIP, "Bash unavailable"
    paths = source_paths("*.sh")
    if not paths:
        return SKIP, "No Bash files found"
    status, message = command_check([bash, "--noprofile", "--norc", "-n", "-c", "exit 0"], env, "")
    if status != PASS:
        return UNKNOWN, f"Bash could not start\n{message}"
    for path in paths:
        status, message = command_check([bash, "--noprofile", "--norc", "-n", "--", path], env, "")
        if status != PASS:
            return status, f"{path}\n{message}"
    return PASS, f"{len(paths)} shell files parsed"


def powershell_check(scratch: Path, env: dict[str, str]) -> tuple[str, str]:
    shell = shutil.which("pwsh") or shutil.which("powershell.exe")
    if shell is None:
        return SKIP, "PowerShell unavailable"
    manifest = scratch / "powershell-inputs.json"
    manifest.write_text(
        json.dumps([str(ROOT / path) for path in source_paths("*.md", "*.ps1")]), encoding="utf-8"
    )
    parser = scratch / "parse.ps1"
    parser.write_text(POWERSHELL_PARSER, encoding="utf-8")
    return command_check(
        [shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(parser), str(manifest)],
        env,
        "",
    )


def web_directory() -> Path:
    # Vitest loads modules twice when the drive letter is lower case, so normalize it.
    path = str(ROOT / "web")
    return Path(path[0].upper() + path[1:]) if os.name == "nt" else Path(path)


def npm_run(arguments: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [shutil.which("npm") or "npm", *arguments],
        cwd=web_directory(),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )


def web_ready() -> tuple[str, str] | None:
    if shutil.which("npm") is None:
        return SKIP, "Node.js and npm unavailable"
    if not (web_directory() / "node_modules").is_dir():
        return (
            UNKNOWN,
            "web/node_modules missing. Run npm --prefix web ci once with network access.",
        )
    return None


def not_run(output: str) -> int:
    """Count tests a Vitest or Playwright summary reports as skipped or todo."""
    plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
    return sum(int(count) for count in re.findall(r"(\d+) (?:skipped|todo)\b", plain))


def web_check(env: dict[str, str]) -> tuple[str, str]:
    if (blocked := web_ready()) is not None:
        return blocked
    tests = ""
    for name, arguments in (
        ("ESLint", ["run", "lint"]),
        ("TypeScript", ["run", "typecheck"]),
        ("Vitest", ["test"]),
        ("Vite build", ["run", "build"]),
    ):
        result = npm_run(arguments, env)
        if result.returncode:
            return FAIL, f"{name}: exit {result.returncode}\n{details(result)}"
        if name == "Vitest":
            # Strict mode treats skipped tests as SKIP, as the pytest check does.
            if skipped := not_run(result.stdout):
                return SKIP, f"Vitest skipped or left {skipped} tests as todo"
            plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
            match = re.search(r"Tests\s+(\d+) passed", plain)
            tests = f", {match.group(1)} unit tests" if match else ""
    return PASS, f"ESLint, TypeScript, Vite build{tests}"


def web_e2e_check(env: dict[str, str]) -> tuple[str, str]:
    if (blocked := web_ready()) is not None:
        return blocked
    if not (web_directory() / "dist" / "index.html").is_file():
        return UNKNOWN, "web/dist missing. The Web check builds it first."
    result = npm_run(["run", "test:e2e"], env)
    output = result.stdout + result.stderr
    if result.returncode and "is not found" in output and "chrome" in output.lower():
        return SKIP, "Google Chrome unavailable for Playwright"
    if result.returncode:
        return FAIL, f"exit {result.returncode}\n{details(result)}"
    if skipped := not_run(output):
        return SKIP, f"Playwright skipped {skipped} tests"
    match = re.search(r"(\d+) passed", output)
    return PASS, f"{match.group(1) if match else 'All'} Playwright tests against the built demo"


def packaging_check(scratch: Path) -> tuple[str, str]:
    revision = git(ROOT, "rev-parse", "HEAD").decode().strip()
    try:
        digest, paths = package_release(ROOT, revision, scratch / "release.tar.gz")
    except (OSError, ValueError) as exc:
        return FAIL, str(exc)
    return PASS, f"HEAD {revision[:12]}, {len(paths)} files, SHA-256 {digest}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Fail if a check or test is skipped")
    args = parser.parse_args()
    results = []
    with tempfile.TemporaryDirectory(prefix="viralclip-verify-") as temp:
        scratch = Path(temp)
        env = offline_env(scratch)
        checks = {
            "pytest": lambda: pytest_check(scratch, env),
            "Ruff lint": lambda: ruff_check(["check"], env),
            "Ruff format": lambda: ruff_check(["format", "--check"], env),
            "Git": git_check,
            "Bash": lambda: bash_check(env),
            "PowerShell": lambda: powershell_check(scratch, env),
            "Web": lambda: web_check(env),
            "Web e2e": lambda: web_e2e_check(env),
            "Packaging": lambda: packaging_check(scratch),
        }
        for name, check in checks.items():
            try:
                status, message = check()
            except (OSError, subprocess.SubprocessError, ET.ParseError, ValueError) as exc:
                status, message = UNKNOWN, str(exc)
            print(f"{status:7} {name} | {message}", flush=True)
            results.append(status)
    print(
        "Summary | "
        + ", ".join(f"{status}={results.count(status)}" for status in (PASS, FAIL, SKIP, UNKNOWN))
    )
    if FAIL in results:
        return 1
    return 2 if UNKNOWN in results or (args.strict and SKIP in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
