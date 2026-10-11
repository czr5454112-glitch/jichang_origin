"""Audit saved negative paired-learning results without fitting or simulation."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from .experiment_protocol import check_output_directory, create_output_directory, write_new_json
from .feature_diagnostics import (FoldNeighbors, collision_report, decode_network, digest,
                                  infer_current_node, observable_context)

DEFAULT_PAIRED = Path("outputs/experiments/ics_circulation_v3/phase4_w3_paired_development_20261009")
DEFAULT_LABELS = Path("outputs/experiments/ics_circulation_v3/phase4_w3_label_stability_20261009")
DEFAULT_OUTPUT = Path("outputs/experiments/ics_circulation_v3/phase4_w3_feature_diagnostics_20261009")
SOURCES = ("run_feature_diagnostics.py", "feature_diagnostics.py", "experiment_protocol.py", "runtime.py", "model.py")


class Inputs:
    def __init__(self):
        self.hashes = {}

    def read(self, path):
        path = Path(path)
        data = path.read_bytes()
        self.hashes[str(path)] = sha256(data).hexdigest()
        return json.loads(data)


def annotate_labels(inputs, paired, labels):
    rows = inputs.read(paired / "normal_candidate_rows.json")
    cached = {}
    for row in rows:
        group = row["source_group"]
        if group not in cached:
            record = inputs.read(labels / (group.replace(":", "_") + ".json"))
            cached[group] = (record, decode_network(record["state"]["network"]))
        record, network = cached[group]
        candidate = record["proposals"][row["candidate_index"]]
        if record["actual_action_keys"][row["candidate_index"]] != row["actual_action_key"]:
            raise ValueError("Label row no longer agrees with original candidate")
        raw = record["state"]
        row["context"] = observable_context(network, raw["bags"][candidate["bag_id"]], candidate,
            now=raw["now"], current_node=raw["trays"][candidate["tray_id"]]["node"])
        row["analytic_delta_error"] = row["delta_mean"] - row["timed_delta"]
    return rows, cached


def audit_checkpoints(inputs, paired, rows):
    assessments = inputs.read(paired / "held_out_checkpoint_assessments.json")
    lookup = {(row["source_group"], row["actual_action_key"]): row for row in rows}
    output = []
    for stream, methods in assessments.items():
        for method, result in methods.items():
            for choice in result["decisions"]:
                row = lookup[choice["source_group"], choice["chosen_key"]]
                output.append({"stream": stream, "method": method, "source_group": row["source_group"],
                    "chosen_candidate_index": row["candidate_index"], "context": row["context"],
                    "chosen_regret": choice["regret"], "chosen_delta": row["delta_mean"],
                    "chosen_analytic_delta_error": row["analytic_delta_error"], "candidate_count": choice["candidate_count"],
                    "scope": "saved held-out checkpoint common-future mean; not a learned deployment-state label"})
    return output


def audit_deployments(inputs, paired, summary, rows, names):
    episodes, decisions, arrivals = [], [], []
    for metric in summary["deployment_metrics"]:
        stream, policy = metric["stream"], metric["policy"]
        path = paired / (stream + "__" + policy + "_deployment.json")
        record = inputs.read(path)
        source = inputs.read(paired / (stream + "_deployment_inputs.json"))
        if record["metrics"] != metric:
            raise ValueError("Deployment aggregate differs from raw record")
        if metric["status"] != "completed_run":
            episodes.append({**metric, "diagnostic_status": "failed_run_retained", "source_file": str(path)})
            continue
        network = decode_network(source["initial"]["network"])
        bags = {**source["initial"]["bags"], **{b["bag_id"]: b for b in source["actual_tape_event_engine_only"]}}
        learned = record["learned_feature_history"]
        routes = record["route_history"]
        if learned and len(learned) != len(routes):
            raise ValueError("Learned feature and physical route call denominators differ")
        neighbors = FoldNeighbors(rows, stream, names)
        counts, departures, examples = Counter(), 0, []
        actual_departures = {(e["time"], e["tray_id"], e["edge_id"]) for e in record["result"]["trace"] if e["event"] == "depart"}
        for index, route in enumerate(routes):
            candidates, chosen, now = route["candidates"], route["chosen"], route["time"]
            if chosen["bag_id"] not in route["visible_bag_ids"]:
                raise ValueError("Offline task metadata would expose an unobserved identity")
            bag = bags[chosen["bag_id"]]
            current = infer_current_node(network, candidates, bag)
            context = observable_context(network, bag, chosen, now=now, current_node=current)
            onsite = any(not c["legs"] for c in candidates) and context["at_destination"]
            leaves = context["at_destination"] and bool(chosen["legs"])
            departed = leaves and (chosen["legs"][0]["depart"], chosen["tray_id"], chosen["legs"][0]["edge_id"]) in actual_departures
            counts[context["role"]] += 1
            departures += departed
            item = {"stream": stream, "policy": policy, "call_index": index, "time": now,
                "bag_id": chosen["bag_id"], "tray_id": chosen["tray_id"], "context": context,
                "authorized_onsite_delivery_available": onsite, "selected_departure_from_destination": leaves,
                "departure_physically_observed": departed, "chosen_witness": chosen,
                "deployment_chosen_regret": None,
                "regret_unavailable_reason": "No paired rollout labels were collected at this learned-policy state"}
            if learned:
                frame = learned[index]
                if frame["time"] != now or candidates[frame["chosen_index"]] != chosen:
                    raise ValueError("Candidate/feature/selection alignment differs")
                item.update(chosen_index=frame["chosen_index"], scores=frame["scores"], features=frame["features"],
                    outside_training_range=frame["outside_training_range"],
                    chosen_neighborhood=neighbors.nearest(frame["features"][frame["chosen_index"]], context),
                    candidate_contexts=[observable_context(network, bag, c, now=now, current_node=current) for c in candidates])
            decisions.append(item)
            if onsite and leaves:
                examples.append({"call_index": index, "time": now, "bag_id": chosen["bag_id"],
                    "node": current, "physically_departed": departed,
                    "chosen_index": item.get("chosen_index"), "chosen_score": item["scores"][item["chosen_index"]] if learned else None,
                    "chosen_edges": [leg["edge_id"] for leg in chosen["legs"]]})
        episodes.append({**metric, "source_file": str(path), "actual_call_role_counts": dict(counts),
            "destination_departure_calls": sum(e["physically_departed"] for e in examples),
            "destination_departure_examples": examples,
            "source_training_roles": sorted({r["context"]["role"] for r in rows if r["stream"] != stream}),
            "source_training_nodes": sorted({r["context"]["current_node"] for r in rows if r["stream"] != stream}),
            "state_shift_scope": "saved full Snapshot hash differences including reservations, versions and retained conditional records; not a physical-trajectory-only statistic"})
    return episodes, decisions


def run(output=DEFAULT_OUTPUT, *, paired=DEFAULT_PAIRED, labels=DEFAULT_LABELS):
    output, paired, labels = check_output_directory(output), Path(paired), Path(labels)
    inputs = Inputs()
    summary = inputs.read(paired / "summary.json")
    protocol = inputs.read(paired / "protocol.json")
    if any(summary[name] for name in ("source_changed_during_run", "frozen_models_changed", "input_files_changed")):
        raise ValueError("Cannot diagnose a changed-source/model/input experiment as frozen evidence")
    names = protocol["features"]
    if len(names) != 23 or len(set(names)) != 23:
        raise ValueError("This diagnostic concerns the frozen old 23-feature schema")
    rows, states = annotate_labels(inputs, paired, labels)
    if len(rows) != summary["normal_candidate_rows"] or len(states) != summary["checkpoint_count"]:
        raise ValueError("Label row/checkpoint denominator changed")
    checkpoints = audit_checkpoints(inputs, paired, rows)
    episodes, decisions = audit_deployments(inputs, paired, summary, rows, names)
    candidate_collisions = collision_report(rows, names)
    paired_collisions = collision_report(rows, names, paired=True)
    role_summary = defaultdict(lambda: {"calls": 0, "physically_left_destination": 0, "selected_without_same_role_training_neighbor": 0})
    for row in decisions:
        key = row["context"]["role"]
        role_summary[key]["calls"] += 1
        role_summary[key]["physically_left_destination"] += row["departure_physically_observed"]
        if "chosen_neighborhood" in row:
            role_summary[key]["selected_without_same_role_training_neighbor"] += not row["chosen_neighborhood"]["nearest_same_role"]
    exact_nonzero = [g for g in candidate_collisions["collision_groups"] if g["target_range"] > 1e-9]
    output = create_output_directory(output)
    code = Path(__file__).parent
    hashes = {name: sha256((code / name).read_bytes()).hexdigest() for name in SOURCES}
    (output / "source_snapshot").mkdir()
    for name in SOURCES:
        (output / "source_snapshot" / name).write_bytes((code / name).read_bytes())
    write_new_json(output / "protocol.json", {"schema": "ics_v3_old_feature_diagnostics_v1", "input_paired": str(paired),
        "input_labels": str(labels), "source_sha256": hashes, "old_feature_names": names,
        "scope": "post-hoc development diagnosis; no training, simulation, new label or seed selection",
        "collision": "exact float feature tuples, separately paired baseline+candidate tuples; original paired MC deltas retained for uncertainty",
        "neighborhood": "Euclidean RMS after per-feature training-fold standard deviation normalization, constant dimensions scaled by one; top three rows, no outcome-tuned threshold",
        "observable_context": "current node inferred from validated candidate sources; immutable bag fields read only after visible-identity check; public graph and owner safe prefix",
        "unavailable": ["full Snapshot at every saved deployment call", "paired true rollout costs/regret at learned deployment states"],
        "new_independent_source_count": 0, "simulator_calls": 0, "fits": 0})
    compact_labels = [{key: value for key, value in row.items() if key not in {"costs", "paired_deltas"}} for row in rows]
    write_new_json(output / "label_role_errors.json", {"rows": compact_labels, "held_out_choices": checkpoints})
    write_new_json(output / "feature_collisions.json", {"candidate_features": candidate_collisions, "paired_features": paired_collisions})
    write_new_json(output / "deployment_diagnostics.json", {"episodes": episodes, "actual_decisions": decisions})
    result = {"schema": "ics_v3_old_feature_diagnostics_summary_v1", "label_checkpoints": len(states),
        "normal_label_rows": len(rows), "held_out_assessment_decisions": len(checkpoints),
        "label_current_nodes": dict(Counter(row["context"]["current_node"] for row in rows if row["is_baseline"])),
        "label_roles": dict(Counter(row["context"]["role"] for row in rows if row["is_baseline"])),
        "candidate_feature_unique_keys": candidate_collisions["unique_feature_keys"],
        "candidate_collision_groups": len(candidate_collisions["collision_groups"]),
        "candidate_collision_groups_with_unequal_empirical_delta": len(exact_nonzero),
        "paired_feature_unique_keys": paired_collisions["unique_feature_keys"],
        "deployment_episodes": len(episodes), "failed_episode_denominator": sum(e["status"] != "completed_run" for e in episodes),
        "scheduled_bags": sum(e["scheduled_bags"] for e in episodes),
        "completed_bags": sum(e["completed"] or 0 for e in episodes),
        "actual_route_calls": len(decisions), "role_breakdown": dict(role_summary),
        "episodes_with_onsite_delivery_rejected_for_departure": sum(bool(e.get("destination_departure_examples")) for e in episodes),
        "physically_departed_when_onsite_delivery_available": sum(e.get("destination_departure_calls", 0) for e in episodes),
        "same_schema_collision_is_not_itself_structural_aliasing_proof": True,
        "minimal_supported_feature_hypotheses": ["current_node_equals_task_destination", "immediate_committed_prefix_completes_delivery"],
        "feature_hypothesis_limit": "Concrete role/decision omissions motivate testing, but this analysis does not prove that additional features improve generalization or are mathematically necessary given the existing reference features.",
        "source_sha256": hashes, "input_sha256": inputs.hashes,
        "source_changed_during_run": hashes != {name: sha256((code / name).read_bytes()).hexdigest() for name in SOURCES},
        "input_changed_during_run": any(sha256(Path(name).read_bytes()).hexdigest() != value for name, value in inputs.hashes.items()),
        "limitations": ["Only four synthetic development streams; no independent operational evidence.",
                       "Exact-feature mean target differences can be MC noise and horizon/state effects.",
                       "Neighbour label errors are not labels for the queried deployment state.",
                       "Departure while a validated onsite delivery is available is a recorded action; no whole-episode counterfactual regret is asserted.",
                       "The preserved 186/192 completion denominator is not improved by this read-only diagnosis."]}
    write_new_json(output / "summary.json", result)
    print({key: result[key] for key in ("normal_label_rows", "deployment_episodes", "actual_route_calls", "role_breakdown",
                                       "physically_departed_when_onsite_delivery_available", "completed_bags", "scheduled_bags")})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--paired", type=Path, default=DEFAULT_PAIRED)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    args = parser.parse_args()
    outcome = run(args.output, paired=args.paired, labels=args.labels)
    raise SystemExit(int(outcome["source_changed_during_run"] or outcome["input_changed_during_run"]))
