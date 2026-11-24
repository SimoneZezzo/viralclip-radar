"""Build and verify a source-only archive from the raw blobs of a Git commit."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import re
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ROOT_FILES = (".python-version", "README.md", "pyproject.toml", "uv.lock")
PACKAGER = "scripts/package_release.py"
REQUIRED = (
    *ROOT_FILES,
    "src/viralclip/gta_vi.py",
    "src/viralclip/operations.py",
    "deploy/dual-collector-health.sh",
)
SOURCES = re.compile(
    r"(?:src/viralclip|tests)/[a-z0-9_/]+\.py|"
    r"deploy/[a-z0-9-]+\.(?:service|timer|sh|env\.example)|"
    r"deploy/viralclip-reliability@\.(?:service|timer)"
)


@dataclass(frozen=True)
class SourceFile:
    mode: int
    data: bytes


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(
        ["git", "--no-replace-objects", "--no-optional-locks", "-C", str(root), *args],
        stderr=subprocess.PIPE,
        timeout=30,
    )


def read_sources(root: Path, revision: str) -> dict[str, SourceFile]:
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Enter a full lowercase commit hash")
    if git(root, "rev-parse", "--verify", f"{revision}^{{commit}}").decode().strip() != revision:
        raise ValueError("The selected object must be a commit")

    entries = git(
        root,
        "ls-tree",
        "-rz",
        "--full-tree",
        revision,
        "--",
        *ROOT_FILES,
        "src",
        "tests",
        "deploy",
        PACKAGER,
    ).split(b"\0")
    sources = {}
    for entry in filter(None, entries):
        metadata, name = entry.split(b"\t", 1)
        path = name.decode("utf-8")
        mode, kind, blob = metadata.decode("ascii").split()
        if path not in (*ROOT_FILES, PACKAGER) and not SOURCES.fullmatch(path):
            raise ValueError(f"Unexpected release path: {path}")
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"Release input must be a regular Git blob: {path}")
        data = git(root, "cat-file", "blob", blob)
        if path.startswith("deploy/") and (b"\r" in data or not data.endswith(b"\n")):
            raise ValueError(f"Linux release input must use LF: {path}")
        sources[path] = SourceFile(int(mode, 8) & 0o777, data)
    missing = set(REQUIRED).difference(sources)
    if missing:
        raise ValueError(f"Missing required release paths: {', '.join(sorted(missing))}")
    return sources


def directories(sources: dict[str, SourceFile]) -> set[str]:
    return {
        parent.as_posix()
        for path in sources
        for parent in PurePosixPath(path).parents
        if parent != PurePosixPath(".")
    }


def verify_archive(payload: bytes, revision: str, sources: dict[str, SourceFile]) -> None:
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(payload)), mode="r:") as archive:
        if archive.pax_headers.get("comment") != revision:
            raise ValueError("Archive commit does not match the selected revision")
        members = archive.getmembers()
        expected = sources.keys() | directories(sources)
        if len(members) != len(expected) or {member.name for member in members} != expected:
            raise ValueError("Archive inventory differs from the reviewed Git tree")
        for member in members:
            source = sources.get(member.name)
            if source is None:
                if not member.isdir():
                    raise ValueError(f"Invalid archive directory: {member.name}")
                continue
            if member.type != tarfile.REGTYPE or member.mode != source.mode:
                raise ValueError(f"Invalid archive file type or mode: {member.name}")
            stream = archive.extractfile(member)
            if stream is None or stream.read() != source.data:
                raise ValueError(f"Archive content differs from Git blob: {member.name}")


def build_archive(revision: str, sources: dict[str, SourceFile]) -> bytes:
    buffer = io.BytesIO()
    with (
        gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", pax_headers={"comment": revision}) as tar,
    ):
        for path in sorted(directories(sources)):
            member = tarfile.TarInfo(path)
            member.type = tarfile.DIRTYPE
            member.mode = 0o755
            tar.addfile(member)
        for path, source in sorted(sources.items()):
            member = tarfile.TarInfo(path)
            member.mode = source.mode
            member.size = len(source.data)
            tar.addfile(member, io.BytesIO(source.data))
    return buffer.getvalue()


def package_release(root: Path, revision: str, output: Path) -> tuple[str, list[str]]:
    if not output.name.endswith(".tar.gz"):
        raise ValueError("Release output must end in .tar.gz")
    sources = read_sources(root, revision)
    payload = build_archive(revision, sources)
    verify_archive(payload, revision, sources)
    with output.open("xb") as stream:
        stream.write(payload)
    return hashlib.sha256(payload).hexdigest(), sorted(sources)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", help="Full reviewed commit SHA")
    parser.add_argument("--output", type=Path, required=True, help="New .tar.gz file")
    args = parser.parse_args()
    try:
        digest, files = package_release(Path.cwd(), args.revision, args.output)
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        parser.exit(1, f"Packaging failed: {exc}\n")
    print(f"Commit {args.revision}")
    print("\n".join(files))
    print(f"SHA-256 {digest}  {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
