"""Isolated bootstrap safety probe; synthetic bytes test I/O, not ICS results."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[4]
DEST = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("prepare_fixtures", DEST.parent / "tools/prepare_fixtures.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main():
    cpu, wall, checks = process_time(), perf_counter(), []
    with tempfile.TemporaryDirectory(prefix="bootstrap-probe-", dir=DEST) as directory:
        root = Path(directory).resolve()
        # Confirm the one temporary tree that the context manager will remove.
        assert root.is_relative_to(DEST.resolve())
        archive_dir = root / MODULE.REVIEW / "fixtures"
        archive_dir.mkdir(parents=True)
        entries = []
        for name in sorted(MODULE.NAMES):
            content = (name + "\nsynthetic bootstrap probe\n").encode()
            packed = gzip.compress(content, mtime=0)
            archive = archive_dir / (name + ".gz")
            archive.write_bytes(packed)
            entries.append(dict(original_path=(MODULE.OUTPUT / name).as_posix(),
                original_sha256=hashlib.sha256(content).hexdigest(), original_bytes=len(content),
                gzip_path=archive.relative_to(root).as_posix(),
                gzip_sha256=hashlib.sha256(packed).hexdigest(), gzip_bytes=len(packed)))
        manifest = {"schema": "ics-v3-complete-cursor-fixtures-v1", "fixtures": entries}
        manifest_path = archive_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        assert all(x["status"] == "materialized" for x in MODULE.prepare(root))
        checks.append("six_atomic_publications")
        assert all(x["status"] == "existing_verified" for x in MODULE.prepare(root))
        checks.append("six_existing_unchanged")
        target = root / entries[0]["original_path"]
        original = target.read_bytes()
        target.write_bytes(b"existing-user-content")
        try:
            MODULE.prepare(root)
        except ValueError as error:
            assert "existing fixture differs" in str(error)
        else:
            raise AssertionError("differing existing file was accepted")
        assert target.read_bytes() == b"existing-user-content"
        checks.append("differing_existing_preserved")
        target.write_bytes(original)
        archive = root / entries[0]["gzip_path"]
        packed = archive.read_bytes()
        archive.write_bytes(packed + b"corrupt")
        try:
            MODULE.prepare(root)
        except ValueError as error:
            assert "gzip SHA256/size mismatch" in str(error)
        else:
            raise AssertionError("corrupt gzip accepted")
        checks.append("corrupt_archive_rejected")
        archive.write_bytes(packed)
        for relative in ("../escape", "C:/outside", "/outside", "dir\\outside"):
            try:
                MODULE.safe_path(root, relative)
            except ValueError:
                pass
            else:
                raise AssertionError("unsafe path accepted: " + relative)
        checks.append("four_unsafe_path_forms_rejected")
        manifest["fixtures"][0]["original_path"] = "../escape"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        try:
            MODULE.prepare(root)
        except ValueError as error:
            assert "six fixed paths" in str(error)
        else:
            raise AssertionError("manifest destination manipulation accepted")
        checks.append("manifest_path_manipulation_rejected")
        assert not list(root.rglob(".ics-fixture-*.tmp"))
        checks.append("failure_temporaries_removed")
    result = dict(status="passed", checks=checks, physical_runs=0, regression_tests_run=0,
                  cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
                  scope="Bootstrap I/O probe on six synthetic byte strings, not reduced ICS fixtures")
    (DEST / "bootstrap_probe.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
