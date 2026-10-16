"""Small handwritten chain metadata; no native and no large shard reads."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.experiments.g31_ics_circulation import audit_chained_saved_horizon as chain


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2),encoding="utf-8")
    return chain.original.sha256_file(path)


def read(path):return json.loads(Path(path).read_bytes())


def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(chain,"ROOT",tmp_path)
    original,resumed,current=(tmp_path/name for name in ("original","resumed","current"))
    for directory in (original,resumed,current):
        directory.mkdir();(directory/"input.json.gz").write_bytes(b"handwritten input identity")
        (directory/"source_archive").mkdir();(directory/"source_archive/policy.py").write_text("# fixed test policy\n")
    input_sha=chain.original.sha256_file(current/"input.json.gz")
    policy={"policy.py":chain.original.sha256_file(current/"source_archive/policy.py")}
    (tmp_path/"policy.py").write_bytes((current/"source_archive/policy.py").read_bytes())
    binary=tmp_path/"binary.pyd";binary.write_bytes(b"never loaded")
    binary_sha=chain.original.sha256_file(binary)
    shards=[{"path":f"segments/{i:04d}.json.gz","sha256":str(i+1)*64} for i in range(3)]
    config={"owners":["A","B"],"command_delay":2.}
    def source_receipt(directory,schema,status,cut=None,stop=None):
        command=["python","-m","handwritten"]
        if cut:
            command += ["--cut-manifest",str(cut),"--expected-cut-sha256",chain.original.sha256_file(cut),
                        "--stop-receipt",str(stop),"--expected-stop-sha256",chain.original.sha256_file(stop)]
        command += ["--binary",str(binary),"--suite","full2x","--horizon","86400","--event-budget","1000000", "--output",str(directory),"--worker"]
        value={"schema":schema,"status":status,"command":command,"source_before":policy,
               "source_changed":[],"binary_sha256":binary_sha,"exit_code":None}
        if cut:value["cut_manifest_sha256"]=chain.original.sha256_file(cut)
        write(directory/"receipt.json",value);return value
    first=source_receipt(original,"g31.full_day_sparse_public_pool_worker.v1","running")
    def heartbeat(directory,index,physical,owners,cost,reconstruction):
        value={"stage":"segment_saved","segment":index+1,"physical_time":physical+1.,"owner_activations":owners+1,
            "offered_total":57012,"controller_wall_seconds":cost,"diagnostic_export_wall_seconds":cost/5,
            "diagnostic_seal_wall_seconds":cost/10,"reconstruction_wall_seconds":reconstruction,
            "latest_native_seal":{"shard":index,"physical_time":physical,"native_state_sha256":str(index+1)*64}}
        write(directory/"heartbeat.json",value);return value
    hb0=heartbeat(original,0,10.,1,10.,0.)
    def prepare_cut(folder,source,source_value,hb,index,prior_recon,ancestor=None):
        folder.mkdir()
        receipt_sha=write(folder/"source_receipt_snapshot.json",source_value)
        heartbeat_sha=write(folder/"source_heartbeat_snapshot.json",hb)
        command=source_value["command"]
        parent={"ProcessId":10+index*2,"ParentProcessId":1,"CreationDate":"2026-10-15T00:00:00Z",
                "CommandLine":subprocess.list2cmdline([v for v in command if v != "--worker"])}
        worker={"ProcessId":11+index*2,"ParentProcessId":parent["ProcessId"],"CreationDate":"2026-10-15T00:00:01Z",
                "CommandLine":subprocess.list2cmdline(command)}
        observation={"schema":"g31.terminated_resume_process_observation.v1" if ancestor else "g31.user_resume_process_observation.v1",
            "observed_utc":"2026-10-15T01:00:00Z","all_original_identities_absent":True,
            "processes":[{"expected":row,"observed":None,"old_identity_present":False} for row in (parent,worker)]}
        if ancestor:
            identity_path=folder/"prior_identity.json";digest=write(identity_path,[parent,worker])
            observation.update(prior_identity_reference={"path":str(identity_path),"sha256":digest},source_receipt_sha256=receipt_sha)
        absence=write(folder/"process_observation.json",observation)
        cut={"schema":"g31.sparse_sealed_resume_cut.v1","source_directory":str(source),"suite":"full2x","horizon":86400.,
            "event_budget":1000000,"source_cut":index,"physical_time":10.*(index+1),"owner_activations":index+1,
            "known_native_seal":str(index+1)*64,"binary":str(binary),"binary_sha256":binary_sha,"offered_total":57012,
            "controller_config":config,"prior_costs":{key:hb[key] for key in chain.COSTS},"source_policy_sha256":policy,
            "excluded_tail":{"first_shard":index+1,"last_published_shard":hb["segment"],"last_physical_time":hb["physical_time"],
                             "native_checkpoint_identity":"unknown"},"prior_cost_scope":"entire frozen source cost and unknown unpublished tail",
            "source_reconstruction_wall_seconds":prior_recon,"source_receipt_sha256":receipt_sha,"source_heartbeat_sha256":heartbeat_sha,
            "input_sha256":input_sha,"absence_sha256":absence,"shards":shards[:index+1],"excluded_tail_shards":shards[index+1:index+2]}
        if ancestor:
            cut.update(ancestor_cut_manifest_sha256=chain.original.sha256_file(ancestor),source_ancestor_reconstruction_wall_seconds=0.,
                source_terminal_status="hard_timeout",source_exit_code=None,selected_seal_origin="source_published_new_seal")
        cut_path=folder/"cut_manifest.json";cut_sha=write(cut_path,cut)
        stop={"schema":"g31.full_day_resume_stop.v1","source_worker_stopped":True,"unchanged_policy":True,
            "cut_manifest_sha256":cut_sha,"process_observation_sha256":absence}
        if ancestor:stop.update(source_terminal_status="hard_timeout",source_exit_code=None)
        stop_path=folder/"source_stop_receipt.json";write(stop_path,stop)
        return cut_path,stop_path,cut
    cut1,stop1,c1=prepare_cut(tmp_path/"cut1",original,first,hb0,0,0.)
    second=source_receipt(resumed,"g31.sparse_sealed_resume_worker.v1","hard_timeout",cut1,stop1)
    hb1=heartbeat(resumed,1,20.,2,30.,3.)
    cut2,stop2,c2=prepare_cut(tmp_path/"cut2",resumed,second,hb1,1,3.,cut1)
    final=source_receipt(current,chain.CHAIN,"hard_timeout",cut2,stop2)
    for directory,cut_path,stop_path,c,wall in ((resumed,cut1,stop1,c1,3.),(current,cut2,stop2,c2,5.)):
        proof=directory/"resume_source";proof.mkdir()
        for source,target in ((cut_path,"cut_manifest.json"),(stop_path,"stop_receipt.json"),
            (cut_path.parent/"source_receipt_snapshot.json","source_receipt_snapshot.json"),
            (cut_path.parent/"source_heartbeat_snapshot.json","source_heartbeat_snapshot.json")):
            shutil.copyfile(source,proof/target)
        count=c["source_cut"]+1
        write(directory/"reconstruction.json",{"status":"verified_against_known_native_seal","native_state_sha256":c["known_native_seal"],
            "parts":count,"owners":count,"native_boundaries":count,"submissions":count,"queries":count*3,"trace_records":count*2,
            "physical_time":c["physical_time"],"native_json_restore":False,"policy_reexecuted":False,
            "prior_reconstruction_wall_seconds":c["source_reconstruction_wall_seconds"],"wall_seconds":wall,"prefix_cost_scope":c["prior_cost_scope"]})
    write(current/"interruption_cost_scope.json",{"prior_costs":c2["prior_costs"],"prior_reconstruction_wall_seconds":3.,"user_pause_in_this_attempt":False})
    return {"directory":current,"receipt":final,"manifest":{"shards":shards},"evidence":{"input.json.gz":input_sha},
            "cut_path":cut2,"stop_path":stop2,"ancestor_cut":cut1,"source":resumed}


def verify(f):return chain.ChainProof(f["directory"],f["receipt"],f["manifest"],f["evidence"]).verify()


def update_current_cut(f,mutate):
    cut=read(f["cut_path"]);mutate(cut);digest=write(f["cut_path"],cut)
    write(f["directory"]/"resume_source/cut_manifest.json",cut)
    f["receipt"]["cut_manifest_sha256"]=digest
    command=f["receipt"]["command"];command[command.index("--expected-cut-sha256")+1]=digest
    stop=read(f["stop_path"]);stop["cut_manifest_sha256"]=digest
    stop_digest=write(f["stop_path"],stop);write(f["directory"]/"resume_source/stop_receipt.json",stop)
    command[command.index("--expected-stop-sha256")+1]=stop_digest


def test_complete_two_link_metadata_keeps_costs_and_unknown_tail(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);before=(f["directory"]/"receipt.json").read_bytes();proof=verify(f)
    assert proof["chain_link_count"] == 2 and proof["cumulative_reconstruction_wall_seconds"] == 8.
    assert [p["prefix_parts"] for p in proof["chain_links"]] == [1,2]
    assert proof["producer_cumulative_field_present"] is False
    assert proof["independently_replayed_here"] is False and proof["excluded_tail_raw_independently_read_here"] is False
    assert (f["directory"]/"receipt.json").read_bytes() == before


@pytest.mark.parametrize("field,value",[("native_state_sha256","0"*64),("parts",1),("owners",True),("trace_records",5),
    ("prior_reconstruction_wall_seconds",0.),("wall_seconds",float("nan")),("cumulative_reconstruction_wall_seconds",7.),
    ("native_json_restore",True),("policy_reexecuted",True)])
def test_current_reconstruction_must_match_known_cut_and_charged_cost(tmp_path,monkeypatch,field,value):
    f=fixture(tmp_path,monkeypatch);path=f["directory"]/"reconstruction.json";row=read(path);row[field]=value;write(path,row)
    with pytest.raises(ValueError):verify(f)


@pytest.mark.parametrize("mutation",["scope","input","prefix","ancestor_hash","ancestor_cost","config","tail","cost","source_status"])
def test_rehashed_cut_cannot_relabel_chain_or_reduce_costs(tmp_path,monkeypatch,mutation):
    f=fixture(tmp_path,monkeypatch)
    def change(cut):
        if mutation == "scope":cut["suite"]="full1x"
        elif mutation == "input":cut["input_sha256"]="0"*64
        elif mutation == "prefix":cut["shards"][0]["sha256"]="0"*64
        elif mutation == "ancestor_hash":cut["ancestor_cut_manifest_sha256"]="0"*64
        elif mutation == "ancestor_cost":cut["source_ancestor_reconstruction_wall_seconds"]=1.
        elif mutation == "config":cut["controller_config"]["command_delay"]=.01
        elif mutation == "tail":cut["excluded_tail"]["native_checkpoint_identity"]="invented"
        elif mutation == "cost":cut["prior_costs"]["controller_wall_seconds"]=0.
        else:cut["source_terminal_status"]="completed"
    update_current_cut(f,change)
    with pytest.raises(ValueError):verify(f)


@pytest.mark.parametrize("mutation",["cut_copy","stop_copy","source_receipt","source_heartbeat","source_archive","prior_identity"])
def test_independently_bound_inherited_files_cannot_drift(tmp_path,monkeypatch,mutation):
    f=fixture(tmp_path,monkeypatch)
    path={"cut_copy":f["directory"]/"resume_source/cut_manifest.json","stop_copy":f["directory"]/"resume_source/stop_receipt.json",
        "source_receipt":f["source"]/"receipt.json","source_heartbeat":f["source"]/"heartbeat.json",
        "source_archive":f["source"]/"source_archive/policy.py","prior_identity":f["cut_path"].parent/"prior_identity.json"}[mutation]
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError):verify(f)


def test_false_process_absence_is_rejected_after_all_enclosing_rehashes(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);path=f["cut_path"].parent/"process_observation.json"
    row=read(path);row["processes"][1]["old_identity_present"]=True;digest=write(path,row)
    update_current_cut(f,lambda cut:cut.update(absence_sha256=digest))
    stop=read(f["stop_path"]);stop["process_observation_sha256"]=digest
    stop_hash=write(f["stop_path"],stop);write(f["directory"]/"resume_source/stop_receipt.json",stop)
    command=f["receipt"]["command"];command[command.index("--expected-stop-sha256")+1]=stop_hash
    with pytest.raises(ValueError,match="exact_stopped_identity"):verify(f)


def test_ancestor_actual_boundary_is_checked_without_second_read():
    proof={"prefix_parts":1,"prefix_counts":{"control_records":1,"native_batches":1,"client_calls":1},"trace_records":2,
           "known_prefix_seal":"a"*64,"physical_time":10.,"cut_manifest_sha256":"c"*64}
    part={"control_records":[{}],"native_batches":[{}],"client_calls":[{}],"native_state_sha256":"a"*64,
          "control_continuation":{"physical_time":10.}}
    calls=[]
    def reader(*args,**kwargs):calls.append(args);return part
    wrapper=chain.BoundaryReader(reader,[proof]);assert wrapper("exact.gz","sha",final=False) is part
    assert len(calls)==1 and wrapper.checked==["c"*64]
    part["native_state_sha256"]="b"*64
    with pytest.raises(ValueError,match="actual_ancestor_boundary"):
        chain.BoundaryReader(reader,[proof])("exact.gz","sha",final=False)


def test_private_function_adapter_does_not_mutate_original_globals(tmp_path,monkeypatch):
    original_verify=chain.original.verify_resume_proof;original_reader=chain.original.read_bound_shard
    # Reuse the actual auditor's terminal-state gate before any proof/shard IO.
    write(tmp_path/"receipt.json",{"schema":chain.CHAIN,"status":"running"})
    with pytest.raises(ValueError,match="producer_receipt_not_terminal"):
        chain.audit_chained(tmp_path,57012,86400.)
    assert chain.original.verify_resume_proof is original_verify
    assert chain.original.read_bound_shard is original_reader


def test_only_explicit_chain_schema_is_adapted(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);f["receipt"]["schema"]="g31.unreviewed_resume.v1"
    with pytest.raises(ValueError,match="requires_chained_schema"):verify(f)


def test_missing_policy_source_is_not_treated_as_an_old_entrypoint(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);f["receipt"]["source_before"]={}
    with pytest.raises(ValueError,match="unknown_predecessor_only_source"):verify(f)


def test_parent_normalization_preserves_values_and_all_other_tokens(tmp_path,monkeypatch):
    monkeypatch.setattr(chain,"ROOT",tmp_path)
    first=["python","-m","same","--horizon","86400","--binary","a/b","--output","x/y"]
    equivalent=["python","-m","same","--horizon","86400.0","--binary","a\\b","--output","x\\y"]
    assert chain.parent_command_form(first)==chain.parent_command_form(equivalent)
    changed=deepcopy(equivalent);changed[4]="86399"
    assert chain.parent_command_form(first)!=chain.parent_command_form(changed)
    assert chain.parent_command_form(first)!=chain.parent_command_form(first+["--extra"])


@pytest.mark.parametrize("status,present,drift,accepted",[
    ("running",True,["policy.py"],False),("running",True,None,False),
    ("running",False,None,True),("completed",False,None,False),("failed",False,None,False)])
def test_rehashed_initial_reported_source_drift_is_not_hidden_by_restored_bytes(tmp_path,monkeypatch,status,present,drift,accepted):
    f=fixture(tmp_path,monkeypatch)
    cut_path=f["ancestor_cut"];cut=read(cut_path)
    initial=Path(cut["source_directory"])
    receipt=read(initial/"receipt.json")
    receipt["status"]=status
    if present:receipt["source_changed"]=drift
    else:receipt.pop("source_changed")
    receipt_hash=write(initial/"receipt.json",receipt)
    write(cut_path.parent/"source_receipt_snapshot.json",receipt)
    write(f["source"]/"resume_source/source_receipt_snapshot.json",receipt)
    cut["source_receipt_sha256"]=receipt_hash
    cut_hash=write(cut_path,cut)
    write(f["source"]/"resume_source/cut_manifest.json",cut)
    resumed=read(f["source"]/"receipt.json")
    stop_path=Path(chain.option(resumed,"--stop-receipt"))
    stop=read(stop_path);stop["cut_manifest_sha256"]=cut_hash
    stop_hash=write(stop_path,stop)
    write(f["source"]/"resume_source/stop_receipt.json",stop)
    resumed["cut_manifest_sha256"]=cut_hash
    command=resumed["command"]
    command[command.index("--expected-cut-sha256")+1]=cut_hash
    command[command.index("--expected-stop-sha256")+1]=stop_hash
    # Deliberately unchanged live/archive bytes: the producer's explicit drift
    # report is material even when a transient edit was later reverted.
    verifier=chain.ChainProof(f["source"],resumed,f["manifest"],f["evidence"])
    if accepted:
        proof=verifier.attempt(f["source"],resumed)
        assert proof["source_drift_finalization_unknown"] is True
        assert read(initial/"receipt.json")==receipt and "source_changed" not in receipt
    else:
        with pytest.raises(ValueError,match="ancestor_reported_source_drift"):
            verifier.attempt(f["source"],resumed)


def test_missing_resumed_ancestor_drift_finalization_is_rejected(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch)
    row=read(f["source"]/"receipt.json");row.pop("source_changed")
    digest=write(f["source"]/"receipt.json",row)
    write(f["cut_path"].parent/"source_receipt_snapshot.json",row)
    write(f["directory"]/"resume_source/source_receipt_snapshot.json",row)
    update_current_cut(f,lambda cut:cut.update(source_receipt_sha256=digest))
    with pytest.raises(ValueError,match="ancestor_reported_source_drift"):verify(f)
