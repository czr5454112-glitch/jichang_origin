"""Independent deadline, delivered-window and strict notification-clock checks."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "event_protocol_original24_015_001/original24"


def read(path):
    return json.load(gzip.open(path, "rt", encoding="utf-8")) if path.suffix == ".gz" else json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if (HERE / "detail.json").exists():
    raise ValueError("review:refusing_to_overwrite_detail")
data = read(SOURCE / "input.json")
contracts = {j["business_bag_id"]: j for j in data["jobs"]}
service = {n[0]: n[2] for n in data["node_records"]}
result = dict(schema="g31.original24_deadline_notification_review.v1", status="passed", policies={},
              runner_sha256=sha(Path(__file__)), prior_review_sha256=sha(HERE/"assessment.json"))
for policy in ("periodic_reactive", "periodic_predictive", "event_reactive", "event_predictive", "event_joint"):
    run_path = SOURCE/policy/"run.json.gz"
    run = read(run_path)
    view_path = SOURCE/policy/"delivered_views.json.gz"
    views = read(view_path)
    events = run["result"]["receipts"]
    forecasts = [m for v in views.values() for m in v["delivered_messages"]
                 if m["kind"] == "service_forecast" and m.get("status") == "conditional"]
    details = []
    for message in forecasts:
        entry = next(e for e in events if e["event"] == "EDGE_ENTER" and e["tray_id"] == message["tray_id"]
                     and e["business_bag_id"] == message["business_bag_id"] and e["from"] == message["from"]
                     and e["time"] >= message["observed_at"])
        details.append(dict(message_id=message["message_id"], source_service=service[message["from"]],
                            delivered_minus_actual_entry=message["delivered_at"]-entry["time"]))
    notices = [row for row in run["control_records"] if row.get("causes", {}).get("notification")]
    assert all(row["causes"]["notification"]["observed_at"] <= row["at"] for row in notices)
    late_ids = [j["business_bag_id"] for j in run["result"]["jobs"]
                if contracts[j["business_bag_id"]]["deadline"] >= 0 and
                j["completed_at"] > contracts[j["business_bag_id"]]["deadline"] + 1e-8]
    deltas = [row["delivered_minus_actual_entry"] for row in details]
    result["policies"][policy] = dict(run_sha256=sha(run_path), views_sha256=sha(view_path),
        completed=sum(j["status"] == "completed" for j in run["result"]["jobs"]), deadline_violations=len(late_ids),
        late_business_ids=late_ids, actual_notification_activations_checked=len(notices),
        every_notification_observed_at_not_after_owner_activation=True,
        delivered_lag_min=min(deltas, default=None), delivered_lag_max=max(deltas, default=None),
        delivered_source_service_counts=dict(Counter(row["source_service"] for row in details)), delivered_details=details)
(HERE/"detail.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
print(json.dumps({"status": result["status"], "policies": {k: {n: v for n, v in row.items()
      if n not in ("late_business_ids", "delivered_details", "run_sha256", "views_sha256")} for k,row in result["policies"].items()}}))
