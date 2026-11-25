from __future__ import annotations

import hashlib
import importlib
import subprocess
import tarfile
from gzip import BadGzipFile
from pathlib import Path

import pytest


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "core.hooksPath=.git/no-hooks",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        text=True,
        stderr=subprocess.PIPE,
        timeout=15,
    ).strip()


def commit(repo: Path, *paths: str) -> str:
    git(repo, "-c", "core.autocrlf=false", "add", "--", *paths)
    git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.test",
        "commit",
        "-qm",
        "Fixture",
    )
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def source_repo(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    packager = importlib.import_module("package_release")
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--quiet", "--template=")
    for name in packager.REQUIRED:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"approved fixture\n")
    (repo / ".gitattributes").write_bytes(b"README.md export-ignore\n")
    revision = commit(repo, *packager.REQUIRED, ".gitattributes")
    return repo, revision, packager


def test_exact_commit_is_independent_of_git_and_checkout_configuration(source_repo, tmp_path):
    repo, revision, packager = source_repo
    (repo / "README.md").write_bytes(b"later commit\n")
    assert commit(repo, "README.md") != revision
    (repo / "README.md").write_bytes(b"working tree only\n")
    (repo / "deploy" / "backup.env").write_bytes(b"SYNTHETIC_ONLY=1\n")
    outputs = []
    for autocrlf, eol, umask in (("true", "crlf", "0077"), ("false", "lf", "0000")):
        git(repo, "config", "core.autocrlf", autocrlf)
        git(repo, "config", "core.eol", eol)
        git(repo, "config", "tar.umask", umask)
        output = tmp_path / f"{autocrlf}.tar.gz"
        digest, inventory = packager.package_release(repo, revision, output)
        payload = output.read_bytes()
        assert digest == hashlib.sha256(payload).hexdigest()
        assert inventory == sorted(packager.REQUIRED)
        with tarfile.open(output) as archive:
            assert archive.pax_headers["comment"] == revision
            assert archive.extractfile("README.md").read() == b"approved fixture\n"
            assert "deploy/backup.env" not in archive.getnames()
        outputs.append(payload)
    assert outputs[0] == outputs[1]


def test_packages_reliability_unit_templates(source_repo, tmp_path):
    repo, _, packager = source_repo
    units = {
        "deploy/viralclip-reliability@.service": b"[Service]\nType=oneshot\n",
        "deploy/viralclip-reliability@.timer": b"[Timer]\nOnCalendar=*:0/5\n",
        "deploy/viralclip-game@.service": b"[Service]\nType=exec\n",
    }
    for name, data in units.items():
        (repo / name).write_bytes(data)
    revision = commit(repo, *units)
    output = tmp_path / "reliability.tar.gz"

    _, inventory = packager.package_release(repo, revision, output)

    assert inventory == sorted((*packager.REQUIRED, *units))
    with tarfile.open(output) as archive:
        for name, data in units.items():
            assert archive.extractfile(name).read() == data


@pytest.mark.parametrize(
    ("name", "data", "error"),
    [
        ("deploy/backup.env", b"SYNTHETIC_ONLY=1\n", "Unexpected release path"),
        ("deploy/other@.service", b"[Service]\n", "Unexpected release path"),
        ("deploy/viralclip-reliability@.timer", b"[Timer]\r\n", "must use LF"),
        ("deploy/extra.service", b"[Service]\r\n", "must use LF"),
        ("deploy/extra.timer", b"[Timer]", "must use LF"),
    ],
)
def test_rejects_unsafe_committed_inputs(source_repo, tmp_path, name, data, error):
    repo, _, packager = source_repo
    (repo / name).write_bytes(data)
    revision = commit(repo, name)
    output = tmp_path / "blocked.tar.gz"
    with pytest.raises(ValueError, match=error):
        packager.package_release(repo, revision, output)
    assert not output.exists()


def test_rejects_symlink_blob_without_following_it(source_repo, tmp_path):
    repo, _, packager = source_repo
    blob = git(repo, "rev-parse", "HEAD:README.md")
    git(repo, "update-index", "--add", "--cacheinfo", f"120000,{blob},deploy/link.sh")
    revision = commit(repo, "README.md")
    with pytest.raises(ValueError, match="regular Git blob"):
        packager.package_release(repo, revision, tmp_path / "blocked.tar.gz")


def test_rejects_abbreviated_revision_and_preserves_existing_output(source_repo, tmp_path):
    repo, revision, packager = source_repo
    target = tmp_path / "existing.tar.gz"
    target.write_bytes(b"previous bytes")
    with pytest.raises(ValueError, match="full lowercase commit hash"):
        packager.package_release(repo, revision[:7], target)
    with pytest.raises(FileExistsError):
        packager.package_release(repo, revision, target)
    assert target.read_bytes() == b"previous bytes"


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ("content", "differs from Git blob"),
        ("missing", "inventory differs"),
        ("revision", "commit does not match"),
    ],
)
def test_rejects_archives_that_do_not_match_the_commit(source_repo, change, error):
    repo, revision, packager = source_repo
    sources = packager.read_sources(repo, revision)
    altered = dict(sources)
    if change == "content":
        altered["README.md"] = packager.SourceFile(sources["README.md"].mode, b"unexpected\n")
    if change == "missing":
        del altered["README.md"]
    packaged_revision = "0" * 40 if change == "revision" else revision
    payload = packager.build_archive(packaged_revision, altered)
    with pytest.raises(ValueError, match=error):
        packager.verify_archive(payload, revision, sources)


def test_rejects_corrupt_gzip_checksum(source_repo):
    repo, revision, packager = source_repo
    sources = packager.read_sources(repo, revision)
    payload = bytearray(packager.build_archive(revision, sources))
    payload[-8] ^= 1
    with pytest.raises(BadGzipFile):
        packager.verify_archive(payload, revision, sources)
