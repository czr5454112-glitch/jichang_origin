"""Fresh immutable five-time certificate reference for the frozen bound context.

The original full baseline is still computed and public baseline() still returns
its isolated full output. Only early certificate construction uses this private
tuple of the five already-validated completion times. No input/action guard,
bound, event, candidate count, public full/partial output or GC policy changes.
No request or projection state is reused across contexts.
"""
from __future__ import annotations
import copy
import hashlib
from pathlib import Path
from . import public_preference_receiver_bound_context as old

EXPECTED_OLD='455bf6029f1336ef29dbbc96ea934375534e756039f519560ec828fc0fa71c36'
_INIT=old.ReceiverBoundRequestContext.__init__
_PREDICT=old.ReceiverBoundRequestContext.predict
_IDENTITIES=tuple((f,f.__code__) for f in (_INIT,_PREDICT))


class ReceiverVectorRequestContext(old.ReceiverBoundRequestContext):
    __slots__=('__completion_vector',)

    def __init__(self,bundle):
        if (hashlib.sha256(Path(old.__file__).read_bytes()).hexdigest()!=EXPECTED_OLD
                or old.ReceiverBoundRequestContext.__init__ is not _INIT
                or old.ReceiverBoundRequestContext.predict is not _PREDICT
                or any(f.__code__ is not code for f,code in _IDENTITIES)):
            raise ValueError('receiver_vector:unreviewed_source')
        super().__init__(bundle)
        # This pinned field is produced only by the original context's actual
        # complete baseline and _reference_times validation, never caller data.
        # Retain insertion order for byte-identical emitted JSON dictionaries.
        times=object.__getattribute__(self,'_ProtectionRequestContext__reference')['times']
        self.__completion_vector=None if times is None else tuple(times.items())

    def predict(self,action):
        # This is the exact method reached by super() in the frozen old predict.
        # Dispatching through old.predict would construct its old full copy.
        try:return old.combined.ProtectionRequestContext.predict(self,action)
        except old._LowerBoundRejected as rejected:
            self._ReceiverBoundRequestContext__early_count+=1
            return {'status':'conditional_protection_rejected_lower_bound','completion':{},'completion_sum':None,
                'witness':copy.deepcopy(rejected.witness),'supplied_snapshot_sha256':self._ReceiverBoundRequestContext__fingerprint,
                'baseline_action':copy.deepcopy(self._ReceiverBoundRequestContext__baseline_action),'baseline_completion':dict(self.__completion_vector),
                'full_candidate_prediction':False,'suffix_status':'unknown_unexecuted',
                'native_protection_certified':False,'native_execution_certified':False,
                'online_information_delivered':False,'complete_100ms_certified':False}
