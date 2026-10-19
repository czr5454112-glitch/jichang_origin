"""Import only the frozen V3 reference namespace, never an entire branch merge.

Run once on the mature G31 checkout before applying v3_correctness.patch.
Existing differing paths are rejected, including already corrected V3 files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REFERENCE = "fccd4819532701ee4173ec598822450d962d4e61"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repository", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    destination = args.destination.absolute()
    if args.manifest.exists():
        raise FileExistsError("Use a new manifest path")
    paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", REFERENCE],
                                    cwd=args.source_repository, text=True).splitlines()
    selected = [p for p in paths if p.startswith(("scripts/experiments/ics_circulation_v3/", "docs/ics_circulation_v3/"))
                or (p.startswith("tests/test_ics_") and ("circulation_v3" in p or "ics_v3_" in p))]
    payload = subprocess.check_output(["git", "cat-file", "--batch"], cwd=args.source_repository,
                                      input="".join(f"{REFERENCE}:{p}\n" for p in selected).encode())
    files = []
    offset = 0
    for path in selected:
        end = payload.index(b"\n", offset)
        count = int(payload[offset:end].split()[-1])
        offset = end + 1
        data = payload[offset:offset+count]
        offset += count+1
        target = destination / path
        if target.exists() and target.read_bytes() != data:
            raise FileExistsError(f"Refusing to overwrite differing path: {target}")
        files.append((path, data))
    # Mutation starts only after all collision checks, and preserves blob bytes.
    for path, data in files:
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps({"source_commit": REFERENCE,
        "files": [{"path": p, "sha256": hashlib.sha256(b).hexdigest()} for p,b in files]}, indent=2), encoding="utf-8")
    print(f"Imported/verified {len(files)} namespace files from {REFERENCE}")


if __name__ == "__main__":
    main()
