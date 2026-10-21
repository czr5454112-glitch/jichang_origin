"""Lossless shared observations, bounded caches and fail-closed artifact audits."""
from copy import deepcopy
import gzip
import json
import sqlite3

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_joint_evidence as evidence
from scripts.experiments.g31_ics_circulation.foundation_airport_batch_patch import digest


def fixture(count=300):
    jobs = [{'business_bag_id': f'包{i}', 'arrival': i*.5, 'status': 'waiting', 'unknown': None}
        for i in range(count)]
    return dict(owner_id='A', now=12., jobs=jobs, trays=[{'tray_id':'T','node':0}],
        control_projection={'waiting_groups':[{'origin':0, 'jobs':jobs[:5], 'unknown':None}]},
        node_records=[[0, 1, .001, [1]], [1, 2, .002, [0]]],
        planning_snapshots=[{'capture':{'jobs':jobs, 'trays':[{'tray_id':'T','node':0}]}}],
        transfers=[], client_transfer_ledger=[], scalars=[True, False, None, -0.0, 2**60, '中文'])


def rewrite_database_binding(path, receipt):
    result = deepcopy(receipt)
    result['database_sha256'] = evidence._file_hash(path)
    return result


def test_reconstruction_conserves_public_digest_unknown_values_unicode_and_metadata(tmp_path):
    path = tmp_path/'observations.sqlite'
    obs = fixture(); row = {'digest':digest(obs), 'observation':obs, 'optional_metadata':None}
    with evidence.ObservationStore(path, page_size=16) as writer:
        writer.extend([row])
        writer.flush()
    with evidence.ObservationReader(path) as reader:
        reconstructed = reader.read(0)
        assert reconstructed == row
        assert digest(reconstructed['observation']) == digest(obs)
        reconstructed['observation']['jobs'][0]['status'] = 'mutated_reader_copy'
        assert reader.read(0) == row
    audit = evidence.audit_store(path)
    assert audit['original_public_digests_conserved']
    assert not audit['native_run_completion_certified']


def test_one_changed_job_only_adds_its_row_and_ancestor_pages(tmp_path):
    with evidence.ObservationStore(tmp_path/'observations.sqlite', page_size=16) as writer:
        first = fixture(300); writer.write(first)
        initial = writer.stats['object_insertions']
        changed = deepcopy(first); changed['now'] += 60.; changed['jobs'][100]['status'] = 'completed'
        writer.write(changed)
        assert writer.stats['object_insertions'] - initial <= 10
        before = writer.stats['object_insertions']; writer.write(changed)
        assert writer.stats['object_insertions'] == before


def test_index_and_reader_caches_are_bounded_not_all_history(tmp_path):
    path = tmp_path/'observations.sqlite'
    with evidence.ObservationStore(path, index_cache_entries=2, page_size=8) as writer:
        for index in range(3):
            obs = fixture(25); obs['now'] = float(index); writer.write(obs)
            assert len(writer.seen) <= 2
    assert writer.receipt['stats']['max_index_cache_entries'] <= 2
    with evidence.ObservationReader(path, cache_bytes=256) as reader:
        assert len(list(reader)) == 3
        assert reader.cache_size <= 256


def test_wrong_original_digest_rolls_back_and_poisoned_writer_cannot_seal(tmp_path):
    path = tmp_path/'observations.sqlite'; writer = evidence.ObservationStore(path)
    with pytest.raises(ValueError, match='original_public_digest_mismatch'):
        writer.write(fixture(3), expected_digest='0'*64)
    with pytest.raises(ValueError, match='writer_not_open'):
        writer.write(fixture(3))
    receipt = writer.close()
    assert receipt['status'] == 'aborted' and receipt['frame_count'] == receipt['object_count'] == 0
    with pytest.raises(ValueError, match='unsealed_store'):
        evidence.audit_store(path)


def test_interrupted_writer_has_committed_prefix_but_never_a_sealed_receipt(tmp_path):
    path = tmp_path/'observations.sqlite'; writer = evidence.ObservationStore(path)
    writer.write(fixture(3))
    writer.connection.close()  # Model process exit before close/receipt, without running any native code.
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT value FROM metadata WHERE key='status'").fetchone()[0] == 'writing'
        assert connection.execute('SELECT count(*) FROM frames').fetchone()[0] == 1
    assert not path.with_suffix('.sqlite.receipt.json').exists()
    with pytest.raises((FileNotFoundError, ValueError)):
        evidence.audit_store(path)


def test_changed_chunk_rejected_even_if_outer_file_binding_is_recomputed(tmp_path):
    path = tmp_path/'observations.sqlite'
    with evidence.ObservationStore(path) as writer:
        writer.write(fixture(3))
    with sqlite3.connect(path) as connection:
        identity = connection.execute("SELECT hash FROM objects WHERE kind='raw' LIMIT 1").fetchone()[0]
        connection.execute('UPDATE objects SET payload=? WHERE hash=?', (gzip.compress(b'null'), identity))
    with pytest.raises(ValueError, match='chunk_digest'):
        evidence.audit_store(path, receipt=rewrite_database_binding(path, writer.receipt))


def test_missing_chunk_rejects_reconstruction_even_if_outer_binding_recomputed(tmp_path):
    path = tmp_path/'observations.sqlite'
    with evidence.ObservationStore(path) as writer:
        writer.write(fixture(3))
    with sqlite3.connect(path) as connection:
        root = connection.execute('SELECT root_hash FROM frames').fetchone()[0]
        connection.execute('DELETE FROM objects WHERE hash=?', (root,))
    with evidence.ObservationReader(path, receipt=rewrite_database_binding(path, writer.receipt)) as reader:
        with pytest.raises(ValueError, match='missing_chunk'):
            reader.read(0)


def test_removed_frame_or_changed_frame_metadata_cannot_pass_chain(tmp_path):
    path = tmp_path/'observations.sqlite'
    with evidence.ObservationStore(path) as writer:
        writer.write(fixture(3)); writer.write(fixture(4))
    with sqlite3.connect(path) as connection:
        connection.execute('DELETE FROM frames WHERE sequence=0')
    with pytest.raises(ValueError, match='frame_sequence_or_chain'):
        evidence.audit_store(path, receipt=rewrite_database_binding(path, writer.receipt))


def test_empty_closed_stream_and_existing_path_are_distinct_from_crash(tmp_path):
    path = tmp_path/'observations.sqlite'
    with evidence.ObservationStore(path):
        pass
    assert evidence.audit_store(path)['frame_count'] == 0
    with pytest.raises(FileExistsError):
        evidence.ObservationStore(path)


@pytest.mark.parametrize('bad', [float('nan'), float('inf')])
def test_nonfinite_values_cannot_become_valid_json_evidence(tmp_path, bad):
    path = tmp_path/'observations.sqlite'
    with pytest.raises(ValueError):
        with evidence.ObservationStore(path) as writer:
            writer.write({'value':bad})
    assert json.loads(path.with_suffix('.sqlite.receipt.json').read_text())['status'] == 'aborted'
