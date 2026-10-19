"""Export reviewable local diffs without staging, committing or pushing."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).absolute().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    files = {".gitattributes", "CMakeLists.txt", "cpp/ics_core/runtime/event_driven_junction.hpp",
             "cpp/ics_core/runtime/circulation.hpp", "cpp/ics_core/runtime/circulation_runtime_impl.hpp",
             "cpp/ics_core/bindings/circulation.cpp", "cpp/tests/test_circulation_runtime.cpp",
             "cpp/tests/g31_legacy_replay_fixture.cpp"}
    for pattern in ("scripts/experiments/g31_ics_circulation/*.py", "tests/test_g31_circulation*.py", "docs/g31_ics_circulation/*"):
        files.update(p.relative_to(ROOT).as_posix() for p in ROOT.glob(pattern) if p.is_file())
    files = sorted(files)
    tracked = set(subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=ROOT, text=True).splitlines())
    patch = subprocess.check_output(["git", "diff", "--binary", "HEAD", "--", *[p for p in files if p in tracked]], cwd=ROOT)
    commands = []
    for path in files:
        if path in tracked:
            continue
        null = "NUL" if __import__("os").name == "nt" else "/dev/null"
        argv = ["git", "diff", "--no-index", "--binary", "--", null, path]
        p = subprocess.run(argv, cwd=ROOT, capture_output=True, check=False)
        if p.returncode not in (0, 1):
            raise RuntimeError(p.stderr.decode(errors="replace"))
        patch += p.stdout
        commands.append({"argv": argv, "exit_code": p.returncode, "stderr": p.stderr.decode(errors="replace")})
    patch_path = out / "native_circulation.patch"
    patch_path.write_bytes(patch)
    check = subprocess.run(["git", "apply", "--reverse", "--check", str(patch_path)], cwd=ROOT, capture_output=True)
    if check.returncode:
        raise RuntimeError("Native reverse-apply check failed: " + check.stderr.decode(errors="replace"))
    correctness = ROOT / "outputs/experiments/g31_ics_circulation_20261013/v3_correctness/v3_correctness.patch"
    (out / correctness.name).write_bytes(correctness.read_bytes())
    v3_files = ["scripts/experiments/ics_circulation_v3/" + name for name in
                ("routing_reference.py", "runtime.py", "terminal_capacity_screen.py")]
    v3_files.append("tests/test_ics_v3_executed_audit_regressions.py")
    protected = ROOT.parent / "cpp/ics_core/runtime/bounded_local_pibt.hpp"
    protected_sha = hashlib.sha256(protected.read_bytes()).hexdigest()
    expected = "b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951"
    if protected_sha != expected:
        raise RuntimeError("Original user modification changed since the baseline receipt")
    manifest = {"schema": "g31.circulation.delivery.v1", "branch": subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip(),
                "base_commit": subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                "v3_reference_commit": "fccd4819532701ee4173ec598822450d962d4e61", "pushed": False,
                "protected_original_file_sha256": protected_sha, "native_patch_reverse_check_exit_code": check.returncode,
                "implementation_files": {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},
                "v3_correctness_files": {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in v3_files},
                "patch_sha256": {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (patch_path,out/correctness.name)},
                "diff_commands": commands}
    (out / "manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    with zipfile.ZipFile(out / "implementation_and_diffs.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(ROOT/path,"working_source/"+path)
        for path in v3_files:
            archive.write(ROOT/path,"working_source/"+path)
        for path in (patch_path,out/correctness.name,out/"manifest.json"):
            archive.write(path,path.name)
    print(json.dumps({"output":str(out),"native_files":len(files),"native_patch_bytes":len(patch),"protected_original_unchanged":True}))


if __name__ == "__main__":
    main()
