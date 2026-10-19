"""Lossless callback recording with immutable content-addressed list chunks.

The live planner receives the original observation and returns its original
decision. References only change audit storage, never online policy input.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import time
import zlib
from functools import lru_cache
from pathlib import Path

SCHEMA = 'g31.foundation.airport_policy_observation.v2'
CONTRACT = {'schema': SCHEMA, 'start_at': 43200., 'end_at': 59400.,
    'scope': 'actual owner policy callback arguments and returned decision, including residual calls',
    'readonly': True, 'extra_native_queries': 0, 'future_truth_join': False,
    'candidate_labels_created': False, 'storage': 'lossless content-addressed64-item chunks and complete gzip reference records',
    'chunk_items': 64, 'same_actor_fields_and_values': True,
    'reconstructed_record_schema_change': {'from': 'g31.foundation.airport_policy_observation.v1', 'to': SCHEMA},
    'all_other_reconstructed_fields_exact': True, 'unknown_values_and_group_counts_preserved': True,
    'partial_rule': 'only complete gzip members and reference rows with all blobs present are reconstructable'}


def encoded(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Recorder:
    def __init__(self, path, *, branch, business_version):
        self.path = Path(path)
        self.blobs_path = self.path.with_name(self.path.name.replace('.jsonl.gz', '.blobs.jsonl.gz'))
        self.stream = self.path.open('xb')
        self.blob_stream = self.blobs_path.open('xb')
        self.branch, self.business_version = branch, business_version
        self.count = self.blob_count = self.blob_bytes = self.reference_bytes = 0
        self.capture_seconds = 0.
        self.first_at = self.last_at = None
        self.owners, self.seen, self.cache = set(), set(), {}

    def _blob(self, scope, value):
        data = encoded(value)
        cached = self.cache.get(scope)
        if cached is not None and cached[0] == data:
            return cached[1]
        digest = hashlib.sha256(data).hexdigest()
        if digest not in self.seen:
            line = b'{"sha256":"' + digest.encode() + b'","value":' + data + b'}\n'
            self.blob_stream.write(gzip.compress(line, compresslevel=1, mtime=0))
            self.blob_count += 1; self.blob_bytes += len(line); self.seen.add(digest)
        # Immutable exact JSON bytes preserve nested bool/int/float distinctions
        # and survive any subsequent mutation without a full object deepcopy.
        self.cache[scope] = (data, digest)
        return digest

    def _pack(self, value, scope):
        if value is None or type(value) in (bool, int, float, str):
            return {'kind': 'inline', 'value': value}
        if isinstance(value, list):
            chunks = [self._blob((*scope, i // CONTRACT['chunk_items']), value[i:i+CONTRACT['chunk_items']])
                for i in range(0, len(value), CONTRACT['chunk_items'])]
            return {'kind': 'list', 'length': len(value), 'chunks': chunks}
        return {'kind': 'value', 'sha256': self._blob(scope, value)}

    def _object(self, value, scope):
        fields = {}
        for key, item in value.items():
            if key == 'transfers' and 'client_transfer_ledger' in fields and item is value['client_transfer_ledger']:
                # Native policy view deliberately supplies this exact alias.
                # Store one descriptor; reconstruction still yields both fields.
                fields[key] = fields['client_transfer_ledger']
            else:
                fields[key] = self._pack(item, (*scope, key))
        return {'kind': 'object', 'fields': fields}

    def wrap(self, planner):
        def recorded(observation, **options):
            now = observation['now']
            include = CONTRACT['start_at'] <= now <= CONTRACT['end_at']
            started = time.perf_counter()
            if include:
                owner = observation['owner_id']
                before = self._object(observation, (owner, 'observation'))
                supplied = self._object(options, (owner, 'options'))
            capture_before = time.perf_counter() - started
            decision = planner(observation, **options)
            if include:
                started = time.perf_counter()
                row = {'schema': SCHEMA, 'sequence': self.count, 'branch': self.branch,
                    'business_contract_version': self.business_version, 'owner_id': owner, 'now': now,
                    'readonly': True, 'scope': CONTRACT['scope'], 'observation': before,
                    'policy_options': supplied, 'decision': self._object(decision, (owner, 'decision')),
                    'native_execution_authority': False, 'candidate_conditional_labels': None}
                line = encoded(row) + b'\n'
                # A completed reference row always follows written complete
                # blob members. A killed final member cannot masquerade as closed.
                self.blob_stream.flush()
                self.stream.write(gzip.compress(line, compresslevel=1, mtime=0)); self.stream.flush()
                self.reference_bytes += len(line); self.count += 1; self.owners.add(owner)
                self.first_at = now if self.first_at is None else self.first_at; self.last_at = now
                self.capture_seconds += capture_before + time.perf_counter() - started
            return decision
        return recorded

    def close(self):
        self.blob_stream.close(); self.stream.close()

    def summary(self):
        if not self.stream.closed or not self.blob_stream.closed:
            raise ValueError('airport_observations_v2:close_before_reference')
        return {'contract': CONTRACT, 'record_count': self.count, 'first_at': self.first_at, 'last_at': self.last_at,
            'owners': sorted(self.owners), 'artifact': {'path': str(self.path.resolve()), 'sha256': sha(self.path)},
            'blobs': {'path': str(self.blobs_path.resolve()), 'sha256': sha(self.blobs_path)},
            'unique_blob_count': self.blob_count, 'uncompressed_blob_bytes': self.blob_bytes,
            'uncompressed_reference_bytes': self.reference_bytes, 'capture_seconds': self.capture_seconds,
            'contains_true_conditional_outcome_labels': False, 'native_training_readiness_established': False}


def members(path, *, allow_partial=False, with_offsets=False):
    """Yield only CRC-checked complete gzip members, never a partial last row."""
    decoder = zlib.decompressobj(31); pieces = []; started = False
    offset = member_start = 0
    with Path(path).open('rb') as f:
        data = b''
        while True:
            if not data:
                data = f.read(65536)
                if not data:
                    if started and not allow_partial:
                        raise ValueError('airport_observations_v2:incomplete_gzip_member')
                    return
            started = True
            pieces.append(decoder.decompress(data))
            if decoder.eof:
                offset += len(data) - len(decoder.unused_data)
                payload = b''.join(pieces)
                yield (payload, member_start, offset-member_start) if with_offsets else payload
                data = decoder.unused_data
                decoder = zlib.decompressobj(31); pieces = []; started = False
                member_start = offset
            else:
                offset += len(data)
                data = b''


def read_records(path, *, blobs_path=None, allow_partial=False):
    path = Path(path)
    blobs_path = Path(blobs_path) if blobs_path is not None else path.with_name(path.name.replace('.jsonl.gz', '.blobs.jsonl.gz'))
    index = {}
    for member, offset, length in members(blobs_path, allow_partial=allow_partial, with_offsets=True):
        row = json.loads(member)
        if hashlib.sha256(encoded(row['value'])).hexdigest() != row['sha256']:
            raise ValueError('airport_observations_v2:blob_hash_mismatch')
        if row['sha256'] in index:
            raise ValueError('airport_observations_v2:duplicate_blob')
        index[row['sha256']] = (offset, length)

    @lru_cache(maxsize=256)
    def blob(key):
        offset, length = index[key]
        with blobs_path.open('rb') as stream:
            stream.seek(offset)
            row = json.loads(gzip.decompress(stream.read(length)))
        if row['sha256'] != key or hashlib.sha256(encoded(row['value'])).hexdigest() != key:
            raise ValueError('airport_observations_v2:blob_hash_mismatch')
        return row['value']

    def unpack(ref):
        kind = ref['kind']
        if kind == 'inline': return copy.deepcopy(ref['value'])
        if kind == 'value': return copy.deepcopy(blob(ref['sha256']))
        if kind == 'list':
            value = [copy.deepcopy(item) for key in ref['chunks'] for item in blob(key)]
            if len(value) != ref['length']: raise ValueError('airport_observations_v2:list_length')
            return value
        if kind == 'object': return {key: unpack(value) for key, value in ref['fields'].items()}
        raise ValueError('airport_observations_v2:reference_kind')

    for sequence, member in enumerate(members(path, allow_partial=allow_partial)):
        row = json.loads(member)
        if row['schema'] != SCHEMA or row['sequence'] != sequence:
            raise ValueError('airport_observations_v2:record_identity')
        for field in ('observation', 'policy_options', 'decision'):
            row[field] = unpack(row[field])
        yield row
