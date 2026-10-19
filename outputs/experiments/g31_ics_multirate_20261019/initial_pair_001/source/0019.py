"""One new600 saved-only candidate; original comparisons and same-text actor copy.

No native or prediction. Prior producer/audit failures remain immutable. All
original all-row/source/physical checks and derived-output redirection remain.
"""
from __future__ import annotations
import time
BOOT=time.monotonic()
from pathlib import Path
import sys
from types import FunctionType
from . import audit_bridge_saved_linear_v3 as previous
from . import bridge_saved_text_actor as core

ROOT,OUT,base,r,prior,require=previous.ROOT,previous.OUT,previous.base,previous.r,previous.prior,previous.require
SCHEMA='g31.bridge.saved_text_actor_audit.v1'
MODULE='scripts.experiments.g31_ics_circulation.audit_bridge_saved_text_actor'
TEST='tests/test_g31_circulation_bridge_saved_text_actor.py'
LIMIT=600.
FAILED=OUT/'bridge_saved_linear_v3_prepare_001'
FAILED_PLAN='4bbf6f364ac097db7fbf2bd1ff35f9ea74500566f367933e552bf6da6f0bd87e'
FAILED_EXTERNAL='277e2c8371e1016600629c0f68536c9f650e5332a48e32f1d0493cae70545a7a'
EVIDENCE={
    'bridge_saved_kernel_cost_readback_001/report.json':'0df9dba718be1f555142711d168fc45a42cdb3717e4cee3100a8f76ce47b8c66',
    'bridge_actor_reparse_readback_001/report.json':'9bca7b1da48ca8c2520df312e5e6589f560cc1ec38cd8e881de017350d83237f',
    'bridge_actor_reparse_prepare_001/result.json':'e23bc20c9e66fd7e6933149c3c8a214043c2bbe41dfa83e3f81f9d0d494e7b50',
    'bridge_actor_reparse_prepare_001/external_application_wall.json':'9c02fa3b5b1216365c714542604df687c3ebd542b99a4f5d9a7186dc4da7257f'}


def latest_failure():
    require(base.sha(FAILED/'plan.json')==FAILED_PLAN and base.sha(FAILED/'external_application_wall.json')==FAILED_EXTERNAL,'text_actor_prior_identity')
    receipt=base.read(FAILED/'bounded_execution.json')
    require(receipt['process']['status']=='hard_timeout' and not (FAILED/'report.json').exists(),'text_actor_prior_status')
    plan=base.read(FAILED/'plan.json')
    for path,digest in plan['source_before'].items():
        require(base.sha(path)==base.sha(FAILED/'source'/Path(path).relative_to(ROOT))==digest,'text_actor_prior_source_changed')
    return {str(FAILED/name):base.sha(FAILED/name) for name in ('plan.json','bounded_execution.json','external_application_wall.json','progress.jsonl')}


def closure():
    paths=set(previous.closure())
    for path in (Path(__file__),Path(core.__file__),ROOT/TEST):
        paths.update(r.original.clone(base.source_paths,{**base.source_paths.__globals__,'__file__':str(path)})())
    return sorted(paths)


def contract():
    inherited=previous.contract()
    for path,digest in EVIDENCE.items():require(base.sha(OUT/path)==digest,'text_actor_diagnostic_changed:'+path)
    return {'fixed_seconds':600,'new_rows':37270,'old_complete_prefix_rows':27218,
        'offered_jobs':28506,'trays':22,'source_proof':core.source_proof(),
        'prior_linear_contract_historical_only':inherited,'latest_failed_audit':latest_failure(),
        'progress_v2':core.progress_contract(),'cost_evidence':dict(EVIDENCE),
        'substitutions':['Original C semantic_api comparisons restored in both full-prefix and bootstrap comparisons.',
            'First parsed row stays with observer; actor receives result from second default parse of identical already-read text.',
            'One synchronous row text sidecar, cleared on all returns/errors; no cross-row cache or new data.'],
        'unchanged':['all37270 compressed hashes and actual API payload/order/clock guards',
            'all27218 old row hashes and ordered comparisons','all source/archive026/binary/input/reference pins',
            'all policy/FIFO/Storage/ACK/cap/clock guards','all28506 jobs/22tray physical audit',
            'original default JSON decoder and exception semantics','observer result/actor identity binding',
            'shared readonly raw/input only','single all_job_states output/hash redirect','1024progress/256row cadence'],
        'cost_plan':{'compare_fixed8_median_ms':{'recursive':342.99155,'original_C':203.5708},
            'actor_fixed16_median_ms':{'deepcopy':424.06245,'same_text_second_parse':137.0207},
            'local_differences_ms':{'compare8':139.42075,'copy16':287.04175},
            'interpretation':'Two measured local costs justify one new bounded candidate. Their percentages cannot be added; historical row-size mix, policy work, I/O, hashing and final export are unmeasured components. No600 completion prediction.',
            'all_costs':'First/second decode, sidecar lifetime, validation, comparison, progress, full policy/physical verification, every hash and output export remain inside the same new600s tree; required outer Python clock includes startup/final parent export.'},
        'failure':'Any failed guard, decoder/error/alias/source drift or timeout remains unknown; no retry, budget extension or old outcome rewrite.',
        'source_only_claim':'Not executed. No complete saved-audit, business-protection, native speed or100ms claim.'}


def namespace():
    # Mutate only this newly built private globals dictionary. It already
    # includes every original inherited dependency (including Path).
    ns=previous.namespace()
    ns.update(BOOT=BOOT,SCHEMA=SCHEMA,MODULE=MODULE,TEST=TEST,LIMIT=LIMIT,core=core,
        closure=closure,contract=contract,namespace=namespace,verify_plan=verify_plan,
        prepare=prepare,audit=audit,pure=pure)
    return ns


def verify_plan(output,expected):
    return r.original.clone(previous.old.verify_plan,namespace())(output,expected)


def prepare(output,pure_receipt):
    return r.original.clone(previous.old.prepare,namespace())(output,pure_receipt)


def audit(output,expected):
    # Keep v3's first-fatal progress handling and unchanged inner checker.
    return r.original.clone(previous.audit,{**previous.audit.__globals__,
        'namespace':namespace,'core':core})(output,expected)


def pure(output,worker=False):
    if worker:
        require(sys.stdin.readline()=='bridge_saved_audit_pure\n','text_actor_pure_admission')
        import pytest
        return pytest.main(['-q',TEST,'--basetemp='+str(ROOT/'outputs'/('tmp_'+output.name)),
            '--junitxml='+str(output/'tests.xml')])
    return r.original.clone(prior.pure,namespace())(output,False)


def main():
    return r.original.clone(prior.main,namespace())()


if __name__=='__main__':raise SystemExit(main())
