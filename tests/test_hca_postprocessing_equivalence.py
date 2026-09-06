import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from scripts.eval import audit_hca_postprocessing_equivalence as audit


def encode(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


class EquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hca_postprocessing_test_")
        self.root = Path(self.temp.name)
        self.key = audit.KEYS[0]
        inputs = {}
        for name in ("raw", "canonical", "map"):
            path = self.root / (name + ".txt")
            path.write_bytes((name + " immutable input\n").encode())
            inputs[name + "_path"] = str(path)
            inputs[name + "_sha256"] = audit.file_sha(path)
        self.identity = inputs
        self.identity_path = self.root / "identity.json"
        self.identity_path.write_bytes(encode(inputs))
        self.old, self.new = self.root / "old", self.root / "new"
        self.fixture(self.old, "1" * 64)
        self.fixture(self.new, "2" * 64)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, directory, runner_sha):
        directory.mkdir()
        items = [{"path": "Test.java", "sha256": "a" * 64}]
        set_sha = audit.digest("Test.java\0".encode() + b"a" * 64 + b"\n")
        build = {"method": audit.METHOD, "source_files": items, "class_files": items,
                 "source_sha256": set_sha, "class_sha256": set_sha}
        (directory / "build_identity.json").write_bytes(encode(build))
        build_sha = audit.file_sha(directory / "build_identity.json")
        population = {"status": "PASS", "completed_segment_count": 1, "planned_segment_count": 1}
        for name in audit.SCIENTIFIC:
            data = encode(population) if name == "population_audit.json" else b"count,method\n1,HCA_SEGMENT_IDENTITY_V1\n" if name == "summary.csv" else b"1,2,3\n"
            (directory / name).write_bytes(data)
        arguments = ["map.txt", "raw.txt", "8260", "90000", "0", "1", "0", str(directory / "routes.csv"),
                     str(directory / "summary.csv"), "none", "0", "0", str(directory / "release.csv"), "2.5", "53", "53",
                     "4800", "2700", str(directory / "segment_execution_identity.csv"), str(directory / "execution_terminal.csv")]
        status = {"status": "complete", "returncode": 0, "method": audit.METHOD, "horizon_seconds": 98259.,
                  "cwd": str(directory), "command": ["java", "HcaSegmentIdentityBenchmark", *arguments],
                  "source_sha256": set_sha, "class_sha256": set_sha, "build_identity_sha256": build_sha,
                  "protocol_sha256": "c" * 64, "python_runner_sha256": runner_sha,
                  "workload_identity_sha256": audit.file_sha(self.identity_path),
                  "inputs": {k: {"sha256": self.identity[k + "_sha256"]} for k in ("raw", "canonical", "map")}}
        (directory / "runner_status.json").write_bytes(encode(status))
        normalized = {"status": "COMPLETE", "method": audit.METHOD, "map": self.key[0], "load_factor": self.key[1],
                      "seed": self.key[2], "fixed_horizon_seconds": 98259., "population_audit": population,
                      "metrics": {"completed_raw_bag_count": 1}, "workload_identity_path": str(self.identity_path),
                      "workload_identity_sha256": audit.file_sha(self.identity_path),
                      "normalization_contract": {"build_identity_sha256": build_sha,
                          "reconstruction_java_source_sha256": set_sha, "compiled_java_class_sha256": set_sha,
                          "protocol_sha256": "c" * 64},
                      **{"workload_" + k + "_sha256": self.identity[k + "_sha256"] for k in ("raw", "canonical", "map")}}
        (directory / "normalized_result.json").write_bytes(encode(normalized))
        self.bind(directory)

    def bind(self, directory):
        path = directory / "normalized_result.json"
        value = json.loads(path.read_bytes())
        value["native_evidence"] = [{"path": str(directory / name), "sha256": audit.file_sha(directory / name),
                                     "size_bytes": (directory / name).stat().st_size}
                                    for name in (*audit.SCIENTIFIC, "runner_status.json", "build_identity.json")]
        path.write_bytes(encode(value))

    def test_runner_version_and_directory_change_pass_with_explicit_disclosure(self):
        result = audit.compare_pair(self.old, self.new, self.key)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["python_runner_identity_changed"])
        self.assertEqual(result["provenance"]["old"]["python_runner_sha256"], "1" * 64)

    def test_no_new_result_is_incomplete_and_never_pass(self):
        result = audit.audit(self.root / "empty_old", self.root / "empty_new")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["passed_paired_cells"], 0)
        self.assertEqual(len(result["missing_cells"]), 5)

    def test_scientific_file_modification_rejected_even_after_self_hash_rebinding(self):
        (self.new / "output.txt").write_bytes(b"1,changed completion\n")
        self.bind(self.new)
        with self.assertRaisesRegex(ValueError, "scientific evidence bytes differ"):
            audit.compare_pair(self.old, self.new, self.key)

    def test_metric_only_modification_is_rejected(self):
        path = self.new / "normalized_result.json"
        value = json.loads(path.read_bytes())
        value["metrics"]["completed_raw_bag_count"] = 2
        path.write_bytes(encode(value))
        with self.assertRaisesRegex(ValueError, "normalized scientific result/metrics/contract differs"):
            audit.compare_pair(self.old, self.new, self.key)

    def test_actual_input_bytes_are_checked_not_only_identity_declarations(self):
        Path(self.identity["map_path"]).write_bytes(b"changed map\n")
        with self.assertRaisesRegex(ValueError, "input file digest differs: map"):
            audit.compare_pair(self.old, self.new, self.key)

    def test_protocol_change_rejected_even_with_consistent_native_provenance(self):
        for name in ("runner_status.json", "normalized_result.json"):
            path = self.new / name
            value = json.loads(path.read_bytes())
            target = value if name == "runner_status.json" else value["normalization_contract"]
            target["protocol_sha256"] = "d" * 64
            path.write_bytes(encode(value))
        self.bind(self.new)
        with self.assertRaisesRegex(ValueError, "protocol changed"):
            audit.compare_pair(self.old, self.new, self.key)

    def test_gzip_fallback_validates_compressed_and_restored_hashes(self):
        name = "segment_lifecycle.csv"
        original = self.new / name
        data = original.read_bytes()
        packed = self.new / "native_archive" / (name + ".gz")
        packed.parent.mkdir()
        packed.write_bytes(gzip.compress(data, mtime=0))
        record = {"source_name": name, "path": "native_archive/" + packed.name,
                  "sha256": audit.file_sha(packed), "uncompressed_sha256": audit.digest(data),
                  "uncompressed_size_bytes": len(data)}
        (packed.parent / "manifest.json").write_bytes(encode({"method": audit.METHOD, "files": [record]}))
        original.unlink()
        result = audit.compare_pair(self.old, self.new, self.key)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["provenance"]["new"]["evidence_storage"][name]["storage"], "VERIFIED_GZIP_FALLBACK")
        packed.write_bytes(packed.read_bytes() + b"tampered")
        with self.assertRaisesRegex(ValueError, "compressed archive digest differs"):
            audit.compare_pair(self.old, self.new, self.key)


if __name__ == "__main__":
    unittest.main()
