"""Run the predeclared headway screen sequentially; never overwrite a run."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
CAMPAIGN = ROOT / "outputs/experiments/g31_no_wait_20261024"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", type=int, choices=(1, 2), required=True)
    parser.add_argument("--suite", choices=("headway_002", "rolling_003", "rolling_004", "rolling_005", "rolling_006"), default="rolling_005")
    parser.add_argument("--variants", nargs="+", default=("fixed1_w0", "fixed1_w1", "adaptive_w1"))
    parser.add_argument("--maps", nargs="+", choices=("map2", "nanning"), default=("map2", "nanning"))
    args = parser.parse_args()
    mode, build = args.suite.split("_")
    allowed = {"fixed1_w0", "fixed1_w1", "adaptive_w1"}
    if mode == "rolling":
        allowed.update({"fixed1_w0_cap0", "fixed1_w0_cap30", "fixed1_w0_cap120"})
    if build == "006":
        allowed.update({"fixed1_w0_cap120_relax1", "fixed1_w0_cap120_relax2"})
    if not set(args.variants) <= allowed:
        raise ValueError("variant was not predeclared for this suite")
    binary = ROOT / f"build/g31_no_wait_{build}/python/g31_nowait.cp311-win_amd64.pyd"
    expected_binary = {"002": "88123cc10928b5fb3049fc871accbd0f59e22bc5d9a724b1094b27238459727f",
                       "003": "48c6dda04ed4df96aea60c7287c2bac8dce20fcea4624e5f4ad2110adc919a77",
                       "004": "adaead44f96975163dcd50a036099be8f1dbc56f5169239ac0cd9330c102e4e1",
                       "005": "f2643e3657e7d9da4e25e403a396801125c533efaaa67b5599c3b49f768f9713",
                       "006": "15615754481c266df972d5360f565ade6661101d0a3df4435877220d585ce1fc"}[build]
    runner = Path(__file__).with_name("run.py")
    for variant in args.variants:
        for map_name in args.maps:
            out = CAMPAIGN / f"g31_{map_name}_{args.scale}x_{mode}_{variant}_{build}"
            config = Path(__file__).with_name("configs") / f"{mode}_{variant}_{build}.json"
            if out.exists():
                manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
                if (manifest["status"] != "complete" or manifest["config"] != json.loads(config.read_text())
                        or manifest["binary_sha256"] != expected_binary):
                    raise ValueError(f"existing result does not match this completed screen: {out}")
                print(f"Keeping completed evidence: {out.name}", flush=True)
                continue
            subprocess.run([sys.executable, str(runner), "--map", map_name,
                            "--scale", str(args.scale), "--binary", str(binary),
                            "--config", str(config), "--output", str(out)], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
