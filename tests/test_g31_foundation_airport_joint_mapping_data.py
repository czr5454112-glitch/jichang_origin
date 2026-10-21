"""Observed TRAIN entry labels cannot be inferred from offered future jobs."""
import copy
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_joint_mapping_data as source
from scripts.experiments.g31_ics_circulation import foundation_airport_loader_mapping as mapping


def fixture():
    parent = dict(split="train", parent_seed=1101, rollout_round=0,
                  parent_group="historical-train-1101", calendar_start_epoch_seconds=1000.,
                  common_historical_template_sha256="one-template")
    jobs = [dict(business_bag_id="projected:1x:0", origin=0, arrival=5.),
            dict(business_bag_id="projected:1x:1", origin=24, arrival=20.)]
    result = dict(physical_clock=10., advance=dict(status="reached", horizon_complete=True),
                  receipts=[dict(event="BAG_ARRIVAL", time=5., business_bag_id="projected:1x:0", node=0)])
    return dict(parent=parent), dict(jobs=jobs), result


def test_actual_entry_gate_excludes_unarrived_future_and_binds_native_loader_time():
    plan, native, result = fixture()
    entries = source.observed_arrivals(plan, native, result, closed_physical_time=10.)
    assert len(entries) == 1 and entries[0]["loader"] == 0
    for key, wrong in (("time", 6.), ("node", 24)):
        changed = copy.deepcopy(result)
        changed["receipts"][0][key] = wrong
        with pytest.raises(ValueError, match="actual_entry_time_and_loader_binding"):
            source.observed_arrivals(plan, native, changed, closed_physical_time=10.)


@pytest.mark.parametrize("split,seed", [("dev", 1201), ("test", 1301)])
def test_development_and_test_cannot_supply_mapping_labels(split, seed):
    plan, native, result = fixture()
    plan["parent"].update(split=split, parent_seed=seed)
    with pytest.raises(ValueError, match="train_only_mapping_label_parent"):
        source.observed_arrivals(plan, native, result, closed_physical_time=10.)


def test_missing_duplicate_and_unclosed_arrivals_fail_closed():
    plan, native, result = fixture()
    changed = copy.deepcopy(result)
    changed["receipts"] = []
    with pytest.raises(ValueError, match="all_and_only_observed"):
        source.observed_arrivals(plan, native, changed, closed_physical_time=10.)
    changed["receipts"] = result["receipts"]*2
    with pytest.raises(ValueError, match="unique_actual_entry"):
        source.observed_arrivals(plan, native, changed, closed_physical_time=10.)
    changed = copy.deepcopy(result)
    changed["advance"]["status"] = "event_budget"
    with pytest.raises(ValueError, match="closed_observed_prefix"):
        source.observed_arrivals(plan, native, changed, closed_physical_time=10.)


def test_region_index_retains_only_observed_ids_and_drops_future_group_fields(tmp_path):
    path = tmp_path/"index.jsonl"
    rows = [dict(bag_id="legacy_0", region="legacy_start_3", arrived_at=5., flight_ref="private-group"),
            dict(bag_id="legacy_1", region="legacy_start_53", arrived_at=20., whole_day_count=9999)]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    selected = source.load_selected_region_labels(path, {"legacy_0"}, expected_sha256=source.sha(path))
    assert selected == {"legacy_0": dict(region="legacy_start_3", original_arrival=5.)}
    with pytest.raises(ValueError, match="frozen_historical_region"):
        source.load_selected_region_labels(path, {"legacy_0"}, expected_sha256="wrong")


def test_receipt_bound_labels_fit_existing_train_only_mapping_contract():
    plan, native, result = fixture()
    entries = source.observed_arrivals(plan, native, result, closed_physical_time=10.)
    labels = source.make_observed_labels(plan["parent"], entries,
        {"legacy_0": dict(region="legacy_start_3")}, source_evidence_id="bound-native-files")
    assert labels[0]["observed_at_epoch_seconds"] == 1005.
    assert labels[0]["provenance_kind"] == "observed_entry"
    fitted = mapping.fit_loader_mapping(labels, train_parent_ids=[plan["parent"]["parent_group"]],
        training_labels_closed_at_epoch_seconds=1010., model_available_at_epoch_seconds=1011.,
        input_domain=dict(split="train", labels_kind="observed_entry_labels", uses_future_crosswalk=False))
    assert fitted["training_label_count"] == 1 and not fitted["dev_or_test_labels_used"]
    assert fitted["regions"]["legacy_start_53"]["fallback_to_prior"]
