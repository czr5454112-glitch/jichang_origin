"""Independent fixed96 native campaign, prepared and dispatched separately.

No old globals, runtime sources or saved outputs are edited. No predictor is
called. One fresh information pair can change the actual physical continuation;
only this campaign's completed native outcomes support its finite comparisons.
"""
from __future__ import annotations
import copy, gzip, hashlib, json, sys, time, traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from types import FunctionType
from . import research_live_obligation_native_domain as prior
from . import live_obligation_recollection_adapter as adapter
from . import live_obligation_recollection_policy as policy
from . import verify_live_obligation_recollection as saved

ROOT, OUT = prior.ROOT, prior.OUT
ORDER, CASE_ORDER = prior.ORDER, prior.CASE_ORDER
HARD_TIMEOUT = 600.
require, sha, read, write, reference = prior.require, prior.sha, prior.read, prior.write, prior.reference
SOURCE_PREP = OUT/'live_obligation_recollection_source_prepare_001/source_preparation.json'
SOURCE_PREP_SHA = '31b9884de31f4c55eddc18525adc0761f98fa70cedf40bb0a98add80cb7b47f7'
OLD_PLAN = OUT/'live_obligation_native_domain_prepare_001/preregistered_protocol.json'
OLD_PLAN_SHA = 'dc9cc27b6a04eae5eb8ce5d97b9ef844e00657b2cec34004bafb41f952586c04'
TEST_XML = OUT/'recollection_campaign_pure_003.xml'


def _clone(function, namespace):
    result = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


_private = dict(vars(prior))
_private.update(adapter=adapter, OwnerPolicy=policy.OwnerPolicy)
_private['owner_first_action'] = _clone(prior.owner_first_action, _private)
_native_branch = _clone(prior._run_branch, _private)


def export_attempts(raw, progress):
    """Actual retained data only, on both success and exception paths."""
    policies = progress.get('policies', {})
    raw['collection_attempts'] = {'A': [], 'B': []}
    try:
        raw['collection_attempts'].update(policy.attempt_evidence(policies))
        raw['collection_attempt_export'] = 'all_recorded_attempts_json_only'
    except Exception:
        raw.setdefault('capture_errors', {})['collection_attempts'] = traceback.format_exc()
        for owner, item in policies.items():
            try: raw['collection_attempts'][owner] = adapter.json_data(item.collection_attempts)
            except Exception: raw['capture_errors']['collection_attempts_' + owner] = traceback.format_exc()
        raw['collection_attempt_export'] = 'failed_unknown_incomplete_attempt_evidence'
        raw['summary'] = {'status': 'unknown_failed_partial', 'business_metrics': None, 'strict_protected': None}
        raw['partial'] = True
        raw.setdefault('exception', 'recorded collection attempt serialization failed')
        raw['result_capture_rule'] = 'only_preexisting_result; result_at_not_called_after_exception'
    if 'native027_acceptance' not in raw and policies:
        try: raw['native027_acceptance'] = next(iter(policies.values())).accepted.audit_copy()
        except Exception: raw.setdefault('capture_errors', {})['native027_acceptance'] = traceback.format_exc()
    raw['communication_policy'] = {'schema': 'g31.one_fresh_pair_per_phase.v1',
        'native_physics_paused': False, 'old_prediction_conformance_assumed': False,
        'first_return_issue_time_can_change': True, 'max_pairs_per_deciding_phase': 2,
        'native_model_protection_certified': False}
    return raw


def run_branch(native, row, contract_reference, semantic_reference, *, accepted_run, branch_key):
    progress = {'specification': copy.deepcopy(row)}
    try:
        raw = _native_branch(native, row, contract_reference, semantic_reference,
            accepted_run=accepted_run, branch_key=branch_key, progress=progress)
    except Exception:
        raw = prior.capture_partial(progress, traceback.format_exc())
    return export_attempts(raw, progress)


def comparisons(rows):
    """Full finite families only; no old-model method selection is reused."""
    c = prior.domain_contract; c.validate_rows(rows); cases = {}
    for case in CASE_ORDER:
        group = {k: rows[k] for k in ORDER if rows[k]['case'] == case}
        basekey = next(k for k, r in group.items() if r['vector'] == c.prior.incumbent_action())
        base = group[basekey]; refs = {}
        for name, field in (('fixed_initial_native_default', 'initial_action'), ('later_native_default', 'later_action')):
            family = {k: r for k, r in group.items() if r['vector'][field] == 'native_default'}
            require(len(family) == 16, 'reference16')
            complete = c.known(base) and all(c.known(r) for r in family.values())
            eligible = [k for k, r in family.items() if complete and c.compare_one(r, base)['strict_protected'] is True]
            best = min(eligible, key=lambda k: (c.score(family[k]), k), default=None)
            refs[name] = {'status': 'complete_native_finite_reference' if complete else 'unknown_incomplete_reference',
                'members': list(family), 'member_count': 16, 'assessed_members': sum(c.known(r) for r in family.values()),
                'best_key': best, 'best_sum': c.score(family[best]) if best else None}
        complete = all(c.known(r) for r in group.values())
        eligible = [k for k, r in group.items() if complete and c.compare_one(r, base)['strict_protected'] is True]
        best = min(eligible, key=lambda k: (c.score(group[k]), k), default=None)
        cases[case] = {'incumbent_key': basekey, 'assessed': sum(c.known(r) for r in group.values()),
            'unknown': sum(not c.known(r) for r in group.values()), 'references': refs,
            'full32_finite_optimum': best, 'rows_vs_incumbent': {k: c.compare_one(r, base) for k, r in group.items()}}
    return {'status': 'complete96_denominator_not_necessarily_assessed', 'row_count': 96, 'cases': cases,
        'objective': 'sum of five completion times; every job <= incumbent, exactly zero tolerance',
        'online_solver_executed': False, 'old_model_selection_mapping': 'not_reused_after_message_policy_change',
        'native_oracle_policy_input': False, 'full_reference_claim_requires_complete_family': True}


def source_closure():
    return list(map(Path, prior.bound.imported_sources()))


def verify(output, plan):
    require(plan['schema'] == 'g31.live_obligation_recollection_fixed96.v1'
            and plan['case_order'] == CASE_ORDER and plan['branch_order'] == ORDER
            and plan['rows'] == prior.probe_rows() and plan['native_branch_budget'] == 96
            and plan['hard_timeout_seconds'] == HARD_TIMEOUT, 'fixed96_plan')
    prior.domain_contract.validate_rows(plan['rows'])
    require(set(plan['source_sha256']) == set(map(str, source_closure())), 'loaded_source_closure')
    for path, digest in plan['source_sha256'].items():
        require(sha(path) == sha(output/plan['source_archive'][path]) == digest, 'source_pin')
    for key in ORDER:
        path = output/'inputs'/(key + '.json')
        require(sha(path) == plan['input_file_sha256'][key]
                and read(path) == prior.native_scene(plan['rows'][key]['case']), 'input_pin')
    require(plan['runtime_overlay'] == prior.RUNTIME_OVERLAY and plan['strict_protection_tolerance'] == 0.
            and plan['common_horizon'] == 40. and plan['native_forks'] == 0, 'physical_contract')
    for ref in (plan['binary'], plan['interpreter'], plan['native_contract_reference'], plan['semantic_gate_reference'],
                *plan['auxiliary_references'].values()):
        require(sha(ref['path']) == ref['sha256'], 'reference_pin')


def prepare(output):
    require(not output.exists(), 'immutable_output')
    require(sha(SOURCE_PREP) == SOURCE_PREP_SHA and sha(OLD_PLAN) == OLD_PLAN_SHA, 'frozen_prior_boundary')
    source_prep = read(SOURCE_PREP)
    for path, digest in source_prep['sources'].items():
        require(sha(path) == sha(SOURCE_PREP.parent/source_prep['source_archive'][path]) == digest, 'old81_pin')
    suites = ET.parse(TEST_XML).getroot().findall('testsuite')
    require(len(suites) == 1 and int(suites[0].get('tests', 0)) == 39
            and all(int(suites[0].get(k, -1)) == 0 for k in ('failures', 'errors', 'skipped')), 'campaign_pure_gate')
    output.mkdir(parents=True)
    sources = source_closure(); pins = {str(p): sha(p) for p in sources}; archives = {}
    for path in sources:
        dest = output/'source'/path.relative_to(ROOT); dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes()); archives[str(path)] = str(dest.relative_to(output))
    old = read(OLD_PLAN)
    plan = {'schema': 'g31.live_obligation_recollection_fixed96.v1', 'case_order': CASE_ORDER,
        'branch_order': ORDER, 'rows': prior.probe_rows(), 'native_branch_budget': 96, 'hard_timeout_seconds': HARD_TIMEOUT,
        'source_sha256': pins, 'source_archive': archives, 'input_file_sha256': {},
        'binary': old['binary'], 'interpreter': reference(sys.executable),
        'native_contract_reference': old['native_contract_reference'], 'semantic_gate_reference': old['semantic_gate_reference'],
        'runtime_overlay': prior.RUNTIME_OVERLAY, 'same_physical_inputs_and_fixed_actions': True,
        'communication_policy': 'One fresh actual source pair after a supported current change or crossed service bound; at most two monotone invitations per deciding phase. All final identity/current/action/ACK-union/stability checks retained.',
        'failure_and_partial_rule': 'All96 rows always retained. Preserve unsuccessful collections, delayed/missing/unexecuted actions, partial prefix and unknown. A new failed collection may not create a third pair. No native clock pause or result reconstruction after exception.',
        'scope': 'Fixed counterfactual execution diagnostic with a new public message policy; no online optimizer, no policy selection from saved native outcomes, no old point-prediction protection claim.',
        'first_return_action_semantics': old['first_return_action_semantics'],
        'references': 'Both complete16 fixed-initial and later-default families; full32 optimum only when all32 known. Exact whole-five-job protection vs the unchanged incumbent.',
        'cost_scope': 'One600s owned Windows Job child includes imports/prechecks/full44+21 entry/all96 native branches/all source checks/raw export/endpoint+attempt+physical saved replay/final44+21/output. Parent application wall separately measured. No100ms claim.',
        'budget_derivation': {'prior96_worker_seconds': 238.117568, 'prior96_external_seconds': 239.2389025,
            'saved_retry_feasibility_candidates': 44, 'fixed_shared_limit_seconds': HARD_TIMEOUT,
            'limits': 'No time extension or selected-case restart; actual new captures and costs unknown.'},
        'common_horizon': 40., 'strict_protection_tolerance': 0., 'native_forks': 0, 'max_native_workers': 1,
        'auxiliary_references': {name: reference(path) for name, path in {
            'old_native96_plan': OLD_PLAN, 'frozen_stageAB_sources': SOURCE_PREP,
            'root_stageB_source_review': SOURCE_PREP.parent/'root_source_review_001.json',
            'recollection_protocol': OUT/'live_obligation_recollection_protocol_001.json',
            'saved_window_evidence': OUT/'live_obligation_recollection_design_evidence_001.json',
            'pure_tests': TEST_XML,
            'pure_test_source': ROOT/'tests/test_g31_circulation_live_obligation_recollection_campaign.py',
            **{'frozen_' + case: OUT/'live_obligation_projection_prepare_003'/(case + '.input.json') for case in CASE_ORDER}
        }.items()}}
    for key in ORDER:
        path = output/'inputs'/(key + '.json'); path.parent.mkdir(parents=True, exist_ok=True)
        data = prior.native_scene(plan['rows'][key]['case']); write(path, data)
        require(prior.validate_runtime_input(data) == read(plan['auxiliary_references']['frozen_' + plan['rows'][key]['case']]['path']),
                'frozen_physical_input')
        plan['input_file_sha256'][key] = sha(path)
    write(output/'preregistered_protocol.json', plan); verify(output, plan)
    command = [sys.executable, '-m', 'scripts.experiments.g31_ics_circulation.launch_live_obligation_recollection',
               '--launch', '--output', str(output)]
    receipt = {'status': 'prepared_unexecuted', 'plan_sha256': sha(output/'preregistered_protocol.json'),
        'source_count': len(sources), 'native_executions': 0, 'model_evaluations': 0, 'launch_command': command}
    write(output/'prepare_receipt.json', receipt)
    return receipt


def worker(output):
    started = time.perf_counter()
    with (output/'worker_claim.json').open('x', encoding='utf8') as stream:
        json.dump({'started_wall': started, 'no_restart': True}, stream)
    plan = read(output/'preregistered_protocol.json')
    require(sha(output/'preregistered_protocol.json') == read(output/'prepare_receipt.json')['plan_sha256'], 'plan_identity')
    rows = copy.deepcopy(plan['rows']); write(output/'branch_ledger.json', rows)
    verify(output, plan)
    campaign = reference(output/'preregistered_protocol.json')
    accepted = prior.run_admission.open_run(plan['native_contract_reference'], plan['semantic_gate_reference'], campaign)
    order = []
    try:
        native = prior.bound.load_native(Path(plan['binary']['path']))
        for key in ORDER:
            row = rows[key]; row['status'] = 'unknown_in_progress'; row['execution_index'] = len(order)
            write(output/'branch_ledger.json', rows); branch_start = time.perf_counter()
            try:
                accepted.enter_branch(key, campaign)
                expected_specification = copy.deepcopy(row)
                raw = run_branch(native, row, plan['native_contract_reference'], plan['semantic_gate_reference'],
                                 accepted_run=accepted, branch_key=key)
                path = output/(key + '.json.gz'); path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(gzip.compress(json.dumps(raw, allow_nan=False).encode(), compresslevel=1, mtime=0))
                row['raw_artifact'] = reference(path); row['summary'] = raw['summary']; row['status'] = raw['summary']['status']
                loaded = json.loads(gzip.decompress(path.read_bytes()))
                if 'input' in loaded:
                    require(loaded['input'] == read(output/'inputs'/(key + '.json')), 'saved_prepared_input')
                if 'specification' in loaded:
                    require(loaded['specification'] == expected_specification, 'saved_prepared_row')
                row['saved_replay'] = saved.verify_partial(loaded) if loaded.get('partial') is True else saved.verify_saved(loaded)
                accepted.finish_branch(key)
            except Exception:
                row['status'] = 'unknown_failed'; row['exception'] = traceback.format_exc()
                if accepted.active_for(key):
                    try: accepted.finish_branch(key)
                    except Exception: row['acceptance_error'] = traceback.format_exc()
            row['branch_wall_seconds_including_save_audit'] = time.perf_counter() - branch_start
            order.append(key); write(output/'branch_ledger.json', rows)
    finally:
        closed = accepted.close(); write(output/'run_acceptance.json', closed)
    verify(output, plan); require(order == ORDER, 'actual96_order')
    valid = closed['status'] == 'closed_run_acceptance_passed'
    receipt = {'schema': 'g31.live_obligation_recollection_fixed96_receipt.v1',
        'status': ('complete96_assessed' if all(prior.domain_contract.known(r) for r in rows.values()) else 'completed_with_unknowns')
                  if valid else 'invalidated_runtime_evidence',
        'plan_sha256': sha(output/'preregistered_protocol.json'), 'branch_order': order, 'branch_count': 96,
        'ledger_sha256': sha(output/'branch_ledger.json'), 'source_changed': [], 'source_closure_changed': [],
        'run_acceptance': reference(output/'run_acceptance.json'), 'run_acceptance_status': closed['status'],
        'comparisons': comparisons(rows) if valid else None, 'worker_wall_seconds': time.perf_counter() - started,
        'native_branch_attempts': len(order), 'old_prediction_conformance_assumed': False,
        'online_optimizer_claim': False, 'complete_request_100ms_certified': False}
    write(output/'receipt.json', receipt)
