from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.eval.g4i_runtime import run_all


if __name__ == "__main__":
    run_all(run_stress=False, run_benchmark=False, include_large_smoke=True)
