"""Conditional common-future experiments on frozen, genuine loaded cursors.

Sampling and evaluation are offline.  Only the cloned event queue receives a
sampled tape; the original published forecasts and controller remain intact.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, replace
import random

from .network_role_labels import validate_tape
from .physical_observation import InstantPhysicalCursorSimulation
from .role_coverage import digest
from .routing_cache_contract import routing_cache_state
from .run_same_zone_supply import exact_json_value
from .same_zone_labels import (LABEL_BUDGET, TAIL_CAP, active_continuation_binding,
    pending_future, restore_matching_continuation, run_cycle, validate_checkpoint_binding)


SCENE_SEEDS = {"cross_cycle": 23011, "counterflow": 23029, "near_full": 23041}
BLOCKS = 2
SIZES = (2, 8, 32)
JITTER = (-2, 0, 2)
EVALUATION_CONTRACT = {"minimum_offset": 80, "tail_cap": TAIL_CAP,
    "budget": asdict(LABEL_BUDGET), "stop": "full ledger and certified controller quiescence",
    "observation": "legacy compatibility hash plus detached instantaneous physical observations v1"}


def canonical_tape(tape):
    return tuple(sorted(tape, key=lambda b: (b.arrival, b.bag_id)))


def tape_sha(tape):
    return digest([asdict(b) for b in canonical_tape(tape)])


def select_strata(collections):
    """Read attempt metadata only; never inspect cost, tape or successful labels."""
    inventory, cells, selected, zeros = [], [], {}, []
    for scene in SCENE_SEEDS:
        rows = collections[scene]
        if isinstance(rows, dict):
            rows = rows["attempts"]
        rows = sorted(rows, key=lambda r: (r["time"], r["decision_index"]))
        for row in rows:
            # Copy only the source attempt. No result or pending-task information
            # is an input to stratification.
            item = deepcopy(row)
            item["scene"] = scene
            item["state_key"] = f"{scene}_d{row['decision_index']:04d}"
            inventory.append(item)
            if row["candidate_count"] == 0:
                zeros.append(item)
        for role in ("origin", "continuation"):
            for low, high in ((0, 40), (40, 80), (80, None)):
                eligible = [r for r in inventory if r["scene"] == scene and r["role"] == role
                    and r["time"] >= low and (high is None or r["time"] < high)]
                first = eligible[0] if eligible else None
                cell = {"scene": scene, "role": role, "time_low": low, "time_high": high,
                    "eligible_attempts": len(eligible), "selected_state": None if first is None else first["state_key"]}
                cells.append(cell)
                if first is not None:
                    selected[first["state_key"]] = {**first, "selection_reason": "first_attempt_in_public_stratum"}
    for row in zeros:
        selected.setdefault(row["state_key"], {**row, "selection_reason": "all_zero_attempts_appendix"})
    return {"attempts": inventory, "cells": cells, "selected": list(selected.values()), "zero_attempts": zeros,
        "counts": {"attempts": len(inventory), "nonempty": sum(r["candidate_count"] > 0 for r in inventory),
            "zero": len(zeros), "selected_records": len(selected),
            "selected_nonempty": sum(r["candidate_count"] > 0 for r in selected.values()),
            "missing_cells": sum(r["selected_state"] is None for r in cells)}}


def conditional_support(bag, now):
    """Discrete prior conditional on this soft task not yet being observed.

    Prior mass is cancel=3/24, each jitter=7/24. Remove observed-by-now
    noncancel outcomes and normalize the remaining integer masses, with no
    clipping and no rejection draws. This is not a calibrated posterior.
    """
    if bag.arrival <= now:
        raise ValueError("original pending arrival must be strictly after now")
    if bag.protected:
        return {"protected": True, "total_mass": 1,
            "outcomes": [{"cancel": False, "jitter": 0, "mass": 1}]}
    outcomes = [{"cancel": True, "jitter": None, "mass": 3}]
    outcomes += [{"cancel": False, "jitter": j, "mass": 7}
        for j in JITTER if bag.arrival + j > now]
    return {"protected": False, "prior_total_mass": 24,
        "total_mass": sum(r["mass"] for r in outcomes), "outcomes": outcomes}


def validate_original_pending(state, pending):
    pending = tuple(pending)
    ids = [b.bag_id for b in pending]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate original pending identity")
    if any(b.bag_id in state.bags for b in pending):
        raise ValueError("observed task cannot be sampled as pending")
    if any(b.arrival <= state.now for b in pending):
        raise ValueError("original pending arrival must be strictly after now")
    validate_tape(pending, state)
    return canonical_tape(pending)


def validate_sampled_future(state, original, sampled):
    original = validate_original_pending(state, original)
    sampled = tuple(sampled)
    ids = [b.bag_id for b in sampled]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate sampled identity")
    original_by_id, sampled_by_id = ({b.bag_id: b for b in rows} for rows in (original, sampled))
    if set(sampled_by_id) - set(original_by_id):
        raise ValueError("sampled future introduced a new identity")
    for bag in original:
        value = sampled_by_id.get(bag.bag_id)
        if bag.protected:
            if value != bag:
                raise ValueError("protected pending task must remain exact")
        elif value is not None:
            jitter = value.arrival - bag.arrival
            if jitter not in JITTER or value.arrival <= state.now or value != replace(
                    bag, arrival=bag.arrival + jitter, deadline=bag.deadline + jitter):
                raise ValueError("sample violates conditional OD/identity/slack/jitter law")
    validate_tape(sampled, state)
    return canonical_tape(sampled)


def sample_conditional_futures(state, pending, seed, count=32):
    if type(seed) is not int or type(count) is not int or count < 1:
        raise ValueError("integer seed and positive count required")
    original = validate_original_pending(state, pending)
    rng, tapes = random.Random(seed), []
    for _ in range(count):
        tasks = []
        for bag in sorted(original, key=lambda b: b.bag_id):
            if bag.protected:
                tasks.append(bag)  # fixed tasks consume no random draws
                continue
            support = conditional_support(bag, state.now)
            draw = rng.randrange(support["total_mass"])
            for outcome in support["outcomes"]:
                draw -= outcome["mass"]
                if draw < 0:
                    if not outcome["cancel"]:
                        j = outcome["jitter"]
                        tasks.append(replace(bag, arrival=bag.arrival+j, deadline=bag.deadline+j))
                    break
        tapes.append(validate_sampled_future(state, original, tasks))
    return tuple(tapes)


def block_seed(scene, decision_index, block):
    if scene not in SCENE_SEEDS or type(block) is not int or not 0 <= block < BLOCKS:
        raise ValueError("unknown fixed scene/replicate block")
    return SCENE_SEEDS[scene] + 1000003 * block + 101 * decision_index


def continuation_observation(engine):
    return {"state_sha256": digest(asdict(engine.state)), "cursor": asdict(engine._cursor),
        "phase": engine._phase, "next_slow_trigger_at": engine.slow_controller.next_trigger_at,
        "cache": routing_cache_state(engine), "continuation": active_continuation_binding(engine),
        "published_forecasts": [asdict(f) for f in engine.slow_controller.controller.forecasts],
        "selector_history": deepcopy(engine.route_selector.history),
        "slow_history": deepcopy(engine.slow_controller.history), "event_trace": deepcopy(engine._trace)}


def restore_sampled_continuation(payload, metadata, sampled):
    original_engine = restore_matching_continuation(payload, metadata)
    if original_engine._phase != "routes" or original_engine._cursor.pending_options is None:
        raise ValueError("sampling requires an actual loaded cursor after arrivals were prepared")
    tape = validate_sampled_future(original_engine.state, payload["future"], sampled)
    before = continuation_observation(original_engine)
    engine = InstantPhysicalCursorSimulation.from_checkpoint(payload["checkpoint"])
    engine._arrivals = defaultdict(list)
    for bag in tape:
        engine._arrivals[bag.arrival].append(bag)
    after = continuation_observation(engine)
    checks = {key: exact_json_value(before[key], after[key]) for key in before}
    if not all(checks.values()):
        raise ValueError("tape replacement changed non-future continuation state")
    if pending_future(engine) != tape:
        raise ValueError("event queue does not equal sampled tape")
    return engine, {"unchanged": checks, "original_future_sha256": tape_sha(payload["future"]),
        "sampled_future_sha256": tape_sha(tape), "original_checkpoint_fingerprint": metadata["checkpoint_fingerprint"],
        "active_continuation_sha256": metadata["active_continuation"]["sha256"],
        "observer": "frozen InstantPhysicalCursorSimulation, no policy input or checkpoint side-channel"}


def memo_key(checkpoint_sha, candidate_index, candidate_key, tape, continuation_sha):
    if type(candidate_index) is not int or candidate_index < 0 or not all(
            isinstance(v, str) and v for v in (checkpoint_sha, candidate_key, continuation_sha)):
        raise ValueError("complete state/action/continuation identity required for memo")
    return digest({"checkpoint_sha256": checkpoint_sha, "candidate_index": candidate_index,
        "candidate_key": candidate_key, "future_sha256": tape_sha(tape),
        "continuation_sha256": continuation_sha, "evaluation_contract": EVALUATION_CONTRACT})


def run_sampled_branch(payload, metadata, sampled, *, candidate_index, minimum_observation_at=None,
                       budget=LABEL_BUDGET, tail_cap=TAIL_CAP):
    engine, binding = restore_sampled_continuation(payload, metadata, sampled)
    expected = {**engine.state.bags, **{b.bag_id: b for b in sampled}}
    minimum = engine.state.now + 80 if minimum_observation_at is None else minimum_observation_at
    outcome = run_cycle(engine, expected, minimum_observation_at=minimum,
        forced_index=candidate_index, budget=budget, tail_cap=tail_cap)
    outcome.update(active_continuation=metadata["active_continuation"], sampled_future=[asdict(b) for b in canonical_tape(sampled)],
        future_replacement_binding=binding,
        checkpoint_binding_checks=validate_checkpoint_binding(payload["checkpoint"], metadata),
        instant_physical_tick_trace=engine.instant_physical_ticks,
        legacy_trace_limitation="physical_tick_trace is frozen legacy alias-compatible representation; instantaneous values are in instant_physical_tick_trace")
    return outcome
