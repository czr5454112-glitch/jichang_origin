"""Pure accounting/dispatch tests: no native, subprocess, real runner or ledger writes."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

MODULE = Path(__file__).with_name('terminal_flow_offline_budget.py')
loaded = importlib.util.spec_from_file_location('offline_budget_under_test', MODULE)
w = importlib.util.module_from_spec(loaded); loaded.loader.exec_module(w)


def limits():
    return dict(active_seconds_limit=172800, new_evidence_bytes_limit=40*1024**3,
                free_space_floor_bytes=30*1024**3)


def state(**updates):
    result = dict(active_seconds=12000., open_runners=[], unfinished_native_tasks=[], post_cutoff_uncovered_calendar_seconds=0.)
    result.update(updates); return result


def admit(**updates):
    args = dict(offline_seconds=8700, remaining_seconds=69900, holdback_seconds=37000,
                existing_bytes=6*1024**3, reserved_bytes=17*1024**3, free_bytes=120*1024**3)
    snapshot = updates.pop('snapshot', state()); args.update(updates)
    return w.preflight(snapshot, limits(), **args)


def test_conservative_holdback_is_added_without_native_subtraction():
    result = admit()
    assert result['total_reserved_active_seconds'] == 127600
    assert result['active_seconds_headroom'] == 45200


@pytest.mark.parametrize('changes', [dict(holdback_seconds=83000), dict(offline_seconds=float('nan')),
    dict(snapshot=state(open_runners=['native'])), dict(snapshot=state(unfinished_native_tasks=['unfinished'])),
    dict(existing_bytes=23*1024**3), dict(free_bytes=47*1024**3-1)])
def test_budget_boundaries_fail_closed(changes):
    with pytest.raises(ValueError): admit(**changes)


def test_exact_active_cap_and_exact_disk_floor_are_allowed():
    assert admit(holdback_seconds=82200, free_bytes=47*1024**3)['active_seconds_headroom'] == 0


def test_existing_own_runner_is_only_allowed_during_charged_phase():
    assert admit(snapshot=state(open_runners=['mine']), owned_runner='mine')
    with pytest.raises(ValueError): admit(snapshot=state(open_runners=['other']), owned_runner='mine')


def test_dynamic_gap_is_added_to_fixed_holdback_and_cannot_be_omitted():
    assert admit(snapshot=state(post_cutoff_uncovered_calendar_seconds=30.45))['total_reserved_active_seconds'] == 127630.45
    with pytest.raises(ValueError, match='active_time_budget'):
        admit(snapshot=state(post_cutoff_uncovered_calendar_seconds=45201))
    missing = state(); del missing['post_cutoff_uncovered_calendar_seconds']
    with pytest.raises(ValueError, match='dynamic_gap_snapshot_required'): admit(snapshot=missing)


def test_calendar_holdback_does_not_claim_measurement():
    record = dict(schema=w.SCHEMA+'.historical_holdback', startup_lower_bound_utc='2026-10-21T03:00:00+00:00',
        cutoff_utc='2026-10-21T13:00:00+00:00', reserve_seconds=36000, native_seconds_subtracted=0,
        ledger_rewritten=False, is_measured_active_time=False)
    assert w.historical_seconds(record) == 36000
    with pytest.raises(ValueError): w.historical_seconds(dict(record, reserve_seconds=35999))
    with pytest.raises(ValueError): w.historical_seconds(dict(record, native_seconds_subtracted=1000))


def test_ledger_snapshot_is_byte_preserving_and_charges_open_interval(tmp_path):
    path = tmp_path/'ledger.jsonl'
    rows = [dict(at='2026-10-21T03:00:00+00:00', event='runner_open', runner_id='x'),
            dict(at='2026-10-21T03:01:00+00:00', event='native_start', task_id='task')]
    raw = b''.join((json.dumps(row)+'\n').encode() for row in rows); path.write_bytes(raw)
    result = w.ledger_snapshot(path, datetime(2026,10,21,3,2,tzinfo=timezone.utc))
    assert result['active_seconds'] == 120 and result['unfinished_native_tasks'] == ['task']
    assert path.read_bytes() == raw
    path.write_bytes(raw[:-1])
    with pytest.raises(ValueError, match='incomplete_ledger'): w.ledger_snapshot(path, datetime.now(timezone.utc))


@pytest.mark.parametrize('cutoff,covered,gap', [(10,60,30),(50,30,20),(90,10,0),(100,0,0)])
def test_dynamic_calendar_subtracts_only_actual_post_cutoff_runner_intersections(tmp_path, cutoff, covered, gap):
    from datetime import timedelta
    start = datetime(2026,10,21,tzinfo=timezone.utc)
    rows = [dict(at=(start+timedelta(seconds=s)).isoformat(),event=e,runner_id=r)
            for s,e,r in [(0,'runner_open','a'),(20,'runner_close','a'),(30,'runner_open','b'),
                           (60,'runner_close','b'),(80,'runner_open','c')]]
    path=tmp_path/'ledger.jsonl'; raw=''.join(json.dumps(r)+'\n' for r in rows).encode(); path.write_bytes(raw)
    snap=w.ledger_snapshot(path,start+timedelta(seconds=100),coverage_cutoff=start+timedelta(seconds=cutoff))
    assert snap['active_seconds']==70
    assert snap['post_cutoff_runner_covered_seconds']==covered
    assert snap['post_cutoff_uncovered_calendar_seconds']==gap
    assert path.read_bytes()==raw


def test_all_idle_time_reserved_and_future_cutoff_or_bad_intervals_rejected(tmp_path):
    from datetime import timedelta
    start=datetime(2026,10,21,tzinfo=timezone.utc); path=tmp_path/'ledger.jsonl'; path.write_bytes(b'')
    assert w.ledger_snapshot(path,start+timedelta(seconds=100),coverage_cutoff=start)['post_cutoff_uncovered_calendar_seconds']==100
    with pytest.raises(ValueError,match='invalid_coverage_cutoff'):
        w.ledger_snapshot(path,start,coverage_cutoff=start+timedelta(seconds=1))
    for rows in ([dict(at=start.isoformat(),event='runner_open',runner_id='a'),
                  dict(at=start.isoformat(),event='runner_open',runner_id='b')],
                 [dict(at=(start+timedelta(seconds=20)).isoformat(),event='runner_open',runner_id='a'),
                  dict(at=start.isoformat(),event='runner_close',runner_id='a')]):
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        with pytest.raises(ValueError): w.ledger_snapshot(path,start+timedelta(seconds=100),coverage_cutoff=start)


def test_evidence_counts_ROOTDATA_and_does_not_double_count_nested_root(tmp_path):
    cycle, data = tmp_path/'cycle', tmp_path/'data'; cycle.mkdir(); data.mkdir()
    model = data/'model'; model.mkdir()
    (cycle/'a').write_bytes(b'123'); (model/'b').write_bytes(b'4567')
    assert w.evidence_bytes([cycle, data, model]) == 7


def closed(**changes):
    result = dict(closure_verified=True, direct_child_wait_completed=True,
        job_active_processes_zero_verified=True, cleanup_errors=[], status='exited', exitcode=0,
        termination_reason=None)
    result.update(changes); return result


def test_zero_leader_exit_with_killed_descendants_can_close_but_is_failure():
    report = closed(termination_reason='remaining_owned_descendants_after_direct_exit')
    assert w.closure_allows_close(report) and not w.child_succeeded(report)


@pytest.mark.parametrize('changes', [dict(closure_verified=False), dict(cleanup_errors=['query failed']),
    dict(job_active_processes_zero_verified=False), dict(direct_child_wait_completed=False)])
def test_unproven_tree_closure_never_allows_runner_close(changes):
    assert not w.closure_allows_close(closed(**changes))


def test_failure_and_timeout_still_close_verified_tree_without_success():
    for report in (closed(exitcode=1), closed(status='hard_timeout', termination_reason='original_job_timeout')):
        assert w.closure_allows_close(report) and not w.child_succeeded(report)


def test_no_native_admit_or_shell_dispatch_in_wrapper():
    import ast
    tree = ast.parse(MODULE.read_text(encoding='utf-8'))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'admit'
                   for node in ast.walk(tree))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and isinstance(n.func.value, ast.Name) and n.func.value.id == 'subprocess']
    assert len(calls) == 1 and calls[0].func.attr == 'run'
    assert any(k.arg == 'shell' and isinstance(k.value, ast.Constant) and k.value.value is False for k in calls[0].keywords)


def test_literal_argv_cannot_be_replaced_with_python_c_or_native(tmp_path, monkeypatch):
    python = tmp_path/'python.exe'; python.write_bytes(b'python')
    spec = dict(python=w.bind(python))
    task = dict(kind='forecast_holdout', argv=[str(python), '-c', 'print(1)'])
    with pytest.raises(ValueError, match='allowed_holdout'): w.validate_argv(task, spec)


def test_binding_detects_producer_mutation(tmp_path):
    path = tmp_path/'producer.py'; path.write_text('before')
    ref = w.bind(path); path.write_text('after')
    with pytest.raises(ValueError, match='binding_changed'): w.checked(ref)


def test_every_actual_entry_script_must_be_in_producer_roster():
    refs = [dict(path=str(path), sha256='not_consumed_in_roster_check') for path in list(w.HELPERS.values())+[w.FIGURES,w.FORECAST_SUMMARY]]
    w.validate_producer_roster(dict(producer_bindings=refs))
    missing = [ref for ref in refs if Path(ref['path']) != w.HELPERS['strong_baseline']]
    with pytest.raises(ValueError, match='actual_script_missing'):
        w.validate_producer_roster(dict(producer_bindings=missing))
    with pytest.raises(ValueError, match='duplicate_producer'):
        w.validate_producer_roster(dict(producer_bindings=refs+[refs[0]]))


def eleven_tasks():
    return ([dict(kind=kind, id=kind) for kind in ('full_train_time_scale','granularity','final_science','unified','strong_baseline')]
            +[dict(kind='forecast_holdout', id=f'holdout_{p}', parent_seed=p) for p in (2201,2202,2203,2204)]
            +[dict(kind=kind, id=kind) for kind in ('forecast_summary','figures')])


def test_all_four_parent_holdouts_are_required_and_cannot_be_duplicated():
    tasks = eleven_tasks(); w.validate_task_roster(tasks)
    with pytest.raises(ValueError, match='fixed_eleven_tasks'): w.validate_task_roster(tasks[:6]+tasks[7:])
    tasks[8]['parent_seed'] = 2201
    with pytest.raises(ValueError, match='all_four_DEV_holdouts'): w.validate_task_roster(tasks)


def test_full_train_timing_is_required_before_dev_scientific_audits():
    tasks = eleven_tasks()
    with pytest.raises(ValueError, match='fixed_eleven_tasks'):
        w.validate_task_roster(tasks[1:])
    with pytest.raises(ValueError, match='fixed_eleven_tasks'):
        w.validate_task_roster(tasks[1:2]+tasks[:1]+tasks[2:])


def test_holdout_argv_parent_binding_and_four_report_summary(tmp_path, monkeypatch):
    python, model, summary = tmp_path/'python.exe', tmp_path/'model.json', tmp_path/'summary.py'
    for path in (python,model,summary): path.write_text('bound bytes')
    monkeypatch.setattr(w,'CYCLE',tmp_path/'cycle'); monkeypatch.setattr(w,'ROOTDATA',tmp_path)
    monkeypatch.setattr(w,'FORECAST_SUMMARY',summary)
    spec = dict(python=w.bind(python), model=w.bind(model), tasks=[])
    for parent in (2201,2202,2203,2204):
        output = tmp_path/f'P{parent}'
        task = dict(kind='forecast_holdout', parent_seed=parent, output=str(output), hard_seconds=900,
                    estimated_evidence_bytes=64, argv=[str(python), '-B', '-m', w.HOLDOUT, '--run',
                    str(w.CYCLE/f'runs/TF_bridge_all_005_C00_P{parent}'),'--model',str(model),'--output',str(output)])
        assert w.validate_argv(task,spec)==output
        spec['tasks'].append(task)
    output = tmp_path/'pooled'
    task = dict(kind='forecast_summary', output=str(output), hard_seconds=120, estimated_evidence_bytes=64,
                argv=[str(python),str(summary),'--model',str(model),'--reports']
                     +[t['output'] for t in spec['tasks']]+['--output-dir',str(output)])
    assert w.validate_argv(task,spec)==output
    task['argv'][8] = spec['tasks'][0]['output']
    with pytest.raises(ValueError,match='all_four_holdouts'): w.validate_argv(task,spec)
    spec['tasks'][3]['argv'][5]=str(w.CYCLE/'runs/TF_bridge_all_005_C00_P2201')
    with pytest.raises(ValueError,match='fixed_DEV_C00'): w.validate_argv(spec['tasks'][3],spec)


def test_figures_argv_requires_exact_prior_final_science_marker(tmp_path, monkeypatch):
    python, figures = tmp_path/'python.exe', tmp_path/'figures.py'
    python.write_bytes(b'python'); figures.write_bytes(b'figures')
    monkeypatch.setattr(w, 'ROOTDATA', tmp_path); monkeypatch.setattr(w, 'FIGURES', figures)
    science = tmp_path/'science'; output = tmp_path/'figures'
    spec = dict(python=w.bind(python), tasks=[dict(kind='final_science', output=str(science))])
    task = dict(kind='figures', argv=[str(python), str(figures), '--complete', str(science/'COMPLETE.json'),
                '--output-dir', str(output)], output=str(output), hard_seconds=60, estimated_evidence_bytes=100)
    assert w.validate_argv(task, spec) == output
    task['argv'][3] = str(tmp_path/'unrelated/COMPLETE.json')
    with pytest.raises(ValueError, match='figures_bound_science'): w.validate_argv(task, spec)


@pytest.mark.parametrize('report,raises,expect_close', [
    (closed(exitcode=1), False, True), (closed(closure_verified=False), False, False),
    (None, True, False),
    (closed(termination_reason='remaining_owned_descendants_after_direct_exit'), False, True)])
def test_dispatch_failure_stops_serial_pipeline_and_preserves_accounting(tmp_path, monkeypatch, report, raises, expect_close):
    cycle, data = tmp_path/'cycle', tmp_path/'data'; cycle.mkdir(); data.mkdir()
    monkeypatch.setattr(w, 'CYCLE', cycle); monkeypatch.setattr(w, 'ROOTDATA', data)
    (cycle/'campaign_budget.json').write_text(json.dumps(limits()))
    historical = data/'history.json'; historical.write_text('{"cutoff_utc":"2026-10-21T03:00:00+00:00"}')
    spec_path = data/'spec.json'
    task = dict(id='first', kind='granularity', argv=[], hard_seconds=60,
                estimated_evidence_bytes=100, output=str(data/'science'), required_outputs=['COMPLETE.json'])
    spec = dict(schema=w.SCHEMA+'.spec', ready=True, wrapper=w.bind(MODULE), budget=w.bind(cycle/'campaign_budget.json'),
        historical_holdback=w.bind(historical), tasks=[task, dict(task, id='never_started')],
        wrapper_overhead_seconds=120, wrapper_estimated_evidence_bytes=100, python=dict(path=sys.executable),
        resource_helper={}, resource_policy=dict(cancel_below=dict(disk_free_bytes=30*1024**3),
        closure_wait_seconds=15, sample_seconds=1))
    spec_path.write_text(json.dumps(spec))
    monkeypatch.setattr(w, 'validate_spec', lambda spec: (limits(), {}))
    monkeypatch.setattr(w, 'checked_preflight', lambda *a, **k: {})
    monkeypatch.setattr(w, 'snapshot', lambda **kwargs: dict(native_starts=10))
    calls, ledger = [], []
    def run(*a, **kwargs):
        calls.append(kwargs)
        if raises: raise RuntimeError('unknown closure')
        w.save(kwargs['directory']/'process_closed.json', report)
        return report
    monkeypatch.setattr(w, 'load_helper', lambda *a: SimpleNamespace(validate_policy=lambda p: None, run=run))
    # Real import is read-only; every ledger mutator is replaced before execution.
    sys.path.insert(0, str(MODULE.parents[1]))
    from scripts.experiments.g31_ics_circulation import foundation_airport_joint_budget as budget
    monkeypatch.setattr(budget, 'append', lambda _cycle, event, **kwargs: ledger.append(event))
    with pytest.raises((ValueError, RuntimeError)):
        w.execute(spec_path, data/'wrapper_attempt')
    assert len(calls) == 1
    assert ledger == (['runner_open', 'runner_close'] if expect_close else ['runner_open'])
    assert (data/'wrapper_attempt/PARTIAL.json').is_file()
    assert not (data/'wrapper_attempt/EXECUTED.json').exists()


@pytest.mark.parametrize('tail_timeout', [False, True])
def test_success_waits_for_all_sequential_children_and_exit_binding_checks_before_close(tmp_path, monkeypatch, tail_timeout):
    cycle, data = tmp_path/'cycle', tmp_path/'data'; cycle.mkdir(); data.mkdir()
    monkeypatch.setattr(w, 'CYCLE', cycle); monkeypatch.setattr(w, 'ROOTDATA', data)
    budget_file = cycle/'campaign_budget.json'; budget_file.write_text(json.dumps(limits()))
    reference = data/'bound.json'; reference.write_text('{"cutoff_utc":"2026-10-21T03:00:00+00:00"}'); ref = w.bind(reference)
    tasks = [dict(id=name, hard_seconds=60, estimated_evidence_bytes=100,
                  output=str(data/name), required_outputs=['COMPLETE.json']) for name in ('one', 'two')]
    spec = dict(schema=w.SCHEMA+'.spec', ready=True, wrapper=w.bind(MODULE), budget=w.bind(budget_file),
        historical_holdback=ref, tasks=tasks, wrapper_overhead_seconds=120, wrapper_estimated_evidence_bytes=100,
        python=dict(path=sys.executable), resource_helper=ref, model=ref, source_manifest=ref,
        producer_bindings=[ref], remaining_work_reserved_seconds=0, remaining_work_reserved_bytes=0,
        disk_guard_bytes=512*1024**2, resource_policy=dict(cancel_below=dict(disk_free_bytes=30*1024**3),
        closure_wait_seconds=15, sample_seconds=1))
    spec_path = data/'spec.json'; spec_path.write_text(json.dumps(spec))
    order, active = [], []
    clock = [10.]
    monkeypatch.setattr(w.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(w, 'validate_spec', lambda spec: (limits(), {}))
    def verify_sources(spec):
        order.append('exit_source_check')
        if tail_timeout: clock[0] += 1000
    monkeypatch.setattr(w, 'validate_sources', verify_sources)
    monkeypatch.setattr(w, 'verify_exit_bindings', lambda *a: None)
    monkeypatch.setattr(w, 'checked_preflight', lambda *a, **k: {})
    monkeypatch.setattr(w, 'preflight', lambda *a, **k: {})
    monkeypatch.setattr(w, 'snapshot', lambda **kwargs: dict(native_starts=10, active_seconds=0,
                         open_runners=list(active), unfinished_native_tasks=[], post_cutoff_uncovered_calendar_seconds=0.))
    monkeypatch.setattr(w, 'historical_seconds', lambda record: 0)
    monkeypatch.setattr(w, 'evidence_bytes', lambda roots: 0)
    def run(command, **kwargs):
        kwargs['before_release']()
        index = len([item for item in order if item.startswith('child_')])
        task = tasks[index]; output = Path(task['output']); output.mkdir()
        w.save(output/'COMPLETE.json', dict(status='complete'))
        w.save(kwargs['directory']/'process_closed.json', closed())
        order.append('child_'+task['id']); return closed()
    monkeypatch.setattr(w, 'load_helper', lambda *a: SimpleNamespace(validate_policy=lambda p: None, run=run))
    from scripts.experiments.g31_ics_circulation import foundation_airport_joint_budget as budget
    def append(_cycle, event, **kwargs):
        order.append(event)
        if event == 'runner_open': active.append(kwargs['runner_id'])
        else:
            assert (data/'attempt/EXECUTED.json').is_file() is not tail_timeout
            assert (data/'attempt/CLOSURE_READY.json').is_file()
            active.clear()
    monkeypatch.setattr(budget, 'append', append)
    if tail_timeout:
        with pytest.raises(ValueError, match='offline_total_allowance_exceeded'):
            w.execute(spec_path, data/'attempt')
        assert (data/'attempt/PARTIAL.json').is_file()
    else:
        w.execute(spec_path, data/'attempt')
    assert order == ['runner_open', 'child_one', 'child_two', 'exit_source_check', 'runner_close']
