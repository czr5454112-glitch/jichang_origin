from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    _prepare_imports()

    from phase8_synthetic_replay_cases import (  # pylint: disable=import-outside-toplevel
        MANIFEST_PATH,
        load_manifest_cases,
        write_manifest,
    )

    output = write_manifest(MANIFEST_PATH)
    cases = load_manifest_cases(output)
    task_total = sum(case.spec.task_count for case in cases)
    print(
        "phase8_synthetic_replay_manifest cases={} tasks={} path={}".format(
            len(cases),
            task_total,
            output,
        )
    )


if __name__ == "__main__":
    main()
