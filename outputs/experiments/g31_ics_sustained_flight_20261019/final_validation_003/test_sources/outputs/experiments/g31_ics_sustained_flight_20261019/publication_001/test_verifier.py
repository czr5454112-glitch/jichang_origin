"""Small portable fixtures for executed-byte versus current-source identities."""
import json
from pathlib import Path
import tempfile
import unittest
from verify_publication import sha, verify
import split_evidence


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = self.root / 'episode/plan.json'
        self.archive = self.root / 'episode/source/0000.py'
        self.archive.parent.mkdir(parents=True)
        self.archive.write_bytes(b'original = True\r\n')
        self.plan.write_text(json.dumps({'source_sha256': {'C:\\old\\module.py': sha(self.archive)},
                                       'source_archive': {'C:\\old\\module.py': 'source\\0000.py'}}))
        (self.root / 'module.py').write_bytes(b'new_source = True\n')
        self.manifest = {'files': [self.row(p) for p in (self.plan, self.archive, self.root / 'module.py')]}

    def row(self, p):
        return {'path': p.relative_to(self.root).as_posix(), 'executed_worktree_sha256': sha(p),
                'expected_committed_content_sha256': sha(p)}

    def test_historical_archive_need_not_equal_new_source(self):
        result = verify(self.root, self.manifest)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['historical_source_archive_checks'], 1)

    def test_eol_mutation_is_not_silently_normalized(self):
        self.archive.write_bytes(b'original = True\n')
        self.assertEqual(verify(self.root, self.manifest)['status'], 'failed')

    def test_archive_must_be_in_selected_publication(self):
        self.manifest['files'].pop(1)
        self.assertEqual(verify(self.root, self.manifest)['status'], 'failed')

    def test_outside_root_and_duplicate_rejected(self):
        self.manifest['files'] += [self.manifest['files'][0], {**self.manifest['files'][0], 'path': '../secret'}]
        result = verify(self.root, self.manifest)
        self.assertEqual(result['status'], 'failed')
        self.assertGreaterEqual(len(result['failures']), 2)

    def test_declared_committed_bytes_must_equal_executed(self):
        self.manifest['files'][0]['expected_committed_content_sha256'] = '0' * 64
        self.assertEqual(verify(self.root, self.manifest)['status'], 'failed')

    def test_outer_registration_archived_sources_required(self):
        attempt = self.root / 'cycle/attempts/one'
        (attempt / 'source').mkdir(parents=True)
        archived = attempt / 'source/0000.py'
        archived.write_bytes(b'saved_outer = True\n')
        registration = attempt / 'registration.json'
        registration.write_text(json.dumps({'source_pins': {'C:\\old\\outer.py': sha(archived)}}))
        self.manifest['files'] += [self.row(registration), self.row(archived)]
        self.assertEqual(verify(self.root, self.manifest)['status'], 'passed')
        archived.write_bytes(b'changed_outer = True\n')
        self.assertEqual(verify(self.root, self.manifest)['status'], 'failed')

    def test_chunked_original_restores_exactly_and_detects_reordering(self):
        old_root, old_size = split_evidence.ROOT, split_evidence.CHUNK_BYTES
        split_evidence.ROOT, split_evidence.CHUNK_BYTES = self.root, 7
        self.addCleanup(setattr, split_evidence, 'ROOT', old_root)
        self.addCleanup(setattr, split_evidence, 'CHUNK_BYTES', old_size)
        source = self.root / 'large.bin'; source.write_bytes(bytes(range(29)))
        chunkdir = self.root / 'chunks'
        split_evidence.split(source, chunkdir)
        manifest = chunkdir / 'CHUNKS.json'
        publication = {'files': [self.row(p) for p in chunkdir.iterdir()]}
        self.assertEqual(verify(self.root, publication)['status'], 'passed')
        destination = self.root / 'restored'
        split_evidence.restore(manifest, destination)
        self.assertEqual((destination / 'large.bin').read_bytes(), source.read_bytes())
        split_evidence.restore(manifest, destination)
        data = json.loads(manifest.read_bytes()); data['chunks'].reverse()
        manifest.write_text(json.dumps(data))
        with self.assertRaises(AssertionError):
            split_evidence.restore(manifest, self.root / 'wrong_order')
        self.assertFalse((self.root / 'wrong_order/large.bin').exists())

    def test_restore_refuses_to_replace_existing_bytes(self):
        target = self.root / 'module.py'
        manifest = self.root / 'CHUNKS.json'
        manifest.write_text(json.dumps({'schema': split_evidence.SCHEMA, 'original_path': 'module.py',
                                       'original_bytes': 0, 'original_sha256': '0' * 64, 'chunks': []}))
        before = target.read_bytes()
        with self.assertRaises(AssertionError):
            split_evidence.restore(manifest, self.root)
        self.assertEqual(target.read_bytes(), before)

    def test_chunk_manifest_original_destination_cannot_escape_publication_root(self):
        manifest = self.root / 'CHUNKS.json'
        for original in ('../outside.bin', '/outside.bin', 'C:\\outside.bin', 'C:outside.bin', '.'):
            with self.subTest(original=original):
                manifest.write_text(json.dumps({'schema': split_evidence.SCHEMA,
                    'original_path': original, 'original_bytes': 0,
                    'original_sha256': '0' * 64, 'chunks': []}))
                result = verify(self.root, {'files': [self.row(manifest)]})
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['failures'][0]['reason'], 'original_stream_path_outside_root')


if __name__ == '__main__':
    unittest.main()
