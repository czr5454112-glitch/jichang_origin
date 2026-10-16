from copy import deepcopy
import gc
import random
import weakref

import pytest

from scripts.experiments.g31_ics_circulation import protocol_control as protocol
from scripts.experiments.g31_ics_circulation import regional_path_pool as m


def observation():
    return {"now": .2, "owner_id": "A", "jobs": [
        {"business_bag_id": "J", "destination": 3, "storage_node": -1, "allow_suffix_reroute": True}],
        "trays": [{"tray_id": "T", "node": 0, "mode": "loaded", "edge_to": -1,
            "business_bag_id": "J", "generation": 1, "traversal_id": 0, "committed_prefix": [0], "available_at": .3}],
        "node_records": [(n, 1, .1, n, 0, []) for n in range(4)],
        "edge_records": [(0, 1, 1., 1.), (0, 2, 1., 1.), (1, 3, 1., 1.), (2, 3, 1., 1.)],
        "edge_contracts": [{"from": u, "to": v, "capacity": 1} for u,v in ((0,1),(0,2),(1,3),(2,3))],
        "node_contracts": [{"node": n, "zone": "A", "resource_owner": "A", "capacity": 2, "occupancy": 0} for n in range(4)],
        "known_faults": [], "delivered_messages": []}


@pytest.mark.parametrize("seed",range(20))
def test_seeded_graphs_all_pairs_and_changed_occupancy_match_original(seed):
    rng=random.Random(seed);obs=observation();n=9
    obs["node_records"]=[(i,1,rng.choice([.001,.1,.2,1.,1e6]),0,0,[]) for i in range(n)]
    obs["node_contracts"]=[{"node":i,"occupancy":rng.randrange(4)} for i in range(n)]
    obs["edge_records"]=[(u,v,rng.choice([.001,.1,.2,1.,1e-8,1e6]),rng.choice([.1,1.,3.]))
        for u in range(n) for v in range(n) if u!=v and rng.random()<.25]
    obs["edge_contracts"]=[{"from":u,"to":v,"capacity":rng.choice([0,1,1])} for u,v,_,_ in obs["edge_records"]]
    obs["known_faults"]=[{"from":u,"to":v,"active":rng.choice([True,False])} for u,v,_,_ in obs["edge_records"][::6]]
    pool=m.RegionalPathPool(max_paths_per_graph=100)
    for activation in range(3):
        current=deepcopy(obs);current["now"]+=activation
        if activation==2:current["node_contracts"][0]["occupancy"]+=5
        old=m.OriginalRouting(current);new=pool.handle(current);before=deepcopy(current)
        for source in range(n):
            for goal in range(n):assert new.path(current,source,goal)==old.path(current,source,goal)
        assert current==before
    assert pool.counts["cross_activation_hits"]==n*n


def test_fresh_handles_share_only_same_input_paths_and_keep_clock_guard():
    pool=m.RegionalPathPool();a=observation();h=pool.handle(a)
    expected=h.path(a,0,3);assert h.path(a,0,3)==expected
    b=deepcopy(a);b["now"]=12.;g=pool.handle(b)
    assert g is not h and g.path(b,0,3) is expected
    assert pool.counts["cross_activation_hits"]==1 and pool.counts["local_hits"]==1
    with pytest.raises(ValueError,match="routing_observation_mismatch"):g.path(deepcopy(b),0,3)
    b["now"]+=1
    with pytest.raises(ValueError,match="routing_observation_mismatch"):g.path(b,0,3)


@pytest.mark.parametrize("change",["occupancy","service","length","speed","capacity","fault","owner",
    "node_order","service_order","edge_order","contract_order","occupancy_type","signed_zero"])
def test_every_consumed_input_or_order_change_invalidates(change):
    a=observation();b=deepcopy(a)
    if change=="occupancy":b["node_contracts"][1]["occupancy"]=99
    elif change=="service":b["node_records"][1]=(1,1,20.,1,0,[])
    elif change=="length":b["edge_records"][0]=(0,1,20.,1.)
    elif change=="speed":b["edge_records"][0]=(0,1,1.,.1)
    elif change=="capacity":b["edge_contracts"][0]["capacity"]=0
    elif change=="fault":b["known_faults"]=[{"from":0,"to":1,"active":True}]
    elif change=="owner":b["owner_id"]="B"
    elif change=="node_order":b["node_contracts"].reverse()
    elif change=="service_order":b["node_records"].reverse()
    elif change=="edge_order":b["edge_records"].reverse()
    elif change=="contract_order":b["edge_contracts"].reverse()
    elif change=="occupancy_type":b["node_contracts"][1]["occupancy"]=0.
    else:a["node_contracts"][1]["occupancy"]=0.;b["node_contracts"][1]["occupancy"]=-0.
    assert m.public_routing_key(a)!=m.public_routing_key(b)
    pool=m.RegionalPathPool();pool.handle(a).path(a,0,3)
    assert pool.handle(b).path(b,0,3)==m.OriginalRouting(b).path(b,0,3)
    assert pool.counts["path_misses"]==2 and pool.counts["cross_activation_hits"]==0


def test_time_jobs_ack_and_forecast_metadata_are_not_path_dependencies():
    a=observation();b=deepcopy(a);b.update(now=99.,jobs=[],trays=[],delivered_messages=[{"kind":"arbitrary"}])
    assert m.public_routing_key(a)==m.public_routing_key(b)


def outcome(handle,obs,source=0,goal=3):
    try:return ("value",handle.path(obs,source,goal))
    except Exception as error:return (type(error),error.args)


@pytest.mark.parametrize("defect",["missing_edges","duplicate_node","boolean_occupancy","nan_occupancy","zero_speed","missing_node","unknown_goal","boolean_source"])
def test_unsupported_or_invalid_input_uses_original_exception_or_result(defect):
    obs=observation();source,goal=0,3
    if defect=="missing_edges":del obs["edge_records"]
    elif defect=="duplicate_node":obs["node_contracts"].append(deepcopy(obs["node_contracts"][0]))
    elif defect=="boolean_occupancy":obs["node_contracts"][1]["occupancy"]=True
    elif defect=="nan_occupancy":obs["node_contracts"][1]["occupancy"]=float("nan")
    elif defect=="zero_speed":obs["edge_records"][0]=(0,1,1.,0.)
    elif defect=="missing_node":obs["node_contracts"].pop()
    elif defect=="unknown_goal":goal=99
    else:source=False
    pool=m.RegionalPathPool();assert outcome(pool.handle(obs),obs,source,goal)==outcome(m.OriginalRouting(obs),obs,source,goal)
    assert pool.snapshot()["resident_paths"]==0 and pool.counts["fallback_calls"]==1


def test_lazy_unused_handle_never_reads_missing_graph():
    pool=m.RegionalPathPool();pool.handle({"now":0.})
    assert pool.counts["key_builds"]==0


def test_unsupported_mapping_keeps_original_read_count_and_result():
    class CountingDict(dict):
        reads=0
        def __getitem__(self,key):
            if key=="now":self.reads+=1
            return super().__getitem__(key)
    old=CountingDict(observation());new=CountingDict(observation())
    original=m.OriginalRouting(old);pool=m.RegionalPathPool();pooled=pool.handle(new)
    assert original.path(old,0,3)==pooled.path(new,0,3)
    assert old.reads==new.reads==2
    assert pool.counts["key_builds"]==0 and pool.counts["fallback_calls"]==1


def test_pool_bounds_paths_graphs_and_caches_unreachable_empty_tuple():
    pool=m.RegionalPathPool(max_graphs=2,max_paths_per_graph=2)
    for activation in range(4):
        obs=observation();obs["node_contracts"][1]["occupancy"]=activation
        handle=pool.handle(obs)
        for source,goal in ((3,0),(0,3),(1,3)):handle.path(obs,source,goal)
        assert pool.snapshot()["resident_graphs"]<=2 and pool.snapshot()["resident_paths"]<=4
    assert pool.counts["graph_evictions"]==2 and pool.counts["path_evictions"]==4
    obs=observation();pool=m.RegionalPathPool();assert pool.handle(obs).path(obs,3,0)==()
    second=deepcopy(obs);assert pool.handle(second).path(second,3,0)==()
    assert pool.counts["cross_activation_hits"]==1


def test_pool_does_not_keep_observation_payload_alive():
    class Marker:pass
    payload=Marker();ref=weakref.ref(payload);obs=observation();obs["jobs"].append(payload)
    pool=m.RegionalPathPool();handle=pool.handle(obs);handle.path(obs,0,3)
    del payload,obs,handle;gc.collect()
    assert ref() is None and pool.snapshot()["resident_paths"]==1


def test_evicted_graph_keeps_live_handle_correct_without_reinserting_old_observation():
    pool=m.RegionalPathPool(max_graphs=1,max_paths_per_graph=2)
    first=observation();handle=pool.handle(first);handle.path(first,0,3)
    changed=deepcopy(first);changed["node_contracts"][1]["occupancy"]=10
    other=pool.handle(changed);other.path(changed,0,3)
    assert handle.path(first,1,3)==m.OriginalRouting(first).path(first,1,3)
    assert other.path(changed,1,3)==m.OriginalRouting(changed).path(changed,1,3)
    assert pool.snapshot()["resident_graphs"]==1 and pool.snapshot()["resident_paths"]==2
    assert pool.counts["graph_evictions"]==1


def test_same_timestamp_new_handle_rechecks_actual_dependencies():
    pool=m.RegionalPathPool();first=observation()
    assert pool.handle(first).path(first,0,3)==(0,1,3)
    changed=deepcopy(first);changed["edge_contracts"][0]["capacity"]=0
    assert changed["now"]==first["now"]
    assert pool.handle(changed).path(changed,0,3)==(0,2,3)
    assert pool.counts["cross_activation_hits"]==0


class Session:
    def __init__(self,reject):self.physical_time=.2;self.reject=reject
    def submit_protocol_command(self,payload):return {"status":"rejected" if self.reject else "pending","reason":"fixture"}


@pytest.mark.parametrize("reject",[True,False])
def test_installed_factory_preserves_service_actions_state_and_serialized_routes(reject):
    def execute(enabled):
        client=protocol.ProtocolClient(Session(reject));state={"routes":{},"forecasts":{}};records=[]
        def invoke():
            for now in (.2,.4,2.):
                obs=observation();obs["now"]=now;client.session.physical_time=now
                records.extend(protocol._publish_services(client,"A",state,command_delay=.01,publication_delay=.01,
                    routes=True,forecasts=True,lease_seconds=5.,observation=obs))
        if enabled:
            with m.installed_regional_path_pool() as pool:
                invoke();assert pool.counts["cross_activation_hits"]>0
        else:invoke()
        calls=[{k:v for k,v in row.items() if k!="submit_compute_ms"} for row in client.calls]
        return records,state,client.state,calls
    assert execute(False)==execute(True)


def test_installation_is_local_non_nested_and_restored_on_exception():
    original=protocol._ObservationRouting
    with pytest.raises(RuntimeError,match="fixture"):
        with m.installed_regional_path_pool() as pool:
            assert protocol._ObservationRouting is not original
            with pytest.raises(ValueError,match="another_installation"): 
                with m.installed_regional_path_pool():pass
            raise RuntimeError("fixture")
    assert protocol._ObservationRouting is original and pool.snapshot()["resident_paths"]==0
