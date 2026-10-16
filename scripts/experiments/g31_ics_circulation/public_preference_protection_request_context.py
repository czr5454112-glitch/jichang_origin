"""One-request guard/potential reuse plus the reviewed completion cut.

The faster existing RequestContext is the reference. Its constructor executes
unchanged in a private namespace, except that its private Projection gets an
observing run wrapper. There is no extra AST split, event fork, quiet-tail
change, static implementation cache, or native authority.
"""
from __future__ import annotations
import builtins
import copy
import hashlib
from pathlib import Path
from types import FunctionType
import weakref

from . import public_preference_request_context as base
from . import public_preference_protection_cut as proof

EXPECTED_CONTEXT = '9c64e97e1e954a3639696ba5ca1f72f9f85e07032121f389b7e34507dfa71c3c'
EXPECTED_CUT = '0c7e1557dd9b4fd3c444e1ea6b944e3bde6a966cd65b90f29d68a5e6e7d08d0a'


def _ledger(projection, reference):
    # The old pure prototype's strong projection reference made a temporary
    # cycle. Keep that evidence frozen; this new context uses a weak proxy.
    return proof._CompletionLedger(weakref.proxy(projection), reference)


class ProtectionRequestContext(base.RequestContext):
    __slots__ = ('__baseline', '__reference', '__counts', '__action', '__digest')

    def __init__(self, bundle):
        for module, expected in ((base, EXPECTED_CONTEXT), (proof, EXPECTED_CUT)):
            if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != expected:
                raise ValueError('protection_request_context:unreviewed_source')
        proof.source_proof()
        reference = {'times': None}
        def run(projection):
            if reference['times'] is None:
                return proof._RUN(projection)
            if projection.completed:
                raise ValueError('protection_request_context:unexpected_initial_completion')
            projection.completed = _ledger(projection, reference['times'])
            result = proof._RUN(projection)
            if 'completion' in result:
                result['completion'] = dict(result['completion'])
            return result
        def private_type(*args):
            if len(args) == 3:
                name, parents, fields = args
                if (name != '_SingleRequestProjection' or parents != (base.original.Projection,)
                        or set(fields) != {'__init__'}
                        or fields['__init__'].__code__ is not base.original.Projection.__init__.__code__):
                    raise ValueError('protection_request_context:unexpected_private_class')
                return builtins.type(name, parents, {**fields, 'run': run})
            return builtins.type(*args)
        source = base.RequestContext.__init__
        initialize = FunctionType(source.__code__, {**source.__globals__, 'type': private_type},
            source.__name__, source.__defaults__, source.__closure__)
        initialize.__kwdefaults__ = copy.deepcopy(source.__kwdefaults__)
        initialize(self, bundle)
        actions = self.actions()
        self.__action = actions[0] if actions else {}
        # The monitor is disabled throughout this same-input complete
        # baseline. No supplied completion vector or saved outcome is read.
        self.__baseline = base.RequestContext.predict(self, self.__action)
        reference['times'] = proof._reference_times(self.__baseline)
        self.__reference = reference
        self.__digest = base.RequestContext.describe(self)['supplied_snapshot_sha256']
        self.__counts = {'baseline_full_simulations': 1, 'candidate_queries': 0,
            'candidate_full_predictions': 0, 'candidate_prefix_rejections': 0, 'candidate_unknowns': 0}

    def baseline(self):
        return copy.deepcopy(self.__baseline)

    def predict(self, action):
        self.__counts['candidate_queries'] += 1
        try:
            result = base.RequestContext.predict(self, action)
        except proof._Rejected as rejected:
            self.__counts['candidate_prefix_rejections'] += 1
            return {'status': 'conditional_protection_rejected_prefix', 'completion': {},
                'completion_sum': None, 'witness': copy.deepcopy(rejected.witness),
                'supplied_snapshot_sha256': self.__digest,
                'baseline_action': copy.deepcopy(self.__action),
                'baseline_completion': dict(self.__baseline['completion']),
                'full_candidate_prediction': False, 'suffix_status': 'unknown_unexecuted',
                'native_protection_certified': False, 'native_execution_certified': False,
                'online_information_delivered': False, 'complete_100ms_certified': False}
        self.__counts['candidate_full_predictions' if result.get('status') == 'conditional_prediction'
                      else 'candidate_unknowns'] += 1
        return result

    def describe(self):
        result = super().describe()
        result.update(version='public_preference_protection_request_context_v1',
            cut_enabled=self.__reference['times'] is not None,
            baseline_status=self.__baseline['status'], counts=dict(self.__counts),
            prefix_sharing=False, static_implementation_cache=False,
            conditional_cut_proof_source_sha256=EXPECTED_CUT,
            complete_100ms_certified=False)
        result['source_proof']['event_loop'] = 'Original Projection.run; only first completed-job assignment may return a conditional strict-protection counterexample and unknown suffix.'
        result['timing_scope'] = 'Full context guards/isolation/fingerprint/potential, full same-input baseline, every candidate guard/dynamic projection and certificate/full-result output must be charged.'
        return result
