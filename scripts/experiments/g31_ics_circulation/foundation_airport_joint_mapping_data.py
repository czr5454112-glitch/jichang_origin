"""Receipt-bound historical TRAIN entry labels for a new loader mapping.

Only already arrived bags enter the label pool. The source historical region
index is an offline label source, never a forecast-time whole-day crosswalk.
The airport loader is the actual native BAG_ARRIVAL node. These are synthetic
assignments derived from one historical template, not independent airport days.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

from .foundation_airport_joint_dataset import digest, number, require
from .foundation_airport_spi_parents import LABEL_SHA256, SOURCE

ROOT = Path(__file__).resolve().parents[3]
OLD_CYCLE = ROOT / "outputs/experiments/g31_ics_inventory_spi_20261020/cycle_001"
SCHEMA = "g31.foundation.airport_joint_observed_mapping_labels.v1"
TRAIN_SEEDS = tuple(range(1101, 1109))
SELECTION_RULE = "longest_complete_r0_reference_export_per_registered_train_parent_then_lexical_run_id"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def bound(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size)


def select_training_exports(cycle=OLD_CYCLE):
    """Inspect only the explicit 16 TRAIN reference records; never scan test."""
    chosen, considered = [], []
    for seed in TRAIN_SEEDS:
        eligible = []
        for root in (0, 1):
            directory = Path(cycle) / "runs" / f"SPI_R0V5_P{seed}_root{root}_a_ref_001"
            paths = {name: directory/name for name in
                     ("plan.json", "worker_report.json", "receipt.json", "final_result.json.gz")}
            if not all(path.is_file() for path in paths.values()):
                considered.append(dict(run=directory.name, status="missing_required_source"))
                continue
            plan, worker, receipt = (read(paths[name]) for name in
                                     ("plan.json", "worker_report.json", "receipt.json"))
            parent = plan["parent"]
            require(parent["split"] == "train" and parent["parent_seed"] == seed
                    and parent["rollout_round"] == 0 and plan["pair"]["branch"] == "a_ref",
                    "registered_historical_train_reference_only")
            require(receipt["plan_sha256"] == sha(paths["plan.json"])
                    and receipt.get("worker") == worker, "historical_process_receipt_binding")
            complete = (worker.get("status") == receipt.get("status") == "complete"
                        and receipt.get("process", {}).get("exitcode") == 0
                        and "final_result" in worker.get("complete_evidence_exports", {}))
            considered.append(dict(run=directory.name, status="complete" if complete else "not_complete",
                                   physical_clock=worker.get("final_physical_time")))
            if complete:
                eligible.append((number(worker["final_physical_time"]), directory.name, directory))
        require(bool(eligible), "no_closed_training_export_for_parent_"+str(seed))
        chosen.append(sorted(eligible, key=lambda value: (-value[0], value[1]))[0][2])
    return chosen, considered


def observed_arrivals(plan, native_input, result, *, closed_physical_time):
    """Pure receipt gate: offered future jobs alone cannot create a label."""
    parent = plan["parent"]
    require(parent["split"] == "train" and parent["parent_seed"] in TRAIN_SEEDS
            and parent["rollout_round"] == 0, "train_only_mapping_label_parent")
    end = number(closed_physical_time)
    require(number(result["physical_clock"]) == end
            and result.get("advance", {}).get("status") == "reached"
            and result.get("advance", {}).get("horizon_complete") is True,
            "closed_observed_prefix_export")
    jobs = {row["business_bag_id"]: row for row in native_input["jobs"]}
    require(len(jobs) == len(native_input["jobs"]), "unique_source_input_population")
    if "jobs_digest" in parent:
        require(parent["jobs_digest"] == digest(native_input["jobs"]), "parent_native_jobs_binding")
    rows, identities = [], set()
    for receipt in result["receipts"]:
        if receipt["event"] != "BAG_ARRIVAL":
            continue
        identity = receipt["business_bag_id"]
        require(identity in jobs and identity not in identities, "unique_actual_entry_receipt")
        identities.add(identity)
        job = jobs[identity]
        at = number(receipt["time"])
        require(0 <= at <= end and at == number(job["arrival"])
                and receipt["node"] == job["origin"], "actual_entry_time_and_loader_binding")
        require(identity.startswith("projected:1x:"), "historical_projected_identity")
        rows.append(dict(business_bag_id=identity, region_label_id="legacy_"+identity.removeprefix("projected:1x:"),
                         loader=receipt["node"], physical_time=at, receipt_sha256=digest(receipt)))
    # This compares the observed prefix only. It does not use future node counts.
    require(identities == {identity for identity, job in jobs.items() if job["arrival"] <= end},
            "all_and_only_observed_prefix_arrivals")
    return rows


def load_selected_region_labels(path, wanted, *, expected_sha256=LABEL_SHA256):
    """Retain only observed IDs and region labels, dropping future/group fields."""
    require(sha(path) == expected_sha256, "frozen_historical_region_label_source")
    result = {}
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            identity = row["bag_id"]
            if identity not in wanted:
                continue
            require(identity not in result, "unique_selected_region_label")
            result[identity] = dict(region=row["region"], original_arrival=row["arrived_at"])
    require(set(result) == set(wanted), "all_observed_entries_have_historical_region_labels")
    return result


def make_observed_labels(parent, arrivals, region_labels, *, source_evidence_id):
    require(parent["split"] == "train" and parent["parent_seed"] in TRAIN_SEEDS,
            "train_only_mapping_label_parent")
    start = number(parent["calendar_start_epoch_seconds"])
    result = []
    for entry in arrivals:
        region = region_labels[entry["region_label_id"]]["region"]
        result.append(dict(label_id=digest([parent["parent_group"], entry["business_bag_id"]]),
            parent_id=parent["parent_group"], split="train", region=region, loader=entry["loader"],
            observed_at_epoch_seconds=start+entry["physical_time"], provenance_kind="observed_entry",
            business_bag_id=entry["business_bag_id"], source_evidence_id=source_evidence_id,
            native_arrival_receipt_sha256=entry["receipt_sha256"],
            synthetic_loader_assignment=True, template_family=parent["common_historical_template_sha256"]))
    return result


def prepare_mapping_labels(output, *, cycle=OLD_CYCLE, label_index=None):
    """Write a new auditable label bundle; no mapping fit or native run occurs."""
    output = Path(output)
    require(not output.exists(), "fresh_mapping_label_output")
    label_index = Path(label_index or SOURCE / "private/flight_label_index.jsonl")
    chosen, considered = select_training_exports(cycle)
    provenance, arrivals_by_source, wanted, boundaries = [], [], set(), []
    for directory in chosen:
        plan = read(directory / "plan.json")
        input_path = Path(plan["input"]["path"])
        require(sha(input_path) == plan["input"]["sha256"], "bound_historical_native_input")
        native_input, result, worker = read(input_path), read(directory/"final_result.json.gz"), read(directory/"worker_report.json")
        entries = observed_arrivals(plan, native_input, result, closed_physical_time=worker["final_physical_time"])
        source = dict(plan=bound(directory/"plan.json"), native_input=bound(input_path),
                      native_result=bound(directory/"final_result.json.gz"), worker=bound(directory/"worker_report.json"),
                      process_receipt=bound(directory/"receipt.json"), parent=plan["parent"],
                      physical_clock=result["physical_clock"], arrival_label_count=len(entries),
                      execution_source_bundle=plan["source_bundle"], native_binary=plan["binary"],
                      future_jobs_used_as_labels=False, branch_selection_uses_service_outcome=False)
        source["source_evidence_id"] = digest(source)
        provenance.append(source)
        arrivals_by_source.append((plan["parent"], entries, source["source_evidence_id"]))
        wanted.update(row["region_label_id"] for row in entries)
        boundaries.append(plan["parent"]["calendar_start_epoch_seconds"]+result["physical_clock"])
    regions = load_selected_region_labels(label_index, wanted)
    labels = [row for parent, arrivals, identity in arrivals_by_source
              for row in make_observed_labels(parent, arrivals, regions, source_evidence_id=identity)]
    require(len({row["label_id"] for row in labels}) == len(labels), "unique_parent_bag_labels")
    domain = dict(split="train", labels_kind="observed_entry_labels", uses_future_crosswalk=False,
        source_kind="historical_closed_native_TRAIN_prefixes", selection_rule=SELECTION_RULE,
        single_template_synthetic=True, template_families=sorted({row["template_family"] for row in labels}),
        independent_real_airport_days=0, loader_labels_are_synthetic_native_entry_nodes=True,
        uses_balanced_assignment_or_whole_day_counts=False,
        prefix_censoring_limitation="Conditional entry frequencies reflect available training prefixes, not a complete-day loader assignment.",
        source_evidence_ids=[row["source_evidence_id"] for row in provenance], region_label_index=bound(label_index))
    report = dict(schema=SCHEMA, input_domain=domain, source_provenance=provenance,
        selection_considered=considered, train_parent_ids=sorted({row["parent_id"] for row in labels}),
        training_labels_closed_at_epoch_seconds=max(boundaries), training_label_count=len(labels),
        labels_sha256=digest(labels), region_counts=dict(sorted(Counter(row["region"] for row in labels).items())),
        source_files_read_outside_train="historical region label index only; selected observed IDs retained",
        future_entries_or_dev_or_test_used=False, native_starts=0, model_fits=0)
    output.mkdir(parents=True)
    with gzip.open(output/"labels.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(labels, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
    report["labels_file"] = bound(output/"labels.json.gz")
    (output/"provenance.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-cycle", type=Path, default=OLD_CYCLE)
    parser.add_argument("--label-index", type=Path)
    args = parser.parse_args()
    report = prepare_mapping_labels(args.output, cycle=args.source_cycle, label_index=args.label_index)
    print(json.dumps({key: report[key] for key in ("training_label_count", "train_parent_ids", "region_counts",
          "training_labels_closed_at_epoch_seconds", "labels_sha256", "labels_file")}, indent=2))


if __name__ == "__main__":
    main()
