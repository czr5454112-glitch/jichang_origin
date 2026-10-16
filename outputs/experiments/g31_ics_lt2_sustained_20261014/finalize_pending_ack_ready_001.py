"""Finalize reviewed immutable three-fault preparation; never dispatch."""
import json
from pathlib import Path
from scripts.experiments.g31_ics_circulation import probe_original_route_update_pending_ack as p

output = p.OUT / "original_route_pending_ack_prepare_001"
campaign = p.verify_campaign(output)
plan = p.old.read(output / "preregistered_protocol.json")
review = output / "independent_source_review_001.json"
wrapper = p.OUT / "user_resume_20261015_001/invoke_route_pending_ack_measured.ps1"
assert p.old.sha(review) == "5c6888eec306d1ad1327e402320122eec32f5d68614c19326dd713fdf4182563"
assert p.old.sha(wrapper) == "d7d43146bcd061f04ccbd708c729724afa25153da1d2d8151aee7ebb1aa5e515"
assert all(not (output / name / "worker_claim.json").exists() for name in p.CASES)
assert not (output / "execution_claim.json").exists()
precheck = p.old.read(output / "pure_precheck_001.json")
assert precheck["campaign_sha256"] == p.old.sha(output / "campaign.json")
assert precheck["source_before"] == plan["source_before"]
ready = {"schema": "g31.original_route_pending_ack.ready.v1", "status": "prepared_reviewed_native_unexecuted",
    "output": str(output), "campaign_sha256": p.old.sha(output / "campaign.json"),
    "preregistered_plan_path": str(output / "campaign.json"),
    "preregistered_plan_sha256": p.old.sha(output / "campaign.json"),
    "protocol_plan": {"path": str(output / "preregistered_protocol.json"), "sha256": p.old.sha(output / "preregistered_protocol.json")},
    "execute_command": [plan["interpreter"]["path"], "-m",
        "scripts.experiments.g31_ics_circulation.launch_original_route_update_pending_ack", "--output", str(output),
        "--campaign-sha256", p.old.sha(output / "campaign.json")],
    "external_wrapper": {"path": str(wrapper), "sha256": p.old.sha(wrapper)},
    "external_receipt_path": str(output / "powershell_launch_receipt.json"),
    "evidence": {str(path): p.old.sha(path) for path in (review, output / "pure_precheck_001.json",
        p.OUT / "pending_ack_campaign_pure_002.xml", p.OUT / "pending_ack_campaign_pure_001.xml")},
    "source_before": plan["source_before"], "source_count": len(plan["source_before"]),
    "compiled_source_count": len(plan["compiled_source_sha256"]),
    "native_binary_sha256": p.old.sha(plan["native_binary"]),
    "readiness_source": {str(Path(__file__).resolve()): p.old.sha(__file__)},
    "pure_tests": {"passed": 84, "failures": 0, "errors": 0, "skipped": 0},
    "scope": p.contract(), "shared_hard_seconds": 600., "native_executions": 0,
    "original_sources_modified": False, "complete_computation_available": False, "complete_100ms_certified": False}
path = output / "ready.json"
assert not path.exists()
p.old.write(path, ready)
print(json.dumps({"path": str(path), "sha256": p.old.sha(path), "campaign_sha256": ready["campaign_sha256"]}))
