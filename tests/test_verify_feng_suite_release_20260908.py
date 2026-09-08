"""Small adversarial release fixtures test integrity and safe extraction."""
import hashlib
import json
import stat
import zipfile

import pytest

from scripts.eval import verify_feng_suite_release_20260908 as verifier


def sha(data):
    return hashlib.sha256(data).hexdigest()


def release(tmp_path, records=None, members=None):
    root = tmp_path / "release"
    root.mkdir()
    part = root / "feng-suite-20260908-part-001.zip"
    contents = {"reports/result.json": b'{"complete": true}\n', "native/log.txt": b"done\n"}
    if records is None:
        records = [{"path": name, "bytes": len(data), "sha256": sha(data), "part": part.name}
                   for name, data in contents.items()]
    with zipfile.ZipFile(part, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in (members if members is not None else contents.items()):
            archive.writestr(name, data)
    index = root / "files.jsonl"
    index.write_bytes(b"".join((json.dumps(r) + "\n").encode() for r in records))
    manifest = {"schema": verifier.SCHEMA, "original_workspace_root": str(tmp_path / "original"),
                "files_manifest": {"name": index.name, "sha256": sha(index.read_bytes()), "count": len(records)},
                "parts": [{"name": part.name, "sha256": sha(part.read_bytes()),
                           "bytes": part.stat().st_size, "file_count": len(records)}]}
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, part, contents


def test_read_only_success_and_extract_exact_bytes(tmp_path):
    manifest, part, contents = release(tmp_path)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = verifier.verify_release(manifest, part.parent)
    assert result["status"] == "PASS" and result["file_count"] == 2
    assert result["extracted_to"] is None
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before
    target = tmp_path / "restored"
    verifier.verify_release(manifest, part.parent, target)
    assert {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()} == contents


@pytest.mark.parametrize("kind", ["index", "archive", "member", "missing", "extra", "duplicate"])
def test_corruption_or_membership_mismatch_never_extracts(tmp_path, kind):
    members = None
    if kind == "member":
        members = [("reports/result.json", b'{"complete": true}\n'), ("native/log.txt", b"evil\n")]
    elif kind == "missing":
        members = [("reports/result.json", b'{"complete": true}\n')]
    elif kind == "extra":
        members = [("reports/result.json", b'{"complete": true}\n'), ("native/log.txt", b"done\n"), ("extra.txt", b"bad")]
    elif kind == "duplicate":
        members = [("reports/result.json", b'{"complete": true}\n'), ("native/log.txt", b"done\n"), ("native/log.txt", b"done\n")]
    if kind == "duplicate":
        with pytest.warns(UserWarning, match="Duplicate name"):
            manifest, part, _ = release(tmp_path, members=members)
    else:
        manifest, part, _ = release(tmp_path, members=members)
    if kind == "index":
        with manifest.with_name("files.jsonl").open("ab") as stream:
            stream.write(b" ")
    elif kind == "archive":
        with part.open("ab") as stream:
            stream.write(b"tampered")
    target = tmp_path / "must_not_exist"
    with pytest.raises(verifier.VerificationError):
        verifier.verify_release(manifest, part.parent, target)
    assert not target.exists()


@pytest.mark.parametrize("name", ["../escape.txt", "/absolute.txt", "C:/drive.txt", "dir\\escape.txt",
                                  "dir/../escape.txt", "file.txt:ads", "CON.txt", "name. "])
def test_unsafe_index_paths_rejected(tmp_path, name):
    record = {"path": name, "bytes": 1, "sha256": sha(b"x"), "part": "feng-suite-20260908-part-001.zip"}
    manifest, part, _ = release(tmp_path, records=[record], members=[(name, b"x")])
    with pytest.raises(verifier.VerificationError):
        verifier.verify_release(manifest, part.parent, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_zip_symlink_rejected_even_with_matching_bytes_and_digest(tmp_path):
    link = zipfile.ZipInfo("link.txt")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    record = {"path": "link.txt", "bytes": 7, "sha256": sha(b"../evil"), "part": "feng-suite-20260908-part-001.zip"}
    manifest, part, _ = release(tmp_path, records=[record], members=[(link, b"../evil")])
    with pytest.raises(verifier.VerificationError, match="Symbolic link"):
        verifier.verify_release(manifest, part.parent)


def test_existing_target_and_original_workspace_are_not_touched(tmp_path):
    manifest, part, _ = release(tmp_path)
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_bytes(b"keep me")
    with pytest.raises(verifier.VerificationError, match="already exists"):
        verifier.verify_release(manifest, part.parent, target)
    assert sentinel.read_bytes() == b"keep me"
    original_target = tmp_path / "original" / "new"
    original_target.parent.mkdir()
    with pytest.raises(verifier.VerificationError, match="outside the original"):
        verifier.verify_release(manifest, part.parent, original_target)
    assert not original_target.exists()


def test_bad_zip_path_is_rejected_even_when_index_paths_are_safe(tmp_path):
    manifest, part, _ = release(tmp_path, members=[("../escaped.txt", b"evil")])
    with pytest.raises(verifier.VerificationError, match="Unsafe path component"):
        verifier.verify_release(manifest, part.parent, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()
    assert not (tmp_path / "escaped.txt").exists()


@pytest.mark.parametrize("names", [("Result.txt", "result.txt"), ("entry", "ENTRY/child.txt")])
def test_windows_aliases_and_file_directory_collisions_rejected(tmp_path, names):
    records = [{"path": name, "bytes": 1, "sha256": sha(b"x"),
                "part": "feng-suite-20260908-part-001.zip"} for name in names]
    manifest, part, _ = release(tmp_path, records=records, members=[(name, b"x") for name in names])
    with pytest.raises(verifier.VerificationError):
        verifier.verify_release(manifest, part.parent)


def test_cli_failure_is_machine_readable(tmp_path, capsys):
    manifest, part, _ = release(tmp_path, members=[])
    assert verifier.main(["--manifest", str(manifest), "--archives-dir", str(part.parent)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FAIL" and "Missing ZIP members" in result["error"]
