"""Read-only chain proof extension of the unchanged saved-horizon auditor.

No producer schema, receipt or source is rewritten. A private function-global
copy selects this proof verifier and a one-pass ancestor boundary checker;
every other byte of audit_saved's function code and dependencies is reused.
Recorded reconstruction seals are checked, not independently replayed here.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import shlex
import time
from types import FunctionType

from . import audit_saved_horizon as original

ROOT = original.ROOT
CHAIN = "g31.chained_sparse_sealed_resume_worker.v1"
RESUMED = {CHAIN,"g31.sparse_sealed_resume_worker.v1"}
INITIAL = {"g31.full_day_sparse_public_pool_worker.v1","g31.full_day_sparse_worker.v1","g31.lt2.profile_worker.v1"}
COSTS = ("controller_wall_seconds","diagnostic_export_wall_seconds","diagnostic_seal_wall_seconds")
PREDECESSOR_ONLY_ENTRYPOINTS = {"scripts/experiments/g31_ics_circulation/full_day_sparse.py",
                              "scripts/experiments/g31_ics_circulation/full_day_sparse_pool.py"}


def require(value,reason):
    if not value:raise ValueError("chained_saved_horizon:"+reason)


def number(value):
    return type(value) in (int,float) and math.isfinite(value) and value >= 0


def option(receipt,key):
    command = receipt["command"]
    require(type(command) is list and command.count(key) == 1 and command.index(key)+1 < len(command),"ambiguous_argument:"+key)
    return command[command.index(key)+1]


def resolve(path):
    return (ROOT/Path(path)).resolve()


def parent_command_form(command):
    """Only the initial driver's documented path/float CLI serialization.

    The worker command remains byte-token exact. Its parent can have supplied
    86400 rather than the driver's serialized 86400.0, or '/' instead of '\\'.
    No option, ordering, module, identity or other payload is discarded.
    """
    result=list(command)
    for key in ("--binary","--output","--cut-manifest","--stop-receipt"):
        if key in result:
            require(result.count(key)==1 and result.index(key)+1<len(result),"ambiguous_parent_path")
            result[result.index(key)+1]=str(resolve(result[result.index(key)+1]))
    for key in ("--horizon","--segment-seconds","--hard-timeout"):
        if key in result:
            require(result.count(key)==1 and result.index(key)+1<len(result),"ambiguous_parent_time")
            value=float(result[result.index(key)+1]);require(number(value) and value>0,"invalid_parent_time")
            result[result.index(key)+1]=value
    return result


class ChainProof:
    def __init__(self,directory,receipt,manifest,evidence):
        self.directory,self.receipt,self.manifest,self.evidence = Path(directory).resolve(),receipt,manifest,evidence
        self.checkpoints,self.links,self.seen = [],[],set()

    def load(self,path,expected=None):
        path = Path(path).resolve();raw = path.read_bytes();digest = hashlib.sha256(raw).hexdigest()
        require(expected is None or digest == expected,"evidence_hash:"+str(path))
        key = str(path.relative_to(self.directory)) if path.is_relative_to(self.directory) else str(path)
        require(key not in self.evidence or self.evidence[key] == digest,"evidence_changed_while_reading")
        self.evidence[key] = digest
        return json.loads(raw),digest

    def bind_file(self,path,expected):
        path = Path(path).resolve();digest = original.sha256_file(path)
        require(digest == expected,"file_hash:"+str(path))
        key = str(path.relative_to(self.directory)) if path.is_relative_to(self.directory) else str(path)
        require(key not in self.evidence or self.evidence[key] == digest,"conflicting_file_hash")
        self.evidence[key] = digest

    def absence(self,cut_path,cut,stop,source_receipt):
        record,digest = self.load(cut_path.parent/"process_observation.json",cut["absence_sha256"])
        require(stop["process_observation_sha256"] == digest and record.get("all_original_identities_absent") is True
            and isinstance(record.get("observed_utc"),str) and bool(record["observed_utc"]),"stop_observation_binding")
        expected_schema = "g31.terminated_resume_process_observation.v1" if source_receipt["schema"] in RESUMED else "g31.user_resume_process_observation.v1"
        require(record.get("schema") == expected_schema,"stop_observation_schema")
        def tokens(row):return [s.strip('"') for s in shlex.split(row["expected"]["CommandLine"],posix=False)]
        matching = []
        for row in record["processes"]:
            command = tokens(row)
            if command.count("--output") == 1 and resolve(command[command.index("--output")+1]) == Path(cut["source_directory"]).resolve():
                matching.append(row)
        parents = [r for r in matching if "--worker" not in tokens(r)]
        workers = [r for r in matching if "--worker" in tokens(r)]
        require(len(matching) == 2 and len(parents) == len(workers) == 1,"exact_stopped_parent_worker")
        require(all(r.get("old_identity_present") is False and r.get("observed") is None
            and type(r["expected"].get("ProcessId")) is int and r["expected"]["ProcessId"] > 0
            and isinstance(r["expected"].get("CreationDate"),str) and bool(r["expected"]["CreationDate"]) for r in matching),"exact_stopped_identity")
        require(workers[0]["expected"]["ParentProcessId"] == parents[0]["expected"]["ProcessId"],"stopped_parent_relationship")
        command = source_receipt["command"]
        require(command.count("--worker") == 1 and tokens(workers[0]) == command
            and parent_command_form(tokens(parents[0])) == parent_command_form([arg for arg in command if arg != "--worker"]),
            "stopped_command_binding")
        if source_receipt["schema"] in RESUMED:
            ref = record["prior_identity_reference"];identities,_ = self.load(resolve(ref["path"]),ref["sha256"])
            require(all(r["expected"] in identities for r in matching),"prior_stopped_identity_binding")
            require(record.get("source_receipt_sha256") == cut["source_receipt_sha256"],"stopped_receipt_binding")
        return digest

    def attempt(self,directory,receipt,*,depth=0):
        require(depth < 8 and receipt["schema"] in RESUMED,"unsupported_or_excessive_chain")
        directory = Path(directory).resolve()
        cut_path = resolve(option(receipt,"--cut-manifest"));expected_cut = option(receipt,"--expected-cut-sha256")
        require(expected_cut == receipt["cut_manifest_sha256"] and expected_cut not in self.seen,"repeated_or_misbound_cut")
        self.seen.add(expected_cut)
        cut,_ = self.load(cut_path,expected_cut)
        copied,_ = self.load(directory/"resume_source/cut_manifest.json",expected_cut)
        require(cut == copied and cut.get("schema") == "g31.sparse_sealed_resume_cut.v1","cut_schema_or_copy")
        stop_path = resolve(option(receipt,"--stop-receipt"));expected_stop = option(receipt,"--expected-stop-sha256")
        stop,_ = self.load(stop_path,expected_stop)
        copied,_ = self.load(directory/"resume_source/stop_receipt.json",expected_stop)
        require(stop == copied and stop.get("schema") == "g31.full_day_resume_stop.v1"
            and stop.get("source_worker_stopped") is True and stop.get("unchanged_policy") is True
            and stop.get("cut_manifest_sha256") == expected_cut,"stop_proof")
        require(cut["binary_sha256"] == receipt["binary_sha256"] == self.receipt["binary_sha256"]
            and resolve(option(receipt,"--binary")) == Path(cut["binary"]).resolve()
            and option(receipt,"--suite") == cut["suite"] and float(option(receipt,"--horizon")) == cut["horizon"]
            and int(option(receipt,"--event-budget")) == cut["event_budget"],"attempt_scope")
        require(cut["input_sha256"] == self.evidence["input.json.gz"]
            and cut["suite"] == option(self.receipt,"--suite") and cut["horizon"] == float(option(self.receipt,"--horizon")),"chain_input_or_suite")
        require(type(cut["source_cut"]) is int and cut["source_cut"] >= 0
            and len(cut["shards"]) == cut["source_cut"]+1 and len(self.manifest["shards"]) >= len(cut["shards"]),"prefix_denominator")
        require(number(cut["physical_time"]) and type(cut["owner_activations"]) is int and cut["owner_activations"] >= 0
            and isinstance(cut["known_native_seal"],str) and len(cut["known_native_seal"]) == 64
            and all(c in "0123456789abcdef" for c in cut["known_native_seal"]),"cut_time_count_or_seal")
        for index,(old,new) in enumerate(zip(cut["shards"],self.manifest["shards"])):
            require(old["path"] == f"segments/{index:04d}.json.gz" and Path(old["path"]) == Path(new["path"])
                and old["sha256"] == new["sha256"],"inherited_prefix_changed")
        source = Path(cut["source_directory"]).resolve()
        source_receipt,_ = self.load(cut_path.parent/"source_receipt_snapshot.json",cut["source_receipt_sha256"])
        missing_drift_finalization = "source_changed" not in source_receipt
        require((source_receipt.get("source_changed") == [] if not missing_drift_finalization else
                 source_receipt.get("schema") in INITIAL and source_receipt.get("status") == "running"),
                "ancestor_reported_source_drift")
        heartbeat,_ = self.load(cut_path.parent/"source_heartbeat_snapshot.json",cut["source_heartbeat_sha256"])
        self.load(directory/"resume_source/source_receipt_snapshot.json",cut["source_receipt_sha256"])
        self.load(directory/"resume_source/source_heartbeat_snapshot.json",cut["source_heartbeat_sha256"])
        self.load(source/"receipt.json",cut["source_receipt_sha256"])
        self.load(source/"heartbeat.json",cut["source_heartbeat_sha256"])
        self.bind_file(source/"input.json.gz",cut["input_sha256"])
        require(cut["source_policy_sha256"] == source_receipt["source_before"]
            and all(self.receipt["source_before"][k] == h for k,h in cut["source_policy_sha256"].items()
                    if k in self.receipt["source_before"]),"inherited_policy_changed")
        predecessor_only = sorted(set(cut["source_policy_sha256"])-set(self.receipt["source_before"]))
        require({Path(p).as_posix() for p in predecessor_only} <= PREDECESSOR_ONLY_ENTRYPOINTS,
                "unknown_predecessor_only_source")
        for path,digest in cut["source_policy_sha256"].items():
            relative = Path(path);require(not relative.is_absolute() and ".." not in relative.parts,"unsafe_policy_path")
            self.bind_file(source/"source_archive"/relative,digest)
            # An older entry point need not be imported by the newer driver.
            # Its original archive and unchanged live bytes remain bound.
            self.bind_file(ROOT/relative,digest)
        self.absence(cut_path,cut,stop,source_receipt)
        require(heartbeat.get("stage") == "segment_saved" and heartbeat["offered_total"] == cut["offered_total"]
            and heartbeat["physical_time"] >= cut["physical_time"]
            and heartbeat["owner_activations"] >= cut["owner_activations"],"source_heartbeat_scope")
        require(all(number(v) for v in cut["prior_costs"].values()) and set(cut["prior_costs"]) == set(COSTS)
            and all(cut["prior_costs"][k] == heartbeat[k] for k in COSTS),"charged_source_cost_changed")
        require(cut["excluded_tail"] == {"first_shard":cut["source_cut"]+1,"last_published_shard":heartbeat["segment"],
            "last_physical_time":heartbeat["physical_time"],"native_checkpoint_identity":"unknown"}
            and len(cut["shards"])+len(cut["excluded_tail_shards"]) == heartbeat["segment"]+1,"excluded_tail_scope")
        for index,row in enumerate(cut["excluded_tail_shards"],len(cut["shards"])):
            require(row["path"] == f"segments/{index:04d}.json.gz","excluded_tail_order")
        reconstruction,_ = self.load(directory/"reconstruction.json")
        require(reconstruction.get("status") == "verified_against_known_native_seal"
            and reconstruction.get("native_state_sha256") == cut["known_native_seal"]
            and reconstruction.get("parts") == len(cut["shards"])
            and reconstruction.get("physical_time") == cut["physical_time"]
            and reconstruction.get("owners") == cut["owner_activations"]
            and reconstruction.get("native_json_restore") is False and reconstruction.get("policy_reexecuted") is False
            and all(type(reconstruction.get(k)) is int and reconstruction[k] >= 0 for k in
                ("owners","native_boundaries","submissions","queries","trace_records"))
            and reconstruction["trace_records"] == reconstruction["owners"]+reconstruction["native_boundaries"],"reconstruction_known_seal_or_counts")
        inherited = cut["source_reconstruction_wall_seconds"]
        require(number(inherited) and number(reconstruction["wall_seconds"])
            and reconstruction.get("prior_reconstruction_wall_seconds") == inherited
            and reconstruction.get("prefix_cost_scope") == cut["prior_cost_scope"],"reconstruction_cost_scope")
        cumulative = inherited+reconstruction["wall_seconds"]
        if "cumulative_reconstruction_wall_seconds" in reconstruction:
            require(reconstruction["cumulative_reconstruction_wall_seconds"] == cumulative,"current_cumulative_cost")
        if source_receipt["schema"] in RESUMED:
            require(receipt["schema"] == CHAIN and source_receipt["status"] in {"failed","hard_timeout"}
                and source_receipt.get("source_changed") == [] and cut["source_terminal_status"] == source_receipt["status"]
                and cut["source_exit_code"] == source_receipt.get("exit_code")
                and stop.get("source_terminal_status") == source_receipt["status"]
                and stop.get("source_exit_code") == source_receipt.get("exit_code"),"terminated_parent_not_bound")
            ancestor = self.attempt(source,source_receipt,depth=depth+1)
            require(cut["ancestor_cut_manifest_sha256"] == ancestor["cut_manifest_sha256"]
                and cut["source_ancestor_reconstruction_wall_seconds"] == ancestor["inherited_reconstruction_wall_seconds"]
                and inherited == ancestor["cumulative_reconstruction_wall_seconds"]
                and heartbeat["reconstruction_wall_seconds"] == ancestor["own_reconstruction_wall_seconds"],"ancestor_reconstruction_cost")
            if "cumulative_reconstruction_wall_seconds" in heartbeat:
                require(heartbeat["cumulative_reconstruction_wall_seconds"] == inherited,"heartbeat_cumulative_cost")
            require(cut["controller_config"] == ancestor["controller_config"],"ancestor_controller_config_changed")
            if cut["selected_seal_origin"] == "ancestor_known_seal":
                expected_seal = {"shard":ancestor["prefix_parts"]-1,"physical_time":ancestor["physical_time"],
                                 "native_state_sha256":ancestor["known_prefix_seal"]}
                require(heartbeat.get("latest_native_seal") is None,"unexpected_inherited_seal_override")
            else:
                require(cut["selected_seal_origin"] == "source_published_new_seal","unknown_seal_origin")
                expected_seal = heartbeat.get("latest_native_seal")
        else:
            require(source_receipt["schema"] in INITIAL and inherited == heartbeat.get("reconstruction_wall_seconds",0.) == 0.,"unsupported_initial_source")
            expected_seal = heartbeat.get("latest_native_seal")
        require(expected_seal == {"shard":cut["source_cut"],"physical_time":cut["physical_time"],
            "native_state_sha256":cut["known_native_seal"]},"selected_source_seal")
        proof = {"resumed":True,"producer_schema":receipt["schema"],"cut_manifest_sha256":expected_cut,
            "prefix_parts":len(cut["shards"]),"known_prefix_seal":cut["known_native_seal"],"physical_time":cut["physical_time"],
            "controller_config":cut["controller_config"],"prefix_counts":{"control_records":reconstruction["owners"],
                "native_batches":reconstruction["native_boundaries"],"client_calls":reconstruction["submissions"]},
            "trace_records":reconstruction["trace_records"],"reconstruction_status":reconstruction["status"],
            "inherited_reconstruction_wall_seconds":inherited,"own_reconstruction_wall_seconds":reconstruction["wall_seconds"],
            "cumulative_reconstruction_wall_seconds":cumulative,"cumulative_cost_derived_here":True,
            "producer_cumulative_field_present":"cumulative_reconstruction_wall_seconds" in reconstruction,
            "source_drift_finalization_unknown":missing_drift_finalization,
            "predecessor_only_sources_individually_archive_and_live_bound":predecessor_only,
            "prior_costs_including_excluded_tail":cut["prior_costs"],"excluded_tail":cut["excluded_tail"],
            "excluded_tail_raw_independently_read_here":False,"independently_replayed_here":False}
        self.checkpoints.append(proof);self.links.append(proof)
        return proof

    def verify(self):
        require(self.receipt.get("schema") == CHAIN,"new_adapter_requires_chained_schema")
        proof = self.attempt(self.directory,self.receipt)
        scope,_ = self.load(self.directory/"interruption_cost_scope.json")
        require(scope["prior_costs"] == proof["prior_costs_including_excluded_tail"]
            and scope["prior_reconstruction_wall_seconds"] == proof["inherited_reconstruction_wall_seconds"]
            and scope.get("user_pause_in_this_attempt") is False,"interruption_cost_scope_changed")
        return {**proof,"chain_links":list(self.links),"chain_link_count":len(self.links),
            "any_ancestor_source_drift_finalization_unknown":any(p["source_drift_finalization_unknown"] for p in self.links),
            "proof_scope":"Hash-bound saved reconstruction reports and exact stopped-process observations, not a new native replay."}


class BoundaryReader:
    def __init__(self,reader,proofs):
        self.reader,self.proofs = reader,proofs
        self.parts,self.counts,self.trace,self.checked = 0,Counter(control_records=0,native_batches=0,client_calls=0),0,[]

    def __call__(self,*args,**kwargs):
        part = self.reader(*args,**kwargs);self.parts += 1
        for key in self.counts:self.counts[key] += len(part[key])
        self.trace += len(part["control_records"])+len(part["native_batches"])
        for proof in self.proofs:
            if proof["prefix_parts"] == self.parts:
                require(dict(self.counts) == proof["prefix_counts"] and self.trace == proof["trace_records"]
                    and part.get("native_state_sha256") == proof["known_prefix_seal"]
                    and part["control_continuation"]["physical_time"] == proof["physical_time"],"actual_ancestor_boundary_mismatch")
                self.checked.append(proof["cut_manifest_sha256"])
        return part


def audit_chained(directory,expected_total,horizon,*,expected_final_seal=None,progress=None):
    proofs=[]
    def verify(directory,receipt,manifest,evidence):
        verifier = ChainProof(directory,receipt,manifest,evidence)
        result = verifier.verify();proofs.extend(verifier.checkpoints);return result
    reader = BoundaryReader(original.read_bound_shard,proofs)
    private_globals = {**original.audit_saved.__globals__,"verify_resume_proof":verify,"read_bound_shard":reader}
    function = FunctionType(original.audit_saved.__code__,private_globals,original.audit_saved.__name__,
                            original.audit_saved.__defaults__,original.audit_saved.__closure__)
    function.__kwdefaults__ = original.audit_saved.__kwdefaults__
    report = function(directory,expected_total,horizon,expected_final_seal=expected_final_seal,progress=progress)
    require(sorted(reader.checked) == sorted(p["cut_manifest_sha256"] for p in proofs),"missing_ancestor_boundary_check")
    report["chain_ancestor_boundary_checks"] = reader.checked
    report["adapter"] = {"schema":"g31.chained_saved_horizon_adapter.v1","original_auditor_function_code_unchanged":True,
        "original_producer_schema_unchanged":True,"native_replay_performed":False}
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--expected-total",type=int,required=True);parser.add_argument("--horizon",type=float,required=True)
    parser.add_argument("--expected-final-seal",required=True);args=parser.parse_args()
    require(not args.output.exists() and not args.output.resolve().is_relative_to(args.directory.resolve()),"new_external_output_required")
    started=time.perf_counter()
    def progress(done,total,name):print(json.dumps({"shards_read":done,"total":total,"last":name,"audit_wall_seconds":time.perf_counter()-started}),flush=True)
    report=audit_chained(args.directory,args.expected_total,args.horizon,expected_final_seal=args.expected_final_seal,progress=progress)
    report["audit_wall_seconds"]=time.perf_counter()-started
    with args.output.open("x",encoding="utf-8") as stream:json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps({k:report[k] for k in ("status","producer_receipt_status","offered","completed","unfinished")}))


if __name__ == "__main__":main()
