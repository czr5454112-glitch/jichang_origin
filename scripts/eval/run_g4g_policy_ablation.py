from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.run_g4g_no_astar_fallback_validation import main


if __name__ == "__main__":
    main()
