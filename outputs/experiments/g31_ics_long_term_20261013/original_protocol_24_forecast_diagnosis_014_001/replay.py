"""Replay the five immutable native011 inputs/requests on a pinned new host."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import native_host


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def summarize(raw):
    ack = raw["client_at_2_8"]["last_delivered_ack"]
    entry = next(r for r in raw["result"]["receipts"] if r["event"] == "EDGE_ENTER")
    forecast = next((m for m in raw["peer_at_2_8"]["delivered_messages"]
                     if m["message_id"] == ack.get("result_id")), None)
    return dict(status=ack["status"], reason=ack["reason"], executed_at=ack["executed_at"],
                actual_first_entry=entry["time"], entry_estimate=forecast["entry_estimate"] if forecast else None,
                estimate_minus_actual=forecast["entry_estimate"]-entry["time"] if forecast else None,
                peer_delivery=forecast["delivered_at"] if forecast else None,
                first_job=raw["result"]["jobs"][0])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    if (HERE / "receipt.json").exists():
        raise ValueError("audit:refusing_to_overwrite_existing_receipt")
    prior_path = HERE.parent / "original_protocol_24_forecast_diagnosis_011_002/raw.json.gz"
    prior = json.load(gzip.open(prior_path, "rt", encoding="utf-8"))
    assert len(prior) == 5
    source_paths = [Path(__file__), Path(native_host.__file__)]
    sources = {str(p): sha(p) for p in source_paths}
    receipt = dict(schema="g31.forecast_timing_replay.v1", status="running",
                   source_before=sources, old_raw_sha256=sha(prior_path),
                   binary=str(args.binary), binary_sha256=sha(args.binary),
                   old_binary_sha256="19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec",
                   scope="Same five frozen011 synthetic input/request objects. Correctness replay, not original-map event policy or performance evidence.")
    started = time.perf_counter()
    outputs, comparisons = [], []
    try:
        assert receipt["binary_sha256"] == args.expected_sha256
        native = native_host.load_native(args.binary)
        for i, old in enumerate(prior):
            data, request = old["input"], old["request"]
            before_input, before_request = digest(data), digest(request)
            session = native.NativeSession(data)
            initial = session.advance_to(0.)
            assert initial["status"] == "reached" and initial["horizon_complete"]
            observation = session.observe_protocol("A")
            submitted = session.submit_protocol_command(request)
            advance = session.advance_to(2.8)
            assert advance["status"] == "reached" and advance["horizon_complete"]
            client, peer = session.protocol_command("A", request["request_id"]), session.observe_protocol("B")
            result = session.result_at(30.)
            audit = native_host.audit_result(data, result)
            new = dict(input=data, initial_observation=observation, request=request, submit=submitted,
                       client_at_2_8=client, peer_at_2_8=peer, result=result, audit=audit)
            outputs.append(new)
            old_summary, new_summary = summarize(old), summarize(new)
            preserved = digest(data) == before_input and digest(request) == before_request
            assert preserved
            assert new_summary["status"] == old_summary["status"]
            assert new_summary["actual_first_entry"] == old_summary["actual_first_entry"]
            if new_summary["status"] == "delivered":
                assert new_summary["estimate_minus_actual"] == 0.
            comparisons.append(dict(index=i, input_sha256=before_input, request_sha256=before_request,
                                    input_request_unchanged=preserved, before=old_summary, after=new_summary,
                                    audit=audit))
        receipt["status"] = "passed"
    except Exception:
        receipt["status"] = "failed"
        receipt["exception"] = traceback.format_exc()
    with gzip.open(HERE / "raw.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(outputs, stream, allow_nan=False)
    receipt["comparisons"] = comparisons
    receipt["source_after"] = {str(p): sha(p) for p in source_paths}
    receipt["source_changed"] = [p for p in sources if sources[p] != receipt["source_after"][p]]
    receipt["elapsed_seconds"] = time.perf_counter()-started
    receipt["raw_sha256"] = sha(HERE / "raw.json.gz")
    write(HERE / "receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "source_changed", "elapsed_seconds", "exception") if k in receipt}))
    return int(receipt["status"] != "passed" or bool(receipt["source_changed"]))


if __name__ == "__main__":
    raise SystemExit(main())
