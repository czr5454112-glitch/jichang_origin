"""Official physical-default registration and small execution checks."""
from __future__ import annotations
import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from scripts.eval import g31_continuous_adapter as adapter
from scripts.eval import run_g31_standard as standard


def record(path):
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def dump(path,value):
    path.write_text(json.dumps(value)+"\n",encoding="utf-8")
    return path


@pytest.fixture
def registered(tmp_path):
    """Small immutable input/build registry; prepare never loads this fake DLL."""
    nodes=[dict(location=0,service_time=0),dict(location=1,service_time=2),dict(location=2,service_time=0)]
    edges=[dict(start=0,end=1,length=2),dict(start=1,end=2,length=2)]
    profile=dump(tmp_path/"map.json",dict(nodes=nodes,edges=edges))
    row=dict(segment_id="0:direct",task_id=0,leg="direct",start=0,goal=2,
             pass_time=0,original_entry_time=0,std=100)
    canonical=tmp_path/"input.jsonl.gz"
    raw=(json.dumps(row)+"\n").encode()
    canonical.write_bytes(gzip.compress(raw,mtime=0))
    build=tmp_path/"build"; (build/"python").mkdir(parents=True);(build/"source").mkdir()
    binary=build/"python/g31_nowait.pyd";binary.write_bytes(b"never load in pure preparation")
    core=build/"source/core.cpp";core.write_bytes(b"registered source")
    dump(build/"build_receipt.json",dict(status="complete",source_sha256={"core.cpp":adapter.digest(core)},
                                       binaries={str(binary):adapter.digest(binary)}))
    controls=dump(tmp_path/"controls.json",dict(end_time=100,adaptive=False,min_depth=1,max_depth=1,congestion_weight=0))
    contract=dict(schema="g31.continuous.physical_contract.v1",execution_model=adapter.MODEL,
        status="explicit_candidate_not_promoted",selected_controls=None,default_binary=record(binary),native_source=record(core),
        speed_mps=2,fault_schedule="none",empty_trays=False,time_grid_seconds=1e-6,
        positive_node_service_seconds=2,edge_entry_headway_seconds=2,end_time=100,
        maps={"map2":dict(original_profile=record(profile),profile=record(profile))},
        cells={"map2_1x":dict(canonical={**record(canonical),"encoding":"gzip_jsonl", "content_sha256":hashlib.sha256(raw).hexdigest()},
                             business_denominator=1,segment_denominator=1)},claim_boundary="fixture, not performance promotion")
    contract_path=dump(tmp_path/"contract.json",contract)
    return dict(contract=contract,contract_path=contract_path,controls=controls,binary=binary,profile=profile,row=row)


def prepare(fixture):
    return adapter.prepare("map2",controls_path=fixture["controls"],contract_path=fixture["contract_path"])


def test_prepare_is_read_only_and_keeps_nominal_identity(registered,monkeypatch):
    monkeypatch.setattr(adapter,"load_native",lambda _:pytest.fail("prepare cannot load native"))
    result=prepare(registered)
    assert result["request"]["tasks"]==[dict(segment_id="0:direct",task_id=0,leg="direct",start=0,goal=2,release=0,deadline=100)]
    assert result["request"]["config"]["enable_inroute_replanning"] is True
    assert result["request"]["config"]["enable_ebs_predecessor_gate"] is True
    assert result["request"]["config"]["source_fifo_order"]=="canonical"
    assert result["selection"]["is_standard_selection"] is False
    assert result["selection"]["historical_profiles_preserved"] is True
    assert result["selection"]["performance_promoted"] is False
    assert "finish-admission" in result["selection"]["paper_tht_definition"]


def test_no_unselected_implicit_controls(registered):
    with pytest.raises(ValueError,match="explicit --controls"):
        adapter.prepare("map2",contract_path=registered["contract_path"])


@pytest.mark.parametrize("mutation",[
    {"interval_mode":"closed_legacy"},{"strict_endpoint_resources":False},
    {"edge_entry_headway_seconds":1.999999},{"enable_inroute_replanning":False},
    {"enable_ebs_predecessor_gate":False},{"terminal_reservation_service":False},
    {"time_grid_seconds":.001},{"unknown":1},{"congestion_weight":float("inf")},
    {"max_depth":True},{"retry_mode":"invented"},{"release_quantum":0},
    {"source_fifo_order":"activation"},
])
def test_invalid_or_weaker_controls_fail_closed(mutation):
    with pytest.raises(ValueError): adapter.validate_controls(mutation,98259)


def test_input_and_frozen_core_hashes_are_checked(registered):
    registered["profile"].write_text("changed",encoding="utf-8")
    with pytest.raises(ValueError,match="hash mismatch"): prepare(registered)


def test_service2_does_not_change_topology_or_zero_connectors():
    original=dict(nodes=[dict(location=0,service_time=0),dict(location=1,service_time=1.5)],
                  edges=[dict(start=0,end=1,length=2)])
    normalized=copy.deepcopy(original);normalized["nodes"][1]["service_time"]=2
    adapter.validate_profile(original,normalized)
    normalized["nodes"][0]["service_time"]=2
    with pytest.raises(ValueError,match="normalization"):adapter.validate_profile(original,normalized)
    normalized=copy.deepcopy(original);normalized["nodes"][1]["service_time"]=2
    normalized["edges"][0]["length"]=3
    with pytest.raises(ValueError,match="topology"):adapter.validate_profile(original,normalized)


def test_standard_dispatch_rejects_cross_model_options(registered):
    for changes in (dict(mode="legacy"),dict(same_hca_release=Path("release.csv"))):
        with pytest.raises(ValueError,match="cannot use legacy"):
            standard.prepare_request("map2",execution_model=adapter.MODEL,controls=registered["controls"],
                                     physical_contract=registered["contract_path"],**changes)
    with pytest.raises(ValueError,match="legacy waiting"):
        standard.prepare_request("map2",execution_model="legacy_waiting",controls=registered["controls"])
    request,selection=standard.prepare_request("map2",execution_model=adapter.MODEL,controls=registered["controls"],
                                             physical_contract=registered["contract_path"])
    assert selection["execution_model"]==adapter.MODEL and len(request["tasks"])==1


def test_execute_failure_remains_reviewable(registered,tmp_path,monkeypatch):
    prepared=prepare(registered)
    def fail(_):raise RuntimeError("native fixture failure")
    monkeypatch.setattr(adapter,"load_native",fail)
    # Source snapshots are real dependencies; only core fixture is synthetic.
    output=tmp_path/"failed"
    with pytest.raises(RuntimeError,match="native fixture failure"):adapter.execute(prepared,output)
    assert adapter.read(output/"manifest.json")["status"]=="failed"
    assert (output/"request.json.gz").is_file()
    with pytest.raises(FileExistsError):adapter.execute(prepared,output)


def test_adapter_actual_native_micro_and_tht(registered,tmp_path,monkeypatch):
    binary=adapter.ROOT/"build/g31_no_wait_006/python/g31_nowait.cp311-win_amd64.pyd"
    if not binary.is_file(): pytest.skip("optional already-built native 006 micro check")
    native=adapter.load_native(binary)
    monkeypatch.setattr(adapter,"load_native",lambda _:native)
    prepared=prepare(registered)
    output=tmp_path/"native_micro"
    manifest=adapter.execute(prepared,output)
    assert manifest["status"]=="complete" and manifest["audits_passed"]
    tht=adapter.read(output/"tht_audit.json")
    assert tht["paper_tht_total_seconds"]==4
    assert tht["paper_tht_mean_per_business_seconds"]==4
    assert tht["user_tht_total_seconds"]==4
    assert tht["user_tht_full_population_available"]
    assert adapter.read(output/"business_audit.json")["completed_businesses"]==1
    assert adapter.read(output/"rolling_replay.json")["passed"]
    assert adapter.read(output/"source_policy_audit.json")["passed"]
    assert (output/"rolling_events.jsonl").is_file()


def test_stable_registry_has_no_runtime_outputs_dependency():
    contract=adapter.read(adapter.DEFAULT_CONTRACT)
    records=[contract["native_source"],contract["selected_controls"]]
    records += [r for m in contract["maps"].values() for r in (m["profile"],m["original_profile"])]
    records += [c["canonical"] for c in contract["cells"].values()]
    assert all("outputs/" not in r["path"] and "draft" not in r["path"] for r in records)
    assert contract["physics_default"] is True and contract["performance_promoted"] is False
    controls=adapter.read(adapter.registered_file(contract["selected_controls"]))
    assert controls["congestion_weight"]==0 and controls["max_route_excess_seconds"]==120
    assert controls["route_excess_retry_relaxation_rate"]==1
    assert adapter.digest(adapter.ROOT/contract["native_source"]["path"])==contract["native_source"]["sha256"]


def test_retry_relaxation_controls_need_finite_base():
    with pytest.raises(ValueError,match="finite base"):
        adapter.validate_controls(dict(route_excess_retry_relaxation_rate=1),98259)
    assert adapter.validate_controls(dict(route_excess_retry_relaxation_rate=1,max_route_excess_seconds=120),98259)["route_excess_retry_relaxation_rate"]==1


def test_auditor_source_drift_rejected_before_replay(tmp_path):
    (tmp_path/"headway_audit.py").write_text("not the reviewed source",encoding="utf-8")
    with pytest.raises(ValueError,match="auditor source changed before"):
        adapter.verified_auditors(tmp_path)


def test_new_standard_run_dispatch_and_evidence(registered,tmp_path,monkeypatch):
    called=[]
    def execute(prepared,output):
        called.append(prepared)
        (output/"standard_sources").mkdir(parents=True)
        return {"status":"complete"}
    monkeypatch.setattr(adapter,"execute",execute)
    output=tmp_path/"new_standard"
    args=standard.parser().parse_args(["run","--map","map2","--execution-model",adapter.MODEL,
        "--controls",str(registered["controls"]),"--physical-contract",str(registered["contract_path"]),
        "--output",str(output)])
    standard.run(args)
    assert len(called)==1
    selection=adapter.read(output/"standard_selection.json")
    assert selection["is_standard_selection"] is False and selection["execution_status"]=="complete"
    assert (output/"standard_sources/run_g31_standard.py").is_file()


def register_physical_default(fixture):
    contract=copy.deepcopy(fixture["contract"])
    contract.update(physics_default=True,performance_promoted=False,
                    selected_controls=record(fixture["controls"]),standard_id="fixture_physical_default")
    dump(fixture["contract_path"],contract)


def test_cli_and_python_api_default_to_continuous(registered,monkeypatch):
    register_physical_default(registered)
    assert standard.parser().parse_args(["inspect","--map","map2"]).execution_model==adapter.MODEL
    monkeypatch.setattr(adapter,"load_native",lambda _:pytest.fail("prepare must not load native"))
    request,selection=standard.prepare_request("map2",physical_contract=registered["contract_path"])
    assert request["config"]["interval_mode"]=="half_open"
    assert selection["physics_default"] and selection["is_standard_selection"]
    assert selection["controls_match_registered_default"] and not selection["performance_promoted"]


def test_missing_namespace_model_uses_physical_default(registered,tmp_path,monkeypatch):
    register_physical_default(registered)
    called=[]
    def execute(prepared,output):
        called.append(prepared)
        (output/"standard_sources").mkdir(parents=True)
        return {"status":"complete"}
    monkeypatch.setattr(adapter,"execute",execute)
    args=standard.parser().parse_args(["run","--map","map2","--physical-contract",str(registered["contract_path"]),
                                      "--output",str(tmp_path/"namespace_default")])
    for name in ("execution_model","controls","scale"): delattr(args,name)
    standard.run(args)
    assert len(called)==1 and args.execution_model==adapter.MODEL
    assert called[0]["selection"]["is_standard_selection"]


def test_default_override_is_recorded_without_performance_promotion(registered,tmp_path):
    register_physical_default(registered)
    override=dump(tmp_path/"override.json",dict(end_time=100,congestion_weight=1))
    result=adapter.prepare("map2",controls_path=override,contract_path=registered["contract_path"])
    assert result["selection"]["physics_default"]
    assert not result["selection"]["controls_match_registered_default"]
    assert not result["selection"]["is_standard_selection"]
    assert not result["selection"]["performance_promoted"]


def test_registered_default_controls_hash_is_required(registered):
    register_physical_default(registered)
    registered["controls"].write_text("{}",encoding="utf-8")
    with pytest.raises(ValueError,match="hash mismatch"):
        adapter.prepare("map2",contract_path=registered["contract_path"])


def test_legacy_flags_without_explicit_model_do_not_silently_switch():
    with pytest.raises(ValueError,match="select --execution-model legacy_waiting explicitly"):
        standard.prepare_request("map2",mode="legacy")
