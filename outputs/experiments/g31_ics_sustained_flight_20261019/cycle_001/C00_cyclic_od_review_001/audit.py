"""Read-only audit of closed native evidence. Standard library; never loads a controller/model/native module."""
import collections
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parent / 'C00_cyclic_od_001'
BRANCH = RUN / 'C00'


def load(path):
    if str(path).endswith('.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            return json.load(stream)
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


plan = load(RUN / 'plan.json')
receipt = load(RUN / 'receipt.json')
worker = load(BRANCH / 'worker_report.json')
raw = load(BRANCH / 'raw.json.gz')
final = raw['final_result']
inputs = load(RUN / 'inputs/C00.json')
acceptance = load(BRANCH / 'acceptance.json')
views = load(BRANCH / 'delivered_ack_views.json.gz')
calls = load(BRANCH / 'client_calls.json.gz')
ledger = load(BRANCH / 'request_ledger.json.gz')
events = final['receipts']
assert len(inputs['jobs']) == len(final['jobs']) == 28506
assert len(inputs['trays']) == len(final['trays']) == 22
assert raw['physical_reset_count'] == 0 and raw['session_instance_count'] == 1
assert raw['final_physical_time'] == final['physical_clock'] == 59400
assert sha(RUN / 'plan.json') == receipt['plan_sha256_at_launch']
assert sha(RUN / 'inputs/C00.json') == plan['input_file_sha256']['C00']
assert sha(BRANCH / 'raw.json.gz') == worker['raw']['sha256']
assert sha(BRANCH / 'acceptance.json') == worker['acceptance']['sha256']
source_bad = [source for source, archive in plan['source_archive'].items()
              if sha(RUN / archive) != plan['source_sha256'][source]]
assert not source_bad
# This checks immutable archived bytes, rather than assuming today's unrelated
# working tree still equals historical run entry. It does not rerun verifiers.
evidence_bad = [path for path, digest in acceptance['evidence_sha256'].items()
                if sha(path) != digest]
assert not evidence_bad
assert acceptance['status'] == 'closed_run_acceptance_passed' and not acceptance['invalid']

by_event = collections.defaultdict(list)
by_tray = collections.defaultdict(list)
for event in events:
    by_event[event['event']].append(event)
    if event['tray_id']:
        by_tray[event['tray_id']].append(event)
assert len(by_event['EDGE_ENTER']) == len(by_event['EDGE_EXIT']) == 541
assert len(by_event['UNLOAD_COMPLETE']) == 7
assert len(by_event['EMPTY_RECEIVED']) == 5
assert len(by_event['STORAGE_ENTER']) == 17
assert len(by_event['LEG_COMPLETE']) == 29  # 17 storage-in + 7 unload + 5 return
assert len(by_event['LEG_FAILED']) == 1


def physical_at(at):
    trays = {t['tray_id']: dict(t, edge_to=-1, reception_node=-1) for t in inputs['trays']}
    for e in events:
        if e['time'] > at:
            continue
        tray = trays.get(e['tray_id'])
        if tray is None:
            continue
        if e['event'] == 'EDGE_ENTER':
            tray['edge_to'] = e['to']
        elif e['event'] == 'EDGE_EXIT':
            tray['node'], tray['edge_to'] = e['to'], -1
        elif e['event'] == 'EXPORT_GRANTED':
            tray['reception_node'] = e['to']
        elif e['event'] in ('EMPTY_RECEIVED', 'UNUSED_RECEIVING_RELEASED'):
            tray['reception_node'] = -1
    return list(trays.values())


def occupants(trays, node):
    # Exact native027 circulation.hpp::occupancy predicate, once per tray.
    return [t['tray_id'] for t in trays if (t['edge_to'] < 0 and t['node'] == node)
            or t['edge_to'] == node or t['reception_node'] == node]


replayed = {x['tray_id']: x for x in physical_at(59400)}
assert all(all(replayed[t['tray_id']][k] == t[k] for k in ('node', 'edge_to', 'reception_node'))
           for t in final['trays'])
contracts = {r['node']: r for r in inputs['node_contracts']}
nodes = {}
for node in (28, 29, 40, 49, 53, 112, 116, 136, 137):
    nodes[str(node)] = dict(capacity=contracts[node]['capacity'],
        physical_trays=[t['tray_id'] for t in final['trays'] if t['node'] == node and t['edge_to'] < 0],
        leased_trays=[t['tray_id'] for t in final['trays'] if t['reception_node'] == node],
        counted_occupancy=occupants(final['trays'], node),
        outgoing=[r for r in inputs['edge_records'] if r[0] == node])
assert nodes['49']['physical_trays'] == [] and len(nodes['49']['counted_occupancy']) == 4
assert all(len(nodes[str(n)]['counted_occupancy']) == 4 for n in (28, 29, 53, 112))
assert [r[:2] for r in inputs['edge_records'] if r[1] == 49] == [[53, 49]]

tray_details = []
for ti, tray in enumerate(final['trays']):
    rows = by_tray[tray['tray_id']]
    active = next((leg for leg in final['leg_identities'] if leg['runtime_id'] == tray['active_leg']), None)
    last_wait = next((r for r in reversed(rows) if r['event'] == 'RESOURCE_WAIT'), None)
    arrival = next((r for r in reversed(rows) if r['event'] in ('EDGE_EXIT', 'LEG_START')), None)
    job = inputs['jobs'][tray['job']] if tray['job'] >= 0 else None
    tray_details.append(dict(index=ti, tray=tray, active_leg=active, job_contract=job,
                             last_resource_wait=last_wait, latest_queue_entry_evidence=arrival,
                             last_events=rows[-8:]))

failed_id = 'live:21:owner:system_domestic:transfer:115'
failure = next(x for x in final['transfers'] if x['request_id'] == failed_id)
failed_calls = [x for x in calls if x['request']['request_id'] == failed_id]
failed_acks = [x for x in views['owner:system_domestic']['delivered_transfer_acks']
               if x['request_id'] == failed_id]
assert failure['departed_at'] == failure['received_at'] == -1
assert failure['reason'] == 'departure_lease_expired_before_physical_entry'
assert len({json.dumps(x['request'], sort_keys=True) for x in failed_calls}) == 1
assert failed_acks[-1]['status'] == 'failed' and failed_acks[-1]['delivered_at'] == 11882.2
assert not [x for x in calls if x['kind'] == 'recover_empty']
assert not by_event['EMPTY_RECOVERY_GRANTED']
empty_rejections = [x for x in by_event['TRANSFER_REJECTED'] if x['tray_id'] == 'initial:26:0']
assert len(empty_rejections) == 642 and all(x['reason'] == 'receiving_full' and x['to'] == 49 for x in empty_rejections)

observation_receipt = load(BRANCH / 'policy_observation_receipt.json')
assert sha(BRANCH / 'policy_observations.jsonl.gz') == observation_receipt['artifact']['sha256']
obs_counts, gate_counts = collections.Counter(), collections.Counter()
obs_times, obs_owners = [], set()
gate_rows = []
unknown_keys = set()
with gzip.open(BRANCH / 'policy_observations.jsonl.gz', 'rt', encoding='utf-8') as stream:
    for sequence, line in enumerate(stream):
        row = json.loads(line)
        obs, decision = row['observation'], row['decision']
        assert row['sequence'] == sequence and row['now'] == obs['now'] == decision['now']
        assert row['owner_id'] == obs['owner_id'] and row['readonly']
        assert row['candidate_conditional_labels'] is None and not row['native_execution_authority']
        assert all(contracts[t['node']]['resource_owner'] == row['owner_id'] for t in obs['trays'])
        assert obs['transfers'] == obs['client_transfer_ledger']
        assert all(x['issued_at'] <= row['now'] for x in obs['transfers'])
        assert all(x.get('delivered_at', row['now']) <= row['now'] for x in obs['delivered_messages'])
        obs_times.append(row['now']); obs_owners.add(row['owner_id'])
        available = sum(s['ledger'] == 'actual_available' for s in decision['supplies'])
        key = (row['owner_id'], available, len(decision['intents']))
        obs_counts[key] += 1
        if row['now'] >= plan['planner_activate_at']:
            # Evaluate only the published new planner's first two guard branches
            # against the REAL callback return. No predictor/controller imported.
            gate = 'baseline_intents_returned' if decision['intents'] else (
                'no_actual_available_supply' if available == 0 else 'forecast_would_be_called')
            gate_counts[gate] += 1
            gate_rows.append(dict(sequence=sequence, now=row['now'], owner=row['owner_id'],
                actual_available=available, intent_count=len(decision['intents']), gate=gate))
assert len(obs_times) == observation_receipt['record_count'] == 946
assert min(obs_times) == 43200 and max(obs_times) == 59400
assert gate_counts == {'baseline_intents_returned': 45, 'no_actual_available_supply': 60}

segments = []
for path in sorted(BRANCH.glob('segment_*.json.gz')):
    segment = load(path)
    result = segment['result']
    segments.append(dict(path=path.name, sha256=sha(path), time=result['physical_clock'],
        population=result['population'], native_summary=result['native_summary'], wall_seconds=segment['wall_seconds']))
assert len(segments) == 20
assert all(row['native_summary']['edge_enter_event_count'] == 541
           for row in segments if row['time'] >= 25200)
save('tray_wait_for.json', tray_details)
save('counterfactual_C10_gate_from_actual_observations.json', gate_rows)
save('failed_request.json', dict(native_transfer=failure, immutable_calls=failed_calls,
    public_ack_history=failed_acks, physical_failure=by_event['LEG_FAILED'][0],
    occupancy_at_grant={str(n): occupants(physical_at(11342), n) for n in (137, 112, 53)}))

report = dict(schema='g31.independent.airport_cyclic_od_native_audit.v1',
    run=str(RUN), evidence_method='Standard library inspection of raw physical receipts, public callback records, ACKs and historical source bytes; no controller/model/native imports or native run.',
    closed_evidence=dict(plan_sha256=sha(RUN/'plan.json'), input_sha256=sha(RUN/'inputs/C00.json'),
        raw_sha256=sha(BRANCH/'raw.json.gz'), archived_source_count=len(plan['source_archive']),
        archive_mismatches=source_bad, acceptance_bound_file_count=len(acceptance['evidence_sha256']),
        evidence_mismatches=evidence_bad, native_acceptance_status=acceptance['status'],
        verifier_reexecuted=False, session_count=raw['session_instance_count'], reset_count=raw['physical_reset_count'],
        physical_end=59400, full_86400_horizon_completed=False),
    business=dict(offered_total=28506, **final['population'], status_counts=dict(collections.Counter(x['status'] for x in final['jobs'])),
        completed_ids=[x['business_bag_id'] for x in final['jobs'] if x['status']=='completed'],
        native_completed_legs=29, native_legs_breakdown={'storage_in':17,'business_unload':7,'empty_return':5},
        unresolved_offered_total=28506-7),
    movement=dict(last_edge_enter=by_event['EDGE_ENTER'][-1], last_edge_exit=by_event['EDGE_EXIT'][-1],
        last_physical_business_completion=by_event['UNLOAD_COMPLETE'][-1],
        last_storage_release=by_event['STORAGE_RELEASE'][-1], last_resource_wait=by_event['RESOURCE_WAIT'][-1],
        no_edge_motion_interval=[by_event['EDGE_EXIT'][-1]['time'],59400],
        no_edge_motion_duration=59400-by_event['EDGE_EXIT'][-1]['time']),
    final_tray_mode_counts=dict(collections.Counter(x['mode'] for x in final['trays'])),
    nodes=nodes, receiving49_grants=[x for x in by_event['EXPORT_GRANTED'] if x['to']==49],
    causal_interpretation={
        'hard_cycle':'Four remote empty-return reservations fill node49. Its only incoming edge is53->49. Four loaded trays occupy53; at112 the FIFO head empty initial:138:0 needs53 before49. Node112 is full;29/137 feed112;28 feeds29;40 feeds28. The reservations cannot be cleared by cancelling already departed transfers.',
        'source_limits':'Trace_limit=0 omits per-decision rankings and internal queue dump. The exact FIFO head/shortest route beyond the observed RESOURCE_WAIT is a source-grounded inference, not an exported full scheduler snapshot. Node53->49 and lease-capacity closure are directly proved.',
        'quarantine':'Transfer115 cannot enter136->137 because137 is occupied by4 real trays during its entire lease; native failure at11839.48900001 releases its unused node26 reservation, leaves the actual empty tray quarantined. Failed ACK arrives11882.2. No recovery command occurs.',
        'old_recovery_api':'recover_empty_tray exists only behind require_legacy_control_endpoint; protocol mode rejects that endpoint, and protocol command whitelist has no recovery kind. Direct use would violate the pinned R2 contract.',
        'repeated_rejection':'642 attempts for actual empty tray initial:26:0 at116 target49 and fail receiving_full; other cross-zone legal ports exist in the public candidate pool but old minimum-cost matching repeatedly chooses49.'},
    transfer_status_counts=dict(collections.Counter(x['status'] for x in final['transfers'])),
    transfer_rejection_reasons=dict(collections.Counter(x['reason'] for x in by_event['TRANSFER_REJECTED'])),
    calls=dict(total=len(calls), unique_requests=ledger['request_count'], retries=ledger['retry_calls'],
        kinds=ledger['requests_by_kind'], terminal_recovery_count=0),
    observations=dict(count=len(obs_times), owners=sorted(obs_owners), first=min(obs_times), last=max(obs_times),
        integrity_and_owner_scope_checks_passed=True, actual_available_tray='initial:26:0@116 domestic',
        raw_sha256=sha(BRANCH/'policy_observations.jsonl.gz'),
        counts=[dict(owner=k[0],actual_available=k[1],intent_count=k[2],count=v) for k,v in sorted(obs_counts.items())],
        conditional_labels_available=False, all_recorded_physical_outcomes_stagnant=True,
        learning_readiness=False),
    C10_readonly_decision=dict(activate_at=plan['planner_activate_at'], actual_callback_count=len(gate_rows),
        gate_counts=dict(gate_counts), forecast_branch_reachable_on_recorded_observations=False,
        recommendation='Do not spend another native run on the current unchanged C10. This is a guard-branch audit, not a native C10 trial or a measured effect.',
        same_action_induction_scope='Same input, native/controller configuration and warmup; current C10 adds no forecast/action at every recorded callback.'),
    segments=segments,
    excluded_claims=['full-flow success','sustained circulation','forecast effect','strict per-job nonharm','native C10 comparison','conditional action-value labels','true multi-step RL'])
save('report.json', report)
print(json.dumps({'report':str(HERE/'report.json'),'source_archives':len(plan['source_archive']),
    'evidence_files':len(acceptance['evidence_sha256']),'completed':7,'last_edge_exit':by_event['EDGE_EXIT'][-1]['time'],
    'actual_empty':1,'observation_count':len(obs_times),'C10_gate_counts':dict(gate_counts)},ensure_ascii=False))
