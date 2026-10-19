"""Native026 gate against original saved native024 seals and same-binary optout.

This is offline API reconstruction, not JSON native restoration. It retains all
raw continuation records, requires the original entry seal before continuing,
and does not promote partial full-day producer receipts to completed outcomes.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback

from .native_host import load_native, tiny_cycle
from .event_protocol_control import run_event_protocol_control
from .reconstruct_native_tape import NativeTapeReconstructor
from .validate_resume_full_day import semantic

ROOT = Path(__file__).resolve().parents[3]
POLICY = ("event_protocol_control.py", "protocol_control.py", "analytic_control.py", "regional_control.py", "native_host.py")
OLD_BINARY_SHA = "b024724e3bf0a8e4232eaeb13d99ab6a42018e85e4166acf9081991510ca311b"
NEW_BINARY_SHA = "c7eab9d81e3e930a3e7f2f3a320b4c92b1c1c2e5a0c07db9c4050b536d821943"


def require(ok, reason):
    if not ok: raise ValueError("delivery_index_gate:" + reason)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def write(path, value): Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
def gzread(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream: return json.load(stream)
def gzwrite(path, value):
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=1) as stream: json.dump(value, stream, ensure_ascii=False, allow_nan=False)
def ordered(value): return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def imported_sources():
    return sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
        if getattr(module, "__file__", None) and Path(module.__file__).suffix == ".py" and
        Path(module.__file__).resolve().is_relative_to(ROOT)})


def validate_build(build, expected_binary_sha):
    require(build.get("status") == "build_passed_tests_held" and not build.get("source_changed") and
            bool(build.get("commands")) and all(row.get("exit_code") == 0 for row in build["commands"]), "build_not_successful")
    binaries = [Path(p) for p in build["binary_sha256"] if p.endswith(".pyd")]
    require(len(binaries) == 1 and build["binary_sha256"][str(binaries[0])] == expected_binary_sha,
            "intended_build_identity_required")
    require(re.fullmatch(r"[0-9a-f]{64}", expected_binary_sha) is not None and
            sha(binaries[0]) == expected_binary_sha, "binary_changed")
    return binaries[0]


def verify_import_closure(plan):
    actual = {str(path): sha(path) for path in imported_sources()}
    require(actual == plan["source_before"], "runtime_source_closure_changed")


def contract_views(session, owners, identities=()):
    return {owner: {"full": session.observe_protocol(owner),
        "compact": session.observe_protocol_control(owner),
        "policy": session.observe_protocol_control_policy(owner),
        "recent": {str(period): session.observe_protocol_control_policy_recent(owner, period) for period in (.01, 1., 120., 1000.)},
        "demand_signature": session.protocol_demand_signature(owner),
        "commands": [session.protocol_command(owner, identity) for identity in identities if f":{owner}:" in identity]}
        for owner in owners}


def short_worker(args):
    native = load_native(args.binary)
    records = []
    for fault in ({}, {"drop_ack_packets": 1, "duplicate_acks": True, "duplicate_ack_delay": .001},
                  {"owner_outages": [{"owner": "B", "start": .05, "end": .8}]}):
        data = tiny_cycle();data["transfers"] = []
        data["jobs"] = [dict(data["jobs"][0], load_seconds=30., allow_suffix_reroute=True)]
        next(row for row in data["node_contracts"] if row["node"] == 1)["resource_owner"] = "B"
        data["owner_protocol"] = dict(enabled=True, timeout=.4, ack_delay=.02, **fault)
        data["owner_notifications"] = {"enabled": True}
        session = native.NativeSession(data);session.advance_to(0.)
        payloads = [dict(request_id="live:1:A:old", owner_id="A", kind="demand", target_owner="B", publication_delay=2.),
            dict(request_id="live:1:A:f0", owner_id="A", kind="service_forecast", target_owner="B", tray_id="T0", next=1),
            dict(request_id="live:1:A:new", owner_id="A", kind="demand", target_owner="B"),
            dict(request_id="live:1:A:f1", owner_id="A", kind="service_forecast", target_owner="B", tray_id="T0", next=1),
            dict(request_id="live:1:A:w", owner_id="A", kind="withdraw_service_forecast", forecast_request_id="live:1:A:f0")]
        tape = []
        for index, payload in enumerate(payloads):
            tape.append(session.submit_protocol_command(payload));session.advance_to(.1*(index+1))
            tape.append(contract_views(session, ("A", "B"), [p["request_id"] for p in payloads[:index+1]]))
        checkpoint = session.checkpoint()
        for pass_index in range(2):
            if pass_index: session.restore(checkpoint)
            for payload in payloads: tape.append(session.submit_protocol_command(payload))
            session.advance_to(2.2)
            tape.append(contract_views(session, ("A", "B"), [p["request_id"] for p in payloads]))
            tape.append({"native_state_sha256": session.offline_state_sha256()})
        records.append({"input": data, "tape": tape})
    gzwrite(args.output / "short.json.gz", records)


def late_worker(args):
    plan = read(args.output / "plan.json")
    for path, digest in plan["pins"].items(): require(sha(path) == digest, "pinned_input_changed:"+path)
    session = load_native(args.binary).NativeSession(gzread(args.source / "input.json.gz"))
    replay = NativeTapeReconstructor(session, event_budget=plan["event_budget"])
    started = time.perf_counter()
    part = None
    for index in range(args.cut+1):
        part = gzread(args.source / "segments" / f"{index:04d}.json.gz")
        report = replay.replay_part(part)
        write(args.output / "heartbeat.json", {**report, "shard": index, "stage": "reconstructing"})
    report = replay.finish(plan["known_native_seal"])
    session = replay.verified_session()
    report["wall_seconds"] = time.perf_counter()-started
    write(args.output / "reconstruction.json", report)
    require(part["controller_state"]["config"] == plan["controller_config"], "cut_config_changed")
    # Full native checkpoint is taken only after the original entry seal passes.
    checkpoint = session.checkpoint()
    offset = replay.next_trace
    del replay
    expected = gzread(args.source / "segments" / f"{args.cut+1:04d}.json.gz")
    config = dict(part["controller_state"]["config"]);owners = config.pop("owners")
    initial = part["controller_state"];part = None
    before = contract_views(session, owners)
    session._set_indexed_message_selection(False)
    require(ordered(before) == ordered(contract_views(session, owners)), "late_entry_public_order_mismatch")
    gzwrite(args.output / "entry_views.json.gz", before);del before
    arms = []
    for enabled in (False, True):
        session.restore(checkpoint);session._set_indexed_message_selection(enabled)
        state = copy.deepcopy(initial)
        started = time.perf_counter()
        actual = run_event_protocol_control(session, owners,
            horizon=expected["control_continuation"]["requested_horizon"],
            max_activations=len(expected["control_records"]), event_budget=plan["event_budget"],
            state=state, _consume_state=True, **config)
        elapsed = time.perf_counter()-started
        for field in ("control_records", "native_batches"):
            for row in actual[field]: row["trace_sequence"] += offset
        seal = session.offline_state_sha256()
        # The old sparse run did not seal every raw shard. Never invent one.
        if "native_state_sha256" in expected: actual["native_state_sha256"] = seal
        label = "indexed" if enabled else "reference"
        gzwrite(args.output / (label+".json.gz"), actual)
        a, b = ordered(semantic(actual)), ordered(semantic(expected))
        require(a == b, label+"_ordered_saved_next_shard_mismatch")
        views = contract_views(session, owners)
        gzwrite(args.output / (label+"_views.json.gz"), views)
        arms.append({"name": label, "controller_wall_seconds": elapsed,
            "ordered_semantic_sha256": hashlib.sha256(a.encode()).hexdigest(),
            "views_sha256": hashlib.sha256(ordered(views).encode()).hexdigest(),
            "native_state_sha256": seal, "owner_activations": len(actual["control_records"]),
            "physical_time": session.physical_time})
        write(args.output / "arms.json", arms)
        del actual, state, a, b, views
    require(all(arms[0][key] == arms[1][key] for key in ("ordered_semantic_sha256", "views_sha256", "native_state_sha256", "physical_time", "owner_activations")), "late_arm_mismatch")
    write(args.output / "assessment.json", {"status": "passed", "known_entry_native_seal": plan["known_native_seal"],
        "entry_seal_verified_against_original_native024": True, "ordered_saved_continuation_exact": True,
        "original_exit_seal_available": "native_state_sha256" in expected,
        "reference_indexed_exit_seals_exact": True, "arms": arms,
        "complete_full_day_certified": False, "complete_100ms_certified": False,
        "timing_scope": "One serial pair after verified offline reconstruction; controller windows include all controller work. No isolated/full-day/100ms claim."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "output", "binary", "old_build", "new_build"):
        parser.add_argument("--"+name.replace("_", "-"), type=Path, required=True)
    parser.add_argument("--cut", type=int, required=True)
    parser.add_argument("--event-budget", type=int, default=1000000)
    parser.add_argument("--hard-timeout", type=float, default=1200.)
    parser.add_argument("--worker", choices=("short", "late"))
    args = parser.parse_args()
    args.output=args.output.resolve();args.source=args.source.resolve();args.binary=args.binary.resolve()
    if args.worker:
        try:
            plan=read(args.output / "plan.json");verify_import_closure(plan)
            (short_worker if args.worker == "short" else late_worker)(args)
            verify_import_closure(plan)
        except Exception:
            (args.output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
        return 0
    require(args.cut >= 0 and args.event_budget > 0 and 0 < args.hard_timeout <= 1800, "invalid_bounds")
    args.output.mkdir(parents=True, exist_ok=False)
    cut = gzread(args.source / "segments" / f"{args.cut:04d}.json.gz")
    require(cut["status"] == "reached" and cut["controller_state"]["native_timestamp_complete"] is True and
        isinstance(cut.get("native_state_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}",cut["native_state_sha256"]), "sealed_complete_cut_required")
    producer = read(args.source / "receipt.json")
    require(producer["binary_sha256"] == "030e4e116cd0ced9e4acc6a00ba5e111cbd5d2a48f14b62e9f2539f1e6a7710c", "original_native024_required")
    for name in POLICY:
        matches = [path for path in producer["source_before"] if Path(path).name == name]
        require(len(matches) == 1 and sha(ROOT / matches[0]) == producer["source_before"][matches[0]], "original_policy_changed:"+name)
    for relative, digest in producer["source_before"].items():
        path=Path(relative)
        require(not path.is_absolute() and ".." not in path.parts and
            sha(ROOT/path) == digest == sha(args.source/"source_archive"/path), "original_archived_source_changed:"+relative)
    paths = [args.source / "input.json.gz", args.source / "receipt.json", args.old_build.resolve(), args.new_build.resolve(),
        *[args.source / "segments" / f"{i:04d}.json.gz" for i in range(args.cut+2)]]
    sources = imported_sources()
    source_before = {str(path): sha(path) for path in sources}
    archive = args.output / "source_archive";archive.mkdir()
    for path in sources:
        target=archive/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    builds = []
    for path, digest in ((args.old_build,OLD_BINARY_SHA), (args.new_build,NEW_BINARY_SHA)):
        build = read(path);binary=validate_build(build,digest)
        for relative, digest in build["source_before"].items(): require(sha(path.parent / "source" / relative) == digest, "compiled_archive_changed")
        builds.append(binary);paths.append(binary)
    require(args.binary == builds[1].resolve(), "candidate_binary_mismatch")
    plan = {"schema": "g31.native_delivery_index_gate.v1", "cut": args.cut, "known_native_seal": cut["native_state_sha256"],
        "event_budget": args.event_budget, "controller_config": cut["controller_state"]["config"],
        "pins": {str(path.resolve()): sha(path) for path in paths}, "source_before": source_before,
        "original_producer_completion": "not claimed; only immutable sealed prefix is used", "native_worker_limit": 1}
    write(args.output / "plan.json", plan);cut=None
    started = time.perf_counter();receipt={"status":"running", "arms":[], "source_before":source_before}
    write(args.output / "receipt.json", receipt)
    try:
        for label, binary, kind in (("old",builds[0],"short"),("new",builds[1],"short"),("late",builds[1],"late")):
            folder=args.output / label;folder.mkdir();write(folder / "plan.json",plan)
            command=[sys.executable,"-m",__spec__.name,"--worker",kind,"--source",str(args.source),"--output",str(folder),
                "--binary",str(binary),"--old-build",str(args.old_build),"--new-build",str(args.new_build),"--cut",str(args.cut)]
            with (folder/"stdout.log").open("wb") as out, (folder/"stderr.log").open("wb") as err:
                result=subprocess.run(command,cwd=ROOT,stdout=out,stderr=err,timeout=args.hard_timeout if kind=="late" else 60.)
            receipt["arms"].append({"label":label,"command":command,"exit_code":result.returncode})
            write(args.output/"receipt.json",receipt);require(result.returncode == 0,label+"_worker_failed")
            if label == "new": require(ordered(gzread(args.output/"old/short.json.gz")) == ordered(gzread(folder/"short.json.gz")), "ordered_cross_binary_contract_mismatch")
        receipt["status"]="passed"
    except Exception as error: receipt.update(status="failed",error=repr(error))
    receipt["source_changed"]=[path for path,digest in source_before.items() if sha(path)!=digest]
    receipt["input_changed"]=[path for path,digest in plan["pins"].items() if sha(path)!=digest]
    if receipt["source_changed"] or receipt["input_changed"]:receipt["status"]="invalidated_identity_changed"
    receipt["wall_seconds"]=time.perf_counter()-started;write(args.output/"receipt.json",receipt);print(json.dumps(receipt))
    return int(receipt["status"]!="passed")


if __name__ == "__main__": raise SystemExit(main())
