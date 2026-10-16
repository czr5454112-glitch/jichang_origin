"""Original-delay chain guards and finite-domain completeness at budget edges."""
from scripts.experiments.g31_ics_circulation import original_tie_path_enumeration as enumeration
from scripts.experiments.g31_ics_circulation import research_original_tie_chain as driver


def test_only_two_second_nodes_can_branch_and_simple_cycles_are_counted():
    graph = {0: [(1, 1.), (2, 2.)], 1: [(2, 1.), (3, 1.)], 2: [(0, 1.), (3, 2.)], 3: []}
    row = enumeration.enumerate_paths(graph, {0: 2., 1: 1.5, 2: 2., 3: 1.}, 0, 3)
    assert row["coverage_complete"] and {tuple(p["path"]) for p in row["paths"]} == {(0, 1, 3), (0, 2, 3)}
    assert row["rejected_extensions"]["simple_prefix_cycle"] == 1
    assert all(c["from"] != 1 for p in row["paths"] for c in p["commands"])


def test_budget_boundary_retains_pending_stack_but_exact_natural_end_is_complete():
    graph = {0: [(1, 1.)], 1: []}; services = {0: 2., 1: 2.}
    partial = enumeration.enumerate_paths(graph, services, 0, 1, max_states=1)
    complete = enumeration.enumerate_paths(graph, services, 0, 1, max_states=2)
    assert partial["status"] == "unknown_budget_frontier" and len(partial["frontier"]) == 1
    assert complete["coverage_complete"] and complete["candidate_path_count"] == 1 and complete["frontier"] == []


class Client:
    def __init__(self): self.state = {"outbox": {}}; self.calls = []
    def submit(self, owner, kind, payload, *, request_id):
        self.calls.append(payload); self.state["outbox"][request_id] = {}
        return request_id, {"status": "pending"}


def view(node=1, prefix=(0, 1), edge_to=-1):
    return {"now": 10., "owner_id": "A", "trays": [{"business_bag_id": driver.TARGET, "tray_id": "L", "mode": "loaded",
        "node": node, "edge_from": node if edge_to >= 0 else -1, "edge_to": edge_to,
        "generation": 1, "traversal_id": 1, "committed_prefix": list(prefix)}],
        "node_contracts": [{"node": 1, "resource_owner": "A"}],
        "jobs": [{"business_bag_id": driver.TARGET, "storage_node": 53, "storage_released_at": -1}]}


def test_chain_never_preissues_from_future_node_or_uses_static_generation():
    chain = driver.ChainIntent([0, 1, 2, 53], [{"from": 1, "next": 2}]); client = Client()
    chain.observe(view(node=0, prefix=(0,), edge_to=1), client)
    assert client.calls == []
    chain.observe(view(), client)
    assert len(client.calls) == 1 and client.calls[0]["message_delay"] == 2.
    assert client.calls[0]["expected_traversal"] == 1 and client.calls[0]["expected_generation"] == 1


def test_delivered_updated_ack_without_actual_edge_does_not_pass():
    chain = driver.ChainIntent([0, 1, 2, 53], [{"from": 1, "next": 2}]); client = Client(); chain.observe(view(), client)
    client.state["outbox"][chain.request_id] = {"client_view": {"last_delivered_ack": {"status": "updated", "delivered_at": 11.}}}
    chain.observe(view(), client)
    assert chain.stage == 0  # future ACK is not yet usable
    current = view(); current["now"] = 11.; chain.observe(current, client)
    assert chain.stage == 1 and chain.status != "all_four_intents_and_edges_observed"
    current = view(edge_to=2); current["now"] = 11.; chain.observe(current, client)
    assert chain.status == "all_four_intents_and_edges_observed"


def test_observed_uncommanded_path_divergence_stops_without_new_intent():
    chain = driver.ChainIntent([0, 1, 2, 53], [{"from": 1, "next": 2}]); client = Client()
    chain.observe(view(edge_to=27), client)
    assert chain.status == "observed_path_divergence" and client.calls == []
