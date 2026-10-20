"""Pure admission fixtures. No actual package/outcomes/native execution."""
import copy
import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
import types
import zipfile

path = Path(__file__).with_name("audit_old_parent_diagnostic_supplement_001.py")
spec = importlib.util.spec_from_file_location("old_diagnostic_supplement_fixture", path)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class AdmissionTests(unittest.TestCase):
    def fixture(self):
        name = next(iter(s.PLANS))
        sha, seed = s.PLANS[name]
        return ({"name": name, "role": "diagnostic", "plan": {"sha256": sha}},
                {"name": name, "pair": None, "old_parent_diagnostic_only": True,
                 "parent": {"parent_seed": seed, "split": "test"}, "method": "C00"})

    def reject(self, change):
        slot, plan = self.fixture()
        change(slot, plan)
        with self.assertRaises(ValueError):
            s.validate_plan(slot, plan)

    def test_exact_old_fixture(self):
        s.validate_plan(*self.fixture())

    def test_all_nine_exact_identities(self):
        for name, (sha, seed) in s.PLANS.items():
            slot, plan = self.fixture()
            slot.update(name=name, plan={"sha256": sha})
            plan.update(name=name, parent={"parent_seed": seed, "split": "test"})
            s.validate_plan(slot, plan)

    def test_new_formal_1301_rejected(self):
        self.reject(lambda a, b: b["parent"].update(parent_seed=1301))

    def test_pair_role_rejected(self):
        self.reject(lambda a, b: a.update(role="round0_pair"))

    def test_formal_role_rejected(self):
        self.reject(lambda a, b: a.update(role="formal"))

    def test_missing_flag_rejected(self):
        self.reject(lambda a, b: b.pop("old_parent_diagnostic_only"))

    def test_numeric_flag_rejected(self):
        self.reject(lambda a, b: b.update(old_parent_diagnostic_only=1))

    def test_pair_present_rejected(self):
        self.reject(lambda a, b: b.update(pair={}))

    def test_unregistered_name_rejected(self):
        self.reject(lambda a, b: a.update(name="D_N22_C00_P901_NEW"))

    def test_plan_sha_rejected(self):
        self.reject(lambda a, b: a["plan"].update(sha256="0" * 64))

    def test_mismatched_name_rejected(self):
        self.reject(lambda a, b: b.update(name="different"))

    def test_split_relabeled_rejected(self):
        self.reject(lambda a, b: b["parent"].update(split="train"))

    def test_seed_type_rejected(self):
        self.reject(lambda a, b: b["parent"].update(parent_seed=901.0))

    def test_learning_method_rejected(self):
        self.reject(lambda a, b: b.update(method="C11"))

    def test_contract_exact(self):
        s.validate_admission(s.admission_document())

    def test_contract_drop_or_duplicate_rejected(self):
        for mode in ("drop", "duplicate"):
            value = copy.deepcopy(s.admission_document())
            if mode == "drop":
                value["plans"].pop()
            else:
                value["plans"][-1] = value["plans"][0]
            with self.assertRaises(ValueError):
                s.validate_admission(value)

    def route_fixture(self, manifest_schema):
        class Package:
            def __init__(self, path):
                self.zip = zipfile.ZipFile(path)
            def raw(self, name):
                return self.zip.read(name)
            def close(self):
                self.zip.close()
        base = types.SimpleNamespace(Package=Package, safe_name=lambda x: x,
                                     SCHEMA="g31.inventory_spi.compact_package.v1")
        def open_mapped(facade, path, sha):
            obj = facade.Package(path)
            try:
                value = json.loads(obj.raw("PACKAGE_MANIFEST.json"))
                s.require(value["schema"] == facade.SCHEMA, "fixture_package_schema")
                return obj
            except BaseException:
                obj.close()
                raise
        nonformal = types.SimpleNamespace(open_mapped=open_mapped)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "DUMMY.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("evidence/PACKAGE_MANIFEST.json", json.dumps({"schema": manifest_schema}))
            obj = s.outer_package(base, nonformal, path)
            obj.close()
        self.assertEqual(base.SCHEMA, "g31.inventory_spi.compact_package.v1")

    def test_partial_schema_and_outer_zip_prefix_route(self):
        self.route_fixture(s.PARTIAL_PACKAGE_SCHEMA)

    def test_old_full_package_schema_rejected_by_route(self):
        with self.assertRaises(ValueError):
            self.route_fixture("g31.inventory_spi.compact_package.v1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
