"""No-simulation control-flow QA for the staged master entry point."""
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import unittest
from unittest.mock import patch, Mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_feng_paper_suite_campaign as m


class CampaignControlTest(unittest.TestCase):
    def fake(self):
        root = ROOT / "tmp" / ("paper_suite_campaign_qa_" + uuid.uuid4().hex)
        root.mkdir(parents=True)
        self.assertTrue(root.resolve().is_relative_to((ROOT / "tmp").resolve()))
        obj = m.Campaign.__new__(m.Campaign)
        obj.root, obj.directory, obj.lock = root, root / "state", root / "master.lock"
        obj.plan_path, obj.wait_seconds, obj.token, obj.run_id = m.PLAN, 1, uuid.uuid4().hex, root.name
        obj.base = [{"cell_id": str(i)} for i in range(16)]
        obj.fault = [{"cell_id": str(i)} for i in range(8)]
        obj.plan = {"cells": [{"cell_id": str(i)} for i in range(1760)]}
        obj.status = {"status": "STARTING", "phase": "initializing", "phases": [], "prerequisites": []}
        obj.unchanged = Mock()
        obj.prior_pool = Mock(return_value={"accepted": 4})
        obj.normal2_probe = Mock(return_value={"name": "normal2", "status": "PASS", "reference": {}})
        return obj

    def test_actual_frozen_plan_stage_selection_is_16_8_1760(self):
        plan = m.pool.read(m.PLAN)
        base, fault = m.stage_cells(plan)
        self.assertEqual((len(base), len(fault), len(plan["cells"])), (16, 8, 1760))
        self.assertEqual({c["method"] for c in base}, set(m.pool.RUNNERS))
        self.assertEqual({c["method"] for c in fault}, {m.pool.NEW_G31, m.pool.HCA})

    def test_full_order_waits_for_normal2_before_last_phase(self):
        obj = self.fake()
        calls = []
        obj.normal2_probe.side_effect = lambda: calls.append("normal2_gate") or {"reference": {}, "support": []}
        def run(_plan, cells, **kwargs):
            self.assertEqual(kwargs, {"workers": 4, "timeout_seconds": 0, "keep_going": False})
            calls.append(len(cells))
            return {"status": "COMPLETE", "accepted_count": len(cells)}
        with patch.object(m, "prerequisites", return_value=[]), patch.object(m.pool, "run_plan", side_effect=run), patch.object(obj, "report") as report:
            result = obj.run()
        self.assertEqual(calls, [16, 8, "normal2_gate", 1760])
        self.assertEqual(result["status"], "COMPLETE")
        report.assert_called_once()
        self.assertFalse(obj.lock.exists())

    def test_first_pool_failure_stops_later_stages_but_attempts_report(self):
        obj = self.fake()
        with patch.object(m, "prerequisites", return_value=[]), patch.object(m.pool, "run_plan", return_value={"status": "FAILED", "accepted_count": 1}) as run, patch.object(obj, "report") as report:
            result = obj.run()
        self.assertEqual(result["status"], "FAILED")
        run.assert_called_once()
        obj.normal2_probe.assert_not_called()
        report.assert_called_once()
        self.assertFalse(obj.lock.exists())

    def test_foreign_master_lock_is_never_removed(self):
        obj = self.fake()
        original = b'{"pid":123,"token":"someone-else"}\n'
        obj.lock.write_bytes(original)
        with patch.object(m.pool, "run_plan") as run:
            with self.assertRaises(FileExistsError):
                obj.run()
        run.assert_not_called()
        self.assertEqual(obj.lock.read_bytes(), original)

    def test_replaced_master_lock_is_retained(self):
        obj = self.fake()
        def run(_plan, cells, **kwargs):
            obj.lock.write_text('{"token":"new-owner"}')
            return {"status": "FAILED", "accepted_count": 0}
        with patch.object(m, "prerequisites", return_value=[]), patch.object(m.pool, "run_plan", side_effect=run), patch.object(obj, "report"):
            result = obj.run()
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("master_lock_release_error", result)
        self.assertEqual(json.loads(obj.lock.read_text())["token"], "new-owner")

    def test_file_wait_timeout_does_not_dispatch_or_kill(self):
        obj = self.fake()
        obj.directory.mkdir()
        with patch.object(m.time, "monotonic", side_effect=[0, 0, 2]), patch.object(m.time, "sleep") as sleep, patch.object(m.pool, "run_plan") as run:
            with self.assertRaises(TimeoutError):
                obj.wait_for("missing_gate", lambda: None)
        run.assert_not_called()
        sleep.assert_called_once_with(1)

    def test_thirteen_passed_cases_cannot_claim_final_fourteen_gate(self):
        value = {"status": "PASS", "test_count": 13, "failed_count": 0, "skipped_count": 0, "binary_sha256": m.BINARY_SHA}
        with patch.object(m, "stable_read", return_value=(value, {})):
            with self.assertRaises(ValueError):
                m.prerequisites()

    def test_missing_normal2_is_waiting_and_failed_normal2_is_rejected(self):
        obj = self.fake()
        probe = m.Campaign.normal2_probe.__get__(obj)
        path = obj.root / "comparison.json"
        with patch.object(m, "NORMAL2", path):
            self.assertIsNone(probe())
            path.write_text('{"status":"FAILED","pair_count":2,"pairs":[]}')
            with self.assertRaises(ValueError):
                probe()

    def test_partial_report_cannot_turn_complete_pool_into_final_complete(self):
        obj = self.fake()
        obj.directory.mkdir()
        obj.status["status"] = "COMPLETE"
        obj.status["reporter_source"] = m.ref(m.REPORTER)
        def fake_process(command, **kwargs):
            output = Path(command[command.index("--output") + 1])
            output.mkdir(parents=True)
            (output / "snapshot.json").write_text(json.dumps({"status": "PARTIAL_NOT_A_FINAL_CONCLUSION", "expected_cells": 1760, "cell_state_counts": {"COMPLETE": 4}}))
            return SimpleNamespace(returncode=0)
        with patch.object(m, "ROOT", obj.root), patch.object(m.subprocess, "run", side_effect=fake_process):
            obj.report()
        self.assertEqual(obj.status["status"], "FAILED")
        self.assertEqual(obj.status["report"]["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
