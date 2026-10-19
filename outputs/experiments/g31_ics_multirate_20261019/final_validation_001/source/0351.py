"""Six bounded original route cells: accepted027 plain/timed, no policy change."""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import shutil
import sys
import time
from types import FunctionType, SimpleNamespace

from . import probe_original_route_update_internal_deadline as policy
from . import native027_request_timing as abi
from . import native027_timing_gate as gate
from . import route_update_phase_measurement as measure

ROOT, OUT, CASES = policy.ROOT, policy.OUT, policy.CASES
ADMISSION, HORIZON, PARENT_SECONDS = policy.ADMISSION, policy.HORIZON, policy.PARENT_SECONDS
JOB, ROOT_ID, ENDPOINTS = policy.JOB, policy.ROOT_ID, policy.ENDPOINTS
RouteUpdate = policy.RouteUpdate
SCHEMA = "g31.original_route_native027_phase.v1"
MODULE = "scripts.experiments.g31_ics_circulation.probe_original_route_update_native027_phase"
ARMS = ("plain", "timed")
REFERENCE = OUT / "original_route_internal_deadline_prepare_001"
CONTRACT = {"path": str(OUT / "native027_accepted_contract_001.json"),
    "sha256": "db7c4bd36a5cdc505afec24473c2f5ce6dc2dd85912c5d9fe8ba9bedee269dc6"}
BINARY_SHA = "845486b745bc6e65a9988d1ef5429336b60fd472eb73c39e133e19ec93a7e7be"
old = SimpleNamespace(**{**vars(policy.old), "BINARY_SHA": BINARY_SHA})
require = policy.require


_SOURCE_CACHE = None


def source_paths():
    global _SOURCE_CACHE
    if _SOURCE_CACHE is not None:
        paths, hashes = _SOURCE_CACHE
        require(all(old.sha(path)==digest for path,digest in hashes.items()), "phase_cached_source_changed")
        return paths
    pending = list(policy.source_paths()) + list(gate.source_paths()) + [Path(__file__), Path(measure.__file__),
        Path(__file__).with_name("verify_original_route_update_native027_phase.py"),
        Path(__file__).with_name("launch_original_route_update_native027_phase.py"),
        ROOT/"tests/test_g31_circulation_original_route_native027_phase.py"]
    found = {}
    def enqueue(target):
        for p in (target.with_suffix(".py"), target/"__init__.py"):
            if p.is_file() and p.resolve().is_relative_to(ROOT):
                pending.append(p)
                for ancestor in p.parents:
                    if ancestor == ROOT: break
                    if (ancestor/"__init__.py").is_file(): pending.append(ancestor/"__init__.py")
    while pending:
        path = pending.pop().resolve()
        if path in found: continue
        require(path.is_file(), "phase_source_missing")
        source=path.read_bytes(); found[path]=hashlib.sha256(source).hexdigest()
        for node in ast.walk(ast.parse(source.decode("utf8"))):
            if isinstance(node, ast.ImportFrom):
                for base in ([path.parent] if node.level else [ROOT, ROOT/"src"]):
                    for _ in range(max(0, node.level-1)): base = base.parent
                    if node.module: base = base.joinpath(*node.module.split(".")); enqueue(base)
                    for alias in node.names:
                        if alias.name != "*": enqueue(base/alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for base in (ROOT, ROOT/"src"): enqueue(base.joinpath(*alias.name.split(".")))
    require(all(old.sha(path)==digest for path,digest in found.items()), "phase_source_changed_during_parse")
    _SOURCE_CACHE=(tuple(sorted(found)), found)
    return _SOURCE_CACHE[0]


def phase_contract():
    return {"schema": SCHEMA, "arms": list(ARMS), "cases": CASES, "sessions": 6,
        "horizon": HORIZON, "admission": ADMISSION, "parent_seconds": PARENT_SECONDS,
        "native": "Accepted027 only; never transfer025 timing authority to026.",
        "policy": "Reuse exact frozen internal-deadline worker code through a private function-global copy. Only binary/schema/pin check and diagnostic constructors differ. All event controller and request logic are unchanged.",
        "parity": "Each027 plain and timed case must match actual026 internal001 pre9600 parts, request API sequence, intent and complete9900 producer seal;027 plain/timed all warm API semantics must also match after declared clocks only.",
        "capture": "Enable accepted027 at complete9600 before root observation; fixed1000000 record capacity, overflow/exception incomplete becomes unknown. Capture take/export remain recorded cold work. Native identities and all nested/exclusive remainder retained.",
        "scope": "Partial computation diagnostics and actual request invocation maximum only. No inferred pure-physics subtraction, no averaging/shared-cost discount, no general100ms certification."}



def accepted_inventory():
    """Every file consumed by the closed44-case ABI verifier, without reaccepting it."""
    pins = {}
    def add(path, expected=None):
        path=Path(path).resolve(strict=True); digest=old.sha(path)
        require(expected is None or digest==expected, "phase_acceptance_pin")
        require(str(path) not in pins or pins[str(path)]==digest,"phase_acceptance_conflict")
        pins[str(path)]=digest
        return old.read(path) if path.suffix==".json" else None
    def build(receipt, archive, binary, expected):
        value=add(receipt); add(binary,expected)
        for relative,digest in value["source_after"].items():
            rel=Path(relative.replace("\\","/")); require(not rel.is_absolute() and ".." not in rel.parts,"phase_archive_path")
            add(Path(archive)/rel,digest)
    contract=add(CONTRACT["path"],CONTRACT["sha256"])
    build(contract["build_receipt"],contract["source_archive"],contract["binary"],contract["binary_sha256"])
    acceptance=contract["runtime_acceptance"]; report=add(acceptance["path"],acceptance["sha256"])
    folder=Path(acceptance["path"]).parent
    plan=add(folder/"plan.json",report["plan_sha256"])
    candidate=add(plan["contract_reference"]["path"],plan["contract_reference"]["sha256"])
    add(folder/"contract_reference.json"); add(folder/"candidate_contract.json",plan["contract_reference"]["sha256"])
    build(candidate["build_receipt"],candidate["source_archive"],candidate["binary"],candidate["binary_sha256"])
    build(plan["native026_build"],plan["native026_source_archive"],plan["native026_binary"],plan["native026_sha256"])
    for path,digest in plan["source_sha256"].items():
        add(path,digest); add(folder/"source"/Path(path).relative_to(ROOT),digest)
    for case,digest in plan["input_sha256"].items(): add(folder/"inputs"/(case+".json.gz"),digest)
    for arm,cases in report["raw"].items():
        add(folder/(arm+".process.json"),report["process_sha256"][arm])
        add(folder/arm/"completion.json",report["completion_sha256"][arm])
        for case,digest in cases.items(): add(folder/arm/(case+".json.gz"),digest)
    for path,digest in contract["validator_source_sha256"].items(): add(path,digest)
    add(gate.__file__,contract["raw_gate_verifier_source_sha256"])
    add(measure.Native027TimingCapture.__module__.replace(".","/")+".py")
    return pins


def reference_pins():
    pins={str(REFERENCE/name):old.sha(REFERENCE/name) for name in
        ("receipt.json","preregistered_protocol.json","independent_verification.json")}
    for case in CASES:
        for name in ("input.json.gz","raw.json.gz","service_tape.jsonl.gz","shards.json"):
            path=REFERENCE/case/name; pins[str(path)]=old.sha(path)
        for row in old.read(REFERENCE/case/"shards.json"):
            path=REFERENCE/case/row["path"]; require(old.sha(path)==row["sha256"],"phase_reference_shard")
            pins[str(path)]=row["sha256"]
    return pins

def prepare(output):
    require(not output.exists(), "phase_output_exists")
    accepted = abi.verify_contract(CONTRACT, require_runtime=True)["contract"]
    require(accepted["binary_sha256"] == BINARY_SHA, "phase_binary_authority")
    reference_plan = old.read(REFERENCE/"preregistered_protocol.json")
    policy.verify_pins(REFERENCE, reference_plan)
    require(old.read(REFERENCE/"receipt.json")["status"] == "completed_finite_probe", "phase_reference_incomplete")
    output.mkdir(parents=True)
    sources = {str(p): old.sha(p) for p in source_paths()}
    plans = {}
    for arm in ARMS:
        directory = output/arm
        plan = policy.prepare(directory)
        plan.update(schema=SCHEMA, phase_arm=arm, phase_contract=phase_contract(), contract_reference=deepcopy(CONTRACT),
            native_binary=accepted["binary"], native_binary_sha256=BINARY_SHA,
            compiled_source_sha256=accepted["source_sha256"], source_before=sources,
            phase_reference=str(REFERENCE), phase_reference_pins=reference_pins(),
            accepted_evidence_pins=accepted_inventory())
        for name in ("receipt.json", "preregistered_protocol.json", "independent_verification.json"):
            plan["phase_reference_pins"][str(REFERENCE/name)] = old.sha(REFERENCE/name)
        for case in CASES:
            for name in ("input.json.gz", "raw.json.gz", "service_tape.jsonl.gz", "shards.json"):
                plan["phase_reference_pins"][str(REFERENCE/case/name)] = old.sha(REFERENCE/case/name)
        for path, digest in sources.items():
            target = directory/"source_archive"/Path(path).relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        for relative in accepted["source_sha256"]:
            target = directory/"compiled_source_archive"/relative
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(Path(accepted["source_archive"])/relative, target)
        old.write(directory/"preregistered_protocol.json", plan)
        plans[arm] = old.sha(directory/"preregistered_protocol.json")
        verify_pins(directory, plan)
    campaign = {"schema": SCHEMA, "status": "prepared_native_unexecuted", "contract": phase_contract(),
        "plans": plans, "contract_reference": deepcopy(CONTRACT), "source_before": sources,
        "interpreter": {"path": sys.executable, "sha256": old.sha(sys.executable)}}
    old.write(output/"campaign.json", campaign)
    old.write(output/"branch_ledger.json", {f"{arm}/{case}": {"status": "unknown_unexecuted"} for arm in ARMS for case in CASES})
    return campaign


def verify_pins(output, plan, *, runtime=False):
    require(plan["schema"] == SCHEMA and plan["phase_arm"] in ARMS and plan["phase_contract"] == phase_contract()
        and plan["contract_reference"] == CONTRACT and plan["cases"] == CASES and plan["horizon"] == HORIZON
        and plan["admission"] == ADMISSION and plan["native_branch_budget"] == 3, "phase_scope")
    require(old.sha(CONTRACT["path"]) == CONTRACT["sha256"], "phase_contract_changed")
    authority = old.read(CONTRACT["path"])
    require(plan["native_binary"] == authority["binary"] and old.sha(plan["native_binary"]) == BINARY_SHA
        and plan["native_binary_sha256"] == BINARY_SHA and plan["compiled_source_sha256"] == authority["source_sha256"], "phase_binary_changed")
    require(set(plan["source_before"]) == {str(p) for p in source_paths()}, "phase_source_closure")
    require(old.sha(output/"input.json.gz") == plan["source_input_sha256"], "phase_input_hash")
    data = old.gzread(output/"input.json.gz"); old.verify_input(data)
    expected=old.read(REFERENCE/"preregistered_protocol.json")
    replaced={"schema","native_binary","native_binary_sha256","compiled_source_sha256","source_before","case_inputs"}
    require(all(plan.get(key)==value for key,value in expected.items() if key not in replaced), "phase_unchanged_policy_plan")
    require(plan["phase_reference_pins"]==reference_pins() and plan["accepted_evidence_pins"]==accepted_inventory(), "phase_evidence_inventory")
    for name in CASES:
        path = output/name/"input.json.gz"
        require(old.sha(path) == plan["case_inputs"][name] and old.gzread(path) == policy.case_input(data, name), "phase_fault_input")
    for path, digest in plan["source_before"].items():
        require(old.sha(path) == digest == old.sha(output/"source_archive"/Path(path).relative_to(ROOT)), "phase_source_changed")
    for relative, digest in plan["compiled_source_sha256"].items():
        require(old.sha(output/"compiled_source_archive"/relative) == digest, "phase_compiled_archive_changed")
    for field in ("authority_pins", "baseline_prefix_pins", "scheduled_reference_pins", "phase_reference_pins"):
        for path, digest in plan[field].items(): require(old.sha(path) == digest, "phase_evidence_changed")
    require(plan["phase_reference"] == str(REFERENCE) and old.sha(plan["interpreter"]["path"]) == plan["interpreter"]["sha256"], "phase_reference_or_interpreter")
    if runtime:
        loaded = {str(Path(m.__file__).resolve()) for m in list(sys.modules.values()) if getattr(m, "__file__", None)
            and Path(m.__file__).suffix == ".py" and Path(m.__file__).resolve().is_relative_to(ROOT)}
        require(loaded <= set(plan["source_before"]), "phase_unarchived_runtime_import")


def worker(output, case):
    plan = old.read(output/"preregistered_protocol.json"); verify_pins(output, plan)
    native = old.load_native(plan["native_binary"])
    spans = measure.PythonSpans(); tapes = []
    def factory(session):
        tape = measure.PhaseTape(session, native_module=native, reference=CONTRACT, timed=plan["phase_arm"] == "timed")
        tapes.append(tape); return tape
    # Exact original worker bytecode; no mutation of imported policy globals.
    environment = {**policy.worker.__globals__, "old": old, "SCHEMA": SCHEMA, "verify_pins": verify_pins,
        "ServiceTape": factory, "RouteUpdate": measure.measured_route_type(spans) if plan["phase_arm"] == "timed" else policy.RouteUpdate}
    inherited = FunctionType(policy.worker.__code__, environment, name="unchanged_internal_worker")
    try: inherited(output, case)
    finally:
        if tapes:
            require(len(tapes) == 1, "phase_multiple_sessions")
            old.gzwrite(output/case/"phase_capture.json.gz", tapes[0].diagnostic(spans))


def verify_campaign(output):
    campaign = old.read(output/"campaign.json")
    require(campaign["schema"] == SCHEMA and campaign["contract"] == phase_contract() and set(campaign["plans"]) == set(ARMS)
        and campaign["contract_reference"] == CONTRACT, "phase_campaign")
    require(campaign["source_before"] == {str(p): old.sha(p) for p in source_paths()}, "phase_campaign_sources")
    for arm in ARMS:
        directory = output/arm
        require(old.sha(directory/"preregistered_protocol.json") == campaign["plans"][arm], "phase_plan_changed")
        verify_pins(directory, old.read(directory/"preregistered_protocol.json"))
    return campaign


def execute(output, admission):
    require(sys.stdin.readline().rstrip("\n") == admission == old.sha(output/"campaign.json"), "phase_job_admission")
    began = time.perf_counter(); measured = time.perf_counter_ns()
    campaign = verify_campaign(output); abi.verify_contract(CONTRACT, require_runtime=True)
    require(all(not (output/arm/name/artifact).exists() for arm in ARMS for name in CASES
        for artifact in ("worker_claim.json","raw.json.gz","error_prefix.json.gz","segments","phase_capture.json.gz")), "phase_preexisting_execution")
    with (output/"execution_claim.json").open("x", encoding="utf8") as f: json.dump({"campaign_sha256": admission}, f)
    ledger = {f"{arm}/{case}": {"status": "unknown_unexecuted"} for arm in ARMS for case in CASES}
    for arm in ARMS:
        directory = output/arm
        receipt = {"schema": SCHEMA, "status": "running", "parent_measured_start_ns": measured,
            "cases": {name: {"status": "unknown_unexecuted"} for name in CASES}}
        old.write(directory/"receipt.json", receipt)
        for name in CASES:
            command = [sys.executable, "-m", MODULE, "--output", str(directory), "--worker", name]
            result = policy.child(command, directory/name/"worker.log", began)
            artifacts={artifact:old.sha(directory/name/artifact) for artifact in
                ("raw.json.gz","service_tape.jsonl.gz","shards.json","phase_capture.json.gz","error_prefix.json.gz")
                if (directory/name/artifact).is_file()}
            receipt["cases"][name] = {**result, "command": command, "artifact_sha256":artifacts}
            if name == next(iter(CASES)) and "parent_child_start_ns" in result:
                receipt["shared_parent_setup_ns"] = result["parent_child_start_ns"]-measured
            ledger[f"{arm}/{name}"] = receipt["cases"][name]
            old.write(directory/"receipt.json", receipt); old.write(output/"branch_ledger.json", ledger)
        receipt["status"] = "children_finished"; old.write(directory/"receipt.json", receipt)
    command = [sys.executable, "-m", "scripts.experiments.g31_ics_circulation.verify_original_route_update_native027_phase", "--output", str(output), "--write-report"]
    verification = {**policy.child(command, output/"verification.log", began), "command": command}
    changed = []
    try: verify_campaign(output); abi.verify_contract(CONTRACT, require_runtime=True)
    except BaseException as error: changed.append(repr(error))
    receipt = {"schema": SCHEMA, "campaign_sha256": admission, "cases": ledger, "verification": verification,
        "source_changed": changed, "wall_seconds": time.perf_counter()-began, "complete_100ms_certified": False}
    receipt["status"] = "completed_finite_phase_cohort" if all(r.get("exit_code") == 0 for r in ledger.values()) and verification.get("exit_code") == 0 and not changed and receipt["wall_seconds"] <= PARENT_SECONDS else "unknown_incomplete_phase_cohort"
    old.write(output/"receipt.json", receipt)
    return 0 if receipt["status"] == "completed_finite_phase_cohort" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--worker", choices=tuple(CASES)); parser.add_argument("--campaign", action="store_true"); parser.add_argument("--admission")
    args = parser.parse_args(); output = args.output.resolve()
    require(sum((args.prepare, args.worker is not None, args.campaign)) == 1, "phase_mode")
    if args.prepare: prepare(output); print("prepared_native_unexecuted")
    elif args.worker: worker(output, args.worker)
    else: raise SystemExit(execute(output, args.admission))


if __name__ == "__main__": main()
