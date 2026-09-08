"""Continue the frozen V4 paper suite in qualified, resumable stages.

This file only coordinates existing runners. It never changes native data,
restarts partial cells, removes another process's lock, or kills processes.
Use --check-only for read-only readiness validation without dispatching cells.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_feng_paper_suite as pool

PLAN = ROOT / "outputs/evidence/paper_suite_20260907/frozen_plan_v4/plan.json"
PLAN_SHA = "ad400a4363958087625903833fa4730e10c3787864e74180b3f5fa4cfcde4e71"
BINARY_SHA = "38b07ddfbc661c5243ab62a4963d84514405a87b11afa41538a94a42d2665b20"
REPORTER = ROOT / "scripts/eval/report_feng_paper_suite.py"
RUNTIME = ROOT / "outputs/runtime/feng_paper_suite_20260907"
EXISTING_POOL = RUNTIME / "orchestration/20260907T081701Z_a0825164cc/status.json"
VALIDATION = ROOT / "outputs/runtime/g31_fault_paper_suite_validation_20260907"
NORMAL1 = VALIDATION / "normal_full_v1/comparison.json"
NORMAL2 = VALIDATION / "normal_full_2x_v1/comparison.json"
MICRO14 = ROOT / "outputs/runtime/g31_fault_potential_repair_20260907/microtests/38b07ddfbc661c52/microtests.json"
CPP4 = ROOT / "outputs/evidence/paper_suite_20260907/g31_advertised_fault_repair/reset_checkpoint_v1/verification.json"
TARAU8 = ROOT / "outputs/evidence/paper_suite_20260907/tarau_native_identity_equivalence_v2/verification.json"
FAULT4 = ROOT / "outputs/runtime/g31_paper_suite_fault_preflight_20260907/preflight_verification.json"
WAIT_SECONDS = 4 * 60 * 60
POLL_SECONDS = 10
SCHEMA = "czr005.feng_paper_suite.staged_campaign.v1"


def require(value, message):
    if not value:
        raise ValueError(message)


def ref(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": pool.sha(path), "bytes": path.stat().st_size}


def bound(path, digest):
    item = ref(path)
    require(item["sha256"] == digest, f"bound evidence changed: {path}")
    return item


def stable_read(path):
    first = ref(path)
    value = pool.read(path)
    require(pool.sha(Path(path)) == first["sha256"], f"evidence changed during read: {path}")
    return value, first


def normal_comparison(path, load):
    value, reference = stable_read(path)
    require(value.get("status") == "PASS" and value.get("pair_count") == 2, "normal on/off comparison is not PASS for two pairs")
    pairs = value.get("pairs", [])
    require(len(pairs) == 2 and {(p.get("map"), p.get("load_factor"), p.get("seed")) for p in pairs}
            == {(m, float(load), 104729) for m in ("map2", "nanning")}, "normal comparison coordinates differ")
    support, qualifications = [], []
    for pair in pairs:
        require(pair.get("exact_native_bag_output_equal") is True and pair.get("segments", 0) > 0,
                "normal comparison lacks exact full native bag equality")
        for enabled in (False, True):
            folder = Path(path).parent / f"{pair['map']}_{load}x_{'on' if enabled else 'off'}"
            result, result_ref = stable_read(folder / "result.json")
            status, status_ref = stable_read(folder / "runner_status.json")
            identity, identity_ref = stable_read(folder / "identity.json")
            recovered = (Path(path).resolve() == NORMAL1.resolve() and pair["map"] == "map2" and not enabled
                         and result.get("native_reexecuted") is False)
            require((status.get("status") == "COMPLETE" or recovered) and result.get("status") == "PASS"
                    and result.get("audit", {}).get("status") == "PASS", "normal native run/audit is incomplete")
            require(identity == result["identity"] and identity.get("enabled") is enabled
                    and identity.get("map") == pair["map"] and identity.get("load_factor") == load
                    and identity.get("seed") == 104729 and identity.get("binary_sha256") == BINARY_SHA,
                    "normal native run identity differs")
            require(result["audit"]["segment_count"] == pair["segments"]
                    and result["audit"]["completed_segment_count"] == pair["completed_segments"],
                    "normal comparison does not cover each full segment population")
            support += [result_ref, status_ref, identity_ref,
                        bound(identity["binary_path"], BINARY_SHA),
                        bound(identity["workload_identity_path"], identity["workload_identity_sha256"])]
            if recovered:
                reaudit, reaudit_ref = stable_read(folder / "reaudit.json")
                require(reaudit.get("status") == "PASS" and reaudit["audit"] == result["audit"]
                        and status.get("status") == "RUNNING", "specific retained-native reaudit differs")
                archive_path = folder / "native_payload.json.gz"
                support += [reaudit_ref, bound(archive_path, reaudit["native_sha256"])]
                with gzip.open(archive_path, "rt", encoding="utf-8") as stream:
                    summary = json.load(stream)["summary"]
                require(summary.get("loaded_cpp_binary_sha256") == BINARY_SHA
                        and summary.get("completed_count") == pair["completed_segments"]
                        and summary.get("requested_count") == pair["segments"]
                        and summary.get("safe_execution_pass") is True
                        and summary.get("merge_grant_active_state_integrity_pass") is True
                        and summary.get("event_limit_reached") is False
                        and summary.get("physical_fault_edge_entry_violation_count") == 0
                        and summary.get("merge_grant_protocol_integrity_pass") is False
                        and summary.get("merge_grant_lifecycle_dropped_count", 0) > 0,
                        "retained original native summary does not support the separated execution/log-completeness reaudit")
                qualifications.append({"cell": folder.name, "acceptance": "EXPLICIT_REAUDIT_OF_RETAINED_NATIVE",
                    "original_runner_status": status["status"], "original_full_protocol_flag": False,
                    "native_reexecuted": False, "reason": reaudit["reason"],
                    "scope": "Historical RUNNING is retained as recorded; acceptance comes from native SHA and explicit population/execution reaudit, not that stale status."})
            else:
                archive = result["native_archive"]
                archive_path = folder / archive["path"]
                require(archive_path.resolve().parent == folder.resolve(), "normal native archive leaves its cell")
                support.append(bound(archive_path, archive["sha256"]))
            require(all(not val for key, val in result.get("repair_counters", {}).items()
                        if key != "s4_advertised_fault_potential_repair_enabled"), "normal control unexpectedly performed fault repair")
    return {"name": f"normal_full_{load}x", "status": "PASS", "reference": reference, "support": support,
            "qualifications": qualifications,
            "scope": "Full submitted population on/off identity and exact native bag equality; unfinished population is retained, not rejected."}


def prerequisites():
    gates = []
    value, reference = stable_read(MICRO14)
    require(value.get("status") == "PASS" and value.get("test_count") == 14
            and value.get("failed_count") == 0 and value.get("skipped_count") == 0
            and value.get("binary_sha256") == BINARY_SHA, "final 14 native tests are not PASS")
    gates.append({"name": "g31_final_14", "status": "PASS", "reference": reference,
                  "support": [bound(value["binary_path"], BINARY_SHA),
                              bound(value["assertion_driver_path"], value["assertion_driver_sha256"]),
                              bound(value["pytest_xml_path"], value["pytest_xml_sha256"])]})
    value, reference = stable_read(CPP4)
    result = value.get("result", {})
    require(value.get("status") == result.get("status") == "PASS" and value.get("returncode") == 0
            and result.get("cases") == 4 and all(result.get(k) is True for k in
            ("reset_same_object", "checkpoint_park_restore", "reachable_sibling", "unsupported_source_contract_rejected")),
            "native reset/checkpoint four-case gate failed")
    artifacts = [bound(CPP4.parent / row["path"], row["sha256"]) for row in value["artifacts"]]
    stdout = json.loads((CPP4.parent / "stdout.txt").read_text(encoding="utf-8-sig"))
    require(stdout == result, "native C++ stdout and four-case result disagree")
    gates.append({"name": "cpp_reset_checkpoint_4", "status": "PASS", "reference": reference, "support": artifacts})
    value, reference = stable_read(TARAU8)
    cases = value.get("cases", [])
    require(value.get("status") == "PASS" and value.get("case_count") == len(cases) == 8
            and value.get("binary_identities", {}).get("final38b") == BINARY_SHA, "Tarau eight-pair gate is incomplete")
    require(len({c["case"] for c in cases}) == 8 and all(c["new_active_bijection"] is True
            and c["old_active_bijection"] is True and set(c["equality"]) ==
            {"bags", "decisions", "events", "hold_attempts", "merge_grant_lifecycle"}
            and all(v is True for v in c["equality"].values()) for c in cases), "Tarau native equality/integrity differs")
    gates.append({"name": "tarau_identity_8", "status": "PASS", "reference": reference, "support": []})
    gates.append(normal_comparison(NORMAL1, 1))
    value, reference = stable_read(FAULT4)
    expected = {f"f_{m}_1x_v2p5_s104729_q{q}_g31" for m in ("map2", "nanning") for q in ("01", "02")}
    require(value.get("status") == "PASS" and value.get("audited_cell_count") == value.get("expected_cell_count") == 4
            and value.get("formal_matrix_cells_executed") == 0 and value.get("population_prefiltered") is False
            and len(value.get("cells", [])) == 4 and {c["cell_id"] for c in value["cells"]} == expected,
            "four isolated fault preflights are not complete")
    support = []
    for cell in value["cells"]:
        require(cell["audit_status"] == cell["population_audit"]["status"] == "PASS"
                and cell["binary_sha256"] == BINARY_SHA, "fault preflight audit/binary differs")
        summary = cell["native_summary"]
        require(summary["safe_execution_pass"] is True and summary["merge_grant_active_state_integrity_pass"] is True
                and summary["physical_fault_edge_entry_violation_count"] == 0
                and summary["event_limit_reached"] is False, "fault preflight execution failed")
        support.append(bound(cell["normalized_result_path"], cell["normalized_result_sha256"]))
    # These historical native runs bind their saved generating source. Do not
    # substitute the latest adapter SHA or reinterpret their legacy flags.
    binding_path = FAULT4.parent / "loader_source_binding.json"
    binding, binding_ref = stable_read(binding_path)
    require(binding.get("status") == "PASS" and binding["exact_preflight_receipt_sha256"] == reference["sha256"],
            "historical fault-preflight source binding differs")
    support += [binding_ref, bound(binding["frozen_native_runner_path"], binding["frozen_native_runner_sha256"])]
    gates.append({"name": "historical_fault_full_1x_4", "status": "PASS", "reference": reference, "support": support})
    return gates


def stage_cells(plan):
    base = pool.select_cells(plan, {"family": ["base"], "seed": [104729], "speed_mps": [2.5]})
    fault = pool.select_cells(plan, {"family": ["all_day_fault"], "seed": [104729], "load_factor": [1], "scenario_index": [1, 2]})
    require(len(base) == 16 and len(fault) == 8 and len(plan["cells"]) == 1760, "registered stage cell counts differ")
    require(plan.get("family_counts") == {"base": 480, "all_day_fault": 1280}, "wrong suite family population")
    return base, fault


def campaign_root(plan):
    root = pool.safe_root(plan["result_root"])
    return root.parent if root.name == "cells" else root


class Campaign:
    def __init__(self, plan_path, wait_seconds=WAIT_SECONDS):
        require(0 < wait_seconds <= WAIT_SECONDS, "file waits must be positive and at most four hours")
        self.plan_path, self.wait_seconds = Path(plan_path).resolve(), wait_seconds
        require(pool.sha(self.plan_path) == PLAN_SHA, "only the fixed V4 plan is authorized")
        self.plan = pool.load_plan(self.plan_path)
        self.base, self.fault = stage_cells(self.plan)
        self.root = campaign_root(self.plan)
        self.token = uuid.uuid4().hex
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + self.token[:10]
        self.directory = self.root / "campaign_master" / self.run_id
        self.lock = self.root / ".paper_suite_campaign_master.lock"
        self.status = {"schema": SCHEMA, "status": "STARTING", "run_id": self.run_id, "pid": os.getpid(),
            "plan_path": str(self.plan_path), "plan_sha256": PLAN_SHA, "master_source": ref(Path(__file__)),
            "pool_source": ref(Path(pool.__file__)), "phase": "initializing", "phases": [], "prerequisites": [],
            "workers": 4, "native_timeout_seconds": 0, "poll_seconds": POLL_SECONDS,
            "file_wait_timeout_seconds": wait_seconds, "unknown_processes_terminated": 0,
            "started_at_unix": time.time(), "scope": "Terminal accounting completion is separate from full population completion."}

    def save(self):
        self.status["updated_at_unix"] = time.time()
        pool.write(self.directory / "status.json", self.status)

    def unchanged(self):
        bound(self.plan_path, PLAN_SHA)
        for item in (self.status["master_source"], self.status["pool_source"]):
            bound(item["path"], item["sha256"])
        for gate in self.status["prerequisites"]:
            for item in [gate["reference"]] + gate.get("support", []):
                bound(item["path"], item["sha256"])

    def wait_for(self, name, probe):
        self.status["phase"] = name
        started = time.monotonic()
        self.status["waiting"] = {"name": name, "started_at_unix": time.time(), "timeout_seconds": self.wait_seconds}
        self.save()
        while True:
            self.unchanged()
            result = probe()
            if result is not None:
                self.status.pop("waiting", None)
                self.save()
                return result
            elapsed = time.monotonic() - started
            if elapsed >= self.wait_seconds:
                raise TimeoutError(f"{name}: required file/lock state did not become ready within {self.wait_seconds:g} seconds")
            self.status["waiting"]["last_checked_at_unix"] = time.time()
            self.save()
            time.sleep(min(POLL_SECONDS, self.wait_seconds - elapsed))

    def prior_pool(self):
        if not EXISTING_POOL.exists():
            return None
        value, reference = stable_read(EXISTING_POOL)
        state = value.get("status")
        if state in ("FAILED", "ABORTED", "TIMED_OUT") or value.get("campaign_lock_retained"):
            raise RuntimeError("existing HCA/DH pool failed or retained its execution lock; no process/lock will be removed")
        if state != "COMPLETE" or (self.root / ".paper_suite_orchestration.lock").exists():
            return None
        expected = {f"b_{m}_1x_v2p5_s104729_q00_{method}" for m in ("map2", "nanning") for method in ("hca", "dh")}
        require(value.get("selected_count") == value.get("accepted_count") == 4
                and set(value.get("selected_cell_ids", [])) == expected
                and len(value.get("cells", [])) == 4
                and {c["cell_id"] for c in value["cells"]} == expected
                and all(c["status"] in ("COMPLETE", "REUSED_VERIFIED") for c in value["cells"]), "existing pool is not the expected four-cell success")
        envelopes = []
        for cell in self.plan["cells"]:
            if cell["cell_id"] in expected:
                envelopes.append({"cell_id": cell["cell_id"], **pool.check_result_envelope(cell)})
        return {"reference": reference, "cells": envelopes, "full_reuse_verification": "performed by phase1 run_plan before REUSED_VERIFIED"}

    def normal2_probe(self):
        if not NORMAL2.exists():
            return None
        value = pool.read(NORMAL2)
        if value.get("status") in ("RUNNING", "INCOMPLETE", "WAITING"):
            return None
        return normal_comparison(NORMAL2, 2)

    def execute_stage(self, name, cells):
        self.unchanged()
        require(not (self.root / ".paper_suite_orchestration.lock").exists(), "another pool owns the campaign; refusing parallel dispatch")
        stage = {"name": name, "status": "RUNNING", "selected_count": len(cells),
                 "selected_cell_ids": [c["cell_id"] for c in cells], "started_at_unix": time.time()}
        self.status["phase"] = name
        self.status["phases"].append(stage)
        self.save()
        result = pool.run_plan(self.plan, cells, workers=4, timeout_seconds=0, keep_going=False)
        stage.update(status=result["status"], finished_at_unix=time.time(), pool_result=result)
        if result.get("status_path"):
            stage["pool_status_reference"] = ref(Path(result["status_path"]))
        self.save()
        require(result["status"] == "COMPLETE" and result.get("accepted_count") == len(cells), f"{name} failed; later stages will not dispatch")

    def report(self):
        output = ROOT / "outputs/reports/feng_paper_suite_20260907" / f"campaign_{self.run_id}"
        record = {"output_dir": str(output), "status": "STARTING"}
        self.status["report"] = record
        self.save()
        try:
            source = self.status.get("reporter_source")
            if source is None:
                source = self.wait_for("wait_for_reporter", lambda: ref(REPORTER) if REPORTER.exists() else None)
            bound(source["path"], source["sha256"])
            require(not output.exists(), "report snapshot already exists")
            command = [sys.executable, str(REPORTER), "--plan", str(self.plan_path), "--output", str(output)]
            record.update(source=source, command=command)
            kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            with (self.directory / "report_stdout.txt").open("wb") as stdout, (self.directory / "report_stderr.txt").open("wb") as stderr:
                done = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, **kwargs)
            record["returncode"] = done.returncode
            require(done.returncode == 0, "report generator failed; see retained logs")
            snapshot = pool.read(output / "snapshot.json")
            record.update(status=snapshot["status"], snapshot=ref(output / "snapshot.json"),
                          observed_cell_state_counts=snapshot.get("cell_state_counts"))
            if self.status["status"] == "COMPLETE":
                require(snapshot["status"] == "COMPLETE" and snapshot.get("expected_cells") == 1760,
                        "all pools returned but the report is not a complete 1760-cell result")
        except Exception as error:
            record.update(status="FAILED", error=str(error), traceback=traceback.format_exc())
            if self.status["status"] == "COMPLETE":
                self.status.update(status="FAILED", error="final report qualification failed")
        finally:
            self.save()

    def run(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock.open("x", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "token": self.token, "run_id": self.run_id, "plan_sha256": PLAN_SHA}, stream)
        try:
            self.directory.mkdir(parents=True, exist_ok=False)
            self.save()
            self.status["prerequisites"] = prerequisites()
            self.status["reporter_source"] = self.wait_for("wait_for_reporter", lambda: ref(REPORTER) if REPORTER.exists() else None)
            self.status["prior_pool"] = self.wait_for("wait_for_existing_hca_dh_pool", self.prior_pool)
            self.status["status"] = "RUNNING"
            self.execute_stage("phase1_base_seed104729_speed2p5", self.base)
            self.execute_stage("phase2_fault_seed104729_load1_scenarios1_2", self.fault)
            normal = self.wait_for("phase3_wait_normal_full_2x", self.normal2_probe)
            self.status["prerequisites"].append(normal)
            self.save()
            self.execute_stage("phase4_full_1760_resume_verified", self.plan["cells"])
            self.status.update(status="COMPLETE", phase="all_pools_complete")
        except BaseException as error:
            self.status.update(status="FAILED", error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        finally:
            self.status["finished_at_unix"] = time.time()
            self.save()
            self.report()  # A failed native/precondition phase still gets a partial report.
            try:
                owned = pool.read(self.lock)
                require(owned.get("token") == self.token, "master lock owner changed; refusing to remove it")
                self.lock.unlink()
            except Exception as error:
                self.status.update(status="FAILED", master_lock_release_error=str(error))
            self.save()
        return self.status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--wait-hours", type=float, default=4, help="maximum per-file/lock wait, at most four hours; polls every 10 seconds")
    parser.add_argument("--check-only", action="store_true", help="validate present evidence without locks, waits, reports or native dispatch")
    args = parser.parse_args(argv)
    campaign = Campaign(args.plan, args.wait_hours * 3600)
    if args.check_only:
        gates = prerequisites()
        prior = campaign.prior_pool()
        normal2 = campaign.normal2_probe()
        print(json.dumps({"status": "PRECHECK_PASS_NOT_EXECUTED", "plan_sha256": PLAN_SHA,
                          "stage_counts": [len(campaign.base), len(campaign.fault), len(campaign.plan["cells"])],
                          "prerequisites": gates, "existing_pool_ready": prior is not None,
                          "normal_full_2x_ready": normal2 is not None, "native_simulations_invoked": 0}, ensure_ascii=False))
        return 0
    result = campaign.run()
    print(json.dumps({"status": result["status"], "phase": result["phase"],
                      "status_path": str(campaign.directory / "status.json"), "report": result.get("report")}, ensure_ascii=False))
    return 0 if result["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
