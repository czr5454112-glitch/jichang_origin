"""Frozen-011 short-service communication boundary diagnosis, no shared edits."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation.native_host import load_native, prepare_input, tiny_cycle, audit_result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    start = time.perf_counter()
    binary = ROOT / "build_lt_session_011/python/czr005_circulation.cp311-win_amd64.pyd"
    assert sha(binary) == "19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec"
    prior_path = HERE.parent / "original_protocol_24_forecast_diagnosis_011_001/diagnosis.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    original = copy.deepcopy(prior["policies"])
    for policy in original.values():
        policy.pop("earliest_event_notification_cannot_beat_delay")
        policy.pop("earliest_event_notification_might_beat_delay")
        for row in policy["rows"]:
            t = row["earliest_notification_would_execute_at"]
            d = row["physical_edge_enter"]
            row["earliest_timing_class"] = "strictly_late" if t > d else "exact_tie" if t == d else "strictly_early"
        policy["timing_classes"] = {k: sum(r["earliest_timing_class"] == k for r in policy["rows"])
                                    for k in ("strictly_late", "exact_tie", "strictly_early")}
    native = load_native(binary)
    raw, results = [], []
    for load_seconds, service in ((0., .001), (0., 1.5), (0., 2.), (0., 3.), (3., .001)):
        data = tiny_cycle()
        data["transfers"] = []
        data["jobs"] = [data["jobs"][0]]
        data["jobs"][0]["load_seconds"] = load_seconds
        data["node_records"] = [(n, kind, service if n == 0 else duration, x, y, neighbors)
                                for n, kind, duration, x, y, neighbors in data["node_records"]]
        data["node_contracts"][1]["resource_owner"] = "B"
        data["owner_protocol"] = dict(enabled=True, timeout=5., ack_delay=.2)
        data["options"].update(trace_limit=1000, scorer_mode="S4_queue_aware_rule_only")
        data = prepare_input(data)
        s = native.NativeSession(data)
        s.advance_to(0.)
        observation = s.observe_protocol("A")
        request = dict(kind="service_forecast", request_id="live:1:A:earliest", owner_id="A", target_owner="B",
                       tray_id="T0", next=1, message_delay=2., publication_delay=.5)
        submit = s.submit_protocol_command(request)
        s.advance_to(2.8)
        command = s.protocol_command("A", request["request_id"])
        peer = s.observe_protocol("B")
        result = s.result_at(30.)
        audit = audit_result(data, result)
        entry = next(r for r in result["receipts"] if r["event"] == "EDGE_ENTER")
        ack = command["last_delivered_ack"]
        assert submit["status"] == "pending" and ack["executed_at"] == 2.
        row = dict(load_seconds=load_seconds, node_service_seconds=service,
                   issue_time=0., command_delay=2., observation_mode=observation["trays"][0]["mode"],
                   first_edge_entry=entry, ack=ack, delivered_peer_messages=peer["delivered_messages"], audit=audit)
        results.append(row)
        raw.append(dict(input=data, initial_observation=observation, request=request, submit=submit,
                        client_at_2_8=command, peer_at_2_8=peer, result=result))
    with gzip.open(HERE / "raw.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(raw, stream, allow_nan=False)
    receipt = dict(schema="g31.original24.forecast_delay_diagnosis.v2", status="passed",
                   scope="Frozen original raw timings plus five declared synthetic native011 communication-boundary probes; not an original-scene event-trigger replay or benefit claim",
                   prior_diagnosis_sha256=sha(prior_path), prior_identity=prior["identity"],
                   runner_sha256=sha(Path(__file__)), binary_sha256=sha(binary),
                   original_policies=original, synthetic_boundaries=results, elapsed_seconds=time.perf_counter()-start)
    write(HERE / "diagnosis.json", receipt)
    print(json.dumps(dict(status="passed", original_classes={k:v["timing_classes"] for k,v in original.items()},
                        synthetic=[dict(load=r["load_seconds"], service=r["node_service_seconds"],
                                        status=r["ack"]["status"], reason=r["ack"]["reason"],
                                        edge_enter=r["first_edge_entry"]["time"],
                                        estimates=[m["entry_estimate"] for m in r["delivered_peer_messages"]]) for r in results],
                        elapsed_seconds=receipt["elapsed_seconds"])))


if __name__ == "__main__":
    main()
