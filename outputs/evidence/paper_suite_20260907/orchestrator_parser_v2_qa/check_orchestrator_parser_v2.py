"""SYNTHETIC QA: fixed runner selection and stage control; no native/pool dispatch.

Run from the repository root. Small synthetic CSVs exercise the actual old/new
DH normalizers and retained-archive verifier. All process dispatch is mocked.
"""
from pathlib import Path
import copy
import csv
import gzip
import hashlib
import json
import shutil
import sys
import threading
import uuid
from unittest.mock import patch

ROOT = Path.cwd().resolve()
sys.path.insert(0, str(ROOT))
from scripts.eval import run_feng_paper_suite_v2 as pool
from scripts.eval import run_feng_paper_suite_campaign_v2 as master
from scripts.eval import run_feng_dh_paper_suite as dh_old
from scripts.eval import run_feng_dh_paper_suite_v2 as dh_new
from scripts.eval import recover_feng_dh_paper_suite_v2 as recovery_helper

OUT = ROOT / "build/paper_suite_orchestrator_parser_v2_qa" / uuid.uuid4().hex[:12]
OUT.mkdir(parents=True)
CHECKS = []
ORIGINALS = {
    "scripts/eval/run_feng_paper_suite.py": "5be8f62e7fa31fd60900c30a5c2796d958acec366de7735e3335e86e9f8ad798",
    "scripts/eval/run_feng_paper_suite_campaign.py": "50e390e83dc950e15fc05fbfddb1574655e7e8f4d431424865d12d079dd2c4b5",
    "scripts/eval/run_feng_dh_paper_suite.py": "f1879d989364e4f9b051d37c85f8458d0e16c5221e3340d529a42e84828de3d6",
}


def check(name, condition):
    assert condition, name
    CHECKS.append(name)


def reject(name, action):
    try:
        action()
    except (ValueError, FileNotFoundError):
        CHECKS.append(name)
    else:
        raise AssertionError(name)


def dump_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


protocols = []
for family in ("base", "all_day_fault"):
    path = OUT / (family + ".md")
    path.write_text("SYNTHETIC QA ONLY " + family, encoding="utf-8")
    protocols.append(dict(family=family, path=str(path), sha256=pool.sha(path)))


def fixture(name, module, incomplete):
    output = OUT / "fixtures" / name
    output.mkdir(parents=True)
    canonical = output / "canonical.jsonl"
    rows = [dict(task_id=i, leg="direct", segment_id=f"{i}:direct", start=0, goal=1,
                 pass_time=100, std=4000) for i in (1, 2)]
    canonical.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    identity = dict(canonical_path=str(canonical), raw_bag_count=2)
    identity_path = output / "identity.json"
    pool.write(identity_path, identity)
    spec = dict(method=pool.DH, family="base", seed=104729, speed_mps=2.5, map="nanning",
                load_factor=2, scenario_index=0, timing_policy="full_population_only", horizon_seconds=98259,
                protocol_path=protocols[0]["path"], protocol_sha256=protocols[0]["sha256"],
                workload_identity_path=str(identity_path), workload_identity_sha256=pool.sha(identity_path),
                classes_dir=str(module.BUILD))
    spec_path = output / "spec.json"
    pool.write(spec_path, spec)
    cell = dict(spec, cell_id=name, output_dir=str(output), spec_path=str(spec_path),
                spec_sha256=pool.sha(spec_path), runner_path=module.__file__, runner_sha256=pool.sha(Path(module.__file__)))
    native = [dict(source_raw_bag_id=i, segment_id=0, start=0, goal=1, release_seconds=100,
                   completion_time_seconds="N/A" if incomplete and i == 2 else 110+i,
                   admission_time_seconds="N/A" if incomplete and i == 2 else 101,
                   status="WAITING" if incomplete and i == 2 else "COMPLETED",
                   final_node=0 if incomplete and i == 2 else 1) for i in (1, 2)]
    dump_csv(output / "segments.csv", native)
    for filename in ("bags.csv", "trace.csv", "summary.csv", "event_summary.csv"):
        (output / filename).write_text("SYNTHETIC QA ONLY\n", encoding="utf-8")
    archive = []
    for filename in ("segments.csv", "bags.csv", "trace.csv", "summary.csv", "event_summary.csv"):
        raw = (output / filename).read_bytes()
        target = output / (filename + ".gz")
        target.write_bytes(gzip.compress(raw, mtime=0))
        archive.append(dict(file=target.name, sha256=pool.sha(target), uncompressed_sha256=hashlib.sha256(raw).hexdigest()))
    derived = module.normalize(identity, output)
    bags = derived.pop("bags")
    pool.write(output / "population_audit.json", derived)
    (output / "raw_bag_metrics.jsonl.gz").write_bytes(gzip.compress(
        "".join(json.dumps(bag) + "\n" for bag in bags).encode(), mtime=0))
    pool.write(output / "build_identity.json", pool.read(module.BUILD / "build_identity.json"))
    pool.write(output / "runner_status.json", dict(status="COMPLETE", runner_sha256=cell["runner_sha256"],
               spec_sha256=cell["spec_sha256"], returncode=0))
    result = dict(status="COMPLETE", method=pool.DH, audit_status="PASS", map="nanning", load_factor=2,
                  speed_mps=2.5, seed=104729, spec_sha256=cell["spec_sha256"],
                  workload_identity_sha256=pool.sha(identity_path), archives=archive,
                  full_population_complete=derived["full_population_complete"], metrics=derived["metrics"])
    pool.write(output / "normalized_result.json", result)
    return cell, spec, identity_path, identity


fixtures = [fixture("old_complete", dh_old, False), fixture("new_censored", dh_new, True)]
modules = {"scripts.eval.run_feng_dh_paper_suite": dh_old, "scripts.eval.run_feng_dh_paper_suite_v2": dh_new}
for (cell, spec, identity_path, identity), module in zip(fixtures, (dh_old, dh_new)):
    check(cell["cell_id"] + "_bound_whitelist", pool.verify_bound_cell(cell) == spec)
    imported = []
    def import_selected(name):
        imported.append(name)
        return modules[name]
    with patch.object(pool.importlib, "import_module", side_effect=import_selected), \
         patch.object(module.external, "_identity_payload", return_value=(identity_path, identity)), \
         patch.object(module, "normalize", wraps=module.normalize) as normalize, \
         patch.object(pool.subprocess, "Popen", side_effect=AssertionError("native launch forbidden")):
        verified = pool.verify_cell(cell)
        reused = pool.execute_cell(cell, OUT / (cell["cell_id"] + "_reuse_record"), 0, threading.Event())
    check(cell["cell_id"] + "_selected_actual_normalizer",
          imported == [module.__name__, module.__name__] and normalize.call_count == 2)
    check(cell["cell_id"] + "_archive_reuse_no_dispatch", reused["status"] == "REUSED_VERIFIED")
    check(cell["cell_id"] + "_full_population_flag", verified["full_population_complete"] == (module is dh_old))

cell, spec, identity_path, identity = fixtures[1]
result = pool.read(Path(cell["output_dir"]) / "normalized_result.json")
check("censored_bag_retained_and_both_THT_clocks_null",
      result["metrics"]["raw_bag_denominator"] == 2 and result["metrics"]["completed_raw_bag_count"] == 1
      and all(value is None for key, value in result["metrics"].items() if key.startswith("tht_")))
reject("old_parser_rejects_NA_negative_control", lambda: dh_old.normalize(identity, Path(cell["output_dir"])))
reject("old_SHA_cannot_bind_new_parser", lambda: pool.selected_runner(dict(cell, runner_sha256=fixtures[0][0]["runner_sha256"])))
reject("unknown_runner_even_with_valid_SHA_rejected", lambda: pool.selected_runner(dict(cell,
       runner_path=__file__, runner_sha256=pool.sha(Path(__file__)))))
reject("non_DH_cannot_select_DH_v2", lambda: pool.selected_runner(dict(cell, method=pool.HCA)))
reject("missing_runner_rejected", lambda: pool.selected_runner(dict(cell, runner_path=str(OUT / "missing.py"))))

# Recovery-chain gate: only the helper's existing original-source validator is
# mocked here. The new pool actually verifies every copied byte and the full
# result/status/parser/helper provenance chain, including tampering negatives.
recovered, recovery_spec, recovery_identity_path, recovery_identity = fixture("recovery_output", dh_new, True)
recovery_output = Path(recovered["output_dir"])
source = recovery_output.with_name("recovery_original")
source.mkdir()
source_status = dict(command=["SYNTHETIC native command; never executed"], started_at_unix=1, wall_seconds=2,
                     status="NATIVE_COMPLETE", returncode=0)
for filename in recovery_helper.FILES:
    if filename == "runner_status.json":
        pool.write(source / filename, source_status)
        shutil.copyfile(source / filename, recovery_output / "source_runner_status.json")
    else:
        if not (recovery_output / filename).exists():
            (recovery_output / filename).write_text("SYNTHETIC QA ONLY\n", encoding="utf-8")
        shutil.copyfile(recovery_output / filename, source / filename)
origin = dict(output_dir=str(source), files_sha256={name: pool.sha(source / name) for name in recovery_helper.FILES},
              runner_path=dh_old.__file__, runner_sha256=pool.sha(Path(dh_old.__file__)),
              spec_path=fixtures[0][0]["spec_path"], spec_sha256=fixtures[0][0]["spec_sha256"])
recovery_spec["native_recovery_from"] = origin
pool.write(Path(recovered["spec_path"]), recovery_spec)
recovered["spec_sha256"] = pool.sha(Path(recovered["spec_path"]))
provenance = dict(schema="czr005.dh_parser_recovery.v2", source=origin, native_reexecuted=False,
                  original_native_bytes_unchanged=True, source_spec_sha256=origin["spec_sha256"],
                  native_runner_sha256=origin["runner_sha256"], original_native_command=source_status["command"],
                  native_started_at_unix=1, native_wall_seconds=2,
                  normalizer_path=dh_new.__file__, normalizer_sha256=recovered["runner_sha256"],
                  recovery_tool_path=recovery_helper.__file__, recovery_tool_sha256=pool.sha(Path(recovery_helper.__file__)))
recovery_result = pool.read(recovery_output / "normalized_result.json")
recovery_status = pool.read(recovery_output / "runner_status.json")
recovery_result.update(spec_sha256=recovered["spec_sha256"], native_reexecuted=False)
recovery_status.update(spec_sha256=recovered["spec_sha256"], native_reexecuted=False,
                       native_runner_sha256=origin["runner_sha256"], command=source_status["command"],
                       started_at_unix=1, wall_seconds=2)


def recovery_bind(value):
    pool.write(recovery_output / "native_recovery.json", value)
    recovery_result["native_recovery_sha256"] = pool.sha(recovery_output / "native_recovery.json")
    pool.write(recovery_output / "normalized_result.json", recovery_result)
    recovery_status.update(recovery=value, normalized_result_sha256=pool.sha(recovery_output / "normalized_result.json"))
    pool.write(recovery_output / "runner_status.json", recovery_status)


def verify_recovery():
    return pool.verify_cell(recovered)


recovery_bind(provenance)
with patch.object(recovery_helper, "validate_source", return_value=(source, recovery_output, recovery_identity_path,
                                                                  recovery_identity, source_status)) as validation, \
     patch.object(dh_new.external, "_identity_payload", return_value=(recovery_identity_path, recovery_identity)), \
     patch.object(pool.subprocess, "Popen", side_effect=AssertionError("native launch forbidden")):
    check("recovery_provenance_and_original_copy_chain_accepted", verify_recovery()["full_population_complete"] is False
          and validation.call_count == 1)
    for key, value in (("native_reexecuted", True), ("original_native_bytes_unchanged", False),
                       ("normalizer_path", dh_old.__file__), ("recovery_tool_sha256", "0"*64),
                       ("source_spec_sha256", "0"*64), ("original_native_command", ["different native command"])):
        recovery_bind(dict(provenance, **{key: value}))
        reject("recovery_rebound_" + key + "_tamper_rejected", verify_recovery)
    recovery_bind(provenance)
    for name in ("segments.csv", "source_runner_status.json"):
        path = recovery_output / name
        before = path.read_bytes()
        path.write_bytes(before + b"\n")
        reject("recovery_original_" + name + "_byte_tamper_rejected", verify_recovery)
        path.write_bytes(before)
    recovery_result["native_recovery_sha256"] = "0"*64
    pool.write(recovery_output / "normalized_result.json", recovery_result)
    reject("recovery_result_SHA_binding_tamper_rejected", verify_recovery)
    recovery_bind(provenance)
    check("recovery_restored_chain_still_accepted", verify_recovery()["full_population_complete"] is False)

# Command selection is tested through execute_cell, but Popen and final-envelope
# reads are mocked; no child process or pool is started.
for index, (original, *_rest) in enumerate(fixtures):
    cell = dict(original, output_dir=str(OUT / f"unstarted_{index}"))
    fake = type("ExitedProcess", (), {"pid": 12345, "returncode": 0, "poll": lambda self: 0})()
    with patch.object(pool.subprocess, "Popen", return_value=fake) as popen, \
         patch.object(pool, "check_result_envelope", return_value={"full_population_complete": False}):
        record = pool.execute_cell(cell, OUT / f"command_record_{index}", 0, threading.Event())
    check(f"command_uses_exact_runner_{index}", record["status"] == "COMPLETE"
          and Path(popen.call_args.args[0][1]) == Path(original["runner_path"]).resolve())
partial = OUT / "partial_evidence"
partial.mkdir()
(partial / "native.csv").write_text("preserve this failed attempt", encoding="utf-8")
with patch.object(pool.subprocess, "Popen", side_effect=AssertionError("dispatch forbidden")) as launch:
    record = pool.execute_cell(dict(fixtures[1][0], output_dir=str(partial)), OUT / "partial_record", 0, threading.Event())
check("partial_native_evidence_never_restarted", record["status"] == "FAILED" and launch.call_count == 0)

# Preserve exact original stage dimensions and show that the replacement ID is
# a single coordinate replacement, not an extra experiment.
registered = pool.read(ROOT / "outputs/evidence/paper_suite_20260907/frozen_plan_v4/plan.json")
mixed = copy.deepcopy(registered)
old_ids = {f"b_{map_name}_1x_v2p5_s104729_q00_dh" for map_name in ("map2", "nanning")}
old_ids.add("b_map2_2x_v2p5_s104729_q00_dh")
for c in mixed["cells"]:
    if c["method"] == pool.DH and c["cell_id"] not in old_ids:
        c.update(runner_path=dh_new.__file__, runner_sha256=pool.sha(Path(dh_new.__file__)))
    if c["cell_id"] == "b_nanning_2x_v2p5_s104729_q00_dh":
        c["cell_id"] += "_postprocess_v2"
        c["output_dir"] = str(Path(mixed["result_root"]) / c["cell_id"])
mixed_path = OUT / "synthetic_mixed_plan.json"
pool.write(mixed_path, mixed)
loaded = pool.load_plan(mixed_path)
base, fault = master.stage_cells(loaded)
check("mixed_plan_keeps_1760_unique_coordinates_and_16_8_stages", (len(loaded["cells"]), len(base), len(fault)) == (1760, 16, 8))
check("mixed_plan_exactly_three_DH_old_parser_bindings", sum(c["method"] == pool.DH and Path(c["runner_path"]) == Path(dh_old.__file__)
      for c in loaded["cells"]) == 3)
check("phase1_includes_single_replacement", sum(c["cell_id"].endswith("_postprocess_v2") for c in base) == 1)
bad = copy.deepcopy(mixed)
dup = copy.deepcopy(next(c for c in bad["cells"] if c["cell_id"].endswith("_postprocess_v2")))
dup["cell_id"] = "duplicate_coordinate"
dup["output_dir"] = str(Path(bad["result_root"]) / dup["cell_id"])
bad["cells"].append(dup)
bad_path = OUT / "bad_duplicate.json"
pool.write(bad_path, bad)
reject("replacement_cannot_duplicate_coordinate", lambda: pool.load_plan(bad_path))
bad = copy.deepcopy(mixed)
bad["cells"][0]["output_dir"] = str(Path(bad["result_root"]) / "foreign_id")
bad_path = OUT / "bad_output.json"
pool.write(bad_path, bad)
reject("output_layout_guard_unchanged", lambda: pool.load_plan(bad_path))


def phase_control(fail_stage=None, fail_normal2=False):
    c = master.Campaign.__new__(master.Campaign)
    c.root = OUT / ("phase_" + uuid.uuid4().hex[:8])
    c.token, c.run_id = uuid.uuid4().hex, "synthetic_qa"
    c.directory, c.lock = c.root / "master", c.root / "master.lock"
    c.plan, c.base, c.fault = loaded, base, fault
    c.status = {"status": "STARTING", "phase": "synthetic_qa", "phases": [], "prerequisites": []}
    calls = []
    c.unchanged = lambda: None
    c.report = lambda: calls.append("report")
    def wait_for(name, probe):
        calls.append(name)
        if fail_normal2 and name == "phase3_wait_normal_full_2x":
            raise ValueError("SYNTHETIC QA: failed normal-2x prerequisite")
        return {"status": "PASS", "name": name}
    c.wait_for = wait_for
    def mock_pool(plan, cells, **kwargs):
        calls.append((len(cells), kwargs))
        failed = len(cells) == fail_stage
        return {"status": "FAILED" if failed else "COMPLETE", "accepted_count": len(cells) - int(failed)}
    with patch.object(master, "prerequisites", return_value=[{"name": "synthetic"}]), \
         patch.object(pool, "run_plan", side_effect=mock_pool), \
         patch.object(pool.subprocess, "Popen", side_effect=AssertionError("native launch forbidden")):
        result = c.run()
    return result, calls


for stage, expected in ((16, [16]), (8, [16, 8]), (1760, [16, 8, 1760]), (None, [16, 8, 1760])):
    result, calls = phase_control(stage)
    dispatched = [v[0] for v in calls if isinstance(v, tuple)]
    check(f"stage_control_failure_at_{stage}", dispatched == expected
          and result["status"] == ("COMPLETE" if stage is None else "FAILED")
          and calls[-1] == "report")
    check(f"stage_pool_contract_at_{stage}", all(v[1] == dict(workers=4, timeout_seconds=0, keep_going=False)
          for v in calls if isinstance(v, tuple)))
result, calls = phase_control(fail_normal2=True)
check("normal_2x_gate_blocks_full_stage", result["status"] == "FAILED"
      and [v[0] for v in calls if isinstance(v, tuple)] == [16, 8])
from scripts.eval import run_feng_paper_suite_campaign as original_master
check("original_initial_pool_and_normal_controls_unchanged", all(getattr(master, key) == getattr(original_master, key)
      for key in ("EXISTING_POOL", "NORMAL1", "NORMAL2", "MICRO14", "CPP4", "TARAU8", "FAULT4", "BINARY_SHA")))
check("new_master_imports_only_v2_pool", master.pool is pool)
final_plan = pool.load_plan(master.PLAN)
check("master_bound_to_final_V5_bytes", final_plan["_sha256"] == master.PLAN_SHA
      == "00a95b47298fb1aac808bec9275f6d9b3c28d340859017c0667e39ff736b9719")
final_base, final_fault = master.stage_cells(final_plan)
check("actual_V5_stage_dimensions", [len(final_base), len(final_fault), len(final_plan["cells"])] == [16, 8, 1760])
actual_dh = [c for c in final_plan["cells"] if c["method"] == pool.DH]
check("actual_V5_three_old_and_117_new_DH", len(actual_dh) == 120
      and sum(Path(c["runner_path"]) == Path(dh_old.__file__) for c in actual_dh) == 3
      and sum(Path(c["runner_path"]) == Path(dh_new.__file__) for c in actual_dh) == 117)
actual_recovery = [c for c in actual_dh if "native_recovery_from" in pool.read(Path(c["spec_path"]))]
check("actual_V5_single_recovery_coordinate", len(actual_recovery) == 1
      and actual_recovery[0]["cell_id"] == "b_nanning_2x_v2p5_s104729_q00_dh_postprocess_v2"
      and actual_recovery[0] in final_base)
check("original_frozen_sources_unchanged", all(pool.sha(ROOT / name) == expected for name, expected in ORIGINALS.items()))
result = dict(status="PASS", label="SYNTHETIC QA", check_count=len(CHECKS), checks=CHECKS,
              native_simulations_invoked=0, real_pools_started=0, process_dispatch="mocked",
              actual_DH_normalizer_and_archive_verification=True,
              source_files={str(Path(m.__file__).relative_to(ROOT)): pool.sha(Path(m.__file__))
                            for m in (pool, master, dh_old, dh_new, recovery_helper)}, original_source_hashes=ORIGINALS,
              recovery_QA_scope="Original-source helper validation mocked; copied-byte and recovery provenance guards exercised directly.",
              actual_plan_path=str(master.PLAN), actual_plan_sha256=final_plan["_sha256"],
              fixture_directory=str(OUT), scope="Parser selection and orchestration only; no new scientific observations.")
pool.write(OUT / "verification.json", result)
print(json.dumps(dict(status=result["status"], check_count=result["check_count"], output=str(OUT / "verification.json"))))
