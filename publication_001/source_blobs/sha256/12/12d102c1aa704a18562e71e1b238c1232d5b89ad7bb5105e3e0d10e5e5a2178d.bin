"""Record a discovered historical source-closure limitation without rewriting it.

This is a current-source supplement, never a retrospective pre-run freeze.
Importing the old probe discovers its Python startup dependencies but creates no
NativeSession. Prior archives can corroborate current bytes only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT/"src") not in sys.path: sys.path.insert(0, str(ROOT/"src"))


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(directory, prior_archive):
    from . import probe_installed_operations  # startup imports only
    plan = json.loads((directory/"plan.json").read_text(encoding="utf-8"))
    missing = []
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not filename or not (name == "czr005" or name.startswith("czr005.")): continue
        path = Path(filename).resolve()
        if path.suffix != ".py" or str(path) in plan["source_sha256"]: continue
        if not path.is_relative_to(ROOT): raise ValueError("external_project_module:"+str(path))
        relative = path.relative_to(ROOT); archived = prior_archive/relative
        missing.append({"module": name, "relative_path": relative.as_posix(), "current_sha256": sha(path),
            "prior_archive": str(archived), "prior_archive_sha256": sha(archived) if archived.is_file() else None,
            "same_current_bytes_as_prior_archive": archived.is_file() and sha(path) == sha(archived)})
    missing.sort(key=lambda row: row["relative_path"])
    return {"schema": "g31.historical_source_closure_supplement.v1", "status": "historical_closure_incomplete",
        "original_plan": str(directory/"plan.json"), "original_plan_sha256": sha(directory/"plan.json"),
        "original_declared_source_count": len(plan["source_sha256"]), "currently_loaded_omitted_modules": missing,
        "original_source_archive_complete": False, "retrospective_pre_run_freeze": False,
        "native_rerun": False, "original_native_evidence_rewritten": False,
        "limit": "Current import discovery and matching older archive bytes corroborate current startup sources; they do not establish what unpinned bytes executed in the earlier probe. Its native parity/timing evidence remains, with a limited 42-file frozen-source claim."}


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("directory", type=Path)
    p.add_argument("--prior-archive", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(); result = audit(args.directory, args.prior_archive)
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output.parent/Path(__file__).name).write_bytes(Path(__file__).read_bytes())


if __name__ == "__main__": main()
