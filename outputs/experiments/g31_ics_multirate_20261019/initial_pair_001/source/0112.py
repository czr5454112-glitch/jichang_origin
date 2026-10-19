"""Export a reviewable delta from the verified prior delivery, without Git writes."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).absolute().parents[3]
BASE = ROOT / "outputs/experiments/g31_ics_circulation_20261013/delivery_001/implementation_and_diffs.zip"
BASE_SHA = "bce9c6c9e4954439d157a7bc00610ec691a0668076b9bb70e75a5b1140b96f86"


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    if sha(BASE.read_bytes()) != BASE_SHA:
        raise RuntimeError("prior delivery identity mismatch; do not derive a delta from it")
    with zipfile.ZipFile(BASE) as archive:
        old = {name.removeprefix("working_source/"): archive.read(name)
               for name in archive.namelist() if name.startswith("working_source/")}
    paths = {ROOT / name for name in old}
    for pattern in ("cpp/ics_core/runtime/circulation*.hpp", "cpp/ics_core/bindings/circulation*",
                    "cpp/tests/test_circulation*", "cpp/tests/g31_legacy_replay_fixture.cpp",
                    "scripts/experiments/g31_ics_circulation/*.py",
                    "tests/test_g31_circulation_*.py", "tests/test_g31_fixed_blocking_certificate.py",
                    "tests/test_g31_original_mechanism.py", "docs/g31_ics_circulation/*"):
        paths.update(p for p in ROOT.glob(pattern) if p.is_file())
    patch = []; changed = {}; current = {}
    for path in sorted(paths):
        name = path.relative_to(ROOT).as_posix()
        data = path.read_bytes(); previous = old.get(name, b""); current[name] = sha(data)
        if data == previous:
            continue
        # Normalize text line endings for a portable patch; raw file SHA256
        # and exact current bytes are still included in the source ZIP.
        before = previous.decode("utf-8-sig").replace("\r\n", "\n")
        after = data.decode("utf-8-sig").replace("\r\n", "\n")
        delta = list(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                     fromfile="a/" + name if name in old else "/dev/null", tofile="b/" + name))
        if delta:
            patch.append("diff --git a/" + name + " b/" + name + "\n")
            patch.extend(delta)
        changed[name] = {"before_sha256": sha(previous) if name in old else None,
                         "after_sha256": sha(data), "text_changed": bool(delta)}
    patch_file = args.output / "long_term_from_verified_delivery.patch"
    patch_file.write_text("".join(patch), encoding="utf-8", newline="\n")
    check = subprocess.run(["git", "apply", "--reverse", "--check", str(patch_file.absolute())],
                           cwd=ROOT, capture_output=True, check=False)
    (args.output / "patch_reverse_check.stdout.log").write_bytes(check.stdout)
    (args.output / "patch_reverse_check.stderr.log").write_bytes(check.stderr)
    manifest = {"schema": "g31.long_term_delta.v1", "baseline_zip": str(BASE),
                "baseline_zip_sha256": BASE_SHA, "changed_files": changed, "current_source_sha256": current,
                "patch_sha256": sha(patch_file.read_bytes()), "patch_reverse_check_exit_code": check.returncode,
                "scope": "incremental local source and progress delta; not full repo, raw experiments or binaries",
                "committed": False, "pushed": False}
    manifest_file = args.output / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with zipfile.ZipFile(args.output / "long_term_source_delta.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in changed:
            archive.write(ROOT / name, "working_source/" + name)
        archive.write(patch_file, patch_file.name); archive.write(manifest_file, manifest_file.name)
    print(json.dumps({"changed_files": len(changed), "reverse_check_exit_code": check.returncode,
                      "zip_sha256": sha((args.output / "long_term_source_delta.zip").read_bytes())}))
    return check.returncode


if __name__ == "__main__":
    raise SystemExit(main())
