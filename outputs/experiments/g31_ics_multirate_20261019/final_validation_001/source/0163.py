"""Versioned actual18 target for fresh single-triplet endpoint collection.

Same branch code, inputs, policy, finite2 decisions, native authority and owned
600 lifecycle. Failure-aware saved verification separates physical facts from
complete request certification. Importing this module dispatches nothing.
"""
from __future__ import annotations
import ast
import copy
from pathlib import Path
from . import initial_owner_route_entry_codec_campaign as previous
from . import initial_owner_route_single_capture_integration as integrated

SCHEMA = 'g31.initial_owner_route_single_capture_campaign.v1'
ROOT, OUT, public, image = previous.ROOT, previous.OUT, previous.public, previous.image
LIMIT, ARMS, FAULTS = previous.LIMIT, previous.ARMS, previous.FAULTS
contract, old, gate = integrated.contract, previous.old, previous.gate
for _name in ('require', 'sha', 'read', 'ordered', 'reference', 'write', 'declarations', 'scene',
    'failed_root_evidence', 'close_predictor', 'continuation_result', 'full_outcome', 'check_loaded_sources'):
    globals()[_name] = getattr(previous, _name)
CapturedRequest, FixedDefaultRequest = integrated.CapturedRequest, integrated.FixedDefaultRequest
captured_collection = integrated.single.captured_collection
call_with_recorded_collection = integrated.call_with_recorded_collection
run_continuation, publish_root = integrated.run_continuation, integrated.publish_root
request = previous.request
# branch_function verifies all four actual collection/continuation bindings
# against the original complete globals before only the raw schema is changed.
run_branch = integrated.private(integrated.branch_function(), {'SCHEMA': SCHEMA})
REFERENCES = previous.REFERENCES + ('frozen_entry_codec_campaign', 'entry_codec_saved_review',
    'single_capture_integration_source', 'single_capture_endpoint_source',
    'single_capture_verifier_source', 'single_capture_verifier_pure', 'single_capture_campaign_pure')
SOURCE_DOMAINS = {'frozen_entry_codec_campaign': 169, 'frozen_codec_plan': 135,
    'single_capture_integration_source': 153, 'single_capture_endpoint_source': 131}
SAVED_PASSED = 'passed_saved_with_complete_unknown_denominator'


def source_reference(reference_value, expected_count, campaign_sources=None):
    """Read-only current/archive identity, never replay or native acceptance."""
    path = Path(reference_value['path']).resolve()
    require(sha(path) == reference_value['sha256'], 'single_capture_source_reference_hash')
    value = read(path)
    sources, archive = value['source_sha256'], value['source_archive']
    require(type(sources) is dict and len(sources) == expected_count,
        'single_capture_source_reference_count')
    for name, digest in sources.items():
        current = Path(name); current = current if current.is_absolute() else ROOT/current
        current = current.resolve()
        if type(archive) is dict:
            saved = Path(archive[name]); saved = saved if saved.is_absolute() else path.parent/saved
        else:
            require(type(archive) is str and not Path(name).is_absolute(),
                'single_capture_source_archive_shape')
            saved = Path(archive)/name
        require(sha(current) == sha(saved) == digest,
            'single_capture_reference_current_or_archive_changed:' + name)
        if campaign_sources is not None:
            require(campaign_sources.get(str(current)) == digest,
                'single_capture_reference_not_in_campaign:' + name)
    return {'path': str(path), 'sha256': reference_value['sha256'], 'sources': len(sources)}


def verify_plan(output, expected):
    plan = integrated.private(old.verify_plan, {'SCHEMA': SCHEMA})(output, expected)
    require(plan['entry_source_proof'] == previous.previous.integrated.integration_proof(),
        'single_capture_original_entry_proof_changed')
    require(plan['entry_codec_source_proof'] == previous.integrated.integration_proof(),
        'single_capture_original_codec_proof_changed')
    require(plan['single_capture_integration_proof'] == integrated.integration_proof(),
        'single_capture_integration_proof_changed')
    require(plan['single_capture_campaign_source_proof'] == source_proof(),
        'single_capture_campaign_source_changed')
    from . import verify_initial_owner_route_single_capture_campaign as verifier
    require(plan['single_capture_saved_verifier_source_proof'] == verifier.source_proof(),
        'single_capture_saved_verifier_source_changed')
    for name in REFERENCES:
        ref = plan[name]
        require(sha(ref['path']) == ref['sha256'], 'single_capture_reference_changed:' + name)
    for name, count in SOURCE_DOMAINS.items():
        source_reference(plan[name], count, plan['source_sha256'])
    require(plan['max_native_workers'] == 1 and plan['native_branch_budget'] == 18
        and plan['hard_timeout_seconds'] == 600., 'single_capture_campaign_budget')
    return plan


_WORKER_PROOF = {}


def worker_function():
    syntax = gate.tree(old.worker)
    original = copy.deepcopy(syntax)
    count = 0
    for node in ast.walk(syntax):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None:
            if len(node.names) == 1 and node.names[0].name == 'verify_initial_owner_route_campaign_v3':
                node.names[0].name = 'verify_initial_owner_route_single_capture_campaign'
                count += 1
    require(count == 1, 'single_capture_worker_verifier_import')
    body = syntax.body[0].body
    targets = [index for index, node in enumerate(body) if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
        and node.value.func.id == 'write' and len(node.value.args) == 2
        and ast.unparse(node.value.args[0]) == "output / 'verification.json'"
        and ast.unparse(node.value.args[1]) == 'report']
    require(len(targets) == 1, 'single_capture_worker_verification_write')
    status_gate = ast.parse("require(report.get('status') == SAVED_PASSED, "
        "'single_capture_saved_audit_not_passed')").body[0]
    body.insert(targets[0] + 1, status_gate)
    restored = copy.deepcopy(syntax)
    del restored.body[0].body[targets[0] + 1]
    for node in ast.walk(restored):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None:
            if len(node.names) == 1 and node.names[0].name == 'verify_initial_owner_route_single_capture_campaign':
                node.names[0].name = 'verify_initial_owner_route_campaign_v3'
    require(gate.dump(restored) == gate.dump(original), 'single_capture_worker_AST_changed')
    namespace = {**old.worker.__globals__, **globals()}
    exec(compile(ast.fix_missing_locations(syntax), '<single-capture-owned-worker>', 'exec'), namespace)
    _WORKER_PROOF.update(original_worker_inverse_AST_exact=True, changed_import_sites=count,
        post_saved_verification_status_gates=1, invalid_saved_audit_cannot_write_completed_receipt=True,
        original_unknown_and_cleanup_paths_retained=True, original_request_and_campaign_clocks_retained=True)
    return namespace['worker']


worker = worker_function()
main = integrated.private(old.main, globals())


def source_proof():
    original = previous.run_branch
    expected = {'CapturedRequest': CapturedRequest, 'FixedDefaultRequest': FixedDefaultRequest,
        'run_continuation': run_continuation, 'call_with_recorded_collection': call_with_recorded_collection,
        'SCHEMA': SCHEMA}
    require(run_branch.__code__ is original.__code__ and run_branch.__closure__ is original.__closure__
        and run_branch.__defaults__ is original.__defaults__ and run_branch.__kwdefaults__ is original.__kwdefaults__
        and set(run_branch.__globals__) == set(original.__globals__)
        and all(value is expected.get(name, original.__globals__[name])
            for name, value in run_branch.__globals__.items()), 'single_capture_branch_namespace')
    require(worker.__globals__['run_branch'] is run_branch and worker.__globals__['verify_plan'] is verify_plan
        and main.__globals__['worker'] is worker, 'single_capture_worker_wiring')
    require(request is previous.request and publish_root is previous.publish_root,
        'single_capture_policy_or_publisher_changed')
    return {'schema': 'g31.single_capture.campaign_source.v1', **_WORKER_PROOF,
        'branch_code_defaults_closure_full_globals_retained': True,
        'branch_changed_globals': sorted(expected),
        'same18_inputs_and_faults': declarations() == previous.declarations() and scene is previous.scene,
        'same_finite2_and_100ms_budget': contract.BUDGET_NS == 100_000_000,
        'same_background_policy_native_authority_and_cadence': True,
        'single_capture_getter_effect_equivalence_claimed': False,
        'frozen_prototype_proofs_are_historical_not_current_dispatch': True,
        'C_normalizer_added': False, 'shared_seconds': LIMIT, 'native_dispatched': False}


if __name__ == '__main__':
    raise SystemExit(main())
