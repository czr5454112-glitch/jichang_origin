"""Small artifact-only regressions; no project imports, model or native calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_review_bundle as builder
import verify_review_bundle as verifier


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode()


def minimal_entries():
    payload = b'old\r\nbytes\r\n'
    return {
        'repo/result.txt': payload,
        'PATH_MAP.json': encoded({'references': [{'original_path': 'C:/old/result.txt',
            'sha256': hashlib.sha256(payload).hexdigest(), 'member': 'repo/result.txt'}]}),
        'AUDIT_SPEC.json': encoded({'checks': []}),
        'NATIVE_DEPENDENCIES_NOT_BUNDLED.json': encoded({'dependencies': []}),
        'SNAPSHOT_IDENTITY.json': encoded({'fresh_native_execution_portable': False,
                                           'commit_or_push_performed_by_packager': False}),
    }


def write_archive(path, entries):
    manifest = {'schema': 'g31.refresh.review_bundle.v1', 'files': [
        {'path': name, 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
        for name, payload in entries.items()]}
    with zipfile.ZipFile(path, 'x') as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
        archive.writestr('MANIFEST.sha256.json', encoded(manifest))


class ReviewBundleTests(unittest.TestCase):
    def test_exact_crlf_preserved_zip_and_relocated_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = directory / 'bundle.zip'
            write_archive(archive, minimal_entries())
            result = verifier.verify(archive)
            self.assertEqual(result['verified_reference_count'], 1)
            with zipfile.ZipFile(archive) as source:
                source.extractall(directory / 'moved')
            self.assertEqual(verifier.verify(directory / 'moved')['status'], 'passed')

    def test_manifest_change_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = directory / 'bundle.zip'
            write_archive(archive, minimal_entries())
            with zipfile.ZipFile(archive) as source:
                source.extractall(directory / 'moved')
            (directory / 'moved/repo/result.txt').write_bytes(b'old\nbytes\n')
            with self.assertRaisesRegex(ValueError, 'byte_hash_mismatch'):
                verifier.verify(directory / 'moved')

    def test_wrong_mapping_fails_even_when_manifest_matches(self):
        entries = minimal_entries()
        mapping = json.loads(entries['PATH_MAP.json'])
        mapping['references'][0]['sha256'] = '0' * 64
        entries['PATH_MAP.json'] = encoded(mapping)
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'bundle.zip'
            write_archive(archive, entries)
            with self.assertRaisesRegex(ValueError, 'mapped_reference_hash_mismatch'):
                verifier.verify(archive)

    def test_unsafe_member_names(self):
        for name in ('../escape', '/abs', 'C:/abs', 'a\\b', 'a//b', 'a/./b', 'a/../b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                verifier.safe_name(name)

    def test_strict_full_json_rejects_bool_int_float_negative_zero(self):
        for left, right in ((True, 1), (1, 1.0), (0.0, -0.0)):
            self.assertNotEqual(verifier.canonical({'value': left}), verifier.canonical({'value': right}))

    def test_native_environment_refs_separate_from_offline_artifacts(self):
        refs = list(builder.pin_references({'evidence_sha256': {'C:/build/native.pyd': 'a' * 64},
            'raw': {'path': 'C:/old/raw.json.gz', 'sha256': 'b' * 64}}))
        self.assertEqual([(item[0], item[3]) for item in refs],
                         [('C:/build/native.pyd', True), ('C:/old/raw.json.gz', False)])

    def test_import_closure_includes_sibling_package_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {
                'scripts/g31/entry.py': 'from scripts.sibling.learning import Model\n',
                'scripts/sibling/__init__.py': '',
                'scripts/sibling/learning.py': 'from .model import Model\n',
                'scripts/sibling/model.py': 'class Model:\n    pass\n',
            }
            for name, text in paths.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            (root / 'src').mkdir()
            (root / 'tests').mkdir()
            with patch.object(builder, 'ROOT', root):
                collector = builder.Collector({})
                collector.add(root / 'scripts/g31/entry.py')
                collector.close()
            self.assertTrue({'repo/' + name for name in paths} <= set(collector.entries))

    def test_historical_hash_maps_to_archive_not_current_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('scripts', 'src', 'tests'):
                (root / name).mkdir()
            with patch.object(builder, 'ROOT', root):
                collector = builder.Collector({})
                collector.add_bytes('repo/scripts/current.py', b'new\r\n')
                collector.add_bytes('repo/old/source/current.py', b'old\r\n')
                expected = builder.digest(b'old\r\n')
                collector.resolve_pin(str(root / 'scripts/current.py'), expected, 'plan.json', (), False)
            key = (builder.normalized(root / 'scripts/current.py'), expected)
            self.assertEqual(collector.references[key], 'repo/old/source/current.py')
            self.assertEqual(collector.entries['repo/scripts/current.py'], b'new\r\n')

    def test_required_missing_pin_is_not_silently_omitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('scripts', 'src', 'tests'):
                (root / name).mkdir()
            with patch.object(builder, 'ROOT', root):
                collector = builder.Collector({})
                with self.assertRaisesRegex(ValueError, 'unresolved_required_pin'):
                    collector.resolve_pin(str(root / 'missing.json'), '0' * 64, 'plan.json', (), False)


if __name__ == '__main__':
    unittest.main()
