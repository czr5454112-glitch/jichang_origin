"""Reassemble exact delivery bytes using only Python's standard library.

Never extracts the ZIP or validates scientific evidence. A new output is required.
On an I/O or hash failure, an incomplete new output may remain; it is not valid.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

SCHEMA = "g31.inventory_spi.delivery_parts.v1"
PART_LIMIT = 64 * 1024 * 1024
CHUNK = 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}")


def require(ok, reason):
    if not ok:
        raise ValueError("delivery_reassembly:" + reason)


def file_hash(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            value.update(block)
    return value.hexdigest()


def reassemble(manifest_path, manifest_sha256, output):
    manifest_path, output = Path(manifest_path).resolve(), Path(output).resolve()
    require(HASH.fullmatch(manifest_sha256) is not None, "trusted_manifest_sha256")
    require(manifest_path.stat().st_size <= 1024 * 1024, "small_manifest")
    raw = manifest_path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == manifest_sha256, "manifest_bytes")
    manifest = json.loads(raw)
    require(manifest["schema"] == SCHEMA, "schema")
    require(manifest["part_size_limit_bytes"] == PART_LIMIT, "fixed_64MiB_limit")
    archive, parts = manifest["archive"], manifest["parts"]
    require(type(archive["bytes"]) is int and archive["bytes"] > 0
            and HASH.fullmatch(archive["sha256"]) is not None, "archive_identity")
    expected_count = (archive["bytes"] + PART_LIMIT - 1) // PART_LIMIT
    require(type(manifest["part_count"]) is int
            and manifest["part_count"] == len(parts) == expected_count
            and 1 <= expected_count <= 9999, "complete_part_count")
    own = manifest["reassembler"]
    require(own["name"] == Path(__file__).name
            and type(own["bytes"]) is int
            and Path(__file__).stat().st_size == own["bytes"]
            and file_hash(__file__) == own["sha256"], "exact_reassembler")
    require(not output.exists() and output.parent.is_dir(), "fresh_output_existing_parent")
    files = []
    for index, row in enumerate(parts, 1):
        require(type(row["index"]) is int and row["index"] == index
                and row["name"] == f"archive.part{index:04d}", "ordered_safe_part_name")
        size = min(PART_LIMIT, archive["bytes"] - (index - 1) * PART_LIMIT)
        require(type(row["bytes"]) is int and row["bytes"] == size
                and HASH.fullmatch(row["sha256"]) is not None, "part_identity")
        path = (manifest_path.parent / row["name"]).resolve()
        require(path.parent == manifest_path.parent and path.is_file()
                and path.stat().st_size == size, "part_path_and_size")
        require(file_hash(path) == row["sha256"], "preflight_part_hash:" + row["name"])
        files.append((path, row))
    # Verify once before creating the output and again while copying. No input
    # or existing output is overwritten; failed partial output is retained.
    full = hashlib.sha256()
    total = 0
    with output.open("xb") as target:
        for path, row in files:
            part, copied = hashlib.sha256(), 0
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(CHUNK), b""):
                    target.write(block)
                    part.update(block)
                    full.update(block)
                    copied += len(block)
            require(copied == row["bytes"] and part.hexdigest() == row["sha256"],
                    "part_changed_while_copying:" + row["name"])
            total += copied
    require(total == archive["bytes"] and full.hexdigest() == archive["sha256"], "full_archive_bytes")
    require(output.stat().st_size == total and file_hash(output) == archive["sha256"],
            "saved_output_hash")
    return {"schema": SCHEMA + ".reassembly", "status": "verified_complete_archive",
            "manifest_sha256": manifest_sha256, "output": str(output),
            "bytes": total, "sha256": full.hexdigest(), "parts": len(parts),
            "scientific_audit_performed": False, "zip_extracted": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = reassemble(args.manifest, args.manifest_sha256, args.output)
    except Exception as exc:
        raise SystemExit("Reassembly failed; any newly created output is incomplete and must not be used. "
                         + type(exc).__name__ + ": " + str(exc))
    print(json.dumps(result, ensure_ascii=False))
