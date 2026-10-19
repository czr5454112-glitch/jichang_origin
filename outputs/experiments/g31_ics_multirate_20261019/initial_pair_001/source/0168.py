"""Draft actual18/600 static inventory campaign; no execution on import."""
from __future__ import annotations
import ast
import builtins
import copy
from pathlib import Path

from . import initial_owner_route_single_capture_owned_codec_campaign as previous
from . import single_capture_static_inventory_runtime as runtime

SCHEMA = 'g31.initial_single_capture.static_inventory_campaign.v1'
ROOT, OUT, LIMIT = previous.ROOT, previous.OUT, previous.LIMIT
public, image, contract, request = previous.public, previous.image, previous.contract, previous.request
old, gate, integrated = previous.old, previous.gate, previous.integrated
ARMS, FAULTS, SAVED_PASSED = previous.ARMS, previous.FAULTS, previous.SAVED_PASSED
for _name in ('require', 'sha', 'read', 'ordered', 'reference', 'write', 'declarations', 'scene',
    'failed_root_evidence', 'close_predictor', 'continuation_result', 'full_outcome',
    'check_loaded_sources', 'absolute_sources', 'source_reference'):
    globals()[_name] = getattr(previous, _name)
SOURCE_DOMAINS = {**previous.SOURCE_DOMAINS, 'frozen_owned_C18_campaign': 218,
    'static_inventory_pure_plan': 222}


def verify_plan(output, expected):
    # The accepted checker keeps ALL its defining globals and old proof keys.
    # Only the new schema is supplied to it. New proofs are separate fields.
    plan = integrated.private(previous.verify_plan, {'SCHEMA': SCHEMA})(output, expected)
    from . import verify_initial_owner_route_static_inventory_campaign as verifier
    require(plan['static_inventory_campaign_source_proof'] == source_proof()
        and plan['static_inventory_saved_source_proof'] == verifier.source_proof(),
        'static_campaign_source_proofs')
    for name in ('frozen_owned_C18_campaign', 'static_inventory_pure_plan'):
        source_reference(plan[name], SOURCE_DOMAINS[name], plan['source_sha256'])
    for name in ('static_inventory_pure_receipt', 'static_inventory_root_saved_review',
                 'static_inventory_campaign_pure_receipt'):
        item = plan[name]
        require(sha(item['path']) == item['sha256'], 'static_campaign_reference:' + name)
    require(plan['static_inventory_amendment']['constructor_sidecar'] == 'static_inventory_lifetime.json'
        and plan['native_branch_budget'] == 18 and plan['hard_timeout_seconds'] == 600.,
        'static_campaign_unchanged_budget')
    return plan


_WORKER_PROOF = {}


def _compiler(syntax, filename, mode):
    require(filename == '<single-capture-owned-C-worker>' and mode == 'exec',
        'static_worker_compile_site')
    source = copy.deepcopy(syntax)
    matches = [node for node in ast.walk(syntax) if isinstance(node, ast.ImportFrom)
        and node.level == 1 and node.module is None and len(node.names) == 1
        and node.names[0].name == 'verify_initial_owner_route_single_capture_owned_codec_campaign']
    require(len(matches) == 1, 'static_worker_import_count')
    matches[0].names[0].name = 'verify_initial_owner_route_static_inventory_campaign'
    restored = copy.deepcopy(syntax)
    changed = [node for node in ast.walk(restored) if isinstance(node, ast.ImportFrom)
        and len(node.names) == 1
        and node.names[0].name == 'verify_initial_owner_route_static_inventory_campaign']
    require(len(changed) == 1, 'static_worker_inverse_count')
    changed[0].names[0].name = 'verify_initial_owner_route_single_capture_owned_codec_campaign'
    require(gate.dump(restored) == gate.dump(source), 'static_worker_import_inverse_AST')
    _WORKER_PROOF['only_new_saved_verifier_import_inverse_AST_exact'] = True
    return builtins.compile(ast.fix_missing_locations(syntax), filename, mode)


def worker_function(open_provider, close_provider):
    # The old factory still proves its original worker inverse AST. Its sole
    # compiler hook proves the additional one-import change before compiling.
    function = integrated.private(previous.worker_function,
        {**previous.worker_function.__globals__, **globals(), 'compile': _compiler})
    return function(open_provider, close_provider)


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
            except BaseException: pass  # Original failure remains primary.
        raise


main = integrated.private(old.main, {**old.main.__globals__, **globals()})


def source_proof():
    function = worker_function(None, None)
    require(function.__globals__['verify_plan'] is verify_plan
        and function.__globals__['check_loaded_sources'] is previous.check_loaded_sources
        and main.__globals__['worker'] is worker, 'static_campaign_worker_wiring')
    require(contract is previous.contract and request is previous.request
        and declarations() == previous.declarations() and scene is previous.scene
        and contract.BUDGET_NS == 100_000_000 and LIMIT == 600., 'static_campaign_scope')
    return {'schema': 'g31.initial_single_capture.static_inventory_campaign_source.v1',
        'accepted_C18_worker_source': previous.source_proof(), **_WORKER_PROOF,
        'runtime': runtime.source_proof(),
        'same18_same600_same60ms_cutoff_same100ms_complete_boundary': True,
        'same_C6124_entry_exit_and_saved_third_check': True,
        'same_RPC_native_source_ACK_drain_fullphysical_unknown_checks': True,
        'constructor_sidecar_required_in_addition_to_C_provider_lifetime': True,
        'actual_C_support_or_performance_claim': False}


if __name__ == '__main__': raise SystemExit(main())
