"""Execute immutable paper-suite cells through their existing audited runners.

This is orchestration, not another simulator or metric normalizer. A terminal
COMPLETE cell may have an unfinished population; full-population timing remains
the responsibility of the bound runner. Existing partial evidence is never
restarted or overwritten. One pool lock covers the entire campaign root.
"""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import gzip
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

PLAN_SCHEMA = "czr005.feng_paper_suite.plan.v1"
STATUS_SCHEMA = "czr005.feng_paper_suite.orchestration.v1"
NEW_G31 = "G31_S4_ADVERTISED_FAULT_REPAIR_V1"
HCA = "HCA_TIME_LABEL_REPAIR_V3"
DH = "FENG_DH_PAPER_SUITE_V6"
TARAU = "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY"
RUNNERS = {
    NEW_G31: ROOT / "scripts/eval/run_g31_tarau_paper_suite.py",
    TARAU: ROOT / "scripts/eval/run_g31_tarau_paper_suite.py",
    HCA: ROOT / "scripts/eval/run_hca_paper_suite.py",
    DH: ROOT / "scripts/eval/run_feng_dh_paper_suite.py",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def family(value: str) -> str:
    return "all_day_fault" if value == "fault" else value


def safe_root(value: str | Path) -> Path:
    original = Path(value).absolute()
    resolved = original.resolve()
    require(original == resolved and resolved.is_relative_to(ROOT),
            "campaign output traverses a link/junction or leaves the workspace")
    parts = resolved.relative_to(ROOT).parts
    require((len(parts) >= 3 and parts[:2] == ("outputs", "runtime") and "paper_suite" in parts[2])
            or (len(parts) >= 2 and parts[0] in ("build", "tmp") and "paper_suite" in parts[1]),
            "a new paper_suite runtime or QA namespace is required")
    return resolved


def verify_bound_cell(cell: dict) -> dict:
    """Recheck small immutable identities immediately before each use."""
    method = cell["method"]
    require(method in RUNNERS, "method is outside the four-method paper suite")
    require(Path(cell["runner_path"]).resolve(strict=True) == RUNNERS[method].resolve(strict=True),
            "plan runner does not match the fixed method-to-runner mapping")
    require(sha(RUNNERS[method]) == cell["runner_sha256"], "bound runner changed")
    path = Path(cell["spec_path"]).resolve(strict=True)
    require(sha(path) == cell["spec_sha256"], "bound spec changed")
    spec = read(path)
    for key in ("method", "seed", "speed_mps"):
        require(spec.get(key) == cell[key], f"plan/spec {key} mismatch")
    require(family(spec.get("family")) == family(cell["family"]), "plan/spec family mismatch")
    for key in ("map", "load_factor", "scenario_index"):
        if key in spec:
            require(spec[key] == cell[key], f"plan/spec {key} mismatch")
    require(spec.get("timing_policy") == "full_population_only", "wrong timing contract")
    require(float(spec.get("horizon_seconds", spec.get("fixed_horizon_seconds", -1))) == 98259.0,
            "wrong fixed horizon")
    require(sha(Path(spec["protocol_path"])) == spec["protocol_sha256"], "bound protocol changed")
    return spec


def load_plan(path: Path) -> dict:
    path = Path(path).resolve(strict=True)
    value = read(path)
    require(value.get("schema") == PLAN_SCHEMA and value.get("status") == "FROZEN_SPECS_NOT_ALL_EXECUTED",
            "only an explicitly frozen suite plan may be executed")
    root = safe_root(value["result_root"])
    require(isinstance(value.get("cells"), list) and value["cells"], "empty plan")
    protocols = {}
    for item in value.get("protocols", []):
        key = family(item["family"])
        require(key not in protocols, "duplicate family protocol")
        require(sha(Path(item["path"])) == item["sha256"], "plan protocol drift")
        protocols[key] = (Path(item["path"]).resolve(), item["sha256"])
    require(set(protocols) == {"base", "all_day_fault"}, "both family protocols must be frozen")
    ids, outputs, coordinates = set(), set(), set()
    for cell in value["cells"]:
        cell.setdefault("load_factor", cell.get("load"))
        name = cell["cell_id"]
        require(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,120}", name), "unsafe cell ID")
        require(name not in ids, "duplicate cell ID")
        ids.add(name)
        output = safe_root(cell["output_dir"])
        cells_root = root if root.name == "cells" else root / "cells"
        require(output == cells_root / name and str(output) not in outputs,
                "cell output must be its unique campaign cells/cell_id directory")
        outputs.add(str(output))
        fam = family(cell["family"])
        require(fam in protocols and cell["map"] in ("map2", "nanning")
                and cell["load_factor"] in (1, 2) and isinstance(cell["seed"], int), "invalid registered coordinates")
        require(cell["method"] in RUNNERS, "unregistered method")
        scenario = cell["scenario_index"]
        require(isinstance(scenario, int), "scenario index must be an integer")
        if fam == "base":
            require(scenario == 0 and cell["speed_mps"] in (1.5, 2.5, 3.0), "unregistered base condition")
        else:
            require(1 <= scenario <= 16 and cell["speed_mps"] == 2.5
                    and cell["method"] in (NEW_G31, HCA), "fault suite is G31/HCA at 2.5 m/s only")
        coordinate = tuple(cell[k] for k in ("method", "map", "load_factor", "speed_mps", "seed", "scenario_index"))
        require(coordinate not in coordinates, "duplicate experimental coordinate")
        coordinates.add(coordinate)
        spec = verify_bound_cell(cell)
        require((Path(spec["protocol_path"]).resolve(), spec["protocol_sha256"]) == protocols[fam],
                "cell protocol is not its frozen family protocol")
    value = dict(value, _path=str(path), _sha256=sha(path))
    return value


def select_cells(plan: dict, selectors: dict | None = None, limit: int | None = None) -> list[dict]:
    selectors = selectors or {}
    selected = []
    for cell in plan["cells"]:
        if all(not values or (family(cell[key]) if key == "family" else cell[key]) in
               ({family(v) for v in values} if key == "family" else set(values))
               for key, values in selectors.items()):
            selected.append(cell)
    if limit is not None:
        require(limit > 0, "selection limit must be positive")
        selected = selected[:limit]
    require(selected, "selection is empty")
    return selected


def check_result_envelope(cell: dict) -> dict:
    output = Path(cell["output_dir"])
    value, status = read(output / "normalized_result.json"), read(output / "runner_status.json")
    require(value.get("status") == "COMPLETE" and value.get("method") == cell["method"],
            "runner did not produce an accepted terminal result")
    require(status.get("status", "").lower() == "complete", "runner postprocessing has not completed")
    for key in ("map", "load_factor", "seed"):
        require(value.get(key) == cell[key], f"normalized {key} mismatch")
    if cell["method"] in (NEW_G31, TARAU):
        require(value["population_audit"]["status"] == "PASS", "native population audit failed")
        require(status["normalized_result_sha256"] == sha(output / "normalized_result.json"), "result SHA drift")
        full = value["population_audit"]["full_population_complete"]
        require(value["spec"]["speed_mps"] == cell["speed_mps"], "normalized speed differs")
    else:
        require(value.get("speed_mps") == cell["speed_mps"], "normalized speed differs")
        require((value.get("population_audit", {}).get("status") if cell["method"] == HCA
                 else value.get("audit_status")) == "PASS", "native population audit failed")
        full = value["full_population_complete"]
        spec_key = "run_spec_sha256" if cell["method"] == HCA else "spec_sha256"
        require(value.get(spec_key) == cell["spec_sha256"], "normalized spec hash differs")
        require((output / ("native_archive/manifest.json" if cell["method"] == HCA else "population_audit.json")).exists(),
                "required archive/audit evidence is absent")
    require(isinstance(full, bool), "population completion must be explicit")
    return {"normalized_result_sha256": sha(output / "normalized_result.json"),
            "full_population_complete": full, "method": cell["method"],
            "population_scope": "COMPLETE denotes valid terminal accounting, not necessarily full population completion"}


def verify_dh(cell: dict, spec: dict) -> None:
    """Use the frozen DH normalizer; verify its retained bytes without compiling."""
    module = importlib.import_module("scripts.eval.run_feng_dh_paper_suite")
    output = Path(cell["output_dir"])
    result, status = read(output / "normalized_result.json"), read(output / "runner_status.json")
    require(status["runner_sha256"] == cell["runner_sha256"] and status["spec_sha256"] == cell["spec_sha256"],
            "DH runtime provenance differs")
    require(status.get("returncode") == 0, "DH native process failed")
    classes = Path(spec.get("classes_dir", module.BUILD))
    require((classes / "build_identity.json").exists(), "DH frozen build identity missing; verifier will not compile")
    build = read(output / "build_identity.json")
    require(build == read(classes / "build_identity.json"), "DH consumed a different build")
    require(build["source_files"] == module.file_set(module.SOURCE, "*.java")
            and build["class_files"] == module.file_set(classes, "*.class")
            and build["java_sha256"] == sha(Path(module.JAVA))
            and build["javac_sha256"] == sha(Path(module.JAVAC)), "DH source/class/JDK drift")
    identity_path, identity = module.external._identity_payload(Path(spec["workload_identity_path"]))
    require(sha(identity_path) == spec["workload_identity_sha256"] == result["workload_identity_sha256"],
            "DH workload identity drift")
    expected_archives = {name + ".gz" for name in ("segments.csv", "bags.csv", "trace.csv", "summary.csv", "event_summary.csv")}
    require(len(result["archives"]) == len(expected_archives)
            and {item["file"] for item in result["archives"]} == expected_archives, "DH archive inventory differs")
    for entry in result["archives"]:
        archive = output / entry["file"]
        require(archive.parent.resolve() == output.resolve() and sha(archive) == entry["sha256"], "DH archive SHA drift")
        with gzip.open(archive, "rb") as stream:
            require(hashlib.file_digest(stream, "sha256").hexdigest() == entry["uncompressed_sha256"],
                    "DH archive content drift")
        require(sha(output / entry["file"].removesuffix(".gz")) == entry["uncompressed_sha256"],
                "DH retained native bytes differ")
    derived = module.normalize(identity, output)
    bags = derived.pop("bags")
    require(derived == read(output / "population_audit.json"), "DH population recomputation differs")
    require(derived["metrics"] == result["metrics"] and derived["full_population_complete"] == result["full_population_complete"],
            "DH normalized metrics differ")
    with gzip.open(output / "raw_bag_metrics.jsonl.gz", "rt", encoding="utf-8") as stream:
        require([json.loads(line) for line in stream] == bags, "DH complete raw-bag metric archive differs")


def verify_cell(cell: dict) -> dict:
    spec = verify_bound_cell(cell)
    output = Path(cell["output_dir"])
    require(not any((output / name).exists() for name in ("run.lock", "execution.lock", ".run_lock")),
            "cell has an execution lock; it is active or interrupted")
    before = sha(output / "normalized_result.json")
    if cell["method"] in (NEW_G31, TARAU):
        module = importlib.import_module("scripts.eval.run_g31_tarau_paper_suite")
        module.load_completed(output, prepared=module.prepare_spec(spec))
    elif cell["method"] == HCA:
        module = importlib.import_module("scripts.eval.run_hca_paper_suite")
        require((output / "native_archive/manifest.json").exists(), "HCA native archive is missing")
        module.load_result(output / "normalized_result.json")
        module.archive_cell(output)  # Existing archive required above; verifies raw/gzip/manifest equality.
    else:
        verify_dh(cell, spec)
    require(sha(output / "normalized_result.json") == before, "verification changed normalized result bytes")
    return check_result_envelope(cell)


def terminate_tree(process: subprocess.Popen) -> dict:
    if process.poll() is not None:
        return {"already_exited": True, "tree_termination_confirmed": True}
    if os.name == "nt":
        command = ["taskkill", "/PID", str(process.pid), "/T", "/F"]
        result = subprocess.run(command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        evidence = {"command": command, "returncode": result.returncode,
                    "stdout": result.stdout, "stderr": result.stderr}
        if result.returncode != 0:
            evidence["tree_termination_confirmed"] = False
            evidence["parent_poll"] = process.poll()
            return evidence
    else:
        os.killpg(process.pid, signal.SIGKILL)
        evidence = {"process_group": process.pid, "signal": "SIGKILL"}
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        evidence["tree_termination_confirmed"] = False
        return evidence
    evidence["tree_termination_confirmed"] = True
    return evidence


def execute_cell(cell: dict, record_dir: Path, timeout_seconds: float, abort: threading.Event) -> dict:
    started = time.time()
    record = {"cell_id": cell["cell_id"], "method": cell["method"], "status": "CHECKING",
              "spec_sha256": cell["spec_sha256"], "runner_sha256": cell["runner_sha256"],
              "output_dir": cell["output_dir"], "started_at_unix": started}
    record_dir.mkdir(parents=True, exist_ok=False)
    target = record_dir / "status.json"
    write(target, record)
    try:
        verify_bound_cell(cell)
        output = Path(cell["output_dir"])
        if (output / "normalized_result.json").exists():
            record.update(verify_cell(cell), status="REUSED_VERIFIED")
            return record
        require(not output.exists() or not any(output.iterdir()),
                "partial or foreign evidence exists; refusing to restart or overwrite")
        require(not abort.is_set(), "orchestration aborted before launch")
        command = [sys.executable, str(RUNNERS[cell["method"]]), "run",
                   "--spec", cell["spec_path"], "--output", cell["output_dir"]]
        record.update(status="RUNNING", command=command)
        with (record_dir / "stdout.txt").open("wb") as stdout, (record_dir / "stderr.txt").open("wb") as stderr:
            kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, **kwargs)
            record["pid"] = process.pid
            write(target, record)
            native_started = time.monotonic()
            while process.poll() is None:
                expired = timeout_seconds > 0 and time.monotonic() - native_started >= timeout_seconds
                if expired or abort.is_set():
                    record["termination"] = terminate_tree(process)
                    prefix = "TIMEOUT" if expired else "ABORT"
                    if not record["termination"]["tree_termination_confirmed"]:
                        record["status"] = prefix + "_TERMINATION_FAILED"
                        raise RuntimeError("process-tree termination was not confirmed; child may remain active; retain campaign lock for inspection")
                    record["status"] = "TIMED_OUT" if expired else "ABORTED"
                    raise RuntimeError("child process tree terminated; all scientific evidence and cell locks retained")
                time.sleep(0.5)
            record["returncode"] = process.returncode
        require(process.returncode == 0, f"runner exited {process.returncode}; evidence retained")
        verify_bound_cell(cell)
        record.update(check_result_envelope(cell), status="COMPLETE")
    except Exception as error:
        if record["status"] not in ("TIMED_OUT", "ABORTED", "TIMEOUT_TERMINATION_FAILED", "ABORT_TERMINATION_FAILED"):
            record["status"] = "FAILED"
        record.update(error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
    finally:
        record.update(finished_at_unix=time.time(), wall_seconds=time.time() - started)
        write(target, record)
    return record


def run_plan(plan: dict, cells: list[dict], *, workers: int = 4, timeout_seconds: float = 0,
             keep_going: bool = False) -> dict:
    require(workers > 0 and math.isfinite(timeout_seconds) and timeout_seconds >= 0, "invalid execution limits")
    root = safe_root(plan["result_root"])
    if root.name == "cells":
        root = root.parent
    require(sha(Path(plan["_path"])) == plan["_sha256"], "frozen plan changed before dispatch")
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".paper_suite_orchestration.lock"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:10]
    with lock.open("x", encoding="utf-8") as stream:
        json.dump({"pid": os.getpid(), "plan_sha256": plan["_sha256"], "run_id": run_id}, stream)
    output = root / "orchestration" / run_id
    abort = threading.Event()
    status = {"schema": STATUS_SCHEMA, "status": "RUNNING", "run_id": run_id,
              "plan_path": plan["_path"], "plan_sha256": plan["_sha256"],
              "orchestrator_sha256": sha(Path(__file__)), "python_executable": sys.executable,
              "workers": workers, "timeout_seconds": timeout_seconds, "keep_going": keep_going,
              "selected_cell_ids": [c["cell_id"] for c in cells], "selected_count": len(cells),
              "started_at_unix": time.time(), "cells": []}
    pending = iter(cells)
    stopped = False
    retain_lock = False
    futures = {}
    try:
        output.mkdir(parents=True, exist_ok=False)
        write(output / "status.json", status)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            def submit_one() -> bool:
                try:
                    cell = next(pending)
                except StopIteration:
                    return False
                future = pool.submit(execute_cell, cell, output / "cells" / cell["cell_id"], timeout_seconds, abort)
                futures[future] = cell["cell_id"]
                return True
            for _ in range(min(workers, len(cells))):
                submit_one()
            while futures:
                try:
                    done, _ = wait(futures, timeout=5, return_when=FIRST_COMPLETED)
                except KeyboardInterrupt:
                    abort.set()
                    stopped = True
                    continue
                for future in done:
                    cell_id = futures.pop(future)
                    try:
                        record = future.result()
                    except Exception as error:
                        record = {"cell_id": cell_id, "status": "FAILED", "error": str(error),
                                  "traceback": traceback.format_exc()}
                    status["cells"].append(record)
                    if record.get("termination", {}).get("tree_termination_confirmed") is False:
                        retain_lock = True
                        stopped = True
                    if record["status"] not in ("COMPLETE", "REUSED_VERIFIED") and not keep_going:
                        stopped = True
                if not stopped and not abort.is_set():
                    for _ in range(workers - len(futures)):
                        if not submit_one():
                            break
                status["active_cell_ids"] = list(futures.values())
                status["finished_count"] = len(status["cells"])
                status["stopped_dispatching_after_failure"] = stopped
                status["updated_at_unix"] = time.time()
                write(output / "status.json", status)
        accepted = sum(c["status"] in ("COMPLETE", "REUSED_VERIFIED") for c in status["cells"])
        status["status"] = "COMPLETE" if accepted == len(cells) else "ABORTED" if abort.is_set() else "FAILED"
        status["accepted_count"] = accepted
        status["not_started_cell_ids"] = [c["cell_id"] for c in cells
                                            if c["cell_id"] not in {r["cell_id"] for r in status["cells"]}]
        status["finished_at_unix"] = time.time()
        status["campaign_lock_retained"] = retain_lock
        status["status_path"] = str(output / "status.json")
        write(output / "status.json", status)
        return status
    finally:
        if retain_lock:
            write(lock, {"pid": os.getpid(), "run_id": run_id, "plan_sha256": plan["_sha256"],
                         "status": "PROCESS_TREE_TERMINATION_UNCONFIRMED", "status_path": str(output / "status.json"),
                         "recovery": "Inspect recorded child PIDs and native cell locks before manually releasing this campaign lock"})
        else:
            lock.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status", "verify"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=0)
    parser.add_argument("--keep-going", action="store_true")
    for flag, kind in (("family", str), ("method", str), ("map", str), ("load", float),
                       ("seed", int), ("speed", float), ("scenario", int), ("cell-id", str)):
        parser.add_argument("--" + flag, action="append", type=kind)
    parser.add_argument("--limit", type=int, help="first N matching cells in frozen plan order; intended for preflight")
    args = parser.parse_args(argv)
    plan = load_plan(args.plan)
    selectors = {"family": args.family, "method": args.method, "map": args.map, "load_factor": args.load,
                 "seed": args.seed, "speed_mps": args.speed, "scenario_index": args.scenario, "cell_id": args.cell_id}
    cells = select_cells(plan, selectors, args.limit)
    if args.command == "run":
        result = run_plan(plan, cells, workers=args.workers, timeout_seconds=args.timeout_seconds, keep_going=args.keep_going)
        print(json.dumps({k: result[k] for k in ("status", "selected_count", "accepted_count", "status_path")}))
        return 0 if result["status"] == "COMPLETE" else 1
    records = []
    for cell in cells:
        record = {"cell_id": cell["cell_id"]}
        try:
            if args.command == "verify":
                record.update(verify_cell(cell), status="VERIFIED")
            else:
                output = Path(cell["output_dir"])
                record["status"] = read(output / "runner_status.json").get("status") if (output / "runner_status.json").exists() else "NOT_STARTED"
                record["normalized_exists"] = (output / "normalized_result.json").exists()
                record["scope"] = "status snapshot only; not a fresh scientific audit"
        except Exception as error:
            record.update(status="FAILED", error=str(error))
        records.append(record)
    print(json.dumps({"status": "PASS" if all(r["status"] != "FAILED" for r in records) else "FAILED",
                      "plan_sha256": plan["_sha256"], "selected_count": len(cells), "cells": records}, ensure_ascii=False))
    return 1 if any(r["status"] == "FAILED" for r in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
