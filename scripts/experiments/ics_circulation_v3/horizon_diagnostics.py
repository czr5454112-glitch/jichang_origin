"""Multiple evaluation endpoints on one fixed-policy physical continuation.

Evaluation endpoints never change the controller's planning horizon. The
terminal-free view is arithmetic on the same outcomes, not a new controller.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict

from .role_coverage import CoverageCheckpoint, CursorSimulation
from .runtime import COST_WEIGHTS


def horizon_outcomes(checkpoint, candidate, future, offsets, *, continuation_selector=None):
    offsets = tuple(offsets)
    if (not offsets or any(type(h) is not int or h <= 0 for h in offsets)
            or tuple(sorted(set(offsets))) != offsets):
        raise ValueError("evaluation offsets must be strictly increasing positive integers")
    if not isinstance(checkpoint, CoverageCheckpoint) or checkpoint.cursor.pending_options is None:
        raise ValueError("need a pending decision checkpoint")
    ids = [b.bag_id for b in future]
    if len(set(ids)) != len(ids) or any(b.arrival <= checkpoint.state.now or b.bag_id in checkpoint.state.bags for b in future):
        raise ValueError("future contains observed, duplicate or nonfuture tasks")
    restored = checkpoint.clone()
    restored.base.pending_arrivals = defaultdict(list)
    for bag in future:
        restored.base.pending_arrivals[bag.arrival].append(bag)
    if continuation_selector is not None:
        restored.base.route_selector = deepcopy(continuation_selector)
    engine = CursorSimulation.from_checkpoint(restored)
    engine.choose_pending(candidate)
    start = checkpoint.state.now
    # result() is detached and does not add terminal costs to the running
    # ledger. Advancing past a reporting endpoint must equal a direct replay.
    return {h: engine.advance(start + h) for h in offsets}


def outcome_metrics(outcome):
    state = outcome.final_snapshot
    nonterminal = sum(value * COST_WEIGHTS[key] for key, value in outcome.cost_components.items()
                      if key not in {"terminal_backlog", "terminal_inflight"})
    terminal = sum(outcome.cost_components[key] * COST_WEIGHTS[key]
                   for key in ("terminal_backlog", "terminal_inflight"))
    if abs(nonterminal + terminal - outcome.total_cost) > 1e-8:
        raise ValueError("cost component accounting does not reconstruct total")
    return {"time": state.now, "total_cost": outcome.total_cost,
            "nonterminal_cost_same_trajectory": nonterminal, "terminal_cost": terminal,
            "cost_components": outcome.cost_components, "completed": outcome.completed,
            "uncompleted": list(outcome.uncompleted_bag_ids), "observed_bags": len(state.bags),
            "on_time": sum(k in outcome.completed and outcome.completed[k] <= b.deadline for k, b in state.bags.items()),
            "invariant_checks": outcome.invariant_checks,
            "policy_stats": {k: v for k, v in outcome.policy_stats.items() if not k.endswith("_ms")}}


def audit_old_twenty(old, actual, *, tolerance=1e-8):
    """Only historical physical fields, never nondeterministic timings."""
    return (not old["failed"]
            and abs(old["total_cost"] - actual["total_cost"]) <= tolerance
            and old["cost_components"] == actual["cost_components"]
            and old["completed"] == actual["completed"]
            and list(old["uncompleted"]) == list(actual["uncompleted"]))


def same_saved_decision(old, sample):
    """Bind recollection to physical/control evidence, not the instance hash.

    Runtime cache accounting is an explicitly different contract. Only its
    work meter and implementation/cache provenance may differ; old and new
    control parameters, selector identity, information and decisions may not.
    """
    from .role_coverage import sample_artifact
    new = sample_artifact(sample)
    # Normalize tuples without dropping or rounding any physical values.
    import json
    new = json.loads(json.dumps(new))
    fields = ("identity", "time", "version", "source_node", "role", "revisit", "band",
              "bag_id", "tray_id", "protected", "raw_candidate_count", "candidate_count",
              "candidate_stratum", "selector_called", "state_sha256", "cursor",
              "next_slow_trigger_at", "normal_keys", "features", "features_physical",
              "policy_sha", "state", "proposals")
    differences = [name for name in fields if new[name] != old[name]]
    for name in ("phase", "cursor", "accrued_cost", "next_slow_trigger_at", "slow_trigger_times"):
        if new["checkpoint_metadata"][name] != old["checkpoint_metadata"][name]:
            differences.append("checkpoint_metadata." + name)
    left, right = old["continuation_contract"], new["continuation_contract"]
    for name in ("spec", "information"):
        if left[name] != right[name]:
            differences.append("contract." + name)
    for name, value in left["continuation"].items():
        if name != "implementation_sha256" and right["continuation"].get(name) != value:
            differences.append("continuation." + name)
    return {"equal": not differences, "differences": differences,
            "old_checkpoint_audit_sha256": old["checkpoint_sha256"],
            "new_checkpoint_audit_sha256": new["checkpoint_sha256"],
            "old_search_work": old["search_work"], "new_search_work": new["search_work"],
            "current_contract": new["continuation_contract"],
            "excluded_identity_fields": ["checkpoint_sha256", "search_work", "implementation/cache provenance"]}
