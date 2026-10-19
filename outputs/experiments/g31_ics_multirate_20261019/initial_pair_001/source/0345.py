"""Actual same-clock pledge/cancel counterexample, including saved pre-fix code."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

from . import joint_window_repair
from .native_host import load_native
from .validate_analytic_control import write
from .validate_joint_window_repair import SCENARIOS, prefix, scenario_input


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--implementation-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-fixed", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    implementation = joint_window_repair
    if args.implementation_file:
        spec = importlib.util.spec_from_file_location(
            "scripts.experiments.g31_ics_circulation._saved_joint_before", args.implementation_file)
        implementation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(implementation)
    path = Path(implementation.__file__)
    native = load_native(args.binary)
    rows = []
    for mutation in ("new_pledge", "cancel_pledge"):
        session, _ = prefix(native, scenario_input(SCENARIOS[0]))
        initial = session.observe("A")
        initial_domain = implementation.build_domain(initial)
        first = deepcopy(next(a for a in initial_domain["actions"] if len(a["candidates"]) == 2)["candidates"][0]["request"])
        first["request_id"] += ":other-controller"
        if mutation == "new_pledge":
            observed, domain = initial, initial_domain
            mutation_reply = session.submit_transfer_intent(first)
        else:
            session.submit_transfer_intent(first)
            observed = session.observe("A")
            domain = implementation.build_domain(observed)
            mutation_reply = session.cancel_transfer_intent(first["request_id"], "A")
        current = session.observe("A")
        assert current["version"] == observed["version"] and current["now"] == observed["now"] and current != observed
        selected = next(a for a in domain["actions"] if a["candidates"])
        before = session.offline_state_sha256()
        reply = implementation.submit_action(session, selected, observed)
        after = session.offline_state_sha256()
        rows.append({"mutation": mutation, "original_public": observed, "current_public": current,
                     "action": selected, "mutation_reply": mutation_reply, "submit_reply": reply,
                     "unchanged_version": current["version"], "unchanged_clock": current["now"],
                     "state_before_submission": before, "state_after_submission": after,
                     "passed": reply["status"] == "stale_read_set" and before == after})
    receipt = {"schema": "g31.joint_read_set_probe.v1", "status": "passed" if all(r["passed"] for r in rows) else "failed",
               "implementation": str(path), "implementation_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
               "binary_sha256": hashlib.sha256(Path(args.binary).read_bytes()).hexdigest(), "rows": rows}
    write(args.output / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "rows": [{"mutation": r["mutation"],
        "reply": r["submit_reply"]["status"], "passed": r["passed"]} for r in rows]}))
    if args.require_fixed and receipt["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
