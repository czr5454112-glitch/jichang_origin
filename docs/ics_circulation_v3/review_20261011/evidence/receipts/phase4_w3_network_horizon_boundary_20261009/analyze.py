"""Read saved original-network h80 outcomes; no new simulator or training calls."""
from collections import Counter
from hashlib import sha256
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "outputs/experiments/ics_circulation_v3"
PRIMARY = BASE / "phase4_w3_network_role_labels_parallel_20261009"
COMPLETE = BASE / "phase4_w3_network_role_complete_20261009"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    output = Path(__file__).with_name("summary.json")
    if output.exists():
        raise ValueError("preserve the existing analysis; choose a new directory for another run")
    frozen = read(COMPLETE / "manifest.json")
    ledger_path = COMPLETE / "resolved_request_ledger.json"
    assert digest(ledger_path) == frozen[ledger_path.name]
    ledger = list(read(ledger_path).values())
    assert len(ledger) == 2176 and all(r["status"] == "reached_horizon" for r in ledger)
    sample_rows, request_rows, sources = [], [], {str(ledger_path.relative_to(ROOT)): digest(ledger_path)}
    for scene in ("cross_cycle", "counterflow", "near_full"):
        scene_path = PRIMARY / scene
        summary = read(scene_path / "summary.json")
        for item in summary["samples"]:
            label_path, sample_path = scene_path / item["labels"][0], scene_path / item["file"]
            label, sample = read(label_path), read(sample_path)
            for path in (label_path, sample_path):
                sources[str(path.relative_to(ROOT))] = digest(path)
            future_by_draw = {(g, f): tape for g, group in enumerate(label["future_groups_offline_only"])
                              for f, tape in enumerate(group["tapes"])}
            endpoint = sample["time"] + 80
            local = [r for r in ledger if r["sample"] == item["identity"]]
            assert len(local) == label["candidate_count"] * 32
            for row in local:
                assert row["horizon_ticks"] == 80
                components = row["cost_components"]
                assert components["terminal_backlog"] == row["uncompleted_bags"]
                tape = future_by_draw[row["group"], row["draw"]]
                later = [bag for bag in tape if bag["arrival"] > endpoint]
                request_rows.append({"scene": scene, "sample": item["identity"],
                    "request_key": row["request_key"], "uncompleted_bags": row["uncompleted_bags"],
                    "terminal_inflight_trays": int(components["terminal_inflight"]),
                    "terminal_cost": 10. * components["terminal_backlog"] + 2. * components["terminal_inflight"],
                    "later_arrival_instances": len(later)})
            draw_later = [sum(bag["arrival"] > endpoint for bag in tape) for tape in future_by_draw.values()]
            sample_rows.append({"scene": scene, "sample": item["identity"], "role": sample["role"],
                "sample_time": sample["time"], "endpoint": endpoint,
                "candidate_count": label["candidate_count"], "requested_branches": len(local),
                "future_draws_including_zero_candidate_cell": len(draw_later),
                "future_draws_with_later_arrivals": sum(value > 0 for value in draw_later),
                "later_arrival_instances_per_common_future_draw": sum(draw_later),
                "maximum_saved_future_arrival": max((bag["arrival"] for tape in future_by_draw.values() for bag in tape), default=None)})
    def aggregate(rows):
        return {"requests": len(rows),
            "requests_with_observed_uncompleted_bags": sum(r["uncompleted_bags"] > 0 for r in rows),
            "observed_uncompleted_bag_instances_request_weighted": sum(r["uncompleted_bags"] for r in rows),
            "requests_with_inflight_trays": sum(r["terminal_inflight_trays"] > 0 for r in rows),
            "inflight_tray_instances_request_weighted": sum(r["terminal_inflight_trays"] for r in rows),
            "requests_with_positive_terminal_cost": sum(r["terminal_cost"] > 0 for r in rows),
            "terminal_cost_sum_request_weighted": sum(r["terminal_cost"] for r in rows),
            "requests_with_saved_arrivals_after_endpoint": sum(r["later_arrival_instances"] > 0 for r in rows),
            "saved_later_arrival_task_instances_request_weighted": sum(r["later_arrival_instances"] for r in rows),
            "requests_all_saved_tasks_arrived_and_observed_bags_completed": sum(
                r["uncompleted_bags"] == 0 and r["later_arrival_instances"] == 0 for r in rows),
            "requests_zero_terminal_cost_and_no_saved_later_arrivals": sum(
                r["terminal_cost"] == 0 and r["later_arrival_instances"] == 0 for r in rows)}
    by_scene = {scene: aggregate([r for r in request_rows if r["scene"] == scene])
                for scene in ("cross_cycle", "counterflow", "near_full")}
    for scene, value in by_scene.items():
        evaluated = [s for s in sample_rows if s["scene"] == scene and s["candidate_count"]]
        value["candidate_shared_future_draws_for_evaluated_cells"] = sum(s["future_draws_including_zero_candidate_cell"] for s in evaluated)
        value["candidate_shared_future_draws_with_later_arrivals"] = sum(s["future_draws_with_later_arrivals"] for s in evaluated)
        value["saved_later_task_instances_per_candidate_shared_draw"] = sum(s["later_arrival_instances_per_common_future_draw"] for s in evaluated)
    for sample in sample_rows:
        sample["request_counts"] = aggregate([r for r in request_rows if r["sample"] == sample["sample"]])
    first = next(row for row in ledger if row["scene"] == "cross_cycle" and row["group"] == 0
                 and row["candidate"] == 0 and row["draw"] == 0 and ":d0:" in row["sample"])
    physical = json.loads(gzip.decompress(Path(first["file"]).read_bytes()))["result"]
    example = {"request_key": first["request_key"], "sample": first["sample"],
        "endpoint": physical["final_snapshot"]["now"], "observed_uncompleted_bag_ids": physical["uncompleted_bag_ids"],
        "cost_components": physical["cost_components"],
        "inflight_trays_by_carriage": dict(Counter("loaded" if tray["bag_id"] else "empty"
            for tray in physical["final_snapshot"]["trays"].values() if tray["mode"] == "in_transit")),
        "evidence_file": first["file"], "evidence_sha256": digest(Path(first["file"]))}
    payload = {"schema": "ics_v3_original_network_h80_business_boundary_v1", "simulator_calls": 0,
        "denominator": "2176 original requested candidate-by-draw rollouts, retaining exact duplicate draw weights",
        "overall": aggregate(request_rows), "by_scene": by_scene, "by_sample_time": sample_rows,
        "verified_example": example, "source_sha256": sources,
        "definitions": {"reached_horizon": "The physical rollout reached checkpoint time +80; it does not assert all saved business tasks arrived or completed.",
            "observed_uncompleted": "All task IDs in final_snapshot.bags but not completed, including carried tasks; excludes future arrivals after the endpoint.",
            "terminal_cost": "10 * observed uncompleted bags +2 * all in-transit trays; in-transit trays may carry bags already counted in backlog, or be empty.",
            "later_arrivals": "Read from the exact saved hypothetical future tape, arrival > checkpoint time +80; no simulator or policy access added.",
            "task_instances": "A hypothetical task repeats across candidate/draw requests; these are weighted exposure counts, not distinct operational jobs.",
            "common_future_draws": "Count each (sample, group, draw) once across candidates; duplicate tapes across draws remain separate sampled weights."},
        "conclusion": "The original-network h80 dataset is a finite-window action-value diagnostic, not full business-cycle completion. A follow-up full-cycle or longer-horizon sensitivity evaluation is justified by both observed unfinished work and saved arrivals beyond h80. Do not transfer the toy-map h80 completion claim to these workloads.",
        "next_evaluation_boundary": "Predeclare the complete saved finite tape, a drain condition for all arrived tasks, and separately whether empty-tray return must settle; keep physical work/budget exhaustion and unfinished tasks in the denominator. Preserve current h80 labels unchanged."}
    with output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
    manifest = {p.name: digest(p) for p in output.parent.iterdir() if p.is_file()}
    with output.with_name("manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
    print(json.dumps({"overall": payload["overall"], "by_scene": by_scene, "example": example}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
