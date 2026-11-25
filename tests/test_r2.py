from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta

import pytest

from viralclip import r2
from viralclip.publish import GRACE_SECONDS

NOW = datetime(2026, 12, 20, 12, tzinfo=UTC)
OLD = NOW - timedelta(seconds=GRACE_SECONDS + 60)


class FakeR2:
    """In-memory S3 subset; records calls so the upload order can be checked."""

    class exceptions:  # mirrors boto3 client.exceptions
        class NoSuchKey(Exception):
            pass

    def __init__(self, objects=None):
        self.objects = dict(objects or {})  # key -> (body, last_modified)
        self.calls = []

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise self.exceptions.NoSuchKey
        return {"Body": io.BytesIO(self.objects[Key][0])}

    def put_object(self, *, Bucket, Key, Body, ContentType, CacheControl):
        self.calls.append(("put", Key, CacheControl))
        self.objects[Key] = (Body, NOW)

    def list_objects_v2(self, *, Bucket, Prefix, ContinuationToken=None):
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        start = int(ContinuationToken or 0)
        page = keys[start : start + 2]  # small pages exercise pagination
        more = start + 2 < len(keys)
        return {
            "Contents": [{"Key": k, "LastModified": self.objects[k][1]} for k in page],
            "IsTruncated": more,
            **({"NextContinuationToken": str(start + 2)} if more else {}),
        }

    def delete_object(self, *, Bucket, Key):
        self.calls.append(("delete", Key, None))
        del self.objects[Key]


def publication(tmp_path, files):
    source = tmp_path / "rankings"
    source.mkdir(parents=True)
    for name in files:
        (source / name).write_text("{}", encoding="utf-8")
    index = {"games": [{"id": n.split("-")[0], "file": n} for n in files]}
    (source / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return source


def test_upload_sends_games_then_index_and_prunes_against_the_live_index(tmp_path):
    new = ["42-00000000000000cc.json", "43-00000000000000dd.json"]
    live_index = json.dumps({"games": [{"id": "42", "file": "42-00000000000000bb.json"}]})
    client = FakeR2(
        {
            "rankings/index.json": (live_index.encode(), OLD),
            "rankings/42-00000000000000bb.json": (b"{}", OLD),  # live: kept although old
            "rankings/42-00000000000000aa.json": (b"{}", OLD),  # stale: pruned
            "rankings/42-0000000000000099.json": (b"{}", NOW),  # in grace: kept
            "rankings/32982.json": (b"{}", OLD),  # not a content-hashed name: kept
            "other/42-00000000000000aa.json": (b"{}", OLD),  # outside the prefix
        }
    )
    result = r2.upload(publication(tmp_path, new), "bucket", client, now=NOW)
    assert client.calls == [
        ("put", "rankings/" + new[0], r2.GAME_CACHE),
        ("put", "rankings/" + new[1], r2.GAME_CACHE),
        ("put", "rankings/index.json", r2.INDEX_CACHE),
        ("delete", "rankings/42-00000000000000aa.json", None),
    ]
    assert result["pruned"] == ["42-00000000000000aa.json"]
    assert result["kept_previous"] == ["42-00000000000000bb.json"]
    assert "other/42-00000000000000aa.json" in client.objects


def test_first_upload_and_a_failure_before_the_index(tmp_path):
    files = ["42-00000000000000cc.json"]
    client = FakeR2()
    r2.upload(publication(tmp_path / "a", files), "bucket", client, now=NOW)
    assert set(client.objects) == {"rankings/" + files[0], "rankings/index.json"}

    class Failing(FakeR2):
        def put_object(self, **kwargs):
            if kwargs["Key"].endswith("index.json"):
                raise OSError("network down")
            super().put_object(**kwargs)

    live = dict(client.objects)
    failing = Failing(live)
    with pytest.raises(OSError):
        r2.upload(publication(tmp_path / "b", ["42-00000000000000ee.json"]), "b", failing, now=NOW)
    assert failing.objects["rankings/index.json"] == live["rankings/index.json"]
    assert not any(call[0] == "delete" for call in failing.calls)


def test_incomplete_local_publication_sends_nothing(tmp_path):
    source = publication(tmp_path, ["42-00000000000000cc.json"])
    (source / "42-00000000000000cc.json").unlink()
    client = FakeR2()
    with pytest.raises(ValueError, match="missing"):
        r2.upload(source, "bucket", client, now=NOW)
    (source / "index.json").write_text('{"games": [{"id": "42"}]}', encoding="utf-8")
    with pytest.raises(ValueError, match="content-hashed"):
        r2.upload(source, "bucket", client, now=NOW)
    assert client.calls == []


def test_credentials_come_only_from_the_environment(monkeypatch, capsys):
    for name in r2.ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit) as exit_info:
        r2.main(["--source", "unused", "--bucket", "bucket"])
    assert exit_info.value.code == 1
    assert "R2_ACCOUNT_ID" in capsys.readouterr().err
