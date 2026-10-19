"""Focused source-provenance regressions; standard library, no project imports."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import verify_publication as subject

HERE = Path(__file__).resolve().parent


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def encoded(value):
    return json.dumps(value, indent=2).encode()


def fixture(root):
    source = 'src/czr005/unit.py'
    original = str(subject.ORIGINAL / source)
    executed, committed = b'VALUE = 1\r\n', b'VALUE = 1\n'
    plan = {'source_pins': {original: subject.digest(executed)},
        'source_archive': {original: str(subject.ORIGINAL / 'archive/unit.py')}}
    payloads = {source: committed, 'archive/unit.py': executed,
        'evidence/raw.json': b'{"real_result": 1}\r\n', 'plan.json': encoded(plan)}
    old = {'files': [{'path': name, 'sha256': subject.digest(executed if name == source else payload),
        'bytes': len(executed if name == source else payload)} for name, payload in payloads.items()]}
    old_payload = encoded(old)
    relation = {'original_path': original, 'repository_path': source, 'execution_archive_path': 'archive/unit.py',
        'executed_worktree_sha256': subject.digest(executed), 'executed_bytes': len(executed),
        'committed_content_sha256': subject.digest(committed), 'committed_bytes': len(committed),
        'git_blob_sha1': subject.blob_digest(committed), 'transform': 'executed_CRLF_to_committed_LF'}
    rows = [{'path': name, 'committed_content_sha256': subject.digest(payload), 'committed_bytes': len(payload),
        'git_blob_sha1': subject.blob_digest(payload),
        'executed_publication_worktree_sha256': old['files'][index]['sha256'],
        'executed_publication_bytes': old['files'][index]['bytes']} for index, (name, payload) in enumerate(payloads.items())]
    manifest = {'schema': subject.SCHEMA, 'fixed_git_commit': 'a' * 40, 'fixed_git_tree': 'b' * 40,
        'files': rows, 'historical_publication_manifest': {'path': 'old_manifest.json', 'sha256': subject.digest(old_payload)},
        'historical_execution_plan': {'path': 'plan.json', 'sha256': subject.digest(payloads['plan.json'])},
        'source_relations': [relation], 'explicit_EOL_source_paths': [source]}
    for name, payload in payloads.items():
        write(root / name, payload)
    write(root / 'old_manifest.json', old_payload)
    write(root / 'manifest.json', encoded(manifest))
    return manifest


class PublicationTests(unittest.TestCase):
    def setUp(self):
        base = HERE.parent / 'publication_002_validation/test_tmp'
        base.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.manifest = fixture(self.root)

    def verify(self):
        return subject.verify(self.root, self.root / 'manifest.json')

    def test_only_explicit_source_EOL_relation_is_accepted(self):
        result = self.verify()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['explicit_EOL_source_relations'], 1)
        self.assertFalse(result['non_source_evidence_normalized'])

    def test_real_code_change_is_rejected(self):
        write(self.root / 'src/czr005/unit.py', b'VALUE = 2\n')
        self.assertEqual(self.verify()['status'], 'failed')

    def test_current_source_is_never_normalized_before_committed_hash(self):
        write(self.root / 'src/czr005/unit.py', b'VALUE = 1\r\n')
        self.assertEqual(self.verify()['status'], 'failed')

    def test_normalizing_execution_archive_is_rejected(self):
        write(self.root / 'archive/unit.py', b'VALUE = 1\n')
        self.assertEqual(self.verify()['status'], 'failed')

    def test_normalizing_raw_result_evidence_is_rejected(self):
        write(self.root / 'evidence/raw.json', b'{"real_result": 1}\n')
        self.assertEqual(self.verify()['status'], 'failed')

    def test_undeclared_EOL_relation_is_rejected(self):
        self.manifest['explicit_EOL_source_paths'] = []
        write(self.root / 'manifest.json', encoded(self.manifest))
        with self.assertRaisesRegex(ValueError, 'unexplained_publication'):
            self.verify()

    def test_full_source_bytes_still_match_even_if_hash_fields_are_updated(self):
        relation = copy.deepcopy(self.manifest['source_relations'][0])
        changed = b'VALUE = 2\r\n'
        relation.update(executed_worktree_sha256=subject.digest(changed), executed_bytes=len(changed))
        with self.assertRaisesRegex(ValueError, 'declared_EOL_relation_not_exact'):
            subject.verify_relation(relation, changed, b'VALUE = 1\n')

    def test_EOL_transform_cannot_be_declared_for_raw_evidence(self):
        relation = copy.deepcopy(self.manifest['source_relations'][0])
        relation['repository_path'] = 'evidence/raw.json'
        with self.assertRaisesRegex(ValueError, 'outside_enumerated_source_domain'):
            subject.verify_relation(relation, b'VALUE = 1\r\n', b'VALUE = 1\n')

    def test_bare_CR_is_not_a_registered_CRLF_conversion(self):
        relation = copy.deepcopy(self.manifest['source_relations'][0])
        executed = b'VALUE = 1\r\n#\r'
        committed = b'VALUE = 1\n#\r'
        relation.update(executed_worktree_sha256=subject.digest(executed), executed_bytes=len(executed),
            committed_content_sha256=subject.digest(committed), committed_bytes=len(committed),
            git_blob_sha1=subject.blob_digest(committed))
        with self.assertRaisesRegex(ValueError, 'declared_EOL_relation_not_exact'):
            subject.verify_relation(relation, executed, committed)

    def test_blob_identity_is_required_in_addition_to_sha256(self):
        self.manifest['files'][0]['git_blob_sha1'] = '0' * 40
        self.manifest['source_relations'][0]['git_blob_sha1'] = '0' * 40
        write(self.root / 'manifest.json', encoded(self.manifest))
        self.assertEqual(self.verify()['status'], 'failed')

    def test_external_archive_does_not_claim_current_repository_identity(self):
        raw = b'user protected bytes\r\n'
        relation = {'executed_worktree_sha256': subject.digest(raw), 'executed_bytes': len(raw),
            'transform': 'external_archive_only', 'repository_path': None,
            'committed_content_sha256': None, 'git_blob_sha1': None}
        subject.verify_relation(relation, raw, None)
        relation['repository_path'] = 'src/czr005/unit.py'
        with self.assertRaisesRegex(ValueError, 'external_archive_claims_git_identity'):
            subject.verify_relation(relation, raw, None)

    def test_original_manifest_and_plan_are_not_rewritten(self):
        for filename in ('old_manifest.json', 'plan.json'):
            with self.subTest(filename=filename):
                before = (self.root / filename).read_bytes()
                write(self.root / filename, before + b'\n')
                with self.assertRaisesRegex(ValueError, 'historical_.*bytes_changed'):
                    self.verify()
                write(self.root / filename, before)


if __name__ == '__main__':
    unittest.main()
