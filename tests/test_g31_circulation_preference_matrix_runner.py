"""Pure checks only; saved native evidence is replayed, never rerun."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import research_native_preference_matrix as runner

ROOT = Path(__file__).resolve().parents[1]
SAVED = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014/native_preexisting_v3_bound_business_001/block1_load1/coordinate_strict.json.gz"
SAVED_SHA = "596a5950cf59c9e48a75fd82ae6c5c393d728a290e0f70361cf9b2da86ea9776"


@pytest.fixture
def physical_raw():
    assert hashlib.sha256(SAVED.read_bytes()).hexdigest() == SAVED_SHA
    return json.loads(gzip.decompress(SAVED.read_bytes()))


def vector(raw):
    request = next(c["request"] for c in raw["calls"] if c["kind"] == "transfer")
    return {"initial_action":"prefer_2","empty_departure":request["earliest_departure"],
            "return_delay":0.,"later_action":"prefer_8"}


def assessed(raw, selected=None):
    return runner.assess_cell(raw["input"],raw["result"],SimpleNamespace(rows=raw["outbox"],calls=raw["calls"]),
                              raw["continuation"],selected or vector(raw))


def test_saved_actual_prefer2_prefer8_has_matching_ack_and_edge(physical_raw):
    result = assessed(physical_raw)
    assert result["status"] == "assessed"
    assert result["initial_actual_next"] == 2 and result["first_reuse_actual_next"] == 8
    assert result["audit"]["status"] == "passed"


@pytest.mark.parametrize("mutation",["rejected","wrong_edge","wrong_command","wrong_return_delay","wrong_E_window","horizon","unfinished","bool_completion"])
def test_saved_physics_cannot_hide_unexecuted_or_incomplete_actions(physical_raw,mutation):
    raw = physical_raw
    choice = raw["continuation"]["route_choices"][0]
    if mutation == "rejected":raw["outbox"][choice["request_id"]]["ack"]["status"] = "rejected"
    elif mutation == "wrong_edge":
        next(e for e in raw["result"]["receipts"] if e["event"] == "EDGE_ENTER" and e["business_bag_id"] == "reuse1" and e["from"] == 7)["to"] = 3
    elif mutation == "wrong_command":raw["outbox"][choice["request_id"]]["request"]["next"] = 3
    elif mutation == "wrong_return_delay":raw["continuation"]["returns"][0]["selected_delay"] = .5
    elif mutation == "wrong_E_window":return assert_unknown(assessed(raw,{**vector(raw),"empty_departure":.11}))
    elif mutation == "horizon":raw["result"]["advance"]["horizon_complete"] = False
    elif mutation == "unfinished":raw["result"]["jobs"][0]["completed_at"] = -1.
    elif mutation == "bool_completion":raw["result"]["jobs"][0]["completed_at"] = True
    assert_unknown(assessed(raw))


def assert_unknown(result):
    assert result["status"] == "unknown_incomplete_or_unexecuted"


def test_default_does_not_relabel_an_explicit_route_command(physical_raw):
    assert_unknown(assessed(physical_raw,{**vector(physical_raw),"initial_action":"native_default"}))
    assert_unknown(assessed(physical_raw,{**vector(physical_raw),"later_action":"native_default"}))


def test_default_emits_no_command_and_no_requested_edge():
    policy = object.__new__(runner.OwnerPolicy)
    policy.choices,policy.route_keys = [],set()
    policy.client = SimpleNamespace(submit=lambda *args,**kwargs: pytest.fail("default must not submit"))
    tray = {"business_bag_id":"reuse1","generation":2,"traversal_id":4}
    assert policy.route_tray({"now":8.},tray,None,{}) is None
    assert policy.choices[0]["next"] is None
    assert policy.choices[0]["disposition"] == "native_default_no_command"
    assert policy.choices[0]["r1_update_executed"] is False


def test_known_full_target_is_unknown_no_command():
    policy = object.__new__(runner.OwnerPolicy)
    policy.owner,policy.choices,policy.route_keys = "B",[],set()
    policy.client = SimpleNamespace(submit=lambda *args,**kwargs: pytest.fail("full target must not submit"))
    tray = {"business_bag_id":"reuse1","generation":2,"traversal_id":4}
    view = {"now":8.,"node_contracts":[{"node":8,"resource_owner":"B","occupancy":1,"capacity":1}]}
    assert policy.route_tray(view,tray,8,{}) is None
    assert policy.choices[0]["disposition"] == "unknown_local_receiving_precondition"
    assert policy.choices[0]["next"] == 8


def test_plain_json_cannot_forge_native_collected_authority():
    info = {"status":"conditional_native_delivered_later_v3_model_input","native_delivery_verified":True}
    assert runner.fixed_choice(info,{})["selected_action"] is None


def saved_endpoint_fixture(raw):
    """Derived supplied-data fixture, not a new native execution/authority."""
    for owner,initial in raw["initial_owners"].items():
        info = initial["information"]
        initial["raw_endpoints"] = {"view":copy.deepcopy(initial["local_action_view"]),
            "command":{"request_id":info["native_read"]["own_request_id"],"kind":"planning_snapshot",
                       "last_delivered_ack":info["own_delivered_ack"]},
            "received":[info["envelopes"][info["peer"]]]}
    for owner,sequence in raw["decisions"].items():
        for decision in sequence:
            decision["predecision_call_prefix_count"] = next(i for i,c in enumerate(raw["calls"])
                if c["request"]["request_id"] == decision["native_request_id"])
    return raw


def test_saved_actual_endpoint_data_replays_without_native(physical_raw):
    runner.verify_saved_inputs(saved_endpoint_fixture(physical_raw))


@pytest.mark.parametrize("mutation",["prefix","peer_message","own_ack","own_view","forged_verified"])
def test_raw_data_replay_rejects_identity_state_or_boundary_tampering(physical_raw,mutation):
    raw = saved_endpoint_fixture(physical_raw)
    decision = raw["decisions"]["B"][0]
    if mutation == "prefix":decision["predecision_call_prefix_count"] += 1
    elif mutation == "peer_message":decision["information"]["native_read"]["selected_peer_message_id"] = "not-the-delivered-message"
    elif mutation == "own_ack":raw["initial_owners"]["A"]["raw_endpoints"]["command"]["last_delivered_ack"]["result_id"] = "fake"
    elif mutation == "own_view":decision["actual_local_view"]["now"] += .001
    else:decision["information"]["native_delivery_verified"] = False
    with pytest.raises(ValueError):runner.verify_saved_inputs(raw)


def preregister_fixture(path):
    master = runner.matrix.matrix_protocol();master["source_sha256"] = {}
    runner.write(path/"master_protocol.json",master);runner.write(path/"branch_ledger.json",master["rows"])
    cases = {}
    for case_id in master["case_order"]:
        directory = path/case_id;directory.mkdir()
        plan = {"case_id":case_id,"native_branch_budget":32,"parent_timeout_seconds":180.,
            "master_protocol_reference":runner.reference(path/"master_protocol.json"),"source_sha256":{},
            "rows":{key:master["rows"][key] for key in master["case_groups"][case_id]}}
        runner.write(directory/"preregistered_protocol.json",plan)
        runner.write(directory/"branch_ledger.json",plan["rows"])
        cases[case_id] = runner.reference(directory/"preregistered_protocol.json")
    index = {"schema":"g31.native_preference_matrix.index.v1","master_protocol_sha256":runner.sha(path/"master_protocol.json"),
        "case_plans":cases,"branch_count":192,"max_workers":1,"per_case_seconds":180.,"total_seconds":1080.}
    runner.write(path/"master_index.json",index)
    return index,master


def test_exact192_master_case_binding(tmp_path):
    preregister_fixture(tmp_path)
    _,master = runner.verify_index(tmp_path,runner.sha(tmp_path/"master_index.json"))
    assert len(master["rows"]) == 192


@pytest.mark.parametrize("mutation",["budget","count","path","case_budget","omit_case_row"])
def test_rehashed_index_cannot_change_declared_domain_or_limits(tmp_path,mutation):
    index,master = preregister_fixture(tmp_path)
    case = master["case_order"][0]
    if mutation == "budget":index["total_seconds"] = 2000.
    elif mutation == "count":index["branch_count"] = 191
    elif mutation == "path":index["case_plans"][case]["path"] = "wrong"
    else:
        path = tmp_path/case/"preregistered_protocol.json";plan = runner.read(path)
        if mutation == "case_budget":plan["parent_timeout_seconds"] = 181.
        else:plan["rows"].pop(next(iter(plan["rows"])))
        runner.write(path,plan);index["case_plans"][case] = runner.reference(path)
    runner.write(tmp_path/"master_index.json",index)
    with pytest.raises(ValueError):runner.verify_index(tmp_path,runner.sha(tmp_path/"master_index.json"))


@pytest.mark.parametrize("name",["parent_receipt.json","parent_progress.json","execution_started.json"])
def test_execution_never_overwrites_started_or_partial_attempt(tmp_path,name):
    preregister_fixture(tmp_path);runner.write(tmp_path/name,{"status":"old_attempt"})
    with pytest.raises(ValueError,match="execution_already_recorded"):
        runner.execute(tmp_path,runner.sha(tmp_path/"master_index.json"))
    assert runner.read(tmp_path/name) == {"status":"old_attempt"}


def closed_case_fixture(path,raw,monkeypatch):
    index,master = preregister_fixture(path)
    master.update(native_contract_reference={"path":"contract","sha256":"contract_hash"},
        semantic_gate_reference={"path":"semantic","sha256":"semantic_hash"},native_binary={"path":"native","sha256":"native_hash"})
    case_id = "block1_load1";directory = path/case_id
    plan = runner.read(directory/"preregistered_protocol.json")
    key = next(k for k,r in plan["rows"].items() if r["vector"] == vector(raw))
    raw = saved_endpoint_fixture(raw)
    raw["specification"] = copy.deepcopy(plan["rows"][key])
    for rows in raw["decisions"].values():
        for decision in rows:decision["selected_action_admitted"] = True
    raw["summary"] = runner.completed_summary(raw["input"],raw["result"],SimpleNamespace(rows=raw["outbox"],calls=raw["calls"]),
        raw["continuation"],vector(raw),raw["initial_owners"],raw["decisions"])
    input_path = directory/"inputs"/(key+".json");input_path.parent.mkdir(parents=True)
    runner.write(input_path,raw["input"])
    raw_path = directory/(key+".json.gz");raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(gzip.compress(json.dumps(raw).encode()))
    plan.update(input_file_sha256={key:runner.sha(input_path)},row_configuration_sha256={key:runner.bound.config_sha(raw["input"])})
    runner.write(directory/"preregistered_protocol.json",plan)
    index["case_plans"][case_id] = runner.reference(directory/"preregistered_protocol.json")
    rows = copy.deepcopy(plan["rows"])
    rows[key].update(status=raw["summary"]["status"],summary=raw["summary"],raw_artifact={"path":key+".json.gz",
        "sha256":runner.sha(raw_path),"input_path":"inputs/"+key+".json","input_sha256":runner.sha(input_path)})
    runner.write(directory/"branch_ledger.json",rows)
    admission = {"status":"closed_run_acceptance_passed","active":False,"invalid":[],"branch_keys":[key],
        "run_reference":index["case_plans"][case_id],"contract_reference":master["native_contract_reference"],
        "semantic_reference":master["semantic_gate_reference"],"evidence_sha256":{"fixture":"hash"}}
    runner.write(directory/"run_acceptance.json",admission)
    monkeypatch.setattr(runner.run_admission,"inventory",lambda *args:{"fixture":"hash"})
    receipt = {"status":"completed_with_unknowns","case_id":case_id,"row_count":32,"source_changed":[],"source_closure_changed":[],
        "master_index_sha256":runner.sha(path/"master_index.json"),"case_plan_sha256":index["case_plans"][case_id]["sha256"],
        "ledger_sha256":runner.sha(directory/"branch_ledger.json"),"native_binary":master["native_binary"],
        "run_acceptance":runner.reference(directory/"run_acceptance.json"),
        "status_counts":{"assessed":1,"unknown_unexecuted":31}}
    runner.write(directory/"receipt.json",receipt)
    return index,master,case_id,key


def test_case_replays_actual_data_and_keeps31_unexecuted(tmp_path,physical_raw,monkeypatch):
    index,master,case,key = closed_case_fixture(tmp_path,physical_raw,monkeypatch)
    result = runner.verify_case_artifacts(tmp_path,index,master,case)
    assert result["raw_count"] == 1 and result["row_count"] == 32


@pytest.mark.parametrize("mutation",["raw_bytes","ledger_flag","memo_active","memo_pin","receipt_all32"])
def test_parent_rejects_rehashed_summary_or_open_memo(tmp_path,physical_raw,monkeypatch,mutation):
    index,master,case,key = closed_case_fixture(tmp_path,physical_raw,monkeypatch)
    directory = tmp_path/case;receipt = runner.read(directory/"receipt.json")
    if mutation == "raw_bytes":(directory/(key+".json.gz")).write_bytes(b"changed")
    elif mutation == "ledger_flag":
        ledger = runner.read(directory/"branch_ledger.json");ledger[key]["summary"]["first_reuse_actual_next"] = 3
        runner.write(directory/"branch_ledger.json",ledger);receipt["ledger_sha256"] = runner.sha(directory/"branch_ledger.json")
    elif mutation == "receipt_all32":receipt["status"] = "all32_assessed"
    else:
        admission = runner.read(directory/"run_acceptance.json")
        if mutation == "memo_active":admission["active"] = True
        else:admission["evidence_sha256"] = {"fixture":"changed"}
        runner.write(directory/"run_acceptance.json",admission);receipt["run_acceptance"] = runner.reference(directory/"run_acceptance.json")
    runner.write(directory/"receipt.json",receipt)
    with pytest.raises(ValueError):runner.verify_case_artifacts(tmp_path,index,master,case)
