"""Binding/clock regressions only: no actual input, model or native evaluation."""
import ast,inspect,textwrap
from scripts.experiments.g31_ics_circulation import profile_scoped_public_inputs_six as p


def test_profiler_wraps_fresh_candidate_entry_not_prebuilt_scope():
    assert 'public_live_obligation_scoped_inputs' in p.worker.__code__.co_names
    assert 'public_live_obligation_lazy_communication_projection' not in p.worker.__code__.co_names
    assert 'PublicInputScope' not in p.worker.__code__.co_names
    tree=ast.parse(textwrap.dedent(inspect.getsource(p.old.worker)))
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Lambda) and ast.unparse(n.body)=="lazy.predict(context, public['action'])"]
    assert len(calls)==1


def test_every_original_worker_global_retained_except_report_schema():
    assert set(p.worker.__globals__)==set(p.old.worker.__globals__)
    assert {k for k in p.old.worker.__globals__ if p.worker.__globals__[k] is not p.old.worker.__globals__[k]}=={'SCHEMA','worker'}
    # exec stores the generated function under its own name in the same full
    # defining namespace; it never recursively calls worker.
    assert 'worker' not in p.worker.__code__.co_names


def test_owned_clock_starts_in_new_parent_and_launches_new_module():
    assert p.execute.__code__ is p.old.execute.__code__
    assert p.execute.__globals__['BOOT']==p.BOOT
    assert p.execute.__globals__['MODULE']==p.MODULE
    assert p.LIMIT==120.
    assert p.main.__globals__['execute'] is p.execute and p.main.__globals__['worker'] is p.worker


def test_one_profile_callback_exception_is_retained(tmp_path):
    calls=[]
    def fail():calls.append(1);raise ValueError('synthetic')
    value,detail=p.old.profiled_call(tmp_path/'failure.pstats',fail)
    assert calls==[1] and value is None and detail['status']=='unknown_callback_error'
    assert detail['callback_count']==1 and 'synthetic' in detail['error']
