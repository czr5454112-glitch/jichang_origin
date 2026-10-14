"""Exercise whether unrelated private transport changes a local traversal version."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).absolute().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation.native_host import load_native, prepare_input, tiny_cycle


def inputs():
    plain = tiny_cycle()
    plain["transfers"] = []
    plain["jobs"] = [plain["jobs"][0]]
    plain["jobs"][0]["arrival"] = 1
    plain["node_records"] += [(7, 1, .01, 7, 0, [8]), (8, 1, .01, 8, 0, [7])]
    plain["edge_records"] += [(7, 8, .01, 1), (8, 7, .01, 1)]
    plain["node_contracts"] += [dict(node=n, zone="C", capacity=1) for n in (7, 8)]
    plain["edge_contracts"] += [dict(zip(("from", "to", "capacity", "entry_headway"), (u, v, 1, .01)))
                                for u, v in ((7, 8), (8, 7))]
    plain["trays"].append(dict(tray_id="private-C-tray", node=7))
    plain = prepare_input(plain)
    private = deepcopy(plain)
    private["jobs"].append(dict(business_bag_id="private-C-job", origin=7, destination=8, arrival=0,
                                deadline=40, unload_seconds=.01, hold_seconds=0, load_seconds=.01))
    return plain, private


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--require-fixed", action="store_true")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = {"schema": "g31.private_traversal_counter_probe.v1", "binary": str(args.binary.absolute()),
              "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(), "variants": []}
    try:
        native = load_native(args.binary)
        for private_transport, data in zip((False, True), inputs()):
            s = native.NativeSession(data)
            s.advance_to(.5)
            before = s.observe("A")
            s.advance_to(1.2)
            result["variants"].append({"private_C_transport": private_transport, "input": data,
                                       "A_before": before, "A_after": s.observe("A")})
        a, b = result["variants"]
        result["before_equal"] = a["A_before"] == b["A_before"]
        result["after_equal"] = a["A_after"] == b["A_after"]
        result["fixed"] = result["before_equal"] and result["after_equal"]
        result["status"] = "passed" if result["fixed"] else "reproduced_private_traversal_counter_leak"
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
