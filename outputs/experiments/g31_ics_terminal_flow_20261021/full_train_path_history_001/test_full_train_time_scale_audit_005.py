"""Small synthetic guards only; never consumes real TRAIN or DEV logs."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('full_train_time_scale_under_test', HERE/'full_train_time_scale_audit_005.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


@pytest.fixture(scope='module')
def h():
    root = HERE.parents[2]/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/sources/terminal_flow_runtime_005'
    helpers, _ = a.load_helpers(root)
    return helpers


def gz(path, value=None, text=None):
    with gzip.open(path, 'wt', encoding='utf8') as f:
        f.write(json.dumps(value) if text is None else text)
    return path


def test_streams_nested_array_and_metadata_across_number_chunks(tmp_path):
    path = gz(tmp_path/'synthetic.json.gz', dict(rows=[12345, {'a': [1, 2]}], empty=[], end=3))
    items = []
    meta = a.stream_object(path, {'rows': items.append}, chunk_chars=1)
    assert items == [12345, {'a': [1, 2]}]
    assert meta == {'rows': {'streamed_items': 2}, 'empty': {'streamed_items': 0}, 'end': 3}


@pytest.mark.parametrize('text', ['{"x":[1,]}', '{"x":[1]', '{"x":1}garbage',
    '{"x":1,"x":2}', '{"x":[{"z":1,"z":2}]}', '{"x":[NaN]}', '{"x":[1e999]}'])
def test_stream_rejects_malformed_or_ambiguous_tail(tmp_path, text):
    with pytest.raises(ValueError):
        a.stream_object(gz(tmp_path/'synthetic.json.gz', text=text), {}, chunk_chars=2)


def test_stream_item_bound_and_truncated_gzip(tmp_path):
    path = gz(tmp_path/'synthetic.json.gz', {'rows': ['x'*80]})
    with pytest.raises(ValueError, match='oversized'):
        a.stream_object(path, {}, chunk_chars=8, max_item_chars=20)
    path.write_bytes(path.read_bytes()[:-8])
    with pytest.raises((OSError, EOFError)):
        a.stream_object(path, {})


def test_actual_receipts_mandatory_not_input_substitution():
    jobs = {'bag': {'arrival': 10, 'origin': 1}}
    seen, labels = set(), []
    with pytest.raises(ValueError, match='complete_actual_arrival'):
        a.validate_actual_arrivals(jobs, seen, 20)
    event = dict(event='BAG_ARRIVAL', business_bag_id='bag', time=10, node=1)
    a.actual_arrival(event, jobs, seen, labels, 20)
    a.validate_actual_arrivals(jobs, seen, 20)
    assert labels == [dict(business_bag_id='bag', origin=1, arrival=10)]
    with pytest.raises(ValueError, match='unique_known'):
        a.actual_arrival(event, jobs, seen, labels, 20)
    with pytest.raises(ValueError, match='identity_time_node'):
        a.actual_arrival(dict(event, time=11), jobs, set(), [], 20)


def call(rid='r'):
    return dict(at=10., request=dict(request_id=rid, owner_id='A', tray_id='t', source=1,
        destination=2, issued_at=10.), reply=dict(status='accepted'))


def test_failed_live_censored_and_missing_native_are_distinct():
    row = a.lifecycle(call(), dict(request_id='r', status='failed', received_at=-1), None, cutoff=100)
    assert row['outcome'] == 'failed' and row['unreceived_elapsed_lower_bound_seconds'] is None
    row = a.lifecycle(call(), dict(request_id='r', status='in_transit', received_at=-1), 20, cutoff=100)
    assert row['outcome'] == 'right_censored' and row['unreceived_elapsed_lower_bound_seconds'] == 90
    assert a.lifecycle(call(), None, None, cutoff=100)['outcome'] == 'unknown_native_outcome'
    assert a.lifecycle(call(), dict(request_id='r', status='unfamiliar'), None, cutoff=100)['outcome'] == 'unknown_native_outcome'
    row = a.lifecycle(call(), dict(request_id='r', status='undelivered', received_at=-1), None, cutoff=100)
    assert row['outcome'] == 'right_censored' and row['unreceived_elapsed_lower_bound_seconds'] == 90


def test_lifecycle_identity_and_clock_guards():
    with pytest.raises(ValueError, match='native_payload_identity'):
        a.lifecycle(call(), dict(request_id='r', status='received', received_at=30, tray_id='other'), 20, cutoff=100)
    with pytest.raises(ValueError, match='receipt_clock'):
        a.lifecycle(call(), dict(request_id='r', status='received', received_at=15), 20, cutoff=100)
    with pytest.raises(ValueError, match='received_status_time_consistency'):
        a.lifecycle(call(), dict(request_id='r', status='failed', received_at=30), 20, cutoff=100)


@pytest.mark.parametrize('native', [dict(request_id='r', status='received', received_at=-1),
    dict(request_id='r', status='received'), dict(request_id='r', status='pending', received_at=30)])
def test_inconsistent_received_status_timestamp_fails_closed(native):
    with pytest.raises(ValueError, match='received_status_time_consistency'):
        a.lifecycle(call(), native, None, cutoff=100)


def test_matched_distribution_has_own_denominator(h):
    selected = [dict(outcome='received', estimated_decision_to_arrival_seconds=20,
        actual_decision_to_received_seconds=40), dict(outcome='failed', estimated_decision_to_arrival_seconds=100),
        dict(outcome='right_censored', estimated_decision_to_arrival_seconds=200)]
    report = a.summarize_transfers([], selected, h['transport'].distribution)
    assert report['selected_proposals']['denominator'] == 3
    matched = report['matched_received_selected_proposals']
    assert matched['denominator'] == 1
    assert matched['timing_seconds']['estimated_decision_to_arrival_seconds']['p95'] == 20
    assert matched['timing_seconds']['actual_decision_to_received_seconds']['p95'] == 40


def test_sample_gaps_never_become_zero_or_bridge_episodes():
    rows = [dict(at=0, stock=2, waiting=0), dict(at=60, stock=0, waiting=2),
        dict(at=180, stock=0, waiting=1), dict(at=240, stock=None, waiting=1),
        dict(at=300, stock=1, waiting=0)]
    result = a.sample_bounds(rows, start=0, end=300, period=60)
    assert result['absent_tick_count'] == result['unknown_sample_count'] == 1
    assert len(result['shortage_episodes']) == 2
    assert result['shortage_episodes'][1]['left_censored'] is True
    assert all(r['right_censored'] for r in result['shortage_episodes'])
    assert len(result['sampled_stock_depletion_intervals']) == 1
    assert result['sampled_stock_depletion_intervals'][0]['elapsed_from_first_positive_upper_bound'] == 60


def test_first_sample_shortage_does_not_claim_no_earlier_missing_episode():
    result = a.sample_bounds([dict(at=60, stock=0, waiting=2)], start=0, end=120, period=60)
    assert result['earlier_shortage_unobserved_possible'] is True
    assert result['shortage_episodes'][0]['onset_lower_bound'] is None
    with pytest.raises(ValueError, match='duplicate_station'):
        a.sample_bounds([dict(at=0, stock=1, waiting=0)]*2, start=0, end=120, period=60)


def test_zero_bins_and_horizon_endpoint(h):
    arrivals = [dict(origin=1, arrival=t) for t in (0, 59, 60, 120)]
    bins = a.actual_bins(arrivals, [1, 2], 0, 120)
    result = a.describe_bins(bins, h['transport'].distribution)
    assert result['60']['1']['total_arrivals'] == 3
    assert result['60']['2']['count'] == 2 and result['60']['2']['zero_fraction'] == 1
    frozen = h['transport'].arrival_count_distributions(arrivals, [1, 2], start=0, end=120)
    assert result['60']['1']['p95'] == frozen['60']['1']['p95']


def timing(count=2):
    item = dict(count=count, total_seconds=.02, p50_seconds=.01, p95_seconds=.01, maximum_seconds=.01)
    return dict(item, stages={'feature': dict(item)}, stage_scope='submission/native/export excluded',
        complete_request_100ms_certified=False)


def test_pooled_callback_quantiles_not_averaged():
    result = a.pooled_timing([timing(), timing(3)])
    assert result['count'] == 5 and result['total_seconds'] == .04
    assert result['p50_seconds'] is result['p95_seconds'] is result['submission_wall_seconds'] is None


def test_hash_changed_input_fails_before_complete(tmp_path):
    path = tmp_path/'synthetic.txt'
    path.write_text('first')
    ref = a.bind(path)
    path.write_text('second')
    with pytest.raises(ValueError, match='changed_bound_bytes'):
        a.verify([ref])


def synthetic_run(tmp_path, h):
    """One selected received request plus failed/unknown priority requests."""
    at, end = a.START, a.END
    action = dict(kind='transfer', source=2, destination=1, tray_id='t',
        source_category='loader_optional', static_travel_time=100., nominal_arrival_time=at+102)
    req = dict(call()['request'], issued_at=at, source=2, destination=1)
    native = [dict(request_id='r', status='received', departed_at=at+2, received_at=at+200),
              dict(request_id='failed', status='failed', received_at=-1)]
    observations = [dict(now=t, owner_id='A', static_role_contract=dict(loader_nodes=[1])) for t in (at, end)]
    obs_records = [dict(digest=h['digest'].digest(o), observation=o) for o in observations]
    flow = dict(plan_id='p', information_asof=at, owner_scope='A', solve_seconds=.001,
        dispatch_profile=[dict(tray_id='t', source=2, destination=1, submit_at=at)])
    order = dict(order_id='o', plan_id='p', owner_scope='A', physical_tray_id='t', source_terminal=2,
        destination_terminal=1, proposed_at=at)
    decisions = [dict(decision_id='d', decision_time=at, owner_id='A',
        public_observation_ref=obs_records[0]['digest'], legal_catalog_ref='menu', requested_action=action,
        catalog=dict(candidates=[action]), selection=dict(flow_plan=flow, empty_transport_order=order),
        flow_verification=dict(exact_projection=dict(destination_without_move=dict(first_shortage_offset=300.)))),
        dict(decision_id='endpoint', decision_time=end, owner_id='A', public_observation_ref=obs_records[1]['digest'])]
    edge = dict(event='EDGE_ENTER', time=at+2, transport_leg_id='r:empty_return:0')
    received = dict(event='EMPTY_RECEIVED', time=at+200, transport_leg_id='r:empty_return:0')
    trajectory_row = {k: decisions[0][k] for k in ('decision_id', 'decision_time', 'owner_id',
        'public_observation_ref', 'legal_catalog_ref', 'requested_action')}
    trajectory_row.update(actual_submission=req, request_id='r', first_edge_event=edge, received_event=received)
    parent = dict(parent_seed=2101, split='train', offered_count=2, parent_group='synthetic:2101',
        common_historical_template_sha256='synthetic')
    plan = dict(input=dict(path=str(tmp_path/'input.json')), task_id='synthetic', parent=parent,
        method='TF-B1-300', binary=dict(sha256='synthetic'))
    manifest = dict(trajectory_id='synthetic', split='train', environment_seed=2101, physical_start=at,
        physical_end=end, execution_source_id=a.SOURCE_SHA, native_domain_id='synthetic', episode_parent_group=parent['parent_group'])
    (tmp_path/'input.json').write_text(json.dumps(dict(jobs=[dict(business_bag_id=str(i), arrival=t, origin=1)
        for i, t in enumerate((0, at))])))
    gz(tmp_path/'terminal_evidence.json.gz', dict(physical_clock=end, advance=dict(horizon_complete=True, status='reached'),
        receipts=[dict(event='BAG_ARRIVAL', business_bag_id=str(i), time=t, node=1) for i, t in enumerate((0, at))]+[edge, received],
        transfers=native, jobs=[dict(discarded=True)]))
    gz(tmp_path/'trajectory.json.gz', dict(manifest=manifest, rows=[trajectory_row], scientific_status='closed_finite_horizon',
        physical_clock=end, process_status='completed', logs_complete=True))
    gz(tmp_path/'calls.json.gz', [dict(at=at, request=req, reply=dict(status='accepted'), kind='transfer'),
        dict(call('failed'), kind='transfer', at=at+60, request=dict(call('failed')['request'], issued_at=at+60)),
        dict(call('missing'), kind='transfer', at=at+120, request=dict(call('missing')['request'], issued_at=at+120))])
    gz(tmp_path/'observations.json.gz', obs_records)
    gz(tmp_path/'decisions.json.gz', decisions)
    helpers = dict(h, projection=SimpleNamespace(prepare_inventory_projection=lambda obs: SimpleNamespace(nodes={
        n: dict(local=True, stock=1, inventory_known=True, waiting=0, waiting_known=True) for n in (1, 2)})))
    return dict(directory=tmp_path, plan=plan, worker=dict(policy_timing=timing())), helpers


def test_small_synthetic_full_pipeline_uses_receipts_and_separate_denominators(tmp_path, h):
    row, helpers = synthetic_run(tmp_path, h)
    report, bins = a.analyze(row, helpers)
    assert report['denominators']['native_arrival_labels'] == 2
    assert report['arrival_counts']['60']['1']['total_arrivals'] == 1
    assert report['transfers']['all_actual_requests']['outcomes'] == {'received': 1, 'failed': 1, 'unknown_native_outcome': 1}
    assert report['transfers']['selected_proposals']['denominator'] == 1
    selected = report['selected_transfer_rows'][0]
    assert selected['estimated_decision_to_arrival_seconds'] == 102
    assert selected['arrival_minus_selected_eta_seconds'] == 98
    assert selected['plan_creation_to_submission_seconds'] == 0
    assert selected['order_proposed_to_submission_seconds'] == 0
    assert report['station_observations']['1']['sampling_bounds']['absent_tick_count'] == 869
    assert report['future_jobs_used_as_arrival_labels'] is False
    report2 = copy.deepcopy(report)
    pooled = a.pooled_reports([report, report2], [bins, bins], h['transport'].distribution)
    assert pooled['arrival_counts']['60']['1']['total_arrivals'] == 2
    assert pooled['arrival_counts']['60']['1']['count'] == 1740


def test_synthetic_physical_identity_mismatch_fails(tmp_path, h):
    row, helpers = synthetic_run(tmp_path, h)
    path = tmp_path/'trajectory.json.gz'
    with gzip.open(path, 'rt') as f:
        tr = json.load(f)
    tr['rows'][0]['actual_submission']['tray_id'] = 'wrong'
    gz(path, tr)
    with pytest.raises(ValueError, match='selected_actual_call_join'):
        a.analyze(row, helpers)


def test_fallback_action_does_not_inherit_unmatched_plan_queue(tmp_path, h):
    row, helpers = synthetic_run(tmp_path, h)
    path = tmp_path/'decisions.json.gz'
    with gzip.open(path, 'rt') as f:
        decisions = json.load(f)
    decisions[0]['selection']['flow_plan']['dispatch_profile'] = []
    gz(path, decisions)
    report, _ = a.analyze(row, helpers)
    selected = report['selected_transfer_rows'][0]
    assert selected['original_plan_item_queue_identity_confirmed'] is False
    assert selected['plan_creation_to_submission_seconds'] is None
    assert selected['order_proposed_to_submission_seconds'] == 0
