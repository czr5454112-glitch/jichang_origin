"""Compare a visible A-to-B message with/without unrelated C-to-C publication."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).absolute().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--require-fixed", action="store_true")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = {"schema": "g31.private_message_counter_probe.v1", "binary": str(args.binary.absolute()),
              "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(), "variants": []}
    try:
        native = load_native(args.binary)
        data = tiny_cycle()
        data["transfers"] = []
        data["node_contracts"][1]["resource_owner"] = "B"
        data["node_contracts"][5]["resource_owner"] = "C"
        result["input"] = data
        for private_message in (False, True):
            s = native.NativeSession(data)
            s.advance_to(.05)
            if private_message:
                assert s.publish_demand("C", "C", 0)["status"] == "pending"
                s.advance_to(.05)
            before = s.observe("B")
            assert s.publish_service_forecast("A", "B", "T0", 1, .4)["status"] == "pending"
            assert s.publish_demand("A", "B", .4)["status"] == "pending"
            s.advance_to(.45)
            result["variants"].append({"private_C_publication": private_message,
                                       "B_before": before, "B_after": s.observe("B")})
        a, b = result["variants"]
        result["before_equal"] = a["B_before"] == b["B_before"]
        result["after_equal"] = a["B_after"] == b["B_after"]
        result["fixed"] = result["before_equal"] and result["after_equal"]
        result["status"] = "passed" if result["fixed"] else "reproduced_private_publication_counter_leak"
    except Exception as error:
        result["status"] = "execution_error"
        result["exception"] = repr(error)
        raise
    finally:
        (args.output / "receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "before_equal", "after_equal")}))
    return int(args.require_fixed and not result["fixed"])


if __name__ == "__main__":
    raise SystemExit(main())
