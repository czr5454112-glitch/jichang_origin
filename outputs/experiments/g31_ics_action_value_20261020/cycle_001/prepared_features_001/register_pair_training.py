"""Explicitly authorized registration only; no primary or control fit calls."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_training_campaign as training
from scripts.experiments.g31_ics_circulation import foundation_airport_action_campaign as campaign

CYCLE = ROOT/"outputs/experiments/g31_ics_action_value_20261020/cycle_001"


def refs(stems):
    return [{
        "dataset": training.file_ref(CYCLE/(stem+"_dataset_001.json.gz")),
        "reference_plan": training.file_ref(CYCLE/(stem+"_a_ref_001")/"plan.json"),
        "patched_plan": training.file_ref(CYCLE/(stem+"_a_patch_001")/"plan.json"),
    } for stem in stems]


def main():
    train = ["H_701_calendar", "H_702_calendar", "C_701_extra", "C_702_extra"]
    dev = ["C_801_0", "C_801_1", "C_802_0", "C_802_1"]
    availability = json.loads((CYCLE/"C_801_0_a_ref_001/plan.json").read_bytes())[
        "parent"]["calendar_start_epoch_seconds"]
    result = {}
    for domain, name, train_stems, dev_stems in (
        ("primary_22", "training_primary_001", train, dev),
        ("mixed_18_22_26", "training_resource_001",
            train+["F_18_701", "F_26_702"], dev+["F_18_801", "F_26_802"]),
    ):
        prepared = training.prepare_manifest(output=CYCLE/name, train_inputs=refs(train_stems),
            dev_inputs=refs(dev_stems), training_domain=domain,
            forecast_addendum=training.file_ref(CYCLE/"forecast_capture_addendum_001.json"),
            model_available_at_epoch_seconds=availability)
        manifest = training.read_bound(prepared["manifest"])
        campaign.event(CYCLE, "training_registered", training_domain=domain,
            manifest=prepared["manifest"], status=prepared["status"],
            requested_training_jobs=manifest["requested_training_jobs"],
            primary_fit_calls_planned=manifest["primary_fit_calls_planned"],
            fit_calls_started=0, test_opened=False)
        result[domain] = prepared
        print(json.dumps({"domain": domain, "status": prepared["status"],
            "train_pairs": manifest["sufficiency"]["C01"]["closed_pairs"],
            "train_parents": manifest["sufficiency"]["C01"]["train_parent_groups"],
            "resource_gate": manifest["resource_gate"], "fit_calls_started": 0}, indent=2))
    training._write_new(CYCLE/"pair_training_registration_receipt_001.json",
        {"schema": "g31.airport_pair_training_registration_receipt.v1", "campaigns": result,
            "model_available_at_epoch_seconds": availability, "fit_calls_started": 0,
            "native_jobs": 0, "test_opened": False})


if __name__ == "__main__":
    main()
