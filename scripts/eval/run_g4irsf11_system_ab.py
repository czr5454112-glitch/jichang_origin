"""Generate the fail-closed G4IRSF11 system-level A/B inventory."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.g4irsf11_system_ab import build_system_ab_matrix, write_system_ab_artifacts  # noqa: E402


if __name__ == "__main__":
    rows = build_system_ab_matrix(ROOT)
    paths = write_system_ab_artifacts(ROOT, rows)
    print(f"[g4irsf11-system-ab] rows={len(rows)} table={paths[0]} report={paths[1]}")
