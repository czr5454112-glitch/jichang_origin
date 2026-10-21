"""Predeclared whole-flight-group synthetic plans; private tapes stay offline."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from .foundation_airport_action_campaign import ROOT, parent_input as historical_input, digest, sha

FAMILY = "joint_group_shift_plan_v1"
NAMESPACE = "joint_reposition_group_plan_20261021"
SPLITS = {**{x: "train" for x in range(2101, 2109)},
          **{x: "dev" for x in range(2201, 2205)},
          **{x: "test" for x in range(2301, 2309)}}
SEEDS = tuple(SPLITS)
SOURCE = ROOT / "outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/B1_training_001"
LABEL_SHA256 = "2590fcbae13595f59b0204e477de58c789c3abe961a3cb3a51a8ce53b12ae059"
SAMPLING = "sha256(namespace:parent:flight_ref); whole_group_uniform[-1800,1800] seconds; six_decimals"
DOMAIN = {"fleet": 22, "layout_id": "nested_1701_N22", "plan_family_id": FAMILY,
          "physical_contract_id": "native030_joint_post_priority_v1"}


def group_shifts(seed, flight_refs):
    if seed not in SPLITS or len(set(flight_refs)) != len(flight_refs):
        raise ValueError("spi_parents:registered_seed_unique_flight_refs")
    return {ref: round(3600. * int(hashlib.sha256(
                f"{NAMESPACE}:{seed}:{ref}".encode()).hexdigest()[:16], 16) / (2**64 - 1)
                - 1800., 6) for ref in sorted(flight_refs)}


def public_registration(seed, *, shift_digest, rollout_round=0):
    if seed not in SPLITS:
        raise ValueError("spi_parents:unregistered_seed")
    if rollout_round not in (0, 1) or SPLITS[seed] == "test" and rollout_round != 0:
        raise ValueError("spi_parents:registered_rollout_round")
    offset = (60 + seed - 2301 if SPLITS[seed] == "test"
              else 40 + seed - 2201 if SPLITS[seed] == "dev"
              else seed - 2101 + 20 * rollout_round)
    day = datetime.fromisoformat("2026-11-01T00:00:00+08:00") + timedelta(days=offset)
    return {"parent_seed": seed, "split": SPLITS[seed],
            "parent_group": f"{NAMESPACE}:{seed}:r{rollout_round}", "synthetic": True,
            "rollout_round": rollout_round,
            "calendar_start": day.isoformat(), "calendar_start_epoch_seconds": day.timestamp(),
            "common_historical_template_sha256": "a9611267471a269cc34f5646a4ebb409c61a08fa77dcef4c02266b346c86890c",
            "sampling": SAMPLING, "plan_family_id": FAMILY,
            "plan_group_shifts_sha256": shift_digest, "plan_available_at": 0.}


@lru_cache(maxsize=40)
def _expected_registration(seed, rollout_round):
    path = SOURCE / "public/static_flight_plan.json"
    if sha(path) != "c85693b61757e54bff51fbc014e32e16b902ed225607b250fe43da67681a2508":
        raise ValueError("spi_parents:source_public_plan_changed")
    plan = json.loads(path.read_text(encoding="utf-8"))
    shifts = group_shifts(seed, [e["flight_ref"] for e in plan["entries"]])
    return public_registration(seed, shift_digest=digest(shifts), rollout_round=rollout_round)


def validate_public_parent(parent):
    expected = _expected_registration(parent.get("parent_seed"), parent.get("rollout_round", 0))
    if any(parent.get(k) != v for k, v in expected.items()):
        raise ValueError("spi_parents:public_lineage_changed")
    return copy.deepcopy(expected)


def make_parent(seed, *, formal_unlock=None, rollout_round=0):
    """Offline generation only. Future jobs/private group labels never reach actors."""
    if seed not in SPLITS:
        raise ValueError("spi_parents:unregistered_seed")
    if SPLITS[seed] == "test":
        if not formal_unlock or formal_unlock.get("status") != "all_champions_frozen_test_unlocked":
            raise ValueError("spi_parents:test_locked_until_champions_freeze")
        if formal_unlock.get("test_parent_ids") != list(range(2301, 2309)):
            raise ValueError("spi_parents:formal_parent_roster_changed")
    plan = json.loads((SOURCE / "public/static_flight_plan.json").read_text(encoding="utf-8"))
    shifts = group_shifts(seed, [e["flight_ref"] for e in plan["entries"]])
    label_path = SOURCE / "private/flight_label_index.jsonl"
    if sha(label_path) != LABEL_SHA256:
        raise ValueError("spi_parents:private_generation_source_changed")
    labels = {r["bag_id"]: r for r in
              (json.loads(line) for line in label_path.read_text(encoding="utf-8").splitlines())}
    data, base = historical_input(0, fleet=22)
    assert len(data["jobs"]) == len(labels) == 28506
    crosswalk, counts = [], {}
    for job in data["jobs"]:
        identity = job["business_bag_id"]
        if not identity.startswith("projected:1x:"):
            raise ValueError("spi_parents:original_business_identity")
        label = labels["legacy_" + identity.removeprefix("projected:1x:")]
        if job["arrival"] != label["arrived_at"] or job["deadline"] != label["scheduled_std"]:
            raise ValueError("spi_parents:original_group_time_binding")
        ref = label["flight_ref"]
        delta = shifts[ref]
        for key in ("arrival", "deadline", "storage_release_at"):
            if key == "storage_release_at" and job["storage_node"] < 0:
                continue  # Preserve the native no-storage sentinel.
            job[key] = round(job[key] + delta, 6)
            if job[key] < 0:
                raise ValueError("spi_parents:negative_time_requires_new_preregistration")
        counts[ref] = counts.get(ref, 0) + 1
        crosswalk.append({"business_bag_id": identity, "flight_ref": ref, "shift_seconds": delta})
    if set(counts) != set(shifts):
        raise ValueError("spi_parents:complete_parent_group_coverage")
    parent = {**public_registration(seed, shift_digest=digest(shifts), rollout_round=rollout_round),
              "fleet": 22, "layout_seed": 1701, "static_layout_order": base["static_layout_order"],
              "offered_count": len(data["jobs"]), "jobs_digest": digest(data["jobs"]),
              "spi_domain": copy.deepcopy(DOMAIN)}
    evidence = {"schema": "g31.joint_whole_group_parent_generation.v1",
                "parent": parent, "source_private_labels_sha256": LABEL_SHA256,
                "group_shifts": shifts, "group_counts": counts,
                "private_business_group_crosswalk": crosswalk,
                "private_generation_only_never_actor_input": True,
                "independent_real_airport_days": 0,
                "new_flight_groups_invented": False,
                "split_unit": "entire synthetic parent plan; base historical groups remain shared",
                "forecast_parameters_fit_on_new_jobs": False}
    return data, parent, evidence


def registry():
    return {"schema": "g31.joint_parent_registration.v1", "namespace": NAMESPACE,
            "splits": {str(seed): split for seed, split in SPLITS.items()},
            "sampling": SAMPLING, "domain": copy.deepcopy(DOMAIN),
            "source_private_labels_sha256": LABEL_SHA256,
            "test_materialization_requires_frozen_champions": True,
            "physical_and_service_contract_unchanged_across_same_parent": True,
            "new_plan_is_explicit_b1_inference_domain_not_training_plan_relabel": True,
            "round1_is_replay_of_same_train_dev_parent_plan_at_later_declared_calendar": True,
            "calendar_offsets_from_source_day": {
                "round0_train_dev": "train: index; dev: 40 + index",
                "round1_train_dev": "train: 20 + index; dev: 40 + index",
                "formal_test": "60 + test_index"},
            "independent_real_airport_days": 0}
