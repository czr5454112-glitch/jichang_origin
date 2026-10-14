import pytest

from scripts.experiments.g31_ics_circulation.boundary_reference import (
    ObligationWindow as W, capacity_violations, compare_boundaries,
)


def test_task_precedence_dag_misses_shared_receiving_and_supply_boundary():
    old = [W("bag_A", "reception_B", 0, 2), W("bag_B", "reception_B", 2, 4)]
    new = [W("bag_A", "reception_B", 0, 3)]
    result = compare_boundaries(old, new, changed_tasks={"bag_A"}, capacities={"reception_B": 1},
                                task_successors={"bag_B": {"source_C_service"}},
                                complete_hard_obligation_scope=True)
    assert result["task_dag_domain"] == ["bag_A"]
    assert result["slack_checked_repair_domain"] == ["bag_A", "bag_B", "source_C_service"]
    assert result["patch_capacity_status"] == "conflict"
    assert result["requires_native_replay"]


def test_verified_slack_absorbs_change_without_inventing_policy_independence():
    old = [W("A", "edge", 0, 2), W("B", "edge", 4, 5)]
    new = [W("A", "edge", 0, 3)]
    result = compare_boundaries(old, new, changed_tasks={"A"}, capacities={"edge": 1},
                                task_successors={}, complete_hard_obligation_scope=True)
    assert result["resource_transitive_domain"] == ["A", "B"]
    assert result["slack_checked_repair_domain"] == ["A"]
    assert result["patch_capacity_status"] == "compatible_with_frozen_hard_windows"
    assert result["external_policy_independence"] == "unknown"


def test_individually_safe_repairs_conflict_jointly():
    old = [W("A", "berth", 0, 1), W("B", "berth", 3, 4)]
    a, b = [W("A", "berth", 1, 3)], [W("B", "berth", 1, 3)]
    for seed, patch in [({"A"}, a), ({"B"}, b)]:
        assert not compare_boundaries(old, patch, changed_tasks=seed, capacities={"berth": 1},
                                      task_successors={})["conflicts"]
    both = compare_boundaries(old, a + b, changed_tasks={"A", "B"}, capacities={"berth": 1}, task_successors={})
    assert both["conflicts"][0]["used"] == 2


def test_entry_tail_is_separate_obligation_after_physical_edge_exit():
    old = [W("old_traversal", "edge_capacity", 0, 1),
           W("old_traversal", "headway", 0, 5), W("next_traversal", "headway", 6, 11)]
    new = [W("next_traversal", "headway", 2, 7)]
    result = compare_boundaries(old, new, changed_tasks={"next_traversal"},
                                capacities={"edge_capacity": 1, "headway": 1}, task_successors={})
    assert result["conflicts"][0]["resource"] == "headway"
    assert "old_traversal" in result["slack_checked_repair_domain"]


def test_release_before_acquire_and_unknown_incomplete_scope():
    assert not capacity_violations([W("A", "r", 0, 1), W("B", "r", 1, 2)], {"r": 1})
    result = compare_boundaries([W("A", "r", 0, 1)], [W("A", "r", 0, 2)],
                                changed_tasks={"A"}, capacities={"r": 1}, task_successors={})
    assert result["patch_capacity_status"] == "unknown_scope_incomplete"


def test_actual_policy_read_set_expands_even_with_free_capacity():
    result = compare_boundaries([W("A", "r", 0, 1)], [W("A", "r", 0, 2)],
                                changed_tasks={"A"}, capacities={"r": 1}, task_successors={},
                                policy_read_successors={"A": {"remote_dispatch"}},
                                complete_hard_obligation_scope=True)
    assert result["slack_checked_repair_domain"] == ["A", "remote_dispatch"]
    assert result["external_policy_independence"] == "only_declared_read_graph_checked"
