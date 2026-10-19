"""Serial native024/025 old-contract parity; no performance or v2 timing claim."""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from .native_host import load_native, tiny_cycle


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path, value): path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
def stable(value):
    if isinstance(value, dict): return {k: stable(v) for k, v in value.items() if k != "wall_seconds"}
    if isinstance(value, (list, tuple)): return [stable(v) for v in value]
    return value


def cases(native, timed):
    output = {}
    for name in ("protocol_disabled", "enabled_no_planning", "v1_delivered", "v1_lost_ack", "v1_expired"):
        data = tiny_cycle(); data["transfers"] = []
        data["owner_protocol"] = {"enabled": name != "protocol_disabled", "timeout": .2, "ack_delay": .03,
            "drop_ack_packets": 1 if name == "v1_lost_ack" else 0}
        data["owner_notifications"] = {"enabled": name != "protocol_disabled"}
        session = native.NativeSession(data)
        if timed: session.offline_request_timing_start(100000, 1)
        payload = {"request_id": "live:1:A:old-v1", "owner_id": "A", "kind": "planning_snapshot",
            "target_owner": "B", "message_delay": .01, "publication_delay": .02,
            "expiry": .08 if name == "v1_expired" else 30.}
        history = []
        def observe(at):
            progress = session.advance_to(at)
            history.append({"advance": progress, "public": {o: session.observe_protocol(o) for o in ("A", "B")} if name != "protocol_disabled" else None,
                "v1": {o: session.protocol_planning_snapshots(o) for o in ("A", "B")} if name != "protocol_disabled" else None,
                "command": session.protocol_command("A", payload["request_id"]) if name.startswith("v1_") else None,
                "seal": session.offline_state_sha256(), "checkpoint_seal": session.checkpoint().offline_state_sha256})
        observe(.05)
        if name.startswith("v1_"): history.append({"submission": session.submit_protocol_command(payload)})
        observe(.075)
        checkpoint = session.checkpoint()
        observe(.2)
        restored = copy.deepcopy(history[-1])
        if timed: session.offline_request_timing_take()
        session.restore(checkpoint)
        if timed:
            session.offline_request_timing_take()
            session.offline_request_timing_start(100000, 1)
        observe(.2)
        if stable(restored) != stable(history[-1]): raise ValueError("v2_compat:restore_changed_old_contract")
        if name == "v1_lost_ack": history.append({"retry": session.submit_protocol_command(payload)})
        observe(.5); observe(11.)
        history.append({"result": session.result_at(40.), "seal": session.offline_state_sha256(),
            "checkpoint_seal": session.checkpoint().offline_state_sha256})
        output[name] = stable(history)
    return output


def worker(args):
    build = json.loads(args.build_receipt.read_text())
    expected = build["binary_sha256"].get(str(args.binary.resolve()))
    if expected != sha(args.binary): raise ValueError("v2_compat:binary_identity")
    for name, value in build["source_before"].items():
        if sha(args.build_receipt.parent/"source"/name) != value: raise ValueError("v2_compat:archive_identity")
    native = load_native(args.binary)
    value = {"binary_sha256": expected, "cases": {str(timed): cases(native, timed) for timed in (False, True)}}
    if value["cases"]["False"] != value["cases"]["True"]: raise ValueError("v2_compat:timing_changed_old_contract")
    with gzip.open(args.output, "wt", encoding="utf-8") as stream: json.dump(value, stream, allow_nan=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--build-receipt", type=Path)
    parser.add_argument("--old-build", type=Path)
    parser.add_argument("--new-build", type=Path)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker: worker(args); return
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output/"protocol.json", {"schema": "g31.planning_v2_old_contract_parity.v1",
        "cases": ["protocol_disabled", "enabled_no_planning", "v1_delivered", "v1_lost_ack", "v1_expired"],
        "checks": "exact ordered public/results/checkpoint and actual hidden state seals, off/on, across binaries",
        "native_worker_limit": 1, "source_sha256": {str(Path(__file__).resolve()): sha(__file__)},
        "native_forks_for_policy": 0, "performance_isolated": False, "full_request_100ms_certified": False})
    results = []
    for label, build_path in (("old", args.old_build), ("new", args.new_build)):
        build = json.loads(build_path.read_text()); binary = next(Path(p) for p in build["binary_sha256"] if p.endswith(".pyd"))
        target = args.output/(label+".json.gz")
        done = subprocess.run([sys.executable, "-m", __spec__.name, "--worker", "--output", str(target),
            "--binary", str(binary), "--build-receipt", str(build_path)], capture_output=True, text=True, timeout=60.)
        (args.output/(label+".stdout.log")).write_text(done.stdout, encoding="utf-8")
        (args.output/(label+".stderr.log")).write_text(done.stderr, encoding="utf-8")
        if done.returncode:
            write(args.output/"receipt.json", {"status": "unknown_failed_arm", "arm": label, "exitcode": done.returncode})
            raise SystemExit(done.returncode)
        with gzip.open(target, "rt", encoding="utf-8") as stream: results.append(json.load(stream))
    checks = {name: results[0]["cases"]["False"][name] == results[1]["cases"]["False"][name]
              for name in results[0]["cases"]["False"]}
    checks.update({label+"_timing_off_on": r["cases"]["False"] == r["cases"]["True"] for label, r in zip(("old", "new"), results)})
    receipt = {"status": "passed" if all(checks.values()) else "failed", "checks": checks,
        "binary_sha256": [r["binary_sha256"] for r in results], "native_branch_count": 20,
        "scope": "old contracts only, v2 runtime acceptance is separate", "performance_isolated": False}
    write(args.output/"receipt.json", receipt); print(json.dumps(receipt, indent=2))
    if receipt["status"] != "passed": raise SystemExit(2)


if __name__ == "__main__": main()
