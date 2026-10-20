"""Read a small fixed set of saved shards; never access the running native world."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--shards", type=int, nargs="+", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    heartbeat = json.loads((args.run / "heartbeat.json").read_bytes())
    if max(args.shards) > heartbeat["segment"]:
        raise ValueError("seal_scaling:unpublished_shard")
    input_path = args.run / "input.json.gz"
    data = json.load(gzip.open(input_path, "rt", encoding="utf-8"))
    # Each demand member is length-prefixed UTF-8 bag ID + i64 origin +
    # binary64 arrival + binary64 deadline: exactly 32 + ID bytes.
    sizes = [32 + len(job["business_bag_id"].encode("utf-8")) for job in data["jobs"]]
    del data
    result = []
    for index in args.shards:
        path = args.run / "segments" / f"{index:04d}.json.gz"
        before = sha(path)
        part = json.load(gzip.open(path, "rt", encoding="utf-8"))
        commands = part["controller_state"]["client"]["outbox"]
        members = known = unconfirmed = 0
        for row in commands.values():
            if row["kind"] != "demand":
                continue
            ack = (row.get("client_view") or {}).get("last_delivered_ack") or {}
            signature = ack.get("captured_demand_signature")
            if signature is None:
                unconfirmed += 1
                continue
            known += 1
            members += signature["waiting_count"]
        physical = part["control_continuation"]["physical_time"]
        seal_seconds = part["diagnostic_seal_wall_ms"] / 1000
        result.append({"shard": index, "sha256": before, "physical_time": physical,
            "owner_activations_in_shard": len(part["control_records"]), "controller_wall_seconds": part["wall_seconds"],
            "seal_wall_seconds": seal_seconds, "native_seal": part["native_state_sha256"],
            "outbox_count": len(commands), "confirmed_demand_captures": known,
            "demand_commands_without_confirmed_capture": unconfirmed, "confirmed_captured_members": members,
            "confirmed_member_canonical_bytes_lower": members * min(sizes),
            "confirmed_member_canonical_bytes_upper": members * max(sizes),
            "seal_over_controller_fraction": seal_seconds / part["wall_seconds"]})
        if sha(path) != before:
            raise ValueError("seal_scaling:saved_shard_changed")
        del part, commands
    receipt = {"schema": "g31.saved_seal_scaling_diagnostic.v1", "status": "passed",
        "run": str(args.run.resolve()), "input_sha256": sha(input_path), "heartbeat_read": heartbeat,
        "sample": result, "native_workers": 0, "input_member_size_min": min(sizes), "input_member_size_max": max(sizes),
        "scope": "Demand-member byte interval only for immutable ACK-confirmed captures, each command counted once. Excludes unconfirmed captures, all message headers and all other checkpoint fields; lower bound on total canonical bytes, not exact hidden native state size. Saved shard seal wall is original measured evidence; concurrent work disclosed by campaign."}
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
