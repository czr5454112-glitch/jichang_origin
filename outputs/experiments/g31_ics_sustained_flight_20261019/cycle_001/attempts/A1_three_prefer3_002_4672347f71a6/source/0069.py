"""Fixed96 model-only denominator and conservative supplied-result assessor."""
from __future__ import annotations
import copy
import math
from . import public_live_obligation_projection as model

METHODS=("coordinate_strict","coordinate_plateau","pair_repair","finite_MPC_reference")


def plan_rows():
    return {case+f"/vector_{i:02d}":{"case":case,"action":copy.deepcopy(action),"status":"unknown_unexecuted"}
        for case in model.construction.CASE_IDS for i,action in enumerate(model.actions())}


def incumbent_action():
    windows=model.construction.source_domain.domain(model.construction.SOURCE_CASE)["public_derivation"]["supply_windows"]
    # Keep the stronger historical immediate-return incumbent. The analytic
    # not-before b is one alternative, never a reason to weaken protection.
    return {"initial_action":"native_default","empty_departure":windows[1],"return_delay":0.,"later_action":"native_default"}


def assessment(prediction,action):
    """No actual physics/delivery certificate is created from a model vector."""
    reasons=[];completion=prediction.get("completion",{})
    if (prediction.get("status")!="conditional_prediction" or set(completion)!=model.JOBS
            or any(type(t) not in (int,float) or not math.isfinite(t) or not 0<=t<=model.HORIZON for t in completion.values())
            or prediction.get("completion_sum")!=sum(completion.values())):
        reasons.append("missing_or_nonfinite_five_job_completion")
    if prediction.get("native_protection_certified") is not False or prediction.get("online_information_delivered") is not False:
        reasons.append("invalid_authority_claim")
    commands=prediction.get("projected_commands",[]);events=prediction.get("physical_projection",[])
    actual={}
    for name,job,source,flag,target in (("initial","loaded",0,"initial_action",2),("later","reuse1",7,"later_action",8)):
        route=[r for r in commands if r.get("job")==job and r.get("from")==source]
        traversals=[r for r in events if r.get("event")=="EDGE_ENTER" and r.get("job")==job and r.get("source")==source]
        actual[name]=traversals[0].get("target") if traversals else None
        if len(traversals)!=1:reasons.append(name+"_missing_or_repeated_edge")
        if action[flag]=="native_default":
            if route:reasons.append(name+"_default_must_have_no_command")
        elif (len(route)!=1 or route[0].get("status")!="updated" or route[0].get("next")!=target
                or type(route[0].get("ack_delivered_at")) not in (int,float)
                or not route[0]["executed_at"]<=route[0]["ack_delivered_at"]<=model.HORIZON
                or actual[name]!=target):
            reasons.append(name+"_preference_unexecuted_or_no_target_edge")
    transfers=prediction.get("projected_transfers",[])
    supplied=[r for r in transfers if r.get("tray")=="E"]
    returns=[r for r in transfers if r.get("tray")=="L"]
    received=lambda r:(r.get("physical_status")=="received" and r.get("terminal") is True and r.get("ack")=="received"
        and type(r.get("ack_at")) in (int,float) and r["ack_at"]<=model.HORIZON)
    if (len(returns)!=2 or not all(received(r) for r in returns) or not supplied or not received(supplied[-1])
            or any(r.get("physical_status")!="rejected" or r.get("ack")!="rejected" or r.get("terminal") is not True for r in supplied[:-1])):
        reasons.append("missing_terminal_transfers_or_returns")
    return {"status":"assessed_conditional_model" if not reasons else "unknown_model_or_selected_action",
        "reasons":reasons,"completion":copy.deepcopy(completion),"actual_projected_next":actual,
        "native_protection_certified":False,"actual_native_execution":False}


def valid(row):return row.get("assessment",{}).get("status")=="assessed_conditional_model"


def protected(row,base):
    if not valid(row) or not valid(base):return None
    return all(row["assessment"]["completion"][job]<=base["assessment"]["completion"][job] for job in model.JOBS)


def solve(rows,method):
    """Same32 model queries. Unprotected proposals can be evaluated internally."""
    if method not in METHODS or len(rows)!=32:raise ValueError("unsupported_finite_search")
    bykey={model.action_key(r["action"]):r for r in rows.values()}
    basekey=model.action_key(incumbent_action());base=bykey[basekey]
    queried={};order=[];frontier=[basekey];expanded=set()
    def query(key):
        if key not in queried:
            if len(queried)>=32:return None
            queried[key]=bykey[key];order.append(key)
        return queried[key]
    def score(key):return sum(bykey[key]["assessment"]["completion"].values()),key
    query(basekey)
    if valid(base):
        if method=="finite_MPC_reference":
            for key in sorted(bykey):query(key)
        else:
            while frontier:
                current=min(frontier,key=score);frontier.remove(current)
                if current in expanded:continue
                expanded.add(current);eligible=[]
                for key in sorted(bykey):
                    distance=sum(a!=b for a,b in zip(key,current,strict=True))
                    if not 1<=distance<=(2 if method=="pair_repair" else 1):continue
                    row=query(key)
                    if row is None or protected(row,base) is not True:continue
                    improves=score(key)[0]<score(current)[0] if method=="coordinate_strict" else score(key)[0]<=score(current)[0]
                    if improves and key not in expanded:eligible.append(key)
                if method=="coordinate_strict":frontier=[min(eligible,key=score)] if eligible else []
                else:frontier.extend(k for k in eligible if k not in frontier)
    eligible=[key for key,row in queried.items() if protected(row,base) is True]
    best=min(eligible,key=score) if eligible else None
    return {"method":method,"status":"conditional_finite_selection" if best else "unknown_incumbent_or_candidate",
        "selected_action":copy.deepcopy(bykey[best]["action"]) if best else None,
        "selected_sum":score(best)[0] if best else None,"evaluations":len(queried),"budget":32,
        "query_order":[list(k) for k in order],"unqueried_count":32-len(queried),
        "selection_input":"same public model outputs, not native outcomes", "native_protection_certified":False}


def compare(rows):
    declared=plan_rows()
    if set(rows)!=set(declared) or any(any(rows[k].get(f)!=v[f] for f in ("case","action")) for k,v in declared.items()):
        raise ValueError("incomplete_or_misbound_fixed96")
    result={}
    for case in model.construction.CASE_IDS:
        group={k:r for k,r in rows.items() if r["case"]==case}
        if len(group)!=32:raise ValueError("wrong_case_denominator")
        baseline=next(r for r in group.values() if r["action"]==incumbent_action())
        reference={}
        for name,keep in (("fixed_initial_native_default",lambda a:a["initial_action"]=="native_default"),
                          ("later_native_default",lambda a:a["later_action"]=="native_default")):
            family={k:r for k,r in group.items() if keep(r["action"])}
            if len(family)!=16:raise ValueError("wrong_reference_denominator")
            complete=valid(baseline) and all(valid(r) for r in family.values())
            eligible=[k for k,r in family.items() if complete and protected(r,baseline) is True]
            best=min(eligible,key=lambda k:(sum(family[k]["assessment"]["completion"].values()),k),default=None)
            reference[name]={"status":"complete_conditional_reference" if complete else "unknown_incomplete_reference",
                "members":list(family),"member_count":16,"best_key":best,
                "point_model_only_no_native_protection":True}
        result[case]={"assessed":sum(valid(r) for r in group.values()),"unknown":sum(not valid(r) for r in group.values()),
            "methods":{method:solve(group,method) for method in METHODS},"references":reference,
            "strict_point_comparisons":{k:{"protected":protected(r,baseline),
                "deltas":{job:r["assessment"]["completion"][job]-baseline["assessment"]["completion"][job] for job in model.JOBS}
                    if valid(r) and valid(baseline) else None} for k,r in group.items()}}
    return {"status":"complete_fixed96_model_denominator","row_count":96,"cases":result,
        "all_source_input_facts_hypothetical":True,"native_executions":0,"online_information_delivered":False,
        "joint_method_advantage_certified":False,"native_protection_certified":False}
