"""Conditional protection rejection at a completed-job prefix.

This is an opt-in supplied-data experiment. It does not fork projections, share
dynamic state, authorize native actions, or turn a partial run into a complete
prediction. A baseline is simulated here on this context's isolated snapshot;
external vectors/results are never accepted as the protection reference.
"""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
import pickle
from types import FunctionType

from . import public_preference_request_context as closed
from . import public_native_preference_projection as original

VERSION = 'public_preference_completed_prefix_cut_v1'
_ERRORS = (TypeError, ValueError, KeyError, OverflowError, AttributeError)
_PREDICT = original._predict
_PUBLIC_PREDICT = original.predict
_PROJECTION = original.Projection
_RUN = original.Projection.run
_LOAD = original.legacy.DiscreteProjection.load_waiting
_COMPLETE = original.legacy.DiscreteProjection.complete_leg
_TRY_DEPART = original.Projection.try_depart
_IDENTITIES = tuple((obj, obj.__code__) for obj in (_PREDICT, _PUBLIC_PREDICT, _RUN, _LOAD, _COMPLETE, _TRY_DEPART))


def source_proof():
    for module, digest in ((original, closed.EXPECTED_SOURCE),
                           (original.legacy, closed.EXPECTED_LEGACY)):
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != digest:
            raise ValueError('protection_cut:unreviewed_source')
    if (original._predict is not _PREDICT or original.predict is not _PUBLIC_PREDICT or original.Projection is not _PROJECTION
            or original.Projection.run is not _RUN or original.Projection.try_depart is not _TRY_DEPART
            or original.legacy.DiscreteProjection.load_waiting is not _LOAD
            or original.legacy.DiscreteProjection.complete_leg is not _COMPLETE
            or any(function.__code__ is not code for function, code in _IDENTITIES)):
        raise ValueError('protection_cut:changed_proof_function')
    return {'projection_source_sha256': closed.EXPECTED_SOURCE,
        'legacy_source_sha256': closed.EXPECTED_LEGACY,
        'completion_write': 'Projection.run unload branch is the sole post-constructor completed write.',
        'single_assignment_scope': 'Restricted initial 3-tray/5-job population. load_waiting removes each waiting job by changing its jstatus to loading; no transition restores waiting. Initial loaded/blocker jobs are not waiting. complete_leg clears goal before scheduling unload and try_depart ignores no-goal trays.',
        'future_actions': 'return_decision/later_decision/route command do not modify a completed job or its recorded completion time.',
        'interpretation': 'A strict > witness refutes all-job protection in this pinned conditional model only; unexecuted suffix remains unknown.',
        'runtime_boundary': 'Reviewed repository functions and isolated builtin input, not a security boundary against arbitrary in-process monkeypatches.'}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _reference_times(prediction):
    values = prediction.get('completion')
    if (prediction.get('status') != 'conditional_prediction' or type(values) is not dict
            or set(values) != original.contract.JOBS or not all(_number(v) for v in values.values())):
        return None
    return dict(values)


class _Rejected(Exception):
    def __init__(self, witness):
        self.witness = witness


class _CompletionLedger(dict):
    """Observe only the original unload assignment; never used by policy."""
    def __init__(self, projection, baseline):
        super().__init__()
        self._projection, self._baseline = projection, baseline

    def __setitem__(self, job, value):
        if job not in self._baseline or job in self or not _number(value) or value != self._projection.time:
            raise ValueError('protection_cut:invalid_or_repeated_completion')
        super().__setitem__(job, value)
        if value > self._baseline[job]:
            raise _Rejected({'job': job, 'candidate_completed_at': value,
                'baseline_completed_at': self._baseline[job], 'cut_at': self._projection.time,
                'completed_prefix': dict(self), 'comparison': 'strict >; no tolerance',
                'observed_point': 'original unload assignment before its post-unload notification'})


class ProtectionContext:
    """One input, one complete reference, independent candidate simulations.

The original input and action guards execute on every simulation. This first
candidate isolates the logical cut; it makes no speed claim and deliberately
does not combine the slower prefix-sharing or static-factory experiments.
"""
    def __init__(self, bundle, baseline_action):
        self._proof = source_proof()
        closed._closed_tree(bundle); closed._closed_tree(baseline_action)
        self._snapshot = copy.deepcopy(bundle)
        self._baseline_action = copy.deepcopy(baseline_action)
        self._fingerprint = hashlib.sha256(pickle.dumps(self._snapshot, protocol=5)).hexdigest()
        self._baseline = original.predict(self._snapshot, self._baseline_action)
        reference = _reference_times(self._baseline)
        self._counts = {'baseline_full_simulations': 1, 'candidate_queries': 0,
                        'candidate_full_predictions': 0, 'candidate_prefix_rejections': 0,
                        'candidate_unknowns': 0}
        self._enabled = reference is not None
        if reference is None:
            self._evaluate = original.predict
        else:
            class CutProjection(_PROJECTION):
                def run(projection):
                    if projection.completed:
                        raise ValueError('protection_cut:unexpected_initial_completed_state')
                    projection.completed = _CompletionLedger(projection, reference)
                    result = _RUN(projection)
                    if 'completion' in result:
                        result['completion'] = dict(result['completion'])
                    return result
            # The whole original guard function and constructor/event loop
            # stay intact. Only its private Projection global is substituted.
            self._evaluate = FunctionType(_PREDICT.__code__,
                {**_PREDICT.__globals__, 'Projection': CutProjection},
                _PREDICT.__name__, _PREDICT.__defaults__, _PREDICT.__closure__)
            self._evaluate.__kwdefaults__ = copy.deepcopy(_PREDICT.__kwdefaults__)

    def predict(self, action):
        self._counts['candidate_queries'] += 1
        try:
            closed._closed_tree(action)
            result = self._evaluate(self._snapshot, copy.deepcopy(action))
        except _Rejected as rejected:
            self._counts['candidate_prefix_rejections'] += 1
            return {'status': 'conditional_protection_rejected_prefix', 'completion': {},
                'completion_sum': None, 'witness': copy.deepcopy(rejected.witness),
                'supplied_snapshot_sha256': self._fingerprint,
                'baseline_action': copy.deepcopy(self._baseline_action),
                'baseline_completion': dict(self._baseline['completion']),
                'full_candidate_prediction': False, 'suffix_status': 'unknown_unexecuted',
                'native_protection_certified': False, 'native_execution_certified': False,
                'online_information_delivered': False, 'complete_100ms_certified': False}
        except _ERRORS:
            result = closed.malformed()
        self._counts['candidate_full_predictions' if result.get('status') == 'conditional_prediction'
                     else 'candidate_unknowns'] += 1
        return result

    def baseline(self):
        return copy.deepcopy(self._baseline)

    def describe(self):
        return {'version': VERSION, 'source_proof': copy.deepcopy(self._proof),
            'supplied_snapshot_sha256': self._fingerprint, 'cut_enabled': self._enabled,
            'baseline_status': self._baseline['status'], 'counts': dict(self._counts),
            'native_protection_certified': False, 'complete_100ms_certified': False,
            'timing_scope': 'Baseline source checks, input isolation/fingerprint/full baseline simulation and every original candidate guard/constructor/event up to cut are required costs. No cost measured or excluded by this module.',
            'fair_methods': 'Use the same full baseline, strict cut, declared action domain and candidate/wall budgets for every method. A cut consumes a candidate evaluation; remaining unexecuted candidates stay unknown.'}
