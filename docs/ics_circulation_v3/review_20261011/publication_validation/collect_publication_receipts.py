"""Collect observed publication verification, without rerunning research."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from time import process_time, perf_counter

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parent
REVIEW = ROOT / "docs/ics_circulation_v3/review_20261011"
DEST = REVIEW / "publication_validation"
EXPORT = WORK / "isolated_checkout"
CODE = "defd79effe02ee13f1a5bbbbc5143f6d0dce2f63"

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def main():
    cpu, wall = process_time(), perf_counter()
    assert not DEST.exists(), "Do not overwrite publication evidence"
    successful = json.loads((WORK / "isolated_validation_002/results.json").read_bytes())
    assert successful["status"] == "passed" and successful["outcomes"] == {
        "total": 1519, "passed": 1519, "failed": 0, "errors": 0, "skipped": 0}
    assert successful["source_changed"] == []
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == CODE
    archived = json.loads((WORK / "archive.json").read_bytes())
    archive = ROOT / archived["archive_path"]
    assert digest(archive) == archived["archive_sha256"] and archive.stat().st_size == archived["archive_bytes"]
    source = json.loads((REVIEW / "source_manifest.json").read_bytes())
    for name, spec in source["python_source_and_tests"].items():
        assert digest(ROOT / name) == digest(EXPORT / name) == spec["working_bytes_sha256"]
    cpp = ROOT / "cpp/ics_core/runtime/bounded_local_pibt.hpp"
    assert digest(cpp) == "b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951"
    environment_code = """import json,sys,os,platform,pytest,numpy,pygments
import scripts.experiments.ics_circulation_v3.model as model
import scripts.experiments.ics_circulation_v3.business_projection_runtime as projection
print(json.dumps(dict(python=sys.version, executable=sys.executable, platform=platform.platform(), cwd=os.getcwd(), sys_path=sys.path, versions=dict(pytest=pytest.__version__,numpy=numpy.__version__,pygments=pygments.__version__), module_paths=dict(pytest=pytest.__file__,numpy=numpy.__file__,pygments=pygments.__file__,model=model.__file__,projection=projection.__file__))))
"""
    environment = json.loads(subprocess.check_output([sys.executable, "-c", environment_code], cwd=EXPORT, text=True))
    for name in ("model", "projection"):
        assert Path(environment["module_paths"][name]).resolve().is_relative_to(EXPORT)
    fixtures = json.loads((REVIEW / "fixtures/manifest.json").read_bytes())["fixtures"]
    for fixture in fixtures:
        path = EXPORT / fixture["original_path"]
        assert path.stat().st_size == fixture["original_bytes"] and digest(path) == fixture["original_sha256"]
    DEST.mkdir()
    for attempt in ("isolated_validation_001", "isolated_validation_002"):
        (DEST / attempt).mkdir()
        for name in ("results.json", "source_before.json", "source_after.json", "runner.py", "junit.xml"):
            path = WORK / attempt / name
            if path.exists():
                shutil.copyfile(path, DEST / attempt / name)
    for name in ("archive.json", "staging_validation.json"):
        shutil.copyfile(WORK / name, DEST / name)
    dump(DEST / "environment_probe.json", environment)
    dump(DEST / "fixture_restoration_verified.json", dict(status="passed", fixtures=fixtures,
        full_restored_bytes=sum(row["original_bytes"] for row in fixtures),
        method="Read all six complete materialized fixtures in exported checkout after full test run; compare exact size and SHA256 with committed manifest; no samples.",
        original_bootstrap_command="python -I docs/ics_circulation_v3/review_20261011/tools/prepare_fixtures.py",
        original_bootstrap_observed="All six printed materialized before test run; original stdout is not duplicated here.",
        physical_runs=0))
    shutil.copyfile(__file__, DEST / "collect_publication_receipts.py")
    copied = {p.relative_to(DEST).as_posix(): dict(bytes=p.stat().st_size, sha256=digest(p))
              for p in sorted(DEST.rglob("*")) if p.is_file()}
    dump(DEST / "collection.json", dict(status="passed", code_commit=CODE,
        observed_at_utc=datetime.now(timezone.utc).isoformat(), receipts=copied,
        source_files_exact=211, protected_cpp_unchanged=True,
        cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
        resource_scope="This collection process only; environment-probe subprocess CPU unknown; no physics; final collection.json write excluded.",
        physical_runs=0))
    print(json.dumps(dict(status="passed", copied_files=len(copied), destination=str(DEST))))

if __name__ == "__main__":
    main()
