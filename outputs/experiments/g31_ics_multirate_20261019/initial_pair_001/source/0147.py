"""Private composition of actual-entry observation and full evidence codec.

Only evidence construction/finalization changes from the saved-audited entry
integration. Exact original native handles, query trace, ACK closure, drain,
scheduler and continuation policy remain. No campaign or native auto-run.
"""
from __future__ import annotations
import copy
from . import initial_owner_route_entry_integration as entry
from . import complete_root_evidence_candidate as codec

private,require=entry.private,entry.require
contract=entry.contract
EVIDENCE=private(codec.EVIDENCE,{'root_runtime_proof':entry.root_runtime_proof})


class CapturedRequest(entry.CapturedRequest):
    evidence=EVIDENCE


class FixedDefaultRequest(CapturedRequest):
    choose=entry.FixedDefaultRequest.choose


# No change in the native authority class or either actual observation call.
# The collection method identity checked by this chain is inherited unchanged.
ActualAdvanceChain=entry.ActualAdvanceChain
TRACED_OBSERVE,TRACKED_DRAIN=entry.TRACED_OBSERVE,entry.TRACKED_DRAIN
finish_root=private(codec.finish_root,{'evidence':EVIDENCE})
publish_root=private(codec.publish_root,{'finish_root':finish_root})
run_continuation=private(entry.run_continuation,{'publish_root':publish_root})
run_continuation._source_proof=copy.deepcopy(entry.run_continuation._source_proof)
TracedContinuationOwner,make_client=entry.TracedContinuationOwner,entry.make_client


def integration_proof():
    require(CapturedRequest.collect is entry.CapturedRequest.collect
        and CapturedRequest.observe_after_boundary is entry.TRACED_OBSERVE
        and CapturedRequest.drain_and_finish_if_closed is entry.TRACKED_DRAIN
        and CapturedRequest.final_revalidate_and_submit is entry.CapturedRequest.final_revalidate_and_submit,
        'entry_codec_changed_live_contract')
    require(run_continuation.__code__ is entry.run_continuation.__code__
        and run_continuation.__globals__['ActualAdvanceChain'] is entry.ActualAdvanceChain
        and run_continuation.__globals__['publish_root'] is publish_root,
        'entry_codec_changed_scheduler_or_native_authority')
    require(EVIDENCE.__code__ is codec.EVIDENCE.__code__
        and EVIDENCE.__globals__['root_runtime_proof'] is entry.root_runtime_proof
        and finish_root.__code__ is codec.finish_root.__code__
        and finish_root.__globals__['evidence'] is EVIDENCE
        and publish_root.__globals__['finish_root'] is finish_root,
        'entry_codec_wrong_evidence_binding')
    return {'schema':'g31.initial_root.entry_complete_codec_integration.v1',
        'entry':entry.integration_proof(),'codec':codec.source_proof(),
        'original_collection_observer_drain_and_final_revalidation_unchanged':True,
        'original_accepted_native_and_exact_transport_authority_unchanged':True,
        'actual_entry_marker_and_complete_query_proof_encoded':True,
        'strict_decode_reencode_inside_complete_root':True,
        'original_scheduler_policy_and_publisher_code_unchanged':True,
        'frozen_modules_or_classes_modified':False,'native_or_predictor_dispatched':False,
        'universal100ms_or_business_superiority_claimed':False}
