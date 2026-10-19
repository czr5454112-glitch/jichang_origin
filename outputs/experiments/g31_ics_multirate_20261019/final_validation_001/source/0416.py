"""Pure request-side replay of a proposed observation omission.

Recorded native replies are read unchanged. This is not a new native execution
or a proof of common-horizon physical equivalence or runtime improvement.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from . import route_update_pending_ack as candidate
from . import verify_original_route_update_internal_deadline as original_verify

reference=candidate.reference
require=reference.require


def semantic_intent(intent):
    value=deepcopy(intent)
    for key in ("observation_count","last_now","reservation"):value.pop(key,None)
    return value


def client_calls(calls):
    value=deepcopy(calls)
    for row in value:
        cost=row.pop("submit_compute_ms")
        require(type(cost) in (int,float) and math.isfinite(cost) and cost>=0,"pending_replay_invalid_clock")
    return value


class EventReplay:
    def __init__(self):self.now=reference.ADMISSION;self.rows=[];self.position=0;self.omitted=[];self.consumed=[]
    @property
    def physical_time(self):return self.now
    def begin(self,rows,at,ack_only):
        require(self.position==len(self.rows),"pending_replay_previous_unconsumed")
        self.now=at
        self.omitted.extend(deepcopy([r for r in rows if ack_only and r["endpoint"]=="observe_protocol"]))
        self.rows=[r for r in rows if not (ack_only and r["endpoint"]=="observe_protocol")]
        self.position=0
    def __getattr__(self,endpoint):
        require(endpoint in reference.ENDPOINTS,"pending_replay_unknown_endpoint")
        def invoke(*args,**kwargs):
            require(self.position<len(self.rows),"pending_replay_unrecorded_call")
            row=self.rows[self.position]
            require(endpoint==row["endpoint"] and original_verify.ordered(list(args))==original_verify.ordered(row["args"])
                and original_verify.ordered(kwargs)==original_verify.ordered(row["kwargs"]) and row["before"]==self.now,
                "pending_replay_api_mismatch")
            self.position+=1;self.now=row["after"];self.consumed.append(row)
            return deepcopy(row["result"])
        return invoke


def replay_case(directory):
    raw=reference.old.gzread(directory/"raw.json.gz")
    require(reference.old.sha(directory/"service_tape.jsonl.gz")==raw["api_sha256"],"pending_replay_api_hash")
    rows=original_verify.read_api(directory/"service_tape.jsonl.gz") if hasattr(original_verify,"read_api") else _read_api(directory/"service_tape.jsonl.gz")
    original_verify.validate_tape(rows)
    original_verify.replay_request(raw,rows)  # Fresh old request-policy replay first.
    clocks=iter(raw["root"]["clock_trace"]);session=EventReplay()
    update=candidate.PendingAckRouteUpdate(session,raw["root"]["owner"],clock=lambda:next(clocks))
    modes=[];request_count=0
    for event in raw["events"]:
        first,after=event["first_api"],event["after_api"]
        segment=rows[first:after];require(segment and all(r["role"]=="request" for r in segment),"pending_replay_event_range")
        session.now=event["at"]
        ack_only=not event["initial"] and update._can_refresh_only(False)
        session.begin(segment,event["at"],ack_only)
        before_reads=update.full_view_reads
        update.start() if event["initial"] else update.step()
        require(session.position==len(session.rows),"pending_replay_unused_request_api")
        require(update.full_view_reads-before_reads==(0 if ack_only else 1),"pending_replay_observation_scope")
        modes.append({"at":event["at"],"ack_only":ack_only,"reference_request_api_count":len(segment),
            "candidate_request_api_count":len(session.rows)})
        request_count+=len(segment)
    if raw["root"]["censored_ns"] is not None:update.censor()
    require(next(clocks,None) is None,"pending_replay_clock_coverage")
    now=update.snapshot();prior=raw["root"]
    require(semantic_intent(now["intent"])==semantic_intent(prior["intent"]),"pending_replay_semantic_intent_changed")
    require(now["client_state"]==prior["client_state"] and client_calls(now["client_calls"])==client_calls(prior["client_calls"]),
        "pending_replay_protocol_or_retry_changed")
    require(now["steps"]==prior["steps"] and now["lineage"]==prior["lineage"] and now["protocol_lineage"]==prior["protocol_lineage"]
        and now["clock_trace"]==prior["clock_trace"],"pending_replay_closure_or_schedule_changed")
    require(update.closed==(prior["returned_ns"] is not None),"pending_replay_terminal_changed")
    require(request_count==len(session.consumed)+len(session.omitted),"pending_replay_request_denominator")
    return {"status":"pure_request_side_replay_exact_except_declared_postproof_observations",
        "closed":update.closed,"reference_request_rows":request_count,"candidate_request_rows":len(session.consumed),
        "omitted_full_observations":len(session.omitted),"modes":modes,"candidate_snapshot":now,
        "source_raw_sha256":reference.old.sha(directory/"raw.json.gz"),"source_api_sha256":raw["api_sha256"],
        "reference_physical_horizon":raw["physical_time"],"reference_producer_seal":raw["native_state_sha256"],
        "candidate_native_seal":None,"native_execution":False,"native_equivalence_proved":False,"runtime_speedup_measured":False,
        "scope":"Saved replies and old clocks support only the request-side read-omission conformance check. No recorded clock is a measured candidate runtime; background/physical equivalence and common-H seal require a future actual pair."}


def _read_api(path):
    import gzip
    with gzip.open(path,"rt",encoding="utf8") as stream:return [json.loads(line) for line in stream]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--reference",required=True,type=Path);parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args();require(not args.output.exists(),"pending_replay_output_exists")
    folder=args.reference.resolve();plan=reference.old.read(folder/"preregistered_protocol.json");reference.verify_pins(folder,plan)
    pins={str(Path(module.__file__).resolve()):reference.old.sha(module.__file__) for module in (candidate,reference,original_verify)}
    pins[str(Path(__file__).resolve())]=reference.old.sha(__file__)
    report={"schema":"g31.pending_ack_read_omission.pure_replay.v1","source_sha256":pins,
        "reference_plan_sha256":reference.old.sha(folder/"preregistered_protocol.json"),"cases":{},"native_executions":0}
    candidate.prove_unchanged_closure_tail()
    for name in reference.CASES:report["cases"][name]=replay_case(folder/name)
    require(all(reference.old.sha(path)==digest for path,digest in pins.items()),"pending_replay_source_changed")
    reference.verify_pins(folder,plan);reference.old.write(args.output,report)
    print(json.dumps({name:{key:row[key] for key in ("closed","reference_request_rows","candidate_request_rows","omitted_full_observations")} for name,row in report["cases"].items()}))


if __name__=="__main__":main()
