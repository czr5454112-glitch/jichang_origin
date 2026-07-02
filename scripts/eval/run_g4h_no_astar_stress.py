from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.g4h_runtime import run_all


if __name__ == "__main__":
    run_all(refresh_g4g=False, run_stress=True)
