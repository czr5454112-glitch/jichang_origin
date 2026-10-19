"""Restricted new synthetic five-job projection; no native or online authority.

The original event loop/scorer remains inherited unchanged. Extensions are
generic mandatory Storage and the declared absolute first-return alternative.
Source-shaped facts are explicitly hypothetical, not delivered native data.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import math
from pathlib import Path

from . import public_live_obligation_interval as construction
from . import public_native_preference_projection as original
from . import public_preference_request_context as old_context

VERSION = "public_live_obligation_projection_v1"
START, HORIZON = .11, 40.
JOBS = construction.JOBS
PROTOCOL = {"message_delay":.01, "publication_delay":.01, "ack_delay":.02,
    "retry":.5, "rejection_cooldown":.5, "period":.05, "transfer_expiry":39.,
    "route_lifetime":5., "first_return_not_before":7.84,
    "native_semantics":copy.deepcopy(original.contract.SUPPORTED_NATIVE_SEMANTICS)}
EXPECTED_ORIGINAL = "f501e125feb6ddb4fc343f55ddf684781741d13b71d6fa9178b485ff8ce3b4b7"
EXPECTED_LEGACY = "bb1bf8bc35822b671e9db5844e136ff91f187c4d92d465190f5d630f7cb739d1"


def check_sources():
    for module, expected in ((original,EXPECTED_ORIGINAL),(original.legacy,EXPECTED_LEGACY)):
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != expected:
            raise ValueError("live_model:unreviewed_inherited_source")


def unknown(reason):
    return {"status":"unknown_"+reason, "completion":{},
        "model_version":VERSION, "native_protection_certified":False,
        "native_execution_certified":False,"online_information_delivered":False}


def inputs():
    return {c["case_id"]:c["input"] for c in construction.fixed_contracts()["cases"]}


def identify(data):
    key = construction.digest(data)
    matches = [name for name,value in inputs().items() if construction.digest(value)==key]
    if len(matches) != 1: raise ValueError("unsupported_fixed_input")
    return matches[0]


def actions():
    windows=construction.source_domain.domain(construction.SOURCE_CASE)["public_derivation"]["supply_windows"]
    return [dict(zip(("initial_action","empty_departure","return_delay","later_action"),row))
        for row in itertools.product(("native_default","prefer_2"),windows,(0.,.5),("native_default","prefer_8"))]


def action_key(value):
    return tuple(value[k] for k in ("initial_action","empty_departure","return_delay","later_action"))


def initial_facts(data):
    """Declared finite-fixture initial facts; never claims a real capture."""
    identify(data)
    jobs={j["business_bag_id"]:{**copy.deepcopy(j), "protected_service":True,
        "status":"in_transit" if j["business_bag_id"]=="loaded" else "loading" if j["business_bag_id"]=="blocker" else "waiting_for_tray",
        "loaded_at":.1 if j["business_bag_id"]=="loaded" else -1.,
        "storage_entered_at":-1.,"storage_released_at":-1.} for j in data["jobs"]}
    trays={}
    for key,node,mode,job,generation,ready,kind in (
            ("L",0,"loaded","loaded",1,.1,"observed_load_completion"),
            ("E",5,"empty","",0,0.,"empty_available_at"),
            ("P",1,"loading","blocker",1,3.,"observed_load_completion")):
        trays[key]={"tray_id":key,"node":node,"mode":mode,"business_bag_id":job,
            "edge_from":-1,"edge_to":-1,"reception_node":-1,"generation":generation,
            "traversal_id":0,"committed_prefix":[node],"service_ready_known":True,
            "ready_kind":kind,"service_ready_at":ready,
            "load_complete_at":ready if job else -1.,"available_at":3. if key=="P" else 0.}
        if key=="P":trays[key]["load_end"]=3.
    resources={n["node"]:{"node":n["node"],
        "occupancy":sum(t["node"]==n["node"] for t in trays.values()),
        "actual_available":sum(t["node"]==n["node"] and t["mode"]=="empty" for t in trays.values())}
        for n in data["node_contracts"]}
    return jobs,trays,resources


def declared_captures(data):
    jobs,trays,resources=initial_facts(data)
    owners={n["node"]:n["resource_owner"] for n in data["node_contracts"]}
    result=[]
    for owner in ("A","B"):
        rows={"jobs":[j for j in jobs.values() if owners[j["origin"]]==owner],
            "trays":[t for t in trays.values() if owners[t["node"]]==owner],
            "resources":[r for r in resources.values() if owners[r["node"]]==owner]}
        result.append({"schema":"g31.live_obligation_declared_facts.v1","owner":owner,
            "captured_at":START,"expires_at":.21,"declared_delivered_at":START,
            "provenance":"pure_constructed_public_fixture_NOT_native_delivery",
            "known_faults":[],"pending_action_ids":[],**rows,
            "coverage":{kind:[r[field] for r in values] for (kind,field),values in zip(
                (("jobs","business_bag_id"),("trays","tray_id"),("resources","node")),rows.values(),strict=True)}})
    return result


def assemble(data,captures,*,now=START,protocol=None):
    """Full closed initial domain; supplied dictionaries cannot mint authority."""
    try:
        old_context._closed_tree(data);old_context._closed_tree(captures)
        case=identify(data)
        protocol=copy.deepcopy(PROTOCOL) if protocol is None else protocol
        if construction.encoded(protocol)!=construction.encoded(PROTOCOL):raise ValueError("unsupported_protocol")
        if type(now) is not float or now!=START:raise ValueError("unsupported_epoch")
        if type(captures) is not list or len(captures)!=2:raise ValueError("missing_sources")
        if {c.get("owner") for c in captures}!={"A","B"}:raise ValueError("missing_or_duplicate_owners")
        expected_jobs,expected_trays,expected_resources=initial_facts(data)
        owners={n["node"]:n["resource_owner"] for n in data["node_contracts"]}
        merged={"jobs":{},"trays":{},"resources":{}}
        for capture in captures:
            if capture.get("schema")!="g31.live_obligation_declared_facts.v1":raise ValueError("capture_schema")
            for field in ("captured_at","expires_at","declared_delivered_at"):
                if type(capture.get(field)) not in (int,float) or not math.isfinite(capture[field]):raise ValueError("invalid_capture_time")
            if not capture["captured_at"]==now==capture["declared_delivered_at"]<capture["expires_at"]:
                raise ValueError("unsupported_or_expired_capture_epoch")
            if capture.get("known_faults")!=[] or capture.get("pending_action_ids")!=[]:raise ValueError("unknown_fault_or_pending_action")
            for kind,field in (("jobs","business_bag_id"),("trays","tray_id"),("resources","node")):
                rows=capture[kind]; ids=[r[field] for r in rows]
                if ids!=capture["coverage"][kind] or len(ids)!=len(set(ids)) or set(ids)&set(merged[kind]):
                    raise ValueError("missing_duplicate_or_reordered_coverage")
                for row in rows:
                    if owners.get(row["origin"] if kind=="jobs" else row["node"])!=capture["owner"]:
                        raise ValueError("foreign_source_fact")
                    merged[kind][row[field]]=copy.deepcopy(row)
        for name,expected in (("jobs",expected_jobs),("trays",expected_trays),("resources",expected_resources)):
            if construction.encoded(merged[name])!=construction.encoded(expected):raise ValueError("unsupported_current_"+name)
        return {"status":"conditional_model_input","model_version":VERSION,"case_from_public_input":case,
            "input":copy.deepcopy(data),"contract":copy.deepcopy(data),"now":now,**merged,
            "source_records":copy.deepcopy(captures),"protocol":copy.deepcopy(protocol),
            "owner_pending_tray_requests":[],"online_information_delivered":False,
            "assumptions":["Constructed complete finite initial public state; real capture/delivery has not occurred.",
                "Normal future planning exchange modeled from local physical lifecycle, not proved future message readiness.",
                "New synthetic graph requires native validation; old retrospective conformance is not an error bound."]}
    except (TypeError,ValueError,KeyError,AttributeError,OverflowError) as exc:
        return unknown("input:"+str(exc))


class Projection(original.Projection):
    """Full inherited scorer/loop, isolated generic lifecycle extension.

    new_contract=False is only the old-domain regression mode. It leaves every
    command/output field unchanged; no saved outcomes enter execution.
    """
    def __init__(self,bundle,action,*,new_contract=True):
        self.new_contract=new_contract
        self.storage_pending={};self.storage_passed=set()
        self.operation_guards=[]
        super().__init__(bundle,action)

    def begin_leg(self,key,goal,*,ready=None):
        tray=self.trays[key];job=tray["job"]
        if key in self.storage_pending:
            stored=self.storage_pending.pop(key)
            if stored!=job or tray["node"]!=self.jobs[job]["storage_node"] or tray["mode"]!="loaded":
                raise ValueError("unmatched_storage_release")
            self.storage_passed.add(job);goal=self.jobs[job]["destination"]
        elif job is not None and job not in self.storage_passed and self.jobs[job]["storage_node"]>=0:
            # Initial creation/load completion points at the mandatory Storage;
            # the source leg may not jump directly to the business destination.
            if goal in (self.jobs[job]["destination"],self.jobs[job]["storage_node"]):
                goal=self.jobs[job]["storage_node"]
        super().begin_leg(key,goal,ready=ready)

    def complete_leg(self,key):
        tray=self.trays[key];job=tray["job"]
        if (tray["mode"]!="empty_transit" and job is not None and job not in self.storage_passed
                and self.jobs[job]["storage_node"]>=0 and tray["node"]==self.jobs[job]["storage_node"]):
            if key in self.storage_pending:raise ValueError("duplicate_storage_completion")
            tray["goal"]=None;tray["mode"]="storage";self.storage_pending[key]=job
            self.record("STORAGE_ENTER",key)
            self.schedule(max(self.time+self.jobs[job]["storage_min_dwell"],self.jobs[job]["storage_release_at"]),"storage_release",key)
        else:
            super().complete_leg(key)

    def request(self,key,destination,earliest):
        if self.new_contract:
            tray=self.trays[key];source=tray["node"]
            if (key,destination) not in (("E",1),("L",7)) or tray["mode"]!="empty" or tray["edge_to"]>=0 or tray["job"] is not None:
                raise ValueError("unsupported_nonlocal_or_nonempty_transfer")
            if (key=="E" and source!=5) or (key=="L" and source!=6):raise ValueError("unsupported_transfer_source")
            if (not self.nodes[source]["allow_export"] or not self.nodes[destination]["allow_receive"]
                    or self.nodes[source]["export_min_stock"]!=0):raise ValueError("unsupported_transfer_permissions")
            if key=="L" and self.returns==1:
                earliest=max(self.time,PROTOCOL["first_return_not_before"]) if self.action["return_delay"]==.5 else self.time
            # Immediate requests execute after wire; earliest=self.time is
            # lawful. The fixed expiry may not be silently ignored.
            if earliest<self.time or max(earliest,self.time+.01)>PROTOCOL["transfer_expiry"]:
                raise ValueError("unsupported_transfer_expiry_epoch")
            self.operation_guards.append({"at":self.time,"kind":"transfer","tray":key,
                "source_owner":self.nodes[source]["resource_owner"],"source":source,"destination":destination,
                "earliest":earliest,"expiry":PROTOCOL["transfer_expiry"],"conditional_local_state_only":True})
        super().request(key,destination,earliest)

    def grant(self,request):
        if self.new_contract and request["physical_status"]=="pending" and self.time>PROTOCOL["transfer_expiry"]:
            raise ValueError("unsupported_transfer_expiry_epoch")
        super().grant(request)

    def submit_preference(self,key,target,*,expiry=None):
        if self.new_contract:
            tray=self.trays[key]
            if key!="L" or tray["mode"]!="loaded" or tray["job"] not in ("loaded","reuse1","reuse2") or tray["edge_to"]>=0:
                raise ValueError("unsupported_route_source_lifecycle")
            expires=self.time+5. if expiry is None else expiry
            if not self.time+.01<=expires:raise ValueError("expired_route_before_wire")
            self.operation_guards.append({"at":self.time,"kind":"route","tray":key,
                "source_owner":self.nodes[tray["node"]]["resource_owner"],"source":tray["node"],
                "job":tray["job"],"prefix":tray["projection_prefix"],"next":target,"expiry":expires,
                "conditional_local_state_only":True})
        super().submit_preference(key,target,expiry=expiry)

    def execute_preference(self,record):
        if self.new_contract and self.time>record["expiry"]:
            raise ValueError("unmodeled_expired_route_execution")
        super().execute_preference(record)


def revalidate(bundle):
    if type(bundle) is not dict or bundle.get("model_version")!=VERSION or bundle.get("status")!="conditional_model_input":
        return unknown("unvalidated_input")
    if bundle.get("owner_pending_tray_requests")!=[]:return unknown("current_owned_pending_action")
    rebuilt=assemble(bundle["input"],bundle["source_records"],now=bundle["now"],protocol=bundle["protocol"])
    if rebuilt.get("status")!="conditional_model_input":return rebuilt
    for name in ("input","contract","jobs","trays","resources","now","case_from_public_input","protocol"):
        supplied=bundle.get(name)
        if name=="resources":
            # JSON object keys are strings. Normalize only canonical integer
            # node keys, retaining duplicate/foreign/row identity rejection.
            if type(supplied) is not dict or any(type(k) is not int and
                    not(type(k) is str and k.isascii() and k.isdecimal() and str(int(k))==k) for k in supplied):
                return unknown("invalid_resource_key")
            normalized={int(k):v for k,v in supplied.items()}
            if len(normalized)!=len(supplied):return unknown("duplicate_resource_key")
            supplied=normalized
        if construction.encoded(supplied)!=construction.encoded(rebuilt[name]):return unknown("mutated_assembled_"+name)
    return rebuilt


def predict(bundle,action):
    try:
        check_sources();old_context._closed_tree(bundle);old_context._closed_tree(action)
        rebuilt=revalidate(bundle)
        if rebuilt.get("status")!="conditional_model_input":return rebuilt
        if (set(action)!={"initial_action","empty_departure","return_delay","later_action"}
                or any(type(action.get(k)) not in (int,float) or not math.isfinite(action[k]) for k in ("empty_departure","return_delay"))
                or action not in actions()):return unknown("undeclared_action")
        engine=Projection(rebuilt,copy.deepcopy(action));result=engine.run()
        result.update(model_version=VERSION,conditional_operation_guards=engine.operation_guards,
            projected_transfers=copy.deepcopy(engine.requests),
            online_information_delivered=False,native_protection_certified=False,native_execution_certified=False,
            complete_request_100ms_certified=False)
        result.setdefault("limits",[]).extend(["New graph and generic Storage unvalidated against native.",
            "Hypothetical future capture readiness; no actual lawful delivery or point-estimate protection certificate."])
        # The inherited event loop does not model departure-lease expiration
        # after an earlier grant. Keep every event/output but fail the entire
        # new-domain prediction closed if an actual modeled empty departure is
        # beyond the declared39 deadline. This is a conservative strict bound,
        # not a business tolerance or a simulated native expired ACK.
        empty_entries=[r for r in result.get("physical_projection",[])
            if r.get("event")=="EDGE_ENTER" and r.get("job","missing") is None]
        violations=[copy.deepcopy(r) for r in empty_entries if
            type(r.get("at")) not in (int,float) or not math.isfinite(r["at"])
            or r["at"]>PROTOCOL["transfer_expiry"]]
        result["transfer_departure_expiry_audit"]={"status":"unknown" if violations else "passed_conditional_model",
            "modeled_empty_departures":len(empty_entries),"violations":violations,"deadline":PROTOCOL["transfer_expiry"],
            "actual_native_receipts":False}
        if violations:result["status"]="unknown_projection_empty_departure_expiry"
        return result
    except (TypeError,ValueError,KeyError,AttributeError,OverflowError) as exc:
        return unknown("projection:"+str(exc))
