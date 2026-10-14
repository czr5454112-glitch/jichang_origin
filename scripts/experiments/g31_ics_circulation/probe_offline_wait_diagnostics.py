"""Cross-check exported native wait/index/queue identities on live continuations."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).absolute().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle


def check(data, diagnostics):
    waits = {w["runtime_id"]: w for w in diagnostics["resource_waits"]}
    assert waits, "fixture did not exercise a live native resource wait"
    legs = {l["runtime_id"]: l for l in diagnostics["legs"]}
    queues = {j["node"]: j for j in diagnostics["junctions"]}
    for identity, wait in waits.items():
        leg = legs[identity]
        tray = diagnostics["trays"][leg["tray_index"]]
        assert tray["active_leg"] == identity and tray["node"] == wait["node"]
        assert tray["edge_to"] == -1
        assert identity in queues[wait["node"]]["queue"]
        for edge in wait["edge_indices"]:
            assert data["edge_contracts"][edge]["from"] == wait["node"]
        for field, reverse in (("edge_indices", "edge_waiters"), ("receiving_nodes", "receiving_waiters"),
                               ("ranking_nodes", "ranking_waiters")):
            for resource in wait[field]:
                assert diagnostics[reverse][resource][identity] == wait["generation"]
    for field, reverse in (("edge_indices", "edge_waiters"), ("receiving_nodes", "receiving_waiters"),
                           ("ranking_nodes", "ranking_waiters")):
        for resource, entries in diagnostics[reverse].items():
            for identity, generation in entries.items():
                assert resource in waits[identity][field] and waits[identity]["generation"] == generation
    for junction in queues.values():
        for identity in junction["queue"] + junction["source_queue"]:
            assert identity in legs
    return {"wait_count": len(waits), "active_leg_ids": sorted(waits),
            "input_business_job_count": len(data["jobs"]),
            "runtime_leg_id_outside_business_index_range": any(i >= len(data["jobs"]) for i in waits)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = {"schema": "g31.offline_wait_identity_probe.v1", "binary": str(args.binary.absolute()),
              "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(), "cases": []}
    try:
        native = load_native(args.binary)
        receiving = runpy.run_path(str(ROOT / "tests/test_g31_circulation_recovery.py"))["receiving_release"]()
        tail = tiny_cycle()
        tail["edge_contracts"][0]["entry_headway"] = 100
        tail["edge_contracts"][1]["capacity"] = 0
        for name, data, horizon in (("receiving_berth", receiving, 100), ("reused_tray_new_leg", tail, 13)):
            session = native.NativeSession(data)
            session.advance_to(horizon)
            before = session.offline_state_sha256()
            diagnostics = session.offline_diagnostics()
            facts = check(data, diagnostics)
            assert session.offline_state_sha256() == before
            assert "resource_waits" not in session.observe("A")
            restored = session.fork()
            assert restored.offline_diagnostics() == diagnostics
            result["cases"].append({"name": name, "input": data, "diagnostics": diagnostics, "checks": facts})
        assert any(c["checks"]["runtime_leg_id_outside_business_index_range"] for c in result["cases"])
        result["status"] = "passed"
    except Exception as error:
        result["status"] = "failed"
        result["exception"] = repr(error)
        raise
    finally:
        (args.output / "receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "cases": [c["checks"] for c in result["cases"]]}))


if __name__ == "__main__":
    main()
