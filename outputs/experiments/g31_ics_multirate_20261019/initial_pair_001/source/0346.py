"""One prespecified missing-self-ACK asymmetric-readiness diagnostic."""
from __future__ import annotations
import argparse
import copy
import gzip
import json
from pathlib import Path
import time
from . import research_native_public_joint as online
from . import research_synthetic_reuse_chain as v1
from .native_host import load_native


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), Path(online.__file__), Path(online.adapter.__file__), Path(online.model.__file__), Path(v1.__file__)]
    before = {str(p.resolve()): online.sha(p) for p in sources}
    archive = args.output / "source_archive"
    archive.mkdir()
    for p in sources: (archive / p.name).write_bytes(p.read_bytes())
    protocol = {"schema": "g31.lt2.planning_asymmetric_readiness.v1", "native_branch_budget": 1,
        "gate": 6., "drop_ack_packets": 1, "drop_semantics": "native remaining_ack_drops initialized separately for EVERY immutable request",
        "seed": "same native020 synthetic input; demand and planning submittedat.05; captures.06/delivered.07",
        "targeted_retry": "B retries its EXACT planning request at.075; wire.085, ACK.105; A has no retry beforedecision.11",
        "fault_selection": "fixedbeforeoutcomes fromnative per-request dropcounter semantics, no outcomescreening",
        "decision": "both owners independently run unchanged joint35 proposal from own delivered selfcopy and peer snapshot",
        "observation_horizon": .5, "scope": "readiness/action asymmetry only; no business/protection comparison",
        "expected_diagnostic_not_assumed": "A missing selfACK withholds; B ready may execute supply without A route change",
        "no_atomic_agreement_claim": True, "source_sha256": before}
    online.write(args.output / "preregistered_protocol.json", protocol)
    if online.sha(args.binary) != args.expected_binary_sha256: raise ValueError("asymmetry:binary_identity")
    native = load_native(args.binary)
    data = v1.scene(6.)
    data["owner_protocol"]["drop_ack_packets"] = 1
    online.write(args.output / "input.json", data)
    started = time.perf_counter()
    session = native.NativeSession(data)
    session.advance_to(.05)
    client = v1.Transport(session)
    for owner, peer in (("A", "B"), ("B", "A")):
        client.submit(owner, "demand", "seed-demand", target_owner=peer, message_delay=.01, publication_delay=.01)
    planning = {owner: client.submit(owner, "planning_snapshot", "initial-planning", target_owner=peer,
        message_delay=.01, publication_delay=.01, expiry=.21) for owner, peer in (("A", "B"), ("B", "A"))}
    session.advance_to(.075)
    immutable_before = copy.deepcopy(client.rows[planning["B"]]["request"])
    client.send(planning["B"], retry=True)
    if client.rows[planning["B"]]["request"] != immutable_before: raise ValueError("asymmetry:mutated_retry")
    session.advance_to(.11)
    client.refresh(retry=False)
    decisions = {o: online.owner_first_action(native, session, client, o, planning[o], "joint_model") for o in ("A", "B")}
    session.advance_to(.5)
    client.refresh(retry=False)
    result = session.result_at(.5)
    entered = [r for r in result["receipts"] if r["event"] == "EDGE_ENTER" and r["tray_id"] == "E"]
    raw = {"owners": decisions, "calls": client.calls, "outbox": client.rows, "result": result}
    with gzip.open(args.output / "raw.json.gz", "wt", encoding="utf-8") as stream: json.dump(raw, stream, allow_nan=False)
    report = {"schema": protocol["schema"], "status": "observed", "native_branches": 1,
        "owner_ready": {o: d["information"]["native_delivery_verified"] for o, d in decisions.items()},
        "selected_actions": {o: d["decision"].get("selected_action") for o, d in decisions.items()},
        "submitted_first_intents": {o: d["native_request_id"] for o, d in decisions.items()},
        "E_actual_edges": [{k: r[k] for k in ("time", "from", "to")} for r in entered],
        "own_planning_ACKs": {o: client.rows[planning[o]].get("ack", {}) for o in ("A", "B")},
        "source_changed": [p for p, h in before.items() if online.sha(Path(p)) != h],
        "native_binary_sha256": args.expected_binary_sha256, "wall_seconds": time.perf_counter() - started,
        "business_metrics": None, "strict_protection": "not_assessed", "atomic_agreement_implemented": False}
    if report["source_changed"]: report["status"] = "unknown_source_changed"
    online.write(args.output / "receipt.json", report)
    print(json.dumps(report, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--expected-binary-sha256", required=True)
    run(p.parse_args())


if __name__ == "__main__": main()
