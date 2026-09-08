"""Read-only validation probes; no recovery output/spec or Java execution."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.eval import recover_feng_dh_paper_suite_v2 as recovery


def main():
    source = ROOT / "outputs/runtime/feng_paper_suite_20260907/cells/b_nanning_2x_v2p5_s104729_q00_dh"
    status = recovery.read(source / "runner_status.json")
    oldpath = Path(status["spec_path"])
    spec = deepcopy(recovery.read(oldpath))
    spec["cell_id"] += "_postprocess_v2"
    spec["native_recovery_from"] = {"output_dir": str(source),
        "files_sha256": {name: recovery.sha(source / name) for name in recovery.FILES},
        "runner_path": str(recovery.OLD_RUNNER), "runner_sha256": recovery.OLD_RUNNER_SHA,
        "spec_path": str(oldpath), "spec_sha256": recovery.sha(oldpath)}
    output = source.parent / spec["cell_id"]
    records = []
    with patch.object(recovery.runner.subprocess, "run", side_effect=AssertionError("subprocess forbidden")), \
            patch.object(recovery.runner, "compile_build", side_effect=AssertionError("compile forbidden")):
        recovery.validate_source(spec, output)
        records.append({"case": "real_exact_source_and_parameters", "pass": True})
        for name, mutate, where in [
            ("changed_speed", lambda s: s.update(speed_mps=1.5), output),
            ("changed_horizon", lambda s: s.update(horizon_seconds=98258), output),
            ("changed_seed", lambda s: s.update(seed=130363), output),
            ("source_byte_hash_tamper", lambda s: s["native_recovery_from"]["files_sha256"].update({"segments.csv": "0" * 64}), output),
            ("missing_source_file_hash", lambda s: s["native_recovery_from"]["files_sha256"].pop("bags.csv"), output),
            ("reuse_original_output", lambda s: None, source),
        ]:
            modified = deepcopy(spec)
            mutate(modified)
            try:
                recovery.validate_source(modified, where)
            except (ValueError, KeyError) as error:
                records.append({"case": name, "pass": True, "rejection": str(error)})
            else:
                raise AssertionError("invalid recovery allowed: " + name)
    result = {"schema": "czr005.dh_native_recovery_readonly_review.v1", "status": "PASS",
        "case_count": len(records), "cases": records, "native_simulations_invoked": 0,
        "native_compiles_invoked": 0, "recovery_output_created_by_review": False,
        "recovery_source_path": str(Path(recovery.__file__)), "recovery_source_sha256": recovery.sha(recovery.__file__),
        "normalizer_path": str(Path(recovery.runner.__file__)), "normalizer_sha256": recovery.sha(recovery.runner.__file__),
        "original_native_status_sha256": recovery.sha(source / "runner_status.json"),
        "review_driver_sha256": recovery.sha(__file__),
        "scope": "validate_source on the real 87205-segment native attempt plus in-memory parameter/hash rejection probes only; no recover() invocation or destination creation."}
    path = ROOT / "tmp/dh_recovery_source_review_replay_20260907.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "case_count": len(records), "result": str(path)}))


if __name__ == "__main__":
    main()
