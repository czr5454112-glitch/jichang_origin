"""Freeze the fixed analytic construction; never load a native simulator."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from . import public_live_obligation_interval as model


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def project_sources():
    paths = {Path(__file__).resolve(), ROOT / "tests/test_g31_circulation_live_obligation_interval.py"}
    for module in tuple(sys.modules.values()):
        value = getattr(module, "__file__", None)
        if value:
            path = Path(value).resolve()
            if path.is_file() and path.is_relative_to(ROOT) and path.suffix == ".py":
                paths.add(path)
    paths.update(ROOT / p for p in (
        "cpp/ics_core/runtime/circulation.hpp",
        "cpp/ics_core/runtime/circulation_runtime_impl.hpp",
        "cpp/ics_core/runtime/circulation_recovery_impl.hpp",
        "cpp/ics_core/runtime/event_driven_junction.hpp",
        "scripts/experiments/g31_ics_circulation/public_native_preference_projection.py",
        "scripts/experiments/g31_ics_circulation/public_native_preference_search.py",
        "pyproject.toml"))
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in sorted(paths)}


def write(path, value):
    path.write_bytes(model.encoded(value))


def freeze(output, test_xml):
    output = Path(output).resolve(); test_xml = Path(test_xml).resolve()
    if not output.is_relative_to(OUT):
        raise ValueError("output_outside_declared_experiment_directory")
    if output.exists():
        raise ValueError("immutable_output_already_exists")
    suites = ET.parse(test_xml).getroot().findall("testsuite")
    if len(suites) != 1 or any(int(suites[0].get(k, "-1")) != v for k,v in
            {"tests":19,"failures":0,"errors":0,"skipped":0}.items()):
        raise ValueError("wrong_pure_test_receipt")
    sources = project_sources()
    package = model.fixed_contracts()
    if tuple(c["case_id"] for c in package["cases"]) != model.CASE_IDS:
        raise ValueError("changed_fixed_case_denominator")
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for row in package["cases"]:
        data = row.pop("input")
        path = output / (row["case_id"] + ".input.json")
        write(path, data)
        if sha(path) != row["input_sha256"]:
            raise ValueError("input_canonical_hash_mismatch")
        row["input_path"] = str(path)
        records.append({"case_id":row["case_id"], "interval_status":row["interval_screen"]["status"],
            "failed_predicates":row["interval_screen"]["failed_predicates"],
            "native_embedding":"unknown", "five_job_protection":"unknown"})
    write(output / "construction.json", package)
    for relative, expected in sources.items():
        source = ROOT / relative; target = output / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(source.read_bytes())
        if sha(target) != expected: raise ValueError("archive_source_drift:" + relative)
    xml_target = output / "pure_tests.xml"; xml_target.write_bytes(test_xml.read_bytes())
    design = OUT / "joint_protection_mechanism_design_001.json"
    report = {
        "schema":"g31.live_obligation_interval_frozen.v1", "status":"source_only_fixed_construction_unvalidated_embedding",
        "construction":{"path":str(output / "construction.json"), "sha256":sha(output / "construction.json")},
        "cases":records, "case_count":3, "parameter_grid_searches":0, "new_projection_executions":0,
        "native_executions":0, "old_validation256_read":False,
        "tests":{"path":str(xml_target),"sha256":sha(xml_target),"passed":19,"skipped":0},
        "sources":sources, "source_scope":"All currently imported project Python files plus the named test, freezer, reviewed native semantics, public scorer/search and project configuration. These native files are read-only source references, not a compiled-runtime acceptance.",
        "interpreter":{"path":sys.executable,"sha256":sha(sys.executable)},
        "prior_design":{"path":str(design),"sha256":sha(design)},
        "source_semantics":[
            {"path":"cpp/ics_core/runtime/circulation.hpp","anchor":"occupancy / reserve_enter","finding":"Source occupancy ends and target occupancy begins at irreversible reservation publication through edge_to; arrival time alone is insufficient. Per-tray OR counting includes station, incoming edge and reception reservation."},
            {"path":"cpp/ics_core/runtime/circulation_runtime_impl.hpp","anchor":"EDGE_ENTER handler / source_berth_departed","finding":"Observed entry receipt follows reservation and emits the resource-waiter notification. The named .001 wake bound belongs only to the isolated known source-path timing."},
            {"path":"cpp/ics_core/runtime/circulation_recovery_impl.hpp","anchor":"circulation_wake_resource_wait","finding":"A resource wake after the same node has already arbitrated at this timestamp adds max(minimum_service_seconds,dispatch_headway_seconds). The public fixture uses.001; the analytic bound assumes only the one identified wake, not arbitrary downstream wakes."},
            {"path":"cpp/ics_core/runtime/circulation_runtime_impl.hpp","anchor":"storage_in / ready=max(time,release,time+minimum_dwell)","finding":"Native Storage logic is already per job. The old public predictor has only loaded-specific Storage handling and cannot predict this new P stage unchanged."},
            {"path":"scripts/experiments/g31_ics_circulation/public_native_preference_projection.py","anchor":"candidate_rows / choose_next / commit","finding":"A preference is neither forced edge nor forced waiting. All new edges are ordinary alternatives for every eligible tray; S4 and current capacity must determine the actual edge."}],
        "analytic_proof":{
            "variables":"C is node3 capacity-one reservation occupancy. Q is reuse1 on L; X is the still-live blocker job on P. t0 and x are reservation starts, HQ/HX are reservation-to-release durations. a is Q advance, D=t0-x.",
            "baseline":"D>=HX permits X to release C before baseline Q reserves it.",
            "normal_route":"If0<=a<=D, X remains first; safe Q advance is at most D-HX. IfD<a<=s<D+HQ, Q reserves first but still occupies C at X's otherwise reservation epoch, harming X unless another modeled mechanism changes the premise.",
            "bypass":"When bypass really excludes C and causes only extra Q duration delta, s>delta gives Q improvement. Requiring s-delta>D-HX makes it better than the isolated best protected timing-only bound.",
            "fixed_initial":"delta>m excludes paying the bypass with the assumed slow-path fixed-initial advancement m. This m is NOT a certified bound over native_default's complete16-action family; that family must be explicitly evaluated.",
            "numbers":"D1.2,HQ=HX1.1,s1.5,m.5,delta1.3: isolated normal safe advance<=.1, isolated bypass advance=.2. These are decimal-rational margins, not native completion deltas.",
            "source_bound":"The declared two source paths differ by1.0 in the no-extra-conflict source timing (up to1.001 with the one named same-time wake). Combined with removing the existing .5 first-return wait gives1.5 supply advance. Neither number is a general original-map/native upper bound.",
            "essential_unproved_premises":["Actual E receiving/service occupancy and all rejected/retried supply histories", "Q current-generation irreversible reservation and true C release", "Autonomous native_default path, including new alternatives1->9->3 and3->10", "Actual later preference still authorized before committed edge and after message/ACK delays", "All five complete protected-job outcomes, downstream Storage4/node6 contention and both reuse cycles"]},
        "single_next_falsifiable_experiment":{
            "status":"proposal_only_not_executed_or_native_authorized",
            "experiment":"Implement the new public forward model with generic per-job Storage and full native scorer/calendar semantics, then evaluate exactly these3 fixed inputs x all32 existing action tuples once (96 predictions total). No parameter search or post-result revision of inputs.",
            "why_this_denominator":"Four E windows cannot be dropped: one already analytically overlaps early Q. Both16-action fixed-initial and16-action later-default families are required to avoid a selected-cube necessity claim. Every method receives the same32 actions, observations and evaluation budget.",
            "counterfactual":"For the positive input, compare deployed protected choices with the complete fixed-initial and later-default families; trace first R1 actual modeled release, real cross-owner6->7 transfer, Q resource3 reservation, X conflict and bypass edge. Controls must retain their predicted absent-overlap/insufficient-advance failure and all five outcomes.",
            "falsification":"Reject this fixed mechanism if E/default dispatch, permission, source timing or any five-job regression defeats it; preserve all unknown/unexecuted cells. If ordinary coordinate or LNS matches, record no joint-method advantage even if the physical mechanism exists.",
            "subsequent_native_gate":"Only after separate review of exact source/public-model semantics and legal message input coverage. Native evidence, complete-request timing and novelty remain unassessed."},
        "claims":{"isolated_reservation_lemma":True,"native_embedding":False,"five_job_protection":False,
            "online_delivery":False,"joint_method_advantage":False,"100ms":False}
    }
    after = project_sources()
    if sources != after: raise ValueError("source_changed_during_construction")
    report["source_changed"] = []
    write(output / "receipt.json", report)
    return {"output":str(output),"receipt_sha256":sha(output / "receipt.json"),"sources":len(sources),"cases":records,"pure_passed":19}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True);parser.add_argument("--test-xml",required=True)
    args=parser.parse_args();print(json.dumps(freeze(args.output,args.test_xml),ensure_ascii=False))


if __name__ == "__main__":main()
