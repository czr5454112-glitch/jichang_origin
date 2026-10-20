"""Actual known-seal reconstruction plus unchanged saved-shard continuation.

Conformance fixtures use existing sealed prefixes, not fabricated heartbeat
proofs. The actual full-run cut uses resume_full_day's separate strict prepare.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

from . import resume_full_day as resume

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
TIMING_KEYS = frozenset({"wall_seconds", "wall_ms", "cpu_ms", "compute_wall_ms", "compute_cpu_ms",
                         "native_event_ms", "runtime_seconds", "diagnostic_seal_wall_ms"})


def semantic(value, path=()):
    if isinstance(value, dict):
        return {key: semantic(item, (*path, key)) for key, item in value.items()
                if key not in TIMING_KEYS and not (key == "submit_compute_ms" and
                    len(path) == 2 and path[0] == "client_calls" and type(path[1]) is int)}
    if isinstance(value, (list, tuple)):
        return [semantic(item, (*path, index)) for index, item in enumerate(value)]
    return value


def encoded(value):
    return json.dumps(semantic(value), ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def case(args, name, source, minimum_owners):
    output = args.output / name
    output.mkdir()
    receipt = json.loads((source / "receipt.json").read_bytes())
    resume.require(not receipt.get("source_changed") and receipt["binary_sha256"] == args.expected_binary_sha256,
                   "gate_source_not_frozen")
    resume.validate_policy_sources(source, receipt)
    command = receipt["command"]
    all_paths = sorted((source / "segments").glob("*.json.gz"))
    paths, total, cut_index, cumulative = [], 0, None, []
    for path in all_paths:
        part = resume.read_gz(path)
        paths.append(path)
        total += len(part["control_records"])
        cumulative.append(total)
        if cut_index is None and part["status"] == "control_budget_exhausted" and (
                part["controller_state"]["pending_owners"] or part["controller_state"]["needs_native_drain"]):
            cut_index = len(paths) - 1
        if minimum_owners and total >= minimum_owners and cut_index is not None and len(paths) > cut_index + 1:
            break
    resume.require(cut_index is not None and cut_index < len(paths) - 1, "gate_missing_pending_round_cut")
    before = {str(path): resume.sha(path) for path in paths}
    cut_part = resume.read_gz(paths[cut_index])
    prefix = paths[:cut_index + 1]
    prior_wall = sum(resume.read_gz(path)["wall_seconds"] for path in prefix)
    cut = {"source_directory": str(source), "source_cut": cut_index, "binary": str(args.binary.resolve()),
        "event_budget": int(resume.option(command, "--event-budget", "100000")),
        "offered_total": len(resume.read_gz(source / "input.json.gz")["jobs"]),
        "shards": [{"path": str(path.relative_to(source)).replace("\\", "/"), "sha256": before[str(path)]} for path in prefix],
        "known_native_seal": cut_part["native_state_sha256"], "owner_activations": cumulative[cut_index],
        "physical_time": cut_part["control_continuation"]["physical_time"],
        "prior_costs": {"controller_wall_seconds": prior_wall},
        "controller_config": cut_part["controller_state"]["config"]}
    resume.dump(output / "conformance_cut_fixture.json", {**cut,
        "scope": "Authentic saved sealed raw prefix; derived conformance metadata only. Does not purport to be original heartbeat or original outer-wall timing."})
    rebuilt = output / "reconstructed"
    rebuilt.mkdir()
    started = time.perf_counter()
    session, restored, segments, reconstruction, data = resume.reconstruct(cut, rebuilt)
    resume.require(restored == cut_part, "gate_controller_cut_changed")
    state = restored["controller_state"]
    owner_config = dict(state["config"])
    owners = owner_config.pop("owners")
    offset, activated = reconstruction["trace_records"], reconstruction["owners"]
    actuals = output / "actual_continuations"; actuals.mkdir()
    transitions = []
    maximum = int(resume.option(command, "--max-activations"))
    shard_budget = int(resume.option(command, "--activation-shard-budget"))
    horizon = float(resume.option(command, "--horizon"))
    segment_seconds = float(resume.option(command, "--segment-seconds", "3600"))
    target = resume.next_target(restored, horizon, segment_seconds)
    restored = None
    for index in range(cut_index + 1, len(paths)):
        expected = resume.read_gz(paths[index])
        resume.require(target == expected["control_continuation"]["requested_horizon"], "gate_target_changed")
        actual = resume.run_event_protocol_control(session, owners, horizon=target,
            event_budget=cut["event_budget"], max_activations=min(shard_budget, maximum - activated),
            state=state, _consume_state=True, **owner_config)
        actual["native_state_sha256"] = session.offline_state_sha256()
        for key in ("control_records", "native_batches"):
            for row in actual[key]: row["trace_sequence"] += offset
        offset += len(actual["control_records"]) + len(actual["native_batches"])
        activated += len(actual["control_records"])
        state = actual["controller_state"]
        resume.streaming.gz(actuals / f"{index:04d}.json.gz", actual, compresslevel=1)
        a, b = encoded(actual), encoded(expected)
        resume.require(a == b, "gate_ordered_raw_continuation_mismatch:" + name + ":" + str(index))
        transitions.append({"shard": index, "target": target, "status": actual["status"],
            "physical_time": session.physical_time, "ordered_semantic_sha256": hashlib.sha256(a.encode()).hexdigest(),
            "native_state_sha256": actual["native_state_sha256"], "owner_activations": len(actual["control_records"])})
        if actual["status"] == "reached": target = min(target + segment_seconds, horizon)
        actual = expected = None
    final_seal = session.offline_state_sha256()
    resume.require(final_seal == resume.read_gz(paths[-1])["native_state_sha256"], "gate_final_seal_mismatch")
    del session, state
    wrong_seal_rejected = None
    if name == "synthetic":
        bad = dict(cut, known_native_seal="0" * 64)
        bad_output = output / "wrong_seal_rejected"; bad_output.mkdir()
        try:
            resume.reconstruct(bad, bad_output)
        except ValueError as error:
            resume.require("native_seal_mismatch" in str(error), "gate_unexpected_negative_failure")
            wrong_seal_rejected = str(error)
        else:
            raise ValueError("gate_unverified_session_escaped")
    changed = [path for path, digest in before.items() if resume.sha(path) != digest]
    resume.require(not changed and resume.sha(args.binary) == args.expected_binary_sha256, "gate_sources_changed")
    return {"status": "passed", "source": str(source), "source_shards": before, "cut_index": cut_index,
        "cut_had_pending_owners": bool(cut_part["controller_state"]["pending_owners"]),
        "cut_required_native_drain": cut_part["controller_state"]["needs_native_drain"],
        "cut_reconstruction": reconstruction, "continuations": transitions, "source_owner_updates_total": total,
        "continued_owner_updates": activated - cumulative[cut_index], "physical_time": transitions[-1]["physical_time"],
        "final_native_state_sha256": final_seal, "wrong_native_seal_rejected": wrong_seal_rejected,
        "wall_seconds": time.perf_counter() - started, "ordered_raw_semantics_exact": True}


def worker(args):
    resume.require(resume.sha(args.binary) == args.expected_binary_sha256, "gate_binary_changed")
    cases = {}
    for name, source, minimum in (("synthetic", BASE / "stream_driver_native024_001/synthetic-optimized", 0),
        ("full1x_prefix", BASE / "full_stream_native024_001/full1x", 5000)):
        cases[name] = case(args, name, source, minimum)
        resume.dump(args.output / "cases.json", cases)
    resume.dump(args.output / "assessment.json", {"status": "passed", "cases": cases,
        "scope": "Native024 exact source-seal reconstruction plus unchanged future controller tape. Timing fields alone excluded; all other ordered raw fields, calls, state, boundaries/results and actual native seals exact. No full-day or request100ms claim."})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--expected-binary-sha256", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--hard-timeout", type=float, default=180.)
    p.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.worker:
        try: worker(args)
        except Exception:
            (args.output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
        return 0
    args.output.mkdir(parents=True, exist_ok=False)
    sources = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m, "__file__", None)
        and str(m.__file__).endswith(".py") and Path(m.__file__).resolve().is_relative_to(ROOT)})
    before = {str(path): resume.sha(path) for path in sources}
    for path in sources:
        target = args.output / "source_archive" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(path.read_bytes())
    command = [sys.executable, "-m", __spec__.name, *sys.argv[1:], "--worker"]
    started = time.perf_counter()
    with (args.output / "stdout.log").open("w", encoding="utf-8") as out, (args.output / "stderr.log").open("w", encoding="utf-8") as err:
        try:
            process = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, timeout=args.hard_timeout, check=False)
            status, code = ("passed" if process.returncode == 0 else "failed"), process.returncode
        except subprocess.TimeoutExpired:
            status, code = "hard_timeout_unknown", None
    changed = [path for path, digest in before.items() if resume.sha(path) != digest]
    if changed: status = "source_changed"
    receipt = {"schema": "g31.verified_resume_conformance.v1", "status": status, "exit_code": code,
        "source_before": before, "source_changed": changed, "binary_sha256": resume.sha(args.binary),
        "command": command, "wall_seconds": time.perf_counter() - started, "maximum_native_workers": 1}
    resume.dump(args.output / "receipt.json", receipt)
    print(json.dumps({key: receipt[key] for key in ("status", "exit_code", "wall_seconds", "source_changed")}))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
