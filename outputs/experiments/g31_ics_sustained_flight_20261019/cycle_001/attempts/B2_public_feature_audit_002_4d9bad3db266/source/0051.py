"""Passive archive of arguments actually passed to the owner policy callback."""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path

SCHEMA = 'g31.foundation.airport_policy_observation.v1'
CONTRACT = {'schema': SCHEMA, 'start_at': 43200., 'end_at': 59400.,
    'scope': 'actual owner policy callback arguments and returned decision, including residual calls',
    'readonly': True, 'extra_native_queries': 0, 'future_truth_join': False, 'candidate_labels_created': False,
    'storage': 'concatenated independent gzip JSONL members; an unfinished final member is censored'}


class Recorder:
    def __init__(self, path, *, branch, business_version):
        self.path = Path(path)
        self.stream = self.path.open('xb')
        self.branch = branch
        self.business_version = business_version
        self.count = 0
        self.first_at = self.last_at = None
        self.owners = set()

    def wrap(self, planner):
        def recorded(observation, **options):
            now = observation['now']
            include = CONTRACT['start_at'] <= now <= CONTRACT['end_at']
            # Capture the exact input before the policy runs. Never requery the
            # session, augment private state, or hand a modified view to it.
            before = copy.deepcopy(observation) if include else None
            supplied_options = copy.deepcopy(options) if include else None
            decision = planner(observation, **options)
            if include:
                row = {'schema': SCHEMA, 'sequence': self.count, 'branch': self.branch,
                    'business_contract_version': self.business_version, 'owner_id': before['owner_id'], 'now': now,
                    'readonly': True, 'scope': CONTRACT['scope'], 'observation': before,
                    'policy_options': supplied_options, 'decision': copy.deepcopy(decision),
                    'native_execution_authority': False, 'candidate_conditional_labels': None}
                encoded = (json.dumps(row, separators=(',', ':'), allow_nan=False) + '\n').encode()
                self.stream.write(gzip.compress(encoded, compresslevel=1, mtime=0))
                self.stream.flush()
                self.count += 1; self.owners.add(before['owner_id'])
                self.first_at = now if self.first_at is None else self.first_at; self.last_at = now
            return decision
        return recorded

    def close(self):
        if not self.stream.closed:
            self.stream.close()

    def summary(self):
        if not self.stream.closed:
            raise ValueError('airport_observations:close_before_reference')
        return {'contract': CONTRACT, 'record_count': self.count, 'first_at': self.first_at,
            'last_at': self.last_at, 'owners': sorted(self.owners),
            'artifact': {'path': str(self.path.resolve()), 'sha256': hashlib.sha256(self.path.read_bytes()).hexdigest()},
            'contains_true_conditional_outcome_labels': False, 'native_training_readiness_established': False}
