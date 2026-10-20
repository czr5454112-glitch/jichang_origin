"""Execute, record, and optionally reject online queries into an unissued tape."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).absolute().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-fixed", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": "g31.future_transfer_namespace_probe.v1", "binary": str(args.binary.absolute()),
               "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(), "variants": []}
    try:
        native = load_native(args.binary)
        plain = tiny_cycle()
        plain["transfers"] = []
        request = dict(request_id="future-private", tray_id="T0", source=0, destination=4,
                       issued_at=40, earliest_departure=40, expiry=60, message_delay=0)
        future = deepcopy(plain)
        future["transfers"].append(request)
        for label, data in (("without_future_request", plain), ("with_future_request", future)):
            cancel, submit = native.NativeSession(data), native.NativeSession(data)
            before = cancel.offline_state_sha256()
            observed = cancel.observe("A")
            cancellation = cancel.cancel_transfer_intent(request["request_id"], "A")
            publication = submit.submit_transfer_intent(dict(request, owner_id="A"))
            row = {"name": label, "input": data, "observation_before": observed,
                   "cancel_response": cancellation, "cancel_changed_state": before != cancel.offline_state_sha256(),
                   "submit_response": publication}
            receipt["variants"].append(row)
        a, b = receipt["variants"]
        receipt["observations_equal"] = a["observation_before"] == b["observation_before"]
        receipt["fixed"] = receipt["observations_equal"] and all(
            row["cancel_response"] == dict(status="rejected", reason="unknown_request") and
            row["submit_response"] == dict(status="rejected", reason="online_request_namespace_required") and
            not row["cancel_changed_state"] for row in receipt["variants"])
        receipt["status"] = "passed" if receipt["fixed"] else "reproduced_hidden_future_oracle"
    except Exception as error:
        receipt["status"] = "execution_error"
        receipt["exception"] = repr(error)
        raise
    finally:
        (args.output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in ("status", "fixed", "observations_equal")}, ensure_ascii=False))
    return 1 if args.require_fixed and not receipt["fixed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
