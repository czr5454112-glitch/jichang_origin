"""Read-only native validation for the four isolated G31 all-day fault preflights."""
from pathlib import Path
from collections import defaultdict
import gzip
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.eval import run_g31_tarau_paper_suite as runner

OUTPUT = ROOT / "outputs/runtime/g31_paper_suite_fault_preflight_20260907"
CELLS = [f"f_{m}_1x_v2p5_s104729_q{q}_g31" for q in ("01", "02") for m in ("map2", "nanning")]
FIELDS = (
    "event_count", "declared_max_events", "event_limit_reached", "time_limit_reached",
    "safe_execution_pass", "physical_fault_edge_entry_violation_count", "reservation_conflicts",
    "merge_grant_conservation_holds", "merge_grant_active_bijection_holds",
    "merge_grant_active_state_integrity_pass", "merge_grant_protocol_integrity_pass",
    "merge_grant_lifecycle_complete", "merge_grant_lifecycle_dropped_count",
    "merge_grant_final_active_unconsumed", "merge_grant_outstanding_request_count",
    "s4_advertised_fault_potential_repair_enabled", "s4_fault_potential_rebuild_count",
    "s4_fault_potential_active_advertised_edge_count", "s4_fault_potential_restore_original_count",
    "s4_fault_unreachable_park_count", "s4_fault_unreachable_wakeup_count",
    "s4_fault_unreachable_active_parked_count",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_result(directory):
    """Canonical JSON comparison fixes only the read-side tuple/list mismatch.

    Does not modify/normalize any existing result or invoke the native runtime.
    """
    result_path = directory / "normalized_result.json"
    result = runner._json(result_path)
    status = runner._json(directory / "runner_status.json")
    assert status["status"] == result["status"] == "COMPLETE"
    assert result["schema"] == runner.RESULT_SCHEMA
    assert status["normalized_result_sha256"] == sha(result_path)
    prepared = runner.prepare_spec(result["spec"])
    assert runner._encode(result["provenance"]) == runner._encode(prepared.provenance), "actual input/source/binary provenance mismatch"
    decoded = {}
    for name, entry in result["archives"].items():
        path = directory / entry["path"]
        assert path.parent.resolve() == directory.resolve()
        assert sha(path) == entry["sha256"]
        content = gzip.decompress(path.read_bytes())
        assert hashlib.sha256(content).hexdigest() == entry["content_sha256"]
        decoded[name] = runner._decode(json.loads(content))
    native = decoded["native_payload"]
    audit = runner.audit_payload(prepared, native)
    assert runner._encode(audit.pop("raw_rows")) == runner._encode(decoded["raw_population"])
    assert runner._encode(audit) == runner._encode(result["population_audit"])
    assert runner._encode(native["bags"]) == runner._encode(decoded["bags"])
    with gzip.open(directory / "request.json.gz", "rt", encoding="utf-8") as stream:
        request = runner._decode(json.load(stream))
    assert runner._encode(request) == runner._encode(prepared.request)
    return result, native, request


def main():
    rows = []
    for cell in CELLS:
        directory = OUTPUT / cell
        result_path = directory / "normalized_result.json"
        if not result_path.exists():
            status_path = directory / "runner_status.json"
            rows.append({"cell_id": cell, "audit_status": "INCOMPLETE",
                "runner_status": json.loads(status_path.read_text()) if status_path.exists() else None})
            continue
        try:
            # Reopens every compressed archive and verifies both archive/content
            # hashes, exact input/runner provenance, and all-population metrics.
            result, native, request = verified_result(directory)
            summary = native["summary"]
            disabled = {tuple(edge) for edge in result["spec"]["failed_edges"]}
            incoming = defaultdict(set)
            for u, v, _length, _speed in request["edge_records"]:
                if (u, v) not in disabled:
                    incoming[v].add(u)
            reachable = {}
            for goal in {bag["goal"] for bag in native["bags"]}:
                seen, frontier = {goal}, [goal]
                while frontier:
                    new = incoming[frontier.pop()] - seen
                    seen.update(new)
                    frontier.extend(new)
                reachable[goal] = seen
            unreachable = [bag for bag in native["bags"] if bag["start"] not in reachable[bag["goal"]]]
            assert not any(bag["completed"] for bag in unreachable), "unreachable OD unexpectedly completed"
            topology = {"static_surviving_topology_unreachable_segments": len(unreachable),
                "unreachable_completed_segments": 0,
                "reachable_unfinished_segments": sum(not bag["completed"] and bag["start"] in reachable[bag["goal"]] for bag in native["bags"]),
                "active_parked_equals_unreachable_population": summary["s4_fault_unreachable_active_parked_count"] == len(unreachable),
                "definition": "Read-only reverse reachability on exact request edge records minus frozen all-day disabled edges; no population removal or new simulation."}
            rows.append({"cell_id": cell, "audit_status": "PASS",
                "normalized_result_path": str(result_path), "normalized_result_sha256": sha(result_path),
                "native_archive": result["archives"]["native_payload"],
                "population_audit": result["population_audit"],
                "native_summary": {field: summary.get(field) for field in FIELDS},
                "static_topology_diagnostic": topology,
                "native_wall_seconds": result["native_wall_seconds"],
                "initial_failed_edge_count": len(result["spec"]["initial_failed_edges"]),
                "disabled_edge_count": len(result["spec"]["failed_edges"]),
                "binary_sha256": result["spec"]["binary_sha256"]})
        except Exception as error:
            rows.append({"cell_id": cell, "audit_status": "FAIL", "error": str(error)})
    state = "FAIL" if any(r["audit_status"] == "FAIL" for r in rows) else (
        "PASS" if all(r["audit_status"] == "PASS" for r in rows) else "INCOMPLETE")
    report = {"schema": "czr005.g31_paper_suite_fault_preflight_verification.v1", "status": state,
        "expected_cell_count": 4, "audited_cell_count": sum(r["audit_status"] == "PASS" for r in rows),
        "formal_matrix_cells_executed": 0, "population_prefiltered": False,
        "auditor_path": str(Path(__file__)), "auditor_sha256": sha(Path(__file__)),
        "runner_path": str(Path(runner.__file__)), "runner_sha256": sha(Path(runner.__file__)),
        "verification_compatibility_note": "Frozen load_completed rejects fault provenance list pairs versus reconstructed tuple pairs. This auditor compares canonical JSON representations while retaining all values/hashes; it changes no result or runner.",
        "scope": "Exact native input/binary/provenance/archive validation; all raw bags and segment IDs; native lifetime accounting and active-state counters. Truncated telemetry is disclosed, not a full-path or continuous collision proof.",
        "cells": rows}
    target = OUTPUT / "preflight_verification.json"
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": state, "audited_cell_count": report["audited_cell_count"], "report": str(target)}))
    if state == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
