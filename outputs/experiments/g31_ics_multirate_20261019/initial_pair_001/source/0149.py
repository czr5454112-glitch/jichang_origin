"""Separate actual-entry observer wiring; no campaign or native dispatch.

The existing gate, full outbox trace, complete drain and ACK closure remain.
Only the two root first-hop observation calls use the source-bound predicate.
Earlier closure can change subsequent admissions/IDs; no old tape equivalence
or observed speed improvement is claimed by this source-only integration.
"""
from __future__ import annotations
import copy
from types import SimpleNamespace
from . import initial_owner_route_gated_evidence_v2 as previous
from . import initial_owner_route_entry_hop as entry

private, require = previous.private, previous.require
contract = SimpleNamespace(**vars(previous.request.contract))
contract.observed_first_hop = entry.observed_first_hop
MARKER = {
    'schema': 'g31.initial_root.actual_entry_observation.v1',
    'native_binding': 'accepted_native027_actual_EDGE_ENTER_matching_current_traversal',
    'source_prefix': [0],
    'reservation_without_actual_entry_receipt_sufficient': False,
    'original_ACK_and_complete_drain_required': True,
    'later_admission_or_ID_equality_claimed': False,
}

# Function bytecode and the original refresh wrapper stay unchanged. The
# observer contract facade exists only in these new private function globals.
TRACED_OBSERVE = private(previous.TRACED_OBSERVE, {'contract': contract})


class ActualAdvanceChain(previous.ActualAdvanceChain):
    pass


_actual_root_drain = private(previous._actual_root_drain,
                             {'ActualAdvanceChain': ActualAdvanceChain})
TRACKED_DRAIN = private(previous.TRACKED_DRAIN,
                       {'contract': contract, '_actual_root_drain': _actual_root_drain})


def root_runtime_proof(root):
    result = previous.root_runtime_proof(root)
    result['first_hop_observation_contract'] = copy.deepcopy(MARKER)
    return result


EVIDENCE = private(previous.EVIDENCE, {'root_runtime_proof': root_runtime_proof})


class CapturedRequest(previous.CapturedRequest):
    observe_after_boundary = TRACED_OBSERVE
    drain_and_finish_if_closed = TRACKED_DRAIN
    evidence = EVIDENCE


class FixedDefaultRequest(CapturedRequest):
    choose = previous.FixedDefaultRequest.choose


# The original exact-type/native-handle and complete-method checks also apply
# to this integration. Their concrete expected methods are privately rebound.
ActualAdvanceChain.__init__ = private(previous.ActualAdvanceChain.__init__, {
    'TRACKED_DRAIN': TRACKED_DRAIN, 'TRACED_OBSERVE': TRACED_OBSERVE,
    'CapturedRequest': CapturedRequest,
})
finish_root = private(previous.finish_root, {'evidence': EVIDENCE})
publish_root = private(previous.publish_root, {'finish_root': finish_root})
run_continuation = private(previous.run_continuation, {
    'ActualAdvanceChain': ActualAdvanceChain, 'publish_root': publish_root,
})
run_continuation._source_proof = copy.deepcopy(previous.run_continuation._source_proof)
run_continuation._source_proof.update(firsthop_detector_changed=True,
    original_scheduler_statements_retained=True,
    resulting_admission_or_ID_equality_claimed=False)
TracedContinuationOwner = previous.TracedContinuationOwner
make_client = previous.make_client


def integration_proof():
    before = previous.integration_proof()
    require(TRACED_OBSERVE.__code__ is previous.TRACED_OBSERVE.__code__
        and TRACKED_DRAIN.__code__ is previous.TRACKED_DRAIN.__code__
        and run_continuation.__code__ is previous.run_continuation.__code__,
        'entry_integration_changed_observer_drain_scheduler_code')
    require(contract.closure is previous.request.contract.closure
        and previous.request.contract.observed_first_hop is entry._ORIGINAL,
        'entry_integration_changed_original_contract')
    return {'schema': 'g31.initial_root.entry_integration_source.v1',
        'previous_gated_evidence_proof': before,
        'first_hop_predicate': entry.source_proof(),
        'observation_contract': copy.deepcopy(MARKER),
        'scheduler': copy.deepcopy(run_continuation._source_proof),
        'live_observe_and_post_drain_share_same_new_predicate': True,
        'original_closure_and_ACK_code_unchanged': True,
        'actual_session_and_transport_required': True,
        'all_runtime_proof_encoded_inside_root': True,
        'imported_global_or_class_monkeypatch': False,
        'native_or_predictor_dispatched': False}
