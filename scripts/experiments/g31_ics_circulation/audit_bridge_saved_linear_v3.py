"""New saved-only600 audit: bounded bootstrap progress and first-fatal evidence.

Frozen linear001 and both earlier timeout attempts remain failed. No native or
predictor execution; all original policy/physical checks remain unchanged.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
from pathlib import Path
import sys
from types import FunctionType, SimpleNamespace
from . import audit_bridge_saved_linear as old
from . import bridge_saved_linear_progress_v2 as core

ROOT, OUT, base, r, prior, require = old.ROOT, old.OUT, old.base, old.r, old.prior, old.require
SCHEMA = 'g31.bridge.saved_linear_audit.v3'
MODULE = 'scripts.experiments.g31_ics_circulation.audit_bridge_saved_linear_v3'
TEST = 'tests/test_g31_circulation_bridge_saved_linear_v3.py'
LIMIT = 600.
FAILED = OUT/'bridge_saved_linear_prepare_001'
FAILED_PLAN_SHA = '5048eb9e3365b5a29e69c82f685e821a36cc2417d4d9c9f8ea1876e56ad40032'
FAILED_EXTERNAL_SHA = '8472f61d1d7c3ef19935d58dbbf8a0cb3c905b4620204e1d1df5e1c044685deb'
FROZEN_PREP = OUT/'bridge_saved_linear_v2_prepare_001'
FROZEN_PLAN_SHA = '1292b0466627237c981dc01def95ad14783411b4e96497d1e9c6157b25b71acc'
PURE_FAILURE = OUT/'bridge_saved_linear_v2_pure_001/receipt.json'
PURE_FAILURE_SHA = 'e3bf1148e3010426b4d84f10819e3526db6f1bb49356c7c9a80369956f230656'


def frozen_preparation():
    require(base.sha(FROZEN_PREP/'plan.json') == FROZEN_PLAN_SHA, 'linear_v3_frozen_prepare_identity')
    require(not (FROZEN_PREP/'execution_claim.json').exists(), 'linear_v3_prior_prepare_must_stay_unexecuted')
    value = base.read(FROZEN_PREP/'plan.json')
    for name, digest in value['source_before'].items():
        require(base.sha(name) == base.sha(FROZEN_PREP/'source'/Path(name).relative_to(ROOT)) == digest,
            'linear_v3_prior_prepare_source_changed')
    require(base.sha(PURE_FAILURE) == PURE_FAILURE_SHA, 'linear_v3_pure_failure_changed')
    return value


def previous_failure():
    require(base.sha(FAILED/'plan.json') == FAILED_PLAN_SHA and
        base.sha(FAILED/'external_application_wall.json') == FAILED_EXTERNAL_SHA,
        'linear_v2_previous_failure_identity')
    bounded = base.read(FAILED/'bounded_execution.json')
    require(bounded['process']['status'] == 'exited' and bounded['process']['exitcode'] == 1
        and not (FAILED/'report.json').exists(), 'linear_v2_previous_failed_status')
    for name, digest in base.read(FAILED/'plan.json')['source_before'].items():
        require(base.sha(name) == base.sha(FAILED/'source'/Path(name).relative_to(ROOT)) == digest,
            'linear_v2_frozen87_changed')
    return {str(FAILED/name): base.sha(FAILED/name) for name in
        ('plan.json', 'external_application_wall.json', 'bounded_execution.json', 'progress.jsonl', 'failure.json')}


def closure():
    paths = set(old.closure())
    paths.update(Path(name) for name in frozen_preparation()['source_before'])
    for path in (Path(__file__), Path(core.__file__), ROOT/TEST):
        paths.update(r.original.clone(base.source_paths, {**base.source_paths.__globals__, '__file__':str(path)})())
    return sorted(paths)


def contract():
    result = old.contract()
    result.update(progress_v2=core.progress_contract(), frozen_linear001_failure=previous_failure())
    frozen_preparation()
    result.update(unexecuted_prior_prepare={'path':str(FROZEN_PREP/'plan.json'),'sha256':FROZEN_PLAN_SHA},
        preserved_pure_failure={'path':str(PURE_FAILURE),'sha256':PURE_FAILURE_SHA,
            'status':'owned60_packaging_and_synthetic_path_resolution_timeout',
            'scope':'Not a completed test gate, saved replay or native result. No XML was produced; tests are not counted as passing.'},
        revision='Failure sidecar now labels exact terminal/first-progress exception object identities; no inferred primary-error flag.')
    return result


def namespace():
    ns = old.namespace()
    ns.update(vars(old))
    for name, value in vars(old).items():
        if isinstance(value, FunctionType) and value.__globals__ is vars(old):
            ns[name] = r.original.clone(value, ns)
    ns.update(BOOT=BOOT, SCHEMA=SCHEMA, MODULE=MODULE, TEST=TEST, LIMIT=LIMIT, core=core,
        closure=closure, contract=contract, audit=audit, verify_plan=verify_plan, pure=pure,
        namespace=namespace)
    return ns


def verify_plan(output, expected):
    return r.original.clone(old.verify_plan, {**namespace(), 'namespace':namespace})(output, expected)


def prepare(output, pure):
    return r.original.clone(old.prepare, namespace())(output, pure)


def audit(output, expected):
    progress_objects = []
    def progress_factory(*args, **kwargs):
        value = core.Progress(*args, **kwargs)
        progress_objects.append(value)
        return value
    # Preserve the audit's verification flow; capture its one Progress object
    # only to retain a bounded first-fatal record if the journal cannot write.
    facade = SimpleNamespace(**{**vars(core), 'Progress':progress_factory})
    function = r.original.clone(old.audit, {**namespace(), 'core':facade})
    try:
        return function(output, expected)
    except BaseException as error:
        if progress_objects and progress_objects[0].first_failure is not None:
            progress = progress_objects[0]
            value = {'schema':'g31.bridge.linear_progress.first_failure.v1',
                'status':'unknown_instrumentation_failure', 'first_progress_failure':progress.first_failure,
                'terminal_exception_type':type(error).__name__, 'terminal_exception':str(error),
                'terminal_is_first_progress_error':error is progress.first_error,
                'terminal_is_original_error_whose_failure_logging_failed':error is progress.reporting_original_error,
                'journal_rows_committed':progress.count, 'journal_limit':progress.LIMIT,
                'complete_saved_audit':False}
            try:prior.write_new(Path(output)/'instrumentation_failure.json', value)
            except BaseException as export_error:
                # Never mask the first fatal with a diagnostic-export failure.
                print('instrumentation_failure_export_failed:'+type(export_error).__name__, file=sys.stderr)
        raise


def pure(output, worker=False):
    if worker:
        require(sys.stdin.readline() == 'bridge_saved_audit_pure\n', 'audit_pure_admission')
        import pytest
        return pytest.main(['-q', old.TEST, TEST, '--basetemp='+str(ROOT/'outputs'/('tmp_'+output.name)),
            '--junitxml='+str(output/'tests.xml')])
    return r.original.clone(prior.pure, namespace())(output, False)


def main():
    ns = namespace()
    ns.update(prepare=prepare, namespace=namespace)
    return r.original.clone(prior.main, ns)()


if __name__ == '__main__':raise SystemExit(main())
