"""Build the fail-closed G4IRSF11 A--H pretraining gate artifacts."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
for import_root in (ROOT, ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from scripts.eval.g4irsf11_pretraining_gate import (  # noqa: E402
    evaluate_pretraining_gate,
    write_gate_artifacts,
)


def main() -> int:
    manifest = evaluate_pretraining_gate(ROOT)
    paths = write_gate_artifacts(ROOT, manifest)
    print(
        json.dumps(
            {
                "status": manifest["overall_status"],
                "artifacts": [path.relative_to(ROOT).as_posix() for path in paths],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    # A partial gate is an evidence result, not a script execution failure.  The
    # trainer independently refuses to proceed unless every gate is PASS.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
