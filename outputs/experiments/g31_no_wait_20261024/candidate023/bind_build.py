"""Bind one completed immutable candidate build to fresh development contracts."""
from pathlib import Path
import argparse
import copy
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = HERE.parent / "candidate019" / "registered_contracts_019"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def evidence(path):
    return dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if not args.name.replace("_", "").isalnum():
        raise ValueError("invalid build name")
    build = ROOT / "build" / ("g31_no_wait_" + args.name)
    receipt_path = build / "build_receipt.json"
    receipt = read(receipt_path)
    if receipt["status"] != "complete" or len(receipt["binaries"]) != 1:
        raise ValueError("completed immutable native build required")
    for name, expected in receipt["source_sha256"].items():
        if evidence(build / "source" / name)["sha256"] != expected:
            raise ValueError("frozen build source changed: " + name)
    binary = next((build / "python").glob("g31_nowait*.pyd"))
    if evidence(binary)["sha256"] not in receipt["binaries"].values():
        raise ValueError("binary hash does not match build")
    output = HERE / ("registered_contracts_" + args.name)
    output.mkdir(exist_ok=False)
    contracts = {}
    for label in ("original_window", "drain200000"):
        parent = BASE / ("physical_contract_" + label + ".json")
        contract = copy.deepcopy(read(parent))
        contract["native_source"] = evidence(build / "source" / "core.cpp")
        contract["default_binary"] = evidence(binary)
        contract["candidate_id"] = "g31_continuous_" + args.name + "_source_attempt_edf"
        contract["future_source_policy"] = {
            "status": "development_not_promoted",
            "precommit_is_not_admission": True,
            "source_fifo_advances_only_at_actual_launch": True,
            "first_planning_clock_unchanged": True,
            "search_horizon_independent_of_observation_end": True,
        }
        path = output / ("physical_contract_" + label + ".json")
        save(path, contract)
        contracts[label] = dict(parent=evidence(parent), candidate=evidence(path))
    audit_paths = [HERE.parent / "candidate010" / "auditors" / (name + ".py") for name in (
        "__init__", "headway_audit", "future_metadata", "rolling_replay", "tht_metrics", "source_policy_audit")]
    save(output / "REGISTRATION_RECEIPT.json", dict(
        schema="g31.candidate023.registration.v1", status="isolated_development_only",
        build_receipt=evidence(receipt_path), contracts=contracts,
        runner=evidence(HERE / "run_candidate.py"), adapter=evidence(HERE / "continuous_adapter.py"),
        plan=evidence(HERE / "PREDECLARED_PLAN.json"),
        auditors=[evidence(path) for path in audit_paths],
        controls=[evidence(HERE / ("controls_" + label + ".json")) for label in ("original_window", "drain200000")],
        formal_default_modified=False))
    print(json.dumps(dict(contracts=str(output), binary=evidence(binary)), indent=2))


if __name__ == "__main__":
    main()
