"""Short serial-process native021/022 parity evidence, never a latency claim."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import time

from .capture_native_request_timing import capture_session
from .event_protocol_control import run_event_protocol_control
from .native_host import load_native
from .native_request_timing import analyze_native_timing
from .profile_request_bundles import semantics
from .validate_protocol_control import scenarios


ROOT = Path(__file__).absolute().parents[3]
SOURCES = ("verify_native_timing_parity.py", "capture_native_request_timing.py", "native_request_timing.py",
    "event_protocol_control.py", "protocol_control.py", "analytic_control.py", "regional_control.py",
    "native_host.py", "profile_request_bundles.py", "validate_protocol_control.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def save_gz(path, value):
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(value, stream, allow_nan=False)


def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def stable(value):
    if isinstance(value, dict):
        return {key: stable(child) for key, child in value.items() if key != "wall_seconds"}
    if isinstance(value, list):
        return [stable(child) for child in value]
    return value


def ordered_digest(value):
    return hashlib.sha256(json.dumps(stable(semantics(value)), ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def worker(args):
    args.output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__).with_name(name) for name in SOURCES]
    identities = {str(p): sha(p) for p in paths}
    archive = args.output / "source"; archive.mkdir()
    for path in paths:
        (archive/path.name).write_bytes(path.read_bytes())
    build = json.loads(args.build_receipt.read_text(encoding="utf-8"))
    compiled = build["source_before"]
    changed = [name for name, expected in compiled.items() if sha(ROOT/name) != expected]
    if changed or sha(args.binary) != args.expected_binary_sha256:
        raise ValueError("native_timing_parity:initial_identity_mismatch:" + repr(changed))
    input_manifest = json.loads(args.profile_manifest.read_text(encoding="utf-8"))
    input_path = Path(input_manifest["input_profile"]) / "input.json.gz"
    original = read_gz(input_path)
    config = copy.deepcopy(input_manifest["config"])
    name, synthetic, owners = scenarios()[1]
    assert name == "lost_ack"
    cases = [("lost_ack", synthetic, owners, 20., 1000, 100,
              dict(control_period=.5, command_delay=.01, publication_delay=.02, retry_period=.5, lease_seconds=120.)),
             ("original1x_prefix", original, input_manifest["owners"], 86400., 500, 100, config)]
    native = load_native(args.binary)
    outputs = {}
    for namespace, (case, data, owners, horizon, budget, shard, config) in enumerate(cases, 1):
        data["owner_notifications"] = {"enabled": True}
        raw = native.NativeSession(data)
        session = capture_session(raw, capacity=1_000_000, session_identity=namespace) if args.timed else raw
        state, records, activations = None, [], 0
        started = time.perf_counter()
        while activations < budget:
            part = run_event_protocol_control(session, owners, horizon=horizon, event_budget=100000,
                max_activations=min(shard, budget-activations), state=state, **config)
            state = part["controller_state"]
            activations += len(part["control_records"])
            public = []
            for owner in owners:
                public.append({"owner": owner, "full": session.observe_protocol(owner),
                    "control": session.observe_protocol_control(owner),
                    "policy": session.observe_protocol_control_policy(owner),
                    "recent": session.observe_protocol_control_policy_recent(owner, config.get("forecast_validity", 120.)),
                    "demand": session.protocol_demand_signature(owner),
                    "planning": session.protocol_planning_snapshots(owner)})
            records.append({"part": part, "public_after_return": public,
                "state_seal": raw.offline_state_sha256(), "checkpoint_seal": raw.checkpoint().offline_state_sha256})
            if args.timed:
                session.take_completed()
            if part["status"] != "control_budget_exhausted":
                break
        elapsed = time.perf_counter()-started
        save_gz(args.output/(case+".json.gz"), records)
        report = None
        if args.timed:
            report = analyze_native_timing(session.batches, session.envelopes)
            save_gz(args.output/(case+"_native_timing.json.gz"), {"batches": session.batches, "envelopes": session.envelopes})
            write(args.output/(case+"_phase_report.json"), report)
            if report["status"] != "validated_partial_native_phase_partition":
                raise ValueError("native_timing_parity:invalid_timing:" + repr(report))
        outputs[case] = {"ordered_semantics_sha256": ordered_digest(records),
            "state_seal": raw.offline_state_sha256(), "checkpoint_seal": raw.checkpoint().offline_state_sha256,
            "owner_activations": activations, "parts": len(records), "status": records[-1]["part"]["status"],
            "native_boundaries": sum(len(r["part"]["native_batches"]) for r in records),
            "submissions": sum(len(r["part"]["client_calls"]) for r in records),
            "offered_total": len(data["jobs"]), "physical_time": raw.physical_time,
            "wall_seconds_diagnostic_only": elapsed, "phase_status": report["status"] if report else None}
    changed = [p for p, expected in identities.items() if sha(p) != expected]
    changed += [name for name, expected in compiled.items() if sha(ROOT/name) != expected]
    if sha(args.binary) != args.expected_binary_sha256:
        changed.append(str(args.binary))
    write(args.output/"receipt.json", {"schema": "g31.native_timing_parity_arm.v1", "status": "passed" if not changed else "invalidated",
        "binary": str(args.binary), "binary_sha256": sha(args.binary), "timing_enabled": args.timed,
        "source_sha256": identities, "compiled_source_count": len(compiled), "source_changed": changed,
        "input_sha256": sha(input_path), "cases": outputs,
        "performance_isolated": False, "complete_request_100ms_certified": False,
        "uncompiled_additions_excluded": [str(p.relative_to(ROOT)) for p in (ROOT/"cpp").rglob("*.hpp") if str(p.relative_to(ROOT)) not in compiled]})
    print(json.dumps(outputs, indent=2))
    return 0 if not changed else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--profile-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timed", action="store_true")
    return worker(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
