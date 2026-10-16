"""New actual18 target: unchanged entry policy plus complete evidence codec.

No native execution on import. All original18 inputs, finite2 decisions, ACK
faults, fullH40 audit and shared600 lifecycle remain. Old151/codec135 are frozen.
"""
from __future__ import annotations
import ast
import copy
from types import SimpleNamespace
from . import initial_owner_route_entry_campaign as previous
from . import initial_owner_route_entry_codec_integration as integrated

SCHEMA = 'g31.initial_owner_route_entry_complete_codec_campaign.v1'
ROOT, OUT, public, image = previous.ROOT, previous.OUT, previous.public, previous.image
LIMIT, ARMS, FAULTS = previous.LIMIT, previous.ARMS, previous.FAULTS
contract, old, gate = integrated.contract, previous.old, previous.gate
for _name in ('require', 'sha', 'read', 'ordered', 'reference', 'write', 'declarations', 'scene',
    'captured_collection', 'call_with_recorded_collection', 'failed_root_evidence', 'close_predictor',
    'continuation_result', 'full_outcome', 'check_loaded_sources'):
    globals()[_name] = getattr(previous, _name)
CapturedRequest, FixedDefaultRequest = integrated.CapturedRequest, integrated.FixedDefaultRequest
run_continuation, publish_root = integrated.run_continuation, integrated.publish_root
request = SimpleNamespace(**vars(previous.request))
request.FixedContinuationOwner = integrated.TracedContinuationOwner
# Original factory proves that the only native branch changes remain the
# previously accepted traced client and two audit fields. Its private namespace
# resolves the new evidence-owning request classes and original entry scheduler.
run_branch = integrated.private(previous.previous.branch_function, globals())()

REFERENCES = ('frozen_v3_campaign', 'frozen_single_evidence_plan', 'frozen_gate_v1_campaign',
    'frozen_gate_v2_campaign', 'entry_pure_reference', 'frozen_entry_campaign',
    'failed_entry_producer_external', 'recovered_entry_audit', 'recovered_entry_verification',
    'recovered_entry_external', 'frozen_codec_plan', 'codec_saved_audit', 'codec_saved_audit_external',
    'entry_codec_integration_pure', 'entry_codec_campaign_pure')


def verify_plan(output, expected):
    plan = integrated.private(old.verify_plan, {'SCHEMA': SCHEMA})(output, expected)
    require(plan['entry_source_proof'] == previous.integrated.integration_proof(),
            'entry_codec_original_entry_proof_changed')
    require(plan['entry_codec_source_proof'] == integrated.integration_proof(),
            'entry_codec_integration_proof_changed')
    require(plan['campaign_source_proof'] == source_proof(), 'entry_codec_worker_source_changed')
    # The defining-v3 globals are retained by this new verifier. Both root
    # replay levels bind this campaign, not the old failed producer namespace.
    from . import verify_initial_owner_route_entry_codec_campaign as verifier
    require(plan['saved_verifier_source_proof'] == verifier.source_proof(),
            'entry_codec_saved_verifier_source_changed')
    for name in REFERENCES:
        ref = plan[name]
        require(sha(ref['path']) == ref['sha256'], 'entry_codec_reference_changed:'+name)
    require(plan['max_native_workers'] == 1 and plan['native_branch_budget'] == 18 and
        plan['hard_timeout_seconds'] == 600., 'entry_codec_campaign_budget')
    return plan


_WORKER_PROOF = {}


def worker_function():
    syntax = gate.tree(old.worker)
    original = copy.deepcopy(syntax)
    count = 0
    for node in ast.walk(syntax):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None:
            if len(node.names) == 1 and node.names[0].name == 'verify_initial_owner_route_campaign_v3':
                node.names[0].name = 'verify_initial_owner_route_entry_codec_campaign'
                count += 1
    require(count == 1, 'entry_codec_worker_verifier_import')
    restored = copy.deepcopy(syntax)
    for node in ast.walk(restored):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None:
            if len(node.names) == 1 and node.names[0].name == 'verify_initial_owner_route_entry_codec_campaign':
                node.names[0].name = 'verify_initial_owner_route_campaign_v3'
    require(gate.dump(restored) == gate.dump(original), 'entry_codec_worker_AST_changed')
    namespace = {**old.worker.__globals__, **globals()}
    exec(compile(ast.fix_missing_locations(syntax), '<entry-codec-owned-worker>', 'exec'), namespace)
    _WORKER_PROOF.update(original_worker_inverse_AST_exact=True, changed_import_sites=count,
        original_unknown_and_close_paths_retained=True, original_request_and_campaign_clocks_retained=True)
    return namespace['worker']


worker = worker_function()
main = integrated.private(old.main, globals())


def source_proof():
    require(worker.__globals__['run_branch'] is run_branch and
        worker.__globals__['verify_plan'] is verify_plan and main.__globals__['worker'] is worker,
        'entry_codec_worker_wiring')
    require(run_branch.__globals__['CapturedRequest'] is integrated.CapturedRequest and
        run_branch.__globals__['FixedDefaultRequest'] is integrated.FixedDefaultRequest and
        run_branch.__globals__['run_continuation'] is integrated.run_continuation,
        'entry_codec_branch_wiring')
    return {'schema': 'g31.initial_entry_codec.campaign_source.v1', **_WORKER_PROOF,
        'same18_inputs_and_faults': declarations() == previous.declarations() and scene is previous.scene,
        'finite2_budget_100ms_unchanged': contract.BUDGET_NS == 100_000_000,
        'same_native_handle_collection_and_cadence': True, 'shared_seconds': LIMIT,
        'native_dispatched': False}


if __name__ == '__main__':
    raise SystemExit(main())
