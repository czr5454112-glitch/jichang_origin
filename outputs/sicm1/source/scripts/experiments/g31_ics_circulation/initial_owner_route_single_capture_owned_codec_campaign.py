"""Same actual18/600 cohort with an explicitly loaded complete C publisher.

The reviewed provider may use its original Python fallback. Direct support is
unknown here. No collection/model normalization, request policy, cutoff, native
authority or complete evidence clock is changed. Import dispatches nothing.
"""
from __future__ import annotations
import ast
import copy
from pathlib import Path

from . import initial_owner_route_single_capture_campaign as previous
from . import initial_owner_route_single_capture_owned_codec as integrated
from . import single_capture_owned_codec_runtime as runtime

SCHEMA = 'g31.initial_single_capture.owned_C_publisher_campaign.v1'
ROOT, OUT, LIMIT = previous.ROOT, previous.OUT, previous.LIMIT
public, image, contract, request = previous.public, previous.image, previous.contract, previous.request
old, gate = previous.old, previous.gate
ARMS, FAULTS, SAVED_PASSED = previous.ARMS, previous.FAULTS, previous.SAVED_PASSED
for _name in ('require', 'sha', 'read', 'ordered', 'reference', 'write', 'declarations', 'scene',
    'failed_root_evidence', 'close_predictor', 'continuation_result', 'full_outcome'):
    globals()[_name] = getattr(previous, _name)
SOURCE_DOMAINS = {**previous.SOURCE_DOMAINS, 'frozen_single_capture_campaign': 190,
    'owned_C_binding_source': 156, 'same_C_owned_decoder_plan': 153}


def absolute_sources(sources):
    canonical = runtime.paths.canonical_sources(sources)
    require(canonical == sources, 'owned_campaign_noncanonical_source_keys')
    return {str((ROOT/name).resolve()): digest for name, digest in canonical.items()}


def source_reference(value, count, sources=None):
    return previous.source_reference(value, count, absolute_sources(sources) if sources is not None else None)


def verify_plan(output, expected):
    plan = integrated.private(old.verify_plan, {'SCHEMA': SCHEMA})(output, expected)
    output = Path(output).resolve()
    absolute_sources(plan['source_sha256'])
    for name in plan['source_sha256']:
        target = runtime.paths.archive_target(output, name)
        require((output/plan['source_archive'][name]).resolve() == target,
            'owned_campaign_archive_containment')
    require(plan['entry_source_proof'] == previous.previous.previous.integrated.integration_proof()
        and plan['entry_codec_source_proof'] == previous.previous.integrated.integration_proof()
        and plan['single_capture_integration_proof'] == previous.integrated.integration_proof()
        and plan['single_capture_campaign_source_proof'] == previous.source_proof(),
        'owned_campaign_original_proofs')
    from . import verify_initial_owner_route_single_capture_campaign as old_verifier
    from . import verify_initial_owner_route_single_capture_owned_codec_campaign as verifier
    require(plan['single_capture_saved_verifier_source_proof'] == old_verifier.source_proof()
        and plan['owned_C_campaign_source_proof'] == source_proof()
        and plan['owned_C_saved_source_proof'] == verifier.source_proof(), 'owned_campaign_proof')
    for name in previous.REFERENCES:
        item = plan[name]
        require(sha(item['path']) == item['sha256'], 'owned_campaign_old_reference:' + name)
    for name, count in SOURCE_DOMAINS.items(): source_reference(plan[name], count, plan['source_sha256'])
    require(plan['C_provider'] == runtime.metadata(), 'owned_campaign_C_contract')
    require(plan['native_branch_budget'] == 18 and plan['max_native_workers'] == 1
        and plan['hard_timeout_seconds'] == 600., 'owned_campaign_budget')
    return plan


def check_loaded_sources(plan):
    # Exact old Python-only inventory, with only the path representation
    # canonicalized. C is separately checked by its actual object/spec/loader;
    # no project pyd is silently admitted as a Python source.
    return previous.check_loaded_sources({**plan,
        'source_sha256': absolute_sources(plan['source_sha256'])})


_WORKER_PROOF = {}


def worker_function(open_provider, close_provider):
    syntax = gate.tree(old.worker); original = copy.deepcopy(syntax)
    body = syntax.body[0].body
    plan_indexes = [j for j, node in enumerate(body) if isinstance(node, ast.Assign)
        and ast.unparse(node.targets[0]) == 'plan'
        and ast.unparse(node.value) == 'verify_plan(output, expected)']
    require(len(plan_indexes) == 1, 'owned_worker_plan_site')
    added = ast.parse('provider = open_provider(plan, output)\nrun_branch = provider.run_branch').body
    body[plan_indexes[0]+1:plan_indexes[0]+1] = added
    imports = [(j, node) for j, node in enumerate(body) if isinstance(node, ast.ImportFrom)
        and node.level == 1 and node.module is None and len(node.names) == 1
        and node.names[0].name == 'verify_initial_owner_route_campaign_v3']
    require(len(imports) == 1, 'owned_worker_verifier_site')
    at, node = imports[0]
    node.names[0].name = 'verify_initial_owner_route_single_capture_owned_codec_campaign'
    body.insert(at, ast.parse('close_provider(provider)').body[0])
    writes = [j for j, node in enumerate(body) if isinstance(node, ast.Expr)
        and ast.unparse(node) == "write(output / 'verification.json', report)"]
    require(len(writes) == 1, 'owned_worker_verification_write')
    body.insert(writes[0]+1, ast.parse("require(report.get('status') == SAVED_PASSED, 'owned_saved_audit_not_passed')").body[0])
    restored = copy.deepcopy(syntax)
    excluded = {'provider = open_provider(plan, output)', 'run_branch = provider.run_branch',
        'close_provider(provider)', "require(report.get('status') == SAVED_PASSED, 'owned_saved_audit_not_passed')"}
    require(sum(ast.unparse(x) in excluded for x in restored.body[0].body) == 4,
        'owned_worker_exact_addition_count')
    restored.body[0].body = [x for x in restored.body[0].body if ast.unparse(x) not in excluded]
    for node in restored.body[0].body:
        if isinstance(node, ast.ImportFrom) and node.names[0].name == 'verify_initial_owner_route_single_capture_owned_codec_campaign':
            node.names[0].name = 'verify_initial_owner_route_campaign_v3'
    require(gate.dump(restored) == gate.dump(original), 'owned_worker_inverse_AST')
    namespace = {**old.worker.__globals__, **globals(),
        'open_provider': open_provider, 'close_provider': close_provider}
    exec(compile(ast.fix_missing_locations(syntax), '<single-capture-owned-C-worker>', 'exec'), namespace)
    _WORKER_PROOF.update(original_worker_inverse_AST_exact=True,
        provider_open_after_original_clock_and_plan=True, original_branch_call_uses_local_bound_function=True,
        provider_close_after_native_RPC_cleanup_before_saved_audit=True,
        original_saved_status_gate_retained=True, original_clock_locations_and_unknowns_unchanged=True)
    return namespace['worker']


def worker(output, expected):
    holder = []
    def open_provider(plan, directory):
        instance = runtime.Provider(plan['C_provider'], directory, write)
        holder.append(instance)
        return instance.open(SCHEMA)
    implementation = worker_function(open_provider, lambda instance: instance.close())
    try:
        return implementation(output, expected)
    except BaseException as error:
        if holder:
            try: holder[0].failed(error)
            except BaseException: pass  # Preserve the primary failure; no success receipt is fabricated.
        raise


main = integrated.private(old.main, {**old.main.__globals__, **globals()})


def source_proof():
    function = worker_function(None, None)
    require(function.__globals__['verify_plan'] is verify_plan
        and function.__globals__['check_loaded_sources'] is check_loaded_sources
        and main.__globals__['worker'] is worker, 'owned_campaign_worker_wiring')
    require(contract is previous.contract and request is previous.request
        and declarations() == previous.declarations() and scene is previous.scene
        and contract.BUDGET_NS == 100_000_000 and LIMIT == 600., 'owned_campaign_original_scope')
    return {'schema': 'g31.single_capture.owned_C_campaign_source.v1', **_WORKER_PROOF,
        'binding': integrated.source_proof(), 'same18_same600_same60ms_decision_cutoff': True,
        'same_collection_model_native_and_complete_root_code': True,
        'original_python_import_inventory_retained': True, 'separate_exact_C_runtime_identity_required': True,
        'C_setup_and_close_inside_shared_campaign': True, 'C_provider_original_fallback_retained': True,
        'actual_direct_support_count': None, 'actual_C_loaded_on_source_proof': False,
        'performance_or_complete100ms_claim': False}


if __name__ == '__main__': raise SystemExit(main())
