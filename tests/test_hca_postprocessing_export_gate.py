"""Five miniature archived comparisons test the subgate, not a full 180-cell matrix."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.eval import audit_hca_postprocessing_equivalence as auditor
from scripts.eval import export_hca_segment_identity_campaign as export
from tests import test_hca_postprocessing_equivalence as fixtures

encode = fixtures.encode


class PostprocessingArchiveGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hca_postprocessing_archive_")
        self.root = Path(self.temp.name).resolve()
        self.patch = patch.object(export, "ROOT", self.root)
        self.patch.start()
        self.old = self.root / "outputs/runtime/hca_old"
        self.new = self.root / "outputs/runtime/hca_new"
        self.archived = self.root / "outputs/evidence/subgate_fixture"
        self.support = {}

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def support_file(self, relative, data):
        source = self.root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(data)
        record = export.archive_file(source, self.archived / export.support_destination(source))
        self.support[relative] = record
        return {"path": relative, "sha256": record["source_sha256"]}

    def create_fixture(self):
        old_code = b"def cleanup_epoch_scratch():\n    return 1\n\ndef numeric_code():\n    return 3\n"
        new_code = old_code.replace(b"return 1", b"return 2")
        self.old_runner = hashlib.sha256(old_code).hexdigest()
        self.new_runner = hashlib.sha256(new_code).hexdigest()
        old_root, new_root = (p.relative_to(self.root).as_posix() for p in (self.old, self.new))
        self.saved_key = old_root + "/preflight/superseded_slow_cleanup_tools/run_hca_segment_identity.py"
        self.support_file(self.saved_key, old_code)
        runner = self.support_file("scripts/eval/run_hca_segment_identity.py", new_code)
        protocol = self.support_file("docs/protocol.md", b"one unchanged protocol\n")
        template = fixtures.EquivalenceTests()
        template.root = self.root
        template.identity = {}
        for name in ("raw", "canonical", "map"):
            path = self.root / "data" / (name + ".txt")
            path.parent.mkdir(exist_ok=True)
            path.write_bytes((name + " unchanged bytes\n").encode())
            template.identity[name + "_path"] = str(path)
            template.identity[name + "_sha256"] = auditor.file_sha(path)
        template.identity_path = self.root / "data/identity.json"
        template.identity_path.write_bytes(encode(template.identity))
        identity_bound = {"path": "data/identity.json", "sha256": auditor.file_sha(template.identity_path)}
        old_cells, new_cells, records = [], [], []
        for coordinate in auditor.KEYS:
            template.key = coordinate
            before, after = auditor.cell_dir(self.old, coordinate), auditor.cell_dir(self.new, coordinate)
            for directory, version in ((before, self.old_runner), (after, self.new_runner)):
                directory.parent.mkdir(parents=True)
                template.fixture(directory, version)
                for name in ("runner_status.json", "normalized_result.json"):
                    path = directory / name
                    value = json.loads(path.read_bytes())
                    target = value if name == "runner_status.json" else value["normalization_contract"]
                    target["protocol_sha256"] = protocol["sha256"]
                    path.write_bytes(encode(value))
                template.bind(directory)
            coordinate_row = dict(zip(("map", "load_factor", "seed"), coordinate))
            common = {**coordinate_row, "identity": identity_bound,
                      **{key + "_sha256": template.identity[key + "_sha256"] for key in ("raw", "canonical", "map")}}
            old_cells.append(dict(common, output=before.relative_to(self.root).as_posix()))
            new_cells.append(dict(common, output=after.relative_to(self.root).as_posix()))
            names = (*export.EQUIVALENCE_FILES, "runner_status.json", "build_identity.json", "normalized_result.json")
            old_records, native_files = [], []
            for name in names:
                data = (before / name).read_bytes()
                packed = gzip.compress(data, mtime=0)
                path = "native_archive/" + name + ".gz"
                self.support_file((before.relative_to(self.root) / path).as_posix(), packed)
                old_records.append({"source_name": name, "path": path, "sha256": hashlib.sha256(packed).hexdigest(),
                                    "uncompressed_sha256": hashlib.sha256(data).hexdigest(), "uncompressed_size_bytes": len(data)})
                compress = name.endswith(".csv")
                native_files.append(export.archive_file(after / name,
                    self.archived / "formal" / str(coordinate[2]) / str(coordinate[1]) / (name + ".gz" if compress else name),
                    compress=compress))
            self.support_file((before.relative_to(self.root) / "native_archive/manifest.json").as_posix(),
                              encode({"method": export.HCA, "files": old_records}))
            records.append({**coordinate_row, "method": export.HCA, "origin": "NEW_EXECUTION", "files": native_files})
        build = self.support_file("build/fixture/build_identity.json", (after / "build_identity.json").read_bytes())
        build_value = json.loads((after / "build_identity.json").read_bytes())
        self.freeze = {"method": export.HCA, "protocol": protocol, "runner": runner, "build_identity": build,
                       "microtests": {"path": old_root + "/preflight/microtests.json"}, "cells": new_cells}
        self.old_freeze = {**self.freeze, "runner": {"path": runner["path"], "sha256": self.old_runner}, "cells": old_cells}
        self.old_freeze_key = old_root + "/campaign_freeze.json"
        self.support_file(self.old_freeze_key, encode(self.old_freeze))
        self.freeze_file = {"source_path": new_root + "/campaign_freeze.json"}
        self.validation_key = old_root + "/preflight/cleanup_revision_validation.json"
        self.validation = {"status": "PASS", "old_runner_sha256": self.old_runner, "new_runner_sha256": self.new_runner,
                           "only_changed_production_function": "cleanup_epoch_scratch", "non_cleanup_module_AST_identical": True,
                           "tests": {"files": {}}}
        self.support_file(self.validation_key, encode(self.validation))
        self.support_file(export.EQUIVALENCE_AUDITOR, Path(auditor.__file__).read_bytes())
        self.support_file(export.EQUIVALENCE_TEST, Path(__file__).with_name("test_hca_postprocessing_equivalence.py").read_bytes())
        self.equivalence = auditor.audit(self.old, self.new)
        self.assertEqual(self.equivalence["status"], "PASS", self.equivalence)
        self.equivalence_key = new_root + "/preflight/" + export.EQUIVALENCE_NAME
        eq_bound = self.support_file(self.equivalence_key, encode(self.equivalence))
        self.manifest = {"cells": records, "postprocessing_equivalence": {"status": "PASS", **eq_bound},
                         "source_sha256": build_value["source_sha256"], "class_sha256": build_value["class_sha256"]}

    def verify(self):
        return export.verify_postprocessing_equivalence(self.manifest, self.support, self.freeze, self.freeze_file)

    def test_required_gate_rejects_missing_report_before_export(self):
        with self.assertRaisesRegex(ValueError, "final export requires five-cell"):
            export.postprocessing_gate(self.new, {}, required=True)
        self.assertEqual(export.postprocessing_gate(self.new, {}, required=False)["status"], "INCOMPLETE")

    def test_five_archived_comparisons_pass_only_the_dedicated_subgate(self):
        self.create_fixture()
        result = self.verify()
        self.assertEqual(result["paired_cells_verified"], 5)
        self.assertEqual(result["old_preflight_cells_in_final_matrix"], 0)
        self.assertTrue(result["non_cleanup_module_AST_independently_equal"])
        self.assertEqual(len(self.manifest["cells"]), 5)  # not a fabricated final 180-cell PASS

    def test_wrong_coordinates_and_result_selection_flag_rejected(self):
        self.create_fixture()
        value = copy.deepcopy(self.equivalence)
        value["cells"][0]["seed"] = 999
        with self.assertRaisesRegex(ValueError, "coordinates differ"):
            export.validate_equivalence_shape(value, self.old, self.new)
        value = copy.deepcopy(self.equivalence)
        value["duplicate_selection_by_performance"] = True
        with self.assertRaisesRegex(ValueError, "selection/protocol"):
            export.validate_equivalence_shape(value, self.old, self.new)

    def test_rebound_new_native_scientific_bytes_still_rejected(self):
        self.create_fixture()
        record = next(f for f in self.manifest["cells"][0]["files"] if f["source_path"].endswith("/output.txt"))
        path = export.relocated(record["archive_path"])
        path.write_bytes(b"changed completion\n")
        record["source_sha256"] = record["archive_sha256"] = export.sha(path)
        with self.assertRaisesRegex(ValueError, "cleanup scientific file differs"):
            self.verify()

    def test_old_runner_is_checked_against_saved_source_not_current_path(self):
        self.create_fixture()
        current = export.archived_payload(self.support[self.freeze["runner"]["path"]])
        self.support_file(self.saved_key, current)
        with self.assertRaisesRegex(ValueError, "saved old/current Python runner identities"):
            self.verify()

    def test_equivalence_auditor_digest_must_match_archived_source(self):
        self.create_fixture()
        self.equivalence["auditor_sha256"] = "0" * 64
        bound = self.support_file(self.equivalence_key, encode(self.equivalence))
        self.manifest["postprocessing_equivalence"] = {"status": "PASS", **bound}
        with self.assertRaisesRegex(ValueError, "archived equivalence auditor differs"):
            self.verify()

    def test_rebound_old_gzip_must_still_match_original_native_manifest(self):
        self.create_fixture()
        key = next(key for key in self.support if key.endswith("/native_archive/output.txt.gz"))
        self.support_file(key, gzip.compress(b"changed old completion\n", mtime=0))
        with self.assertRaisesRegex(ValueError, "old native gzip digest differs"):
            self.verify()

    def test_outside_cleanup_ast_change_rejected_even_with_rebound_source_hashes(self):
        self.create_fixture()
        old_code = export.archived_payload(self.support[self.saved_key]).replace(b"return 3", b"return 99")
        bound = self.support_file(self.saved_key, old_code)
        self.old_freeze["runner"]["sha256"] = bound["sha256"]
        self.support_file(self.old_freeze_key, encode(self.old_freeze))
        self.validation["old_runner_sha256"] = bound["sha256"]
        self.support_file(self.validation_key, encode(self.validation))
        with self.assertRaisesRegex(ValueError, "runner changed outside cleanup"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
