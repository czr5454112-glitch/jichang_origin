"""Freeze a finite replay proposal and sources; no native execution or imports.

This is a design package, not a ready execution gate. The eventual worker and
independent verifier must join a new complete source freeze before launch.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

from . import regional_path_pool
# Freeze the actual loaded closure of the proposed reconstruction components.
# Importing these modules does not load a native extension or create a session.
from . import reconstruct_native_tape, validate_resume_full_day, native_host

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
BINARY_SHA = "c7eab9d81e3e930a3e7f2f3a320b4c92b1c1c2e5a0c07db9c4050b536d821943"


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def gzread(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream: return json.load(stream)
def write(path, value): Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = BASE / "full_stream_native024_001/full1x"
    build_path = BASE / "native026_build_001/receipt.json"
    acceptance_path = BASE / "native026_acceptance_001/receipt.json"
    build = read(build_path);acceptance = read(acceptance_path)
    assert build["status"] == "build_passed_tests_held" and build["source_changed"] == []
    assert acceptance["status"] == "passed" and acceptance["source_changed"] == [] and acceptance["input_changed"] == []
    binary = ROOT / "build_lt_session_026/python/czr005_circulation.cp311-win_amd64.pyd"
    assert build["binary_sha256"][str(binary)] == sha(binary) == BINARY_SHA
    compiled = {str(build_path.parent / "source" / name): digest for name, digest in build["source_before"].items()}
    assert all(sha(path) == digest for path, digest in compiled.items())
    policy_names = ("event_protocol_control.py", "protocol_control.py", "analytic_control.py", "regional_control.py", "native_host.py")
    producer = read(source / "receipt.json")
    for name in policy_names:
        relative = Path("scripts/experiments/g31_ics_circulation") / name
        assert sha(ROOT / relative) == producer["source_before"][str(relative)]
    # This cut covers the earlier measured 11980/12131 spike neighbourhood.
    # It is selected for diagnostic relevance, not after observing cache speed.
    paths = [source / "segments" / f"{index:04d}.json.gz" for index in range(12)]
    cut = gzread(paths[9]);following = [gzread(path) for path in paths[10:]]
    assert all(len(part["control_records"]) == 500 for part in following)
    assert cut["native_state_sha256"] == "e245cd4e5345a6838ac0914e512bf550558210131237b3d3d6d83d1a8829f8ef"
    args.output.mkdir(parents=True, exist_ok=False)
    sources = {Path(module.__file__).resolve() for module in list(sys.modules.values())
        if getattr(module, "__file__", None) and Path(module.__file__).suffix == ".py" and
        Path(module.__file__).resolve().is_relative_to(ROOT)}
    sources.update(ROOT / name for name in ("tests/test_g31_circulation_regional_path_pool.py",
        "scripts/experiments/g31_ics_circulation/benchmark_regional_path_pool.py"))
    frozen = {}
    for path in sorted(sources):
        relative = path.relative_to(ROOT);target = args.output / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True);shutil.copyfile(path, target)
        frozen[str(relative)] = sha(path)
    evidence = [source / "input.json.gz", source / "receipt.json", build_path, acceptance_path,
        BASE / "regional_path_pool_pure_004.xml", BASE / "regional_path_pool_micro_002/receipt.json",
        BASE / "regional_path_pool_micro_003/receipt.json", *paths]
    plan = dict(schema="g31.regional_path_pool.replay_proposal.v1", status="prepared_not_executable",
        native_calls=0, driver_and_independent_verifier_pending=True, output=str(args.output.resolve()),
        source_sha256=frozen, compiled_archive_sha256=compiled,
        pins={str(path): sha(path) for path in evidence}, binary=str(binary), binary_sha256=BINARY_SHA,
        original_offered_jobs=28506, original_input_sha256=sha(source / "input.json.gz"),
        source=str(source), cut=9, known_entry_native_seal=cut["native_state_sha256"],
        entry_physical_time=cut["control_continuation"]["physical_time"],
        controller_config=cut["controller_state"]["config"],
        continuation=[dict(index=index, activations=500,
            requested_horizon=part["control_continuation"]["requested_horizon"],
            expected_physical_time=part["control_continuation"]["physical_time"],
            original_exit_native_seal=part["native_state_sha256"]) for index, part in zip((10, 11), following)],
        total_activations_per_arm=1000, arms=["original", "regional_path_pool"],
        limits=dict(native_workers=1, native_parent_hard_timeout_seconds=600,
            max_graphs=4, max_paths_per_graph=256, event_budget=1000000),
        reconstruction="Replay original input and all ten saved prefix shards, finish with exact actual native024 seal, then checkpoint; never restore native from JSON.",
        per_arm="Restore same verified checkpoint and copied exact controller state. Fresh pool only in candidate arm. Two identical 500-owner shard boundaries; preserve pending owner round/mandatory drain.",
        equality=["original native entry seal", "each original exit seal", "all ordered control records apart from declared measured clock fields",
            "ordered client calls/payloads/ACKs", "ordered native notification batches", "controller state", "ordered returned public API values",
            "initial/final full, compact, policy and recent public views", "no source/input/binary changes"],
        accounting="Keep whole initialization/reconstruction/checkpoint/restore/arm/output wall and CPU separately and in process total. Charge all key/lookup/GC/serialization cost; do not subtract native physics or GC. Preserve per-activation outer/inner samples and pool counters without converting them into per-business latency.",
        tracing="Fresh per-arm explicit-capability native proxy, including policy_recent; ordered raw API responses streamed synchronously, its overhead included equally. No retained cross-shard diagnostic graph; preserve every raw row. GC callbacks record capture envelopes and owner context, never disable/force GC.",
        failure="Timeout, exception, source mismatch, any missing/tampered tape or semantic/seal mismatch fails closed and retains both arms/prefix. A slowdown is retained, not relabeled success.",
        expansion="No automatic 2500-owner or whole-flow run. A later expanded domain requires a new predeclared package.",
        complete_business_100ms_certified=False,
        limits_of_evidence="Pure saved-view scenarios are not actual flow hit rates. Existing owner roots remain proxy scopes; no new production business admission or denominator is established.")
    write(args.output / "plan.json", plan)
    write(args.output / "receipt.json", dict(status=plan["status"], native_calls=0,
        plan_sha256=sha(args.output / "plan.json"), source_count=len(frozen), compiled_source_count=len(compiled)))
    print(json.dumps(read(args.output / "receipt.json")))


if __name__ == "__main__": main()
