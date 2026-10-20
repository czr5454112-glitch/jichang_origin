"""New fixed600 saved-only audit with exact replay substitutions and progress.

Old producer2400 and saved-audit002600 failures are never edited or upgraded.
This module does not construct a native session or run a predictor.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET
from types import FunctionType
from . import audit_bridge_serialize_once_saved as prior
from . import bridge_saved_linear_core as core

ROOT, OUT, base, r, require = prior.ROOT, prior.OUT, prior.base, prior.r, prior.require
SCHEMA = 'g31.bridge.saved_linear_audit.v1'
MODULE = 'scripts.experiments.g31_ics_circulation.audit_bridge_saved_linear'
TEST = 'tests/test_g31_circulation_bridge_saved_linear.py'
LIMIT = 600.
PRIOR = OUT/'bridge_serialize_saved_audit_prepare_002'
PRIOR_PLAN_SHA = 'da470fb3e6f1366b32706e82a11f221bac567c5e9c3ac2ad9a878515e761bcf4'
PRIOR_EXTERNAL_SHA = '9eb1a0aa8163fe1221d136f1771c16a52cc76461e1a2a1d6b84a36b1fd625274'


def closure():
    paths = set(prior.closure())
    for path in (Path(__file__), Path(core.__file__), ROOT/TEST):
        paths.update(r.original.clone(base.source_paths, {**base.source_paths.__globals__, '__file__':str(path)})())
    return sorted(paths)


def prior_failure():
    require(base.sha(PRIOR/'plan.json') == PRIOR_PLAN_SHA and
        base.sha(PRIOR/'external_application_wall.json') == PRIOR_EXTERNAL_SHA, 'linear_prior_failure_identity')
    require(base.read(PRIOR/'bounded_execution.json')['process']['status'] == 'hard_timeout'
        and not (PRIOR/'report.json').exists(), 'linear_prior_not_expected_timeout')
    return {str(PRIOR/name):base.sha(PRIOR/name) for name in
        ('plan.json','external_application_wall.json','bounded_execution.json','stage_started.json')}


def contract():
    return {'prior_saved_failure': prior_failure(), 'source_proof':core.source_proof(),
        'fixed_seconds':600, 'new_rows':37270, 'old_complete_prefix_rows':27218,
        'progress_max_rows':core.Progress.LIMIT, 'progress_every_completed_rows':256,
        'substitutions':['shared_readonly_raw_and_input_decodes','remove_observer_second_copy_only',
            'ordered_JSON_comparison_without_two_full_encoded_strings','bounded_phase_and_row_progress'],
        'unchanged':['all_original_source_archive_binary_input_reference_pins','all_new_row_hash_prepass',
            'all_old27218_row_hashes','actual_args_and_kwargs_reconstruction','actor_result_deepcopy',
            'complete_policy_and_physical_audits','all28506jobs22trays','clock_cap_relay_and_FIFO_guards',
            'single_derived_output_redirection','original_owner_summary_canonicalization'],
        'source_only_claim':'No successful saved whole audit or speedup is assumed before this new bounded execution.'}


def namespace():
    ns = dict(vars(prior))
    for name, value in vars(prior).items():
        if isinstance(value, FunctionType) and value.__globals__ is vars(prior):
            ns[name] = r.original.clone(value, ns)
    ns.update(BOOT=BOOT, SCHEMA=SCHEMA, MODULE=MODULE, TEST=TEST, LIMIT=LIMIT, closure=closure,
        prepare=prepare, verify_plan=verify_plan, audit=audit)
    return ns


def verify_plan(output, expected):
    ns = namespace()
    original = r.original.clone(prior.verify_plan, ns)
    plan = original(output, expected)
    require(plan['linear_contract'] == contract(), 'linear_contract_changed')
    return plan


def prepare(output, pure):
    # Source-only preparation inherits immutable large-evidence pins from the
    # actual failed audit. All original artifact reads remain in verify_plan at
    # bounded execution, not silently represented as performed by preparation.
    require(not output.exists(), 'linear_preserve_output'); historical = prior_failure()
    plan = base.read(PRIOR/'plan.json')
    for name, digest in plan['source_before'].items():
        require(base.sha(name) == base.sha(PRIOR/'source'/Path(name).relative_to(ROOT)) == digest,
            'linear_prior_source_changed')
    receipt = base.read(pure); xml = pure.parent/'tests.xml'
    cases = ET.parse(xml).getroot().findall('.//testcase')
    require(receipt['status']=='passed' and receipt['source_changed']==[]
        and receipt['tests']==len(cases)>0 and receipt['XML_sha256']==base.sha(xml)
        and not any(x.tag in ('failure','error','skipped') for t in cases for x in t),'linear_pure_gate')
    for name, digest in receipt['source_before'].items():
        require(base.sha(name) == base.sha(pure.parent/'source'/Path(name).relative_to(ROOT)) == digest,
            'linear_pure_source_changed')
    pins = {str(p):base.sha(p) for p in closure()}; output.mkdir()
    for name, digest in pins.items():
        target=output/'source'/Path(name).relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(Path(name).read_bytes());require(base.sha(target)==digest,'linear_archive_copy')
    plan.update(schema=SCHEMA, source_before=pins, linear_contract=contract(),
        pure={'path':str(pure),'sha256':base.sha(pure),'XML_path':str(xml),'XML_sha256':base.sha(xml)},
        interpreter={'path':sys.executable,'sha256':base.sha(sys.executable)},
        preparation_scope={'large_evidence_hashes':'inherited_from_hash_pinned_failed_audit002_plan',
            'actual_large_evidence_reads_this_preparation':0,'full_recheck':'mandatory_inside_owned600_execution',
            'prior_receipts':historical})
    plan['scope'] += ' New private substitutions are enumerated in linear_contract; original guards and policy/physical semantics are retained.'
    prior.write_new(output/'plan.json',plan); digest=base.sha(output/'plan.json')
    prior.write_new(output/'preparation.json',{'status':'prepared_source_review_pending',
        'plan_sha256':digest,'source_count':len(pins),'pure_tests':len(cases),
        'native_calls':0,'predictions':0,'saved_audit_executed':False,
        'large_evidence_reads_this_preparation':0,'large_hashes_deferred_to_owned_execution':True,
        'command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--plan-sha256',digest]})


def audit(output, expected):
    prior.write_new(output/'worker_claim.json', {'plan_sha256':expected})
    start = time.perf_counter_ns(); progress = core.Progress(output)
    try:
        with progress.stage('entry_plan_source_artifact_and_runtime_checks'):
            plan = verify_plan(output, expected); entry = prior.check_runtime(plan)
        redirect = prior.DerivedOutput(prior.SOURCE, output)
        checker = core.bind(plan, redirect, progress)
        with progress.stage('full_saved_verifier'):
            result, statistics = checker(prior.SOURCE/'bridge')
        require(result['replay']['api_rows'] == 37270 and
            result['same_policy_old001_complete_prefix']['rows'] == 27218, 'linear_actual_denominators')
        result, mapping = redirect.map_result(result)
        result, inherited = prior.current_cost_metadata(result)
        with progress.stage('exit_plan_source_artifact_and_runtime_checks'):
            verify_plan(output, expected); exited = prior.check_runtime(plan)
        progress.emit('all_checks_completed', new_rows=37270, old_rows=27218)
    except BaseException:
        try:progress.close()
        except BaseException:pass
        raise
    else:progress.close()
    report = {'schema':SCHEMA,'status':'passed_complete_saved_audit','original_campaign_status':'timeout_preserved',
        'prior_separate_saved_audit_status':'timeout_preserved','plan_sha256':expected,
        'result':result,'derived_output_mapping':mapping,'inherited_verifier_metadata':inherited,
        'optimization_evidence':statistics,'progress_sha256':base.sha(progress.path),
        'loaded_sources_entry':entry,'loaded_sources_exit':exited,'native_calls':0,'predictions':0,
        'elapsed_before_report_ns':time.perf_counter_ns()-start,
        'limits':['No native or independently replayed native seal. Recorded seal remains saved evidence.',
            'Producer2400 and audit002600 remain failures; this is a separate bounded saved-only check.',
            'No alloffered business success, speedup or100ms claim.']}
    prior.write_new(output/'report.json',report)


def main():
    return r.original.clone(prior.main, namespace())()


if __name__ == '__main__':raise SystemExit(main())
