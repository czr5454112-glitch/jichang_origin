"""Bounded execution-safety checks; no full-population simulator is launched."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts.eval import run_feng_dh_v5_campaign as campaign


class V5CampaignContractTest(unittest.TestCase):
    def test_materialized_load_is_not_multiplied_twice_and_2x_timing_is_disabled(self):
        args = argparse.Namespace(result_root=campaign.RESULT_ROOT, classes_dir=campaign.CLASSES,
            java=campaign.executable("java"), java_heap="1536m")
        # Workload reconstruction is already exercised by the 60-cell preflight.
        # This test isolates runner translation of a materialized workload.
        def identity(path):
            return path, json.loads(path.read_text(encoding="utf-8"))
        with patch.object(campaign.external, "_identity_payload", side_effect=identity):
            for map_name in campaign.external.MAPS:
                for load in campaign.external.LOAD_FACTORS:
                    _, output, command, runtime = campaign.run_spec(args, map_name, load, campaign.external.SEEDS[0])
                    self.assertEqual(command[command.index("--workload-scale") + 1], "1")
                    self.assertEqual(command[command.index("--horizon-seconds") + 1], "98259")
                    self.assertEqual(command[command.index("--formal-timing-eligible") + 1],
                                     "false" if load == 2 else "true")
                    self.assertNotIn("--schedule", command)
                    self.assertEqual(command[1], "-Xmx1536m")
                    self.assertEqual(runtime["method"], campaign.METHOD)
                    self.assertEqual(runtime["compiled_java_class_aggregate_sha256"], campaign.CLASS_SHA)
                    self.assertEqual(output.name, "feng_env_dh_v5")
                    self.assertEqual(runtime["storage_in_goal"], campaign.external.map_protocol(map_name).storage_in_goal)

    def test_unexpected_class_cannot_contaminate_formal_classpath(self):
        campaign.compiled_identity(campaign.CLASSES)
        with tempfile.TemporaryDirectory(prefix="feng_v5_identity_test_", dir=campaign.ROOT / "build") as name:
            root = Path(name)
            shutil.copytree(campaign.CLASSES / "App", root / "App")
            shutil.copyfile(campaign.CLASSES / campaign.BUILD_IDENTITY, root / campaign.BUILD_IDENTITY)
            (root / "App/Unexpected.class").write_bytes(b"foreign fixture class")
            with self.assertRaisesRegex(ValueError, "classes differ"):
                campaign.compiled_identity(root)

    def test_unfrozen_seed_or_load_is_rejected(self):
        for load, seed in (([1.5], None), (None, [123])):
            args = argparse.Namespace(map=None, load_factor=load, seed=seed)
            with self.assertRaises(campaign.external.ExternalBaselineError):
                list(campaign.cells(args))


if __name__ == "__main__":
    unittest.main()
