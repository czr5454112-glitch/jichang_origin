"""Split an existing >95MiB delivery ZIP into <=64MiB Git-sized files.

No original ZIP is deleted or changed. Every output path is fresh. This does
not package evidence, extract a ZIP, use Git/LFS/network, or run any audit.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
PARTS_ROOT = HERE / "delivery_parts"
SCHEMA = "g31.inventory_spi.delivery_parts.v1"
PART_LIMIT = 64 * 1024 * 1024
SPLIT_TRIGGER = 95 * 1024 * 1024
CHUNK = 1024 * 1024
REASSEMBLER_NAME = "reassemble_partial_delivery_001.py"
REASSEMBLER_SHA = "349d8823e71c0c037a43b939ffbe30244eeb349960e49f2b5c6bf3eff7846714"


def require(ok, reason):
    if not ok:
        raise ValueError("delivery_split:" + reason)


def byte_hash(data):
    return hashlib.sha256(data).hexdigest()


def write_bytes(path, data):
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {"name": Path(path).name, "bytes": len(data), "sha256": byte_hash(data)}


def write_json(path, value):
    return write_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2,
                                       allow_nan=False) + "\n").encode("utf-8"))


def split(zip_path, zip_sha256, output=None):
    zip_path = Path(zip_path).resolve()
    require(re.fullmatch(r"[0-9a-f]{64}", zip_sha256) is not None, "trusted_zip_sha256")
    require(zip_path.is_file() and zip_path.suffix.lower() == ".zip", "existing_zip")
    original = zip_path.stat()
    require(original.st_size > SPLIT_TRIGGER, "split_only_if_larger_than_95MiB")
    output = (PARTS_ROOT / zip_path.stem if output is None else Path(output)).resolve()
    require(output.is_relative_to(PARTS_ROOT.resolve())
            and output != PARTS_ROOT.resolve() and not output.exists(), "fresh_parts_subdirectory")
    companion = (HERE / REASSEMBLER_NAME).read_bytes()
    require(byte_hash(companion) == REASSEMBLER_SHA, "pinned_reassembler_source")
    count = (original.st_size + PART_LIMIT - 1) // PART_LIMIT
    require(count <= 9999, "bounded_part_count")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    parts, full, total = [], hashlib.sha256(), 0
    with zip_path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        require((opened.st_size, opened.st_mtime_ns) == (original.st_size, original.st_mtime_ns),
                "zip_changed_before_read")
        for index in range(1, count + 1):
            name = f"archive.part{index:04d}"
            part, size = hashlib.sha256(), 0
            wanted = min(PART_LIMIT, original.st_size - total)
            with (output / name).open("xb") as target:
                while size < wanted:
                    block = stream.read(min(CHUNK, wanted - size))
                    require(bool(block), "zip_truncated")
                    target.write(block)
                    part.update(block)
                    full.update(block)
                    size += len(block)
                target.flush()
                os.fsync(target.fileno())
            parts.append({"index": index, "name": name, "bytes": size,
                          "sha256": part.hexdigest()})
            total += size
        require(stream.read(1) == b"", "zip_grew")
        ended = os.fstat(stream.fileno())
        require((ended.st_size, ended.st_mtime_ns) == (opened.st_size, opened.st_mtime_ns),
                "zip_changed_during_read")
    after = zip_path.stat()
    require((after.st_size, after.st_mtime_ns) == (original.st_size, original.st_mtime_ns),
            "original_path_changed")
    require(total == original.st_size and full.hexdigest() == zip_sha256, "full_zip_hash")
    reassembler = write_bytes(output / REASSEMBLER_NAME, companion)
    manifest = {"schema": SCHEMA, "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "archive": {"name": zip_path.name, "bytes": total, "sha256": zip_sha256},
                "part_size_limit_bytes": PART_LIMIT, "split_trigger_bytes": SPLIT_TRIGGER,
                "part_count": len(parts), "parts": parts, "reassembler": reassembler,
                "original_zip_preserved": True, "scientific_audit_performed": False}
    manifest_entry = write_json(output / "parts_manifest.json", manifest)
    readme = f"""G31 delivery ZIP parts

The original complete ZIP remains at the producer's original local path.
This directory is an exact byte split for Git publication, not a new evidence
package. No part exceeds 64MiB. No Git LFS or network operation was used.

Archive: {zip_path.name}
Archive bytes: {total}
Archive SHA256: {zip_sha256}
Manifest SHA256: {manifest_entry['sha256']}
Reassembler SHA256: {REASSEMBLER_SHA}

Download parts_manifest.json, all archive.partNNNN files and
{REASSEMBLER_NAME} from the same published revision. Obtain the trusted
expected manifest SHA from the separately supplied delivery receipt. Do not
mix revisions, skip a part, concatenate GitHub HTML pages or treat a failed
download as an empty part.

With Python3.11 and the standard library, from the downloaded directory:
  python -I -B {REASSEMBLER_NAME} --manifest parts_manifest.json --manifest-sha256 {manifest_entry['sha256']} --output "NEW_COMPLETE_DELIVERY.zip"

The output must not already exist and its parent directory must exist. Every
part is checked before output creation and again during copying. The saved
ZIP must match the original full bytes and SHA. Success prints status
verified_complete_archive. An error leaves any incomplete new output in place;
do not use or rename it as a verified archive, and do not overwrite evidence.

Reassembly does not extract the archive or establish scientific acceptance.
After a successful full ZIP check, follow the outer delivery README's Windows
Python3.11 deep-directory isolated audit. Its report and the ZIP's own SHA
remain outside evidence/; the existing exact CAS package is not modified.
"""
    readme_entry = write_bytes(output / "README.txt", readme.encode("utf-8"))
    receipt = {"schema": SCHEMA + ".split_receipt", "status": "byte_split_complete",
               "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "implementation": {"path": str(Path(__file__).resolve()),
                                  "sha256": byte_hash(Path(__file__).read_bytes())},
               "source_zip": {"path": str(zip_path), "bytes": total, "sha256": zip_sha256},
               "parts_directory": str(output), "manifest": manifest_entry,
               "reassembler": reassembler, "readme": readme_entry,
               "part_count": len(parts), "largest_part_bytes": max(r["bytes"] for r in parts),
               "original_zip_preserved": True, "reassembly_executed": False,
               "scientific_audit_performed": False, "git_operations": 0}
    receipt_entry = write_json(output / "split_receipt.json", receipt)
    return {"status": receipt["status"], "parts_directory": str(output),
            "manifest": manifest_entry, "receipt": receipt_entry,
            "archive": manifest["archive"], "part_count": len(parts)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", required=True)
    parser.add_argument("--zip-sha256", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        result = split(args.zip, args.zip_sha256, args.output)
    except Exception as exc:
        raise SystemExit("Split failed; original ZIP was not modified. Retain partial output for diagnosis; "
                         "do not publish it as complete. " + type(exc).__name__ + ": " + str(exc))
    print(json.dumps(result, ensure_ascii=False))
