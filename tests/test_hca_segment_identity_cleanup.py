"""Safety and byte-equivalence tests for the non-numerical cleanup revision."""
import ast
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

from scripts.eval import run_hca_segment_identity as hca

OLD = hca.ROOT / "outputs/runtime/hca_segment_identity_20260906/preflight/superseded_slow_cleanup_tools/run_hca_segment_identity.py"
OLD_SHA = "77105ac1695576011118e8fc2d3d450e26149cc5a165728fae7962bb4fd46230"


def native_fixture(output):
    (output / "task").mkdir(parents=True)
    for name in (*hca.NATIVE_FILES, *hca.DERIVED_FILES, hca.BUILD_NAME,
                 "runner_status.json", "normalized_result.json", "stdout.txt", "stderr.txt"):
        (output / name).write_bytes(("identical preserved native/derived fixture: "+name+"\r\n").encode())
    for index in range(8):
        (output / "task" / f"{8260+index}.txt").write_bytes((f"scratch {index}\n"*index).encode())


def old_cleanup():
    parsed = ast.parse(OLD.read_text(encoding="utf-8"))
    node = next(n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name == "cleanup_epoch_scratch")
    namespace = dict(hca.__dict__)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(OLD), "exec"), namespace)
    return namespace["cleanup_epoch_scratch"]


class CleanupRevisionTests(unittest.TestCase):
    def test_only_cleanup_function_changed_and_old_exact_bytes_retained(self):
        self.assertEqual(hca.sha(OLD), OLD_SHA)
        trees = [ast.parse(path.read_text(encoding="utf-8")) for path in (OLD, Path(hca.__file__))]
        for tree in trees:
            tree.body = [node for node in tree.body if not isinstance(node, ast.FunctionDef)
                         or node.name != "cleanup_epoch_scratch"]
        self.assertEqual(ast.dump(trees[0], include_attributes=False), ast.dump(trees[1], include_attributes=False))

    def test_old_new_preserve_identical_native_derived_and_archive_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            before = root / "outputs/runtime/hca_segment_identity_old/cell"
            after = root / "outputs/runtime/hca_segment_identity_fast/cell"
            native_fixture(before)
            native_fixture(after)
            with patch.object(hca, "ROOT", root):
                old = old_cleanup()(before)
                new = hca.cleanup_epoch_scratch(after)
            for key in ("status", "removed_file_count", "removed_size_bytes", "archive_manifest_sha256", "retained"):
                self.assertEqual(old[key], new[key], key)
            self.assertEqual(old["removed_file_count"], 8)
            self.assertFalse((before / "task").exists())
            self.assertFalse((after / "task").exists())
            for path in before.iterdir():
                if path.is_file() and path.name != "scratch_cleanup.json":
                    self.assertEqual(path.read_bytes(), (after / path.name).read_bytes(), path.name)
            for path in (before / "native_archive").iterdir():
                self.assertEqual(path.read_bytes(), (after / "native_archive" / path.name).read_bytes(), path.name)

    def test_subdirectory_rejected_before_any_unlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            output = root / "outputs/runtime/hca_segment_identity_bad_directory/cell"
            native_fixture(output)
            (output / "task/subdirectory").mkdir()
            with patch.object(hca, "ROOT", root), self.assertRaisesRegex(RuntimeError, "non-flat/reparse"):
                hca.cleanup_epoch_scratch(output)
            self.assertEqual(len(list((output / "task").glob("*.txt"))), 8)

    def test_any_reparse_or_symbolic_link_metadata_rejected_before_unlink(self):
        for mode, attrs in ((stat.S_IFREG, stat.FILE_ATTRIBUTE_REPARSE_POINT), (stat.S_IFLNK, 0)):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                output = root / "outputs/runtime/hca_segment_identity_bad_reparse/cell"
                native_fixture(output)
                item = output / "task/8260.txt"
                entry = SimpleNamespace(path=str(item), stat=lambda **kwargs: SimpleNamespace(
                    st_mode=mode, st_file_attributes=attrs, st_size=0))
                fake = MagicMock()
                fake.__enter__.return_value = iter([entry])
                with patch.object(hca, "ROOT", root), patch("os.scandir", return_value=fake), \
                     self.assertRaisesRegex(RuntimeError, "non-flat/reparse"):
                    hca.cleanup_epoch_scratch(output)
                self.assertTrue(item.exists())


if __name__ == "__main__":
    unittest.main()
