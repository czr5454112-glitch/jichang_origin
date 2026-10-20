"""Candidate/calendar counterexamples only: no native session or campaign fit."""
from copy import deepcopy
from datetime import datetime
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_batch_patch as patch
from scripts.experiments.g31_ics_circulation import foundation_airport_calendar_forecast as calendar
from scripts.experiments.g31_ics_circulation import foundation_airport_flight as flight
from scripts.experiments.g31_ics_circulation import foundation_airport_opportunities as opportunities
from scripts.experiments.g31_ics_circulation import foundation_airport_spi as spi
from scripts.experiments.g31_ics_circulation import foundation_airport_spi_parents as parents


LOADERS = sorted(flight.STANDARD_LOADERS + flight.TRANSFER_LOADERS)
# Registered first weights availability is after the last train day and before
# the first dev day. Champion selection has a separate, later availability.
FIRST_WEIGHTS_AVAILABLE = datetime.fromisoformat("2026-09-28T23:59:59+08:00").timestamp()
REGISTERED_FINAL_HORIZON = 59400.


def public_fixture(source=150):
    nodes = sorted(set(LOADERS + [source]))
    target = next(node for node in LOADERS if node != source)
    observation = {
        "now": 100., "owner_id": "A", "version": 7,
        "static_role_contract": {"schema": "g31.static_node_roles.v1", "loader_nodes": LOADERS.copy()},
        "node_contracts": [{"node": n, "zone": "A", "resource_owner": "A",
            "capacity": 4, "allow_receive": True, "allow_export": True} for n in nodes],
        "node_records": [[n, 0, .1] for n in nodes],
        "edge_records": [[source, n, float(rank+1), 1.]
            for rank, n in enumerate(LOADERS) if n != source],
        "edge_contracts": [], "transfers": [], "client_transfer_ledger": [],
        "delivered_messages": [], "delivered_transfer_acks": [], "jobs": [],
        "trays": [{"tray_id": "one", "node": source, "mode": "empty", "available_at": 99.,
            "edge_to": -1, "reception_node": -1, "generation": 1}],
    }
    supply = {"tray_id": "one", "node": source, "earliest": 100., "estimate": 100.,
        "ledger": "actual_available", "owner_id": "A", "version": 7,
        "dependency": "one:empty", "latest": None}
    intent = {"tray_id": "one", "source": source, "destination": target,
        "issued_at": 100., "earliest_departure": 102., "expiry": 300., "message_delay": 2.,
        "owner_id": "A", "expected_version": 7, "transfer_scope": "local_empty_return",
        "forecast_ledger": "actual_available", "forecast_dependency": "one:empty",
        "control_reason": "observed_source_queue", "service_window": None}
    return observation, {"intents": [intent], "supplies": [supply], "demands": [], "includes_wait": True}


def catalogue(observation, baseline, **options):
    return opportunities.build_opportunity(observation, baseline,
        continuation_version="airport_common_inventory_pi0_v1",
        message_delay=2., respect_service_forecasts=False, **options)


def test_full_catalogue_covers_all_eleven_loaders_including_legacy_omissions_once():
    observation, baseline = public_fixture()
    before = deepcopy((observation, baseline))
    old = catalogue(observation, baseline)
    full = catalogue(observation, baseline, k_max=13)
    represented = [baseline["intents"][0]["destination"], *full["candidate_destination_nodes"]]
    assert len(LOADERS) == 11
    assert set(represented) == set(LOADERS) and len(represented) == len(set(represented))
    assert set(full["candidate_destination_nodes"]) - set(old["candidate_destination_nodes"])
    assert 149 in full["candidate_destination_nodes"] and 149 not in old["candidate_destination_nodes"]
    assert full["K_max"] == 13 and full["K"] == 12  # reference + ten alternatives + hold
    assert full["legal_destination_count"] == 10
    identities = [a["action_id"] for a in full["candidates"]]
    assert len(identities) == len(set(identities))
    for action in full["candidates"]:
        actual = patch.apply_patch(observation, baseline, action)
        assert len(actual["intents"]) <= 1
    assert (observation, baseline) == before


def test_legacy_default_k3_keeps_exact_catalogue_and_patch_hold_order():
    observation, baseline = public_fixture()
    default = catalogue(observation, baseline)
    assert default == catalogue(observation, baseline, k_max=3)
    assert default["candidate_catalog_version"] == opportunities.CATALOG_VERSION
    assert default["K"] == 3 and default["candidate_destination_nodes"] == [24]
    assert [a["action_id"] for a in default["candidates"]] == ["a_ref", "a_patch", "hold_optional"]
    assert [a["kind"] for a in default["candidates"]] == ["a_ref", "replace_optional", "hold_optional"]


@pytest.mark.parametrize("capacity", [0, -1])
def test_full_catalogue_masks_static_nonpositive_capacity_without_global_inventory(capacity):
    observation, baseline = public_fixture()
    target = next(n for n in observation["node_contracts"] if n["node"] == 24)
    target["capacity"] = capacity
    assert all("free" not in n and "occupancy" not in n for n in observation["node_contracts"])
    full = catalogue(observation, baseline, k_max=13)
    assert 24 not in full["candidate_destination_nodes"]
    assert full["mask_reasons"]["static_nonpositive_receive_capacity"] == 1
    assert set(full["candidate_destination_nodes"]) == set(LOADERS) - {0, 24}
    # Legacy mode is deliberately preserved; this test does not rewrite its contract.
    assert catalogue(observation, baseline)["candidate_destination_nodes"] == [24]


def test_full_catalogue_masks_self_disabled_receiver_and_statically_blocked_edge():
    observation, baseline = public_fixture(source=0)
    next(n for n in observation["node_contracts"] if n["node"] == 26)["allow_receive"] = False
    observation["edge_contracts"] = [{"from": 0, "to": 49, "capacity": 0}]
    full = catalogue(observation, baseline, k_max=13)
    assert not {0, 24, 26, 49}.intersection(full["candidate_destination_nodes"])
    assert set(full["candidate_destination_nodes"]) == set(LOADERS) - {0, 24, 26, 49}
    assert full["mask_reasons"]["static_scope_or_receive_not_eligible"] == 1
    assert full["mask_reasons"]["static_unreachable"] == 1
    assert all(a["intent"]["source"] != a["intent"]["destination"]
        for a in full["candidates"] if a.get("intent"))


def test_positive_static_capacity_does_not_claim_dynamic_receiving_admission():
    observation, baseline = public_fixture()
    original = catalogue(observation, baseline, k_max=13)
    changed = deepcopy(observation)
    for node in changed["node_contracts"]:
        node.update(occupancy=node["capacity"], free=0)
    current = catalogue(changed, baseline, k_max=13)
    assert current["candidate_destination_nodes"] == original["candidate_destination_nodes"]
    assert current["legal_destination_count"] == original["legal_destination_count"]
    assert current["public_state_digest"] != original["public_state_digest"]
    assert current["current_guard_status"] == "shared_resource_nonharm_unknown"
    assert current["protected_takeover_eligible"] is False


def test_duplicate_role_directory_is_rejected_instead_of_duplicating_legal_actions():
    observation, baseline = public_fixture()
    observation["static_role_contract"]["loader_nodes"].append(24)
    with pytest.raises(ValueError, match="invalid_static_role_contract"):
        catalogue(observation, baseline, k_max=13)


def registration(seed, rollout_round):
    # Public registration only: never materializes held-out jobs.
    return parents._expected_registration(seed, rollout_round)


def test_round1_dates_follow_first_weights_and_dev_selection_without_reusing_old_day():
    train = [registration(seed, 0) for seed in range(1101, 1109)]
    dev = [registration(seed, 0) for seed in range(1201, 1205)]
    later = [registration(seed, 1) for seed in (*range(1101, 1109), *range(1201, 1205))]
    assert train[-1]["calendar_start"] == "2026-09-28T00:00:00+08:00"
    assert dev[0]["calendar_start"] == "2026-09-29T00:00:00+08:00"
    assert dev[-1]["calendar_start"] == "2026-10-02T00:00:00+08:00"
    assert later[0]["calendar_start"] == "2026-10-11T00:00:00+08:00"
    assert later[-1]["calendar_start"] == "2026-10-22T00:00:00+08:00"
    assert max(p["calendar_start_epoch_seconds"]+REGISTERED_FINAL_HORIZON for p in train) < FIRST_WEIGHTS_AVAILABLE
    assert FIRST_WEIGHTS_AVAILABLE < min(p["calendar_start_epoch_seconds"] for p in dev)
    dev_closed_upper_bound = max(p["calendar_start_epoch_seconds"]+REGISTERED_FINAL_HORIZON for p in dev)
    assert dev_closed_upper_bound < min(p["calendar_start_epoch_seconds"] for p in later)
    for early, late in zip(train+dev, later, strict=True):
        assert late["calendar_start_epoch_seconds"]-early["calendar_start_epoch_seconds"] == 20*86400
        assert late["parent_seed"] == early["parent_seed"]
        assert late["plan_group_shifts_sha256"] == early["plan_group_shifts_sha256"]
        assert late["parent_group"] != early["parent_group"]
        assert parents.validate_public_parent(late) == late


def test_first_champion_availability_blocks_old_collection_day_but_allows_round1():
    contract = spi.make_spi_contract(allowed_domains=[parents.DOMAIN],
        behavior_policy_id="airport_common_inventory_pi0_v1",
        continuation_policy_id="airport_common_inventory_pi0_v1")
    dev_closed_upper_bound = registration(1204, 0)["calendar_start_epoch_seconds"] + REGISTERED_FINAL_HORIZON
    model = spi.make_reference_champion(information_variant="C01", contract=contract,
        model_available_at_epoch_seconds=FIRST_WEIGHTS_AVAILABLE,
        champion_selection_available_at_epoch_seconds=dev_closed_upper_bound)
    predict = spi.prepare_supported_predictor(model)
    def rows(seed, rollout_round):
        parent = dict(registration(seed, rollout_round), spi_domain=deepcopy(parents.DOMAIN))
        return [{"parent": deepcopy(parent), "observation": {"now": 7200.}} for _ in range(2)]
    assert not predict(*rows(1108, 0))["supported"]  # weights unavailable
    assert not predict(*rows(1201, 0))["supported"]  # weights exist; champion not yet selected
    assert spi.prepare_supported_predictor(model, development_evaluation=True)(*rows(1201, 0))["supported"]
    assert predict(*rows(1101, 1))["reference_champion"]
    assert predict(*rows(1204, 1))["reference_champion"]


def test_round1_parent_materialization_preserves_every_no_storage_sentinel():
    data, parent, evidence = parents.make_parent(1101, rollout_round=1)
    original, _ = parents.historical_input(0, fleet=22)
    unassigned = [(before, after) for before, after in zip(original["jobs"], data["jobs"], strict=True)
        if before["storage_node"] == -1]
    assert unassigned
    for before, after in unassigned:
        assert after["business_bag_id"] == before["business_bag_id"]
        assert after["storage_node"] == -1
        # The absent-node sentinel is -1; the historical unused release field
        # is 0.0 and must also stay unchanged instead of receiving a group shift.
        assert after["storage_release_at"] == before["storage_release_at"]
    assert any(before["storage_release_at"] == 0. for before, _ in unassigned)
    assert parent["rollout_round"] == 1 and len(data["jobs"]) == 28506
    assert evidence["independent_real_airport_days"] == 0


@pytest.mark.parametrize("seed", [1101, 1204])
def test_round1_calendar_inverse_recovers_exact_original_plan_and_frozen_weights(seed, monkeypatch):
    original_plan = json.loads((calendar.SOURCE / "public/static_flight_plan.json").read_text(encoding="utf8"))
    early = calendar.load_calendar_binding(registration(seed, 0))
    later = calendar.load_calendar_binding(registration(seed, 1))
    assert early["checkpoint"] == later["checkpoint"]
    assert early["producer_manifest"]["parameter_sha256"] == later["producer_manifest"]["parameter_sha256"]
    assert early["absolute_plan_template"] != later["absolute_plan_template"]
    assert early["binding_sha256"] != later["binding_sha256"]
    recovered = []
    original_digest = calendar.digest
    def observe_digest(value):
        if isinstance(value, dict) and value.get("source_id") == original_plan["source_id"]:
            recovered.append(deepcopy(value))
        return original_digest(value)
    monkeypatch.setattr(calendar, "digest", observe_digest)
    calendar._validate_binding(later)
    assert recovered == [original_plan]
    assert original_digest(recovered[0]) == later["checkpoint"]["static_plan_sha256"]
    for key in ("new_fit_performed", "observed_count_update"):
        assert later["producer_manifest"][key] is False


def test_round1_rehashed_plan_tampering_cannot_pass_original_plan_inverse_binding():
    binding = calendar.load_calendar_binding(registration(1101, 1))
    changed = deepcopy(binding)
    changed["absolute_plan_template"]["entries"][-1]["scheduled_event_at"] += .01
    changed["producer_manifest"]["target_plan_template_sha256"] = calendar.digest(changed["absolute_plan_template"])
    changed["binding_sha256"] = calendar.digest({k: v for k, v in changed.items() if k != "binding_sha256"})
    with pytest.raises(ValueError, match="inverse_binding_must_recover_frozen_public_plan"):
        calendar._validate_binding(changed)


def test_rollout_round_cannot_relabel_formal_test_or_change_registered_date():
    with pytest.raises(ValueError, match="registered_rollout_round"):
        parents.public_registration(1301, shift_digest="unused", rollout_round=1)
    changed = deepcopy(registration(1101, 1))
    changed["calendar_start"] = registration(1101, 0)["calendar_start"]
    changed["calendar_start_epoch_seconds"] = registration(1101, 0)["calendar_start_epoch_seconds"]
    with pytest.raises(ValueError, match="public_lineage_changed"):
        parents.validate_public_parent(changed)
