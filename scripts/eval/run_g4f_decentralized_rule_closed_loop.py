from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.g4f_no_astar_runtime import main


if __name__ == "__main__":
    main()
