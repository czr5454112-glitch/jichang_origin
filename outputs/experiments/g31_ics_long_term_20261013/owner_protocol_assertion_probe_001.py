"""Reproduce the root runner's overly specific latest-attempt assertion."""
import json
from pathlib import Path
from scripts.experiments.g31_ics_circulation.native_host import load_native

base = Path("outputs/experiments/g31_ics_long_term_20261013")
source = base/"owner_protocol_native_001/duplicate_wire_on_recovery"
data = json.loads((source/"input.json").read_text())
request = json.loads((source/"request.json").read_text())
session = load_native("build_lt_session_009/python/czr005_circulation.cp311-win_amd64.pyd").NativeSession(data)
session.advance_to(10.)
session.submit_protocol_transfer(request)
for target in (19.8, 19.8):
    session.advance_to(target)
    session.submit_protocol_transfer(request)
result = session.result_at(70.)
view = session.observe_protocol("B")
client = session.protocol_request("B", request["request_id"])
acks = view["delivered_transfer_acks"]
receipt = {"status": "reproduced_assertion_contract_error", "client": client, "acks": acks,
           "incorrect_latest_attempt_assertion": client["last_delivered_ack"]["attempt"] == 3,
           "highest_attempt_actually_acknowledged": client["status"] == "acknowledged" and any(a["attempt"] == 3 for a in acks),
           "latest_is_newest_emission_sequence": client["last_delivered_ack"]["sequence"] == max(a["sequence"] for a in acks),
           "physical_transfer_count": len(result["transfers"]),
           "grant_count": sum(r["event"] == "EXPORT_GRANTED" for r in result["receipts"]),
           "explanation": "A later-emitted response to an older attempt may carry the newer physical snapshot. Sequence orders emitted snapshots; delivered_attempt covers retry acknowledgement. No native fix or weaker highest-attempt requirement is needed.",
           "evidence_scope": "separate deterministic reproduction after the first recorded assertion failure; not a log captured by that failed invocation"}
path = base/"owner_protocol_assertion_probe_001.json"
if path.exists():
    raise FileExistsError(path)
path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
