"""Root small binding review and full-denominator outcome arithmetic.

The completed independent24070-row saved replay is hash-bound, not rerun.
"""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
ROOT, OUT = HERE.parents[3], HERE.parent
DIRECTORY = OUT / 'original_low_wip_cap_relay_prepare_001'
CASE = DIRECTORY / 'cap8'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_bytes())
def gzread(p): return json.loads(gzip.decompress(Path(p).read_bytes()))
start = time.perf_counter()
pins = {
 'ready.json': 'b4bc0d28e4f2caf2e09afe262167bea6eb0d65a55031df19aa211b9182c5365a',
 'campaign.json': 'cdd989387f84292ab4f3d07f5f22ec1d83429726114257f2a3a620d9d600c4ac',
 'receipt.json': '7445f7cfb8454987890ef92e1fad100884cbeeea33af44edb2c63e3a8354545a',
 'cap8/independent_verification.json': 'aea5ba0eea5594deef09fe162a170670b329a100b9ca36cf772f950941e7b8e8',
 'powershell_launch_receipt.json': '5d376f5545853d8239467f1a5a0774bc9d9f60598ccd10619d53c98389fee995',
 'cap8/preregistered_protocol.json': '59e2d0923b8fdd2647d382edaad5ab0aacd72b5307d38972878ac7a9c3cc6025',
 'cap8/all_job_states.json.gz': '6215abc21ef032b5c8501ea21ff9c88b9e1f59ba7a6008d05c6a1ab7db158c6e',
}
for name, digest in pins.items(): assert sha(DIRECTORY/name) == digest, name
ready, producer = read(DIRECTORY/'ready.json'), read(DIRECTORY/'receipt.json')
verified, plan = read(CASE/'independent_verification.json'), read(CASE/'preregistered_protocol.json')
outer = read(DIRECTORY/'powershell_launch_receipt.json')
assert producer['status'] == 'completed_finite_campaign' and producer['source_changed'] == []
assert producer['new_same_policy_cap3_pair'] is False and set(producer['cases']) == {'cap8'}
assert all(producer['cases']['cap8'][key]['exit_code'] == 0 for key in ('execution', 'verification'))
assert outer['status'] == 'application_exited_zero' and outer['exit_code'] == 0
assert outer['evidence_identities_unchanged'] is True and outer['whole_application_campaign_wall_seconds'] < 2400
assert outer['ready']['sha256'] == pins['ready.json'] and outer['preregistered_plan']['sha256'] == pins['campaign.json']
assert verified['status'] == 'passed_saved_policy_replay' and verified['native_executions'] == 0
assert verified['replay']['status'] == 'passed_saved_raw_replay' and verified['replay']['api_rows'] == 24070
assert verified['full_saved_api_replays'] == 1
assert verified['cap_relay_assessment'] == producer['assessment']
assert producer['assessment']['status'] == 'complete_cap8_with_bidirectional_cap_relay'
assert len(plan['source_before']) == 82 and len(plan['compiled_source_sha256']) == 67
for path, digest in plan['source_before'].items():
    assert sha(path) == digest
    assert sha(CASE/'source_archive'/Path(path).relative_to(ROOT)) == digest
for path, digest in plan['authority_pins'].items():
    assert sha(path) == digest
build = read(OUT/'native026_build_001/receipt.json')
acceptance = read(OUT/'native026_acceptance_001/receipt.json')
assert build['status'] == 'build_passed_tests_held' and build['source_changed'] == []
assert acceptance['status'] == 'passed' and acceptance['source_changed'] == []
assert build['source_before'] == build['source_after'] == plan['compiled_source_sha256']
live_compiled_differences = []
for relative, digest in plan['compiled_source_sha256'].items():
    assert sha(CASE/'compiled_source_archive'/relative) == digest
    if sha(ROOT/relative) != digest:
        live_compiled_differences.append(relative)
assert sha(plan['binary']) == plan['binary_sha256'] == ready['native_binary_sha256']
assert sha(CASE/'input.json.gz') == plan['input_sha256']
pins['cap8/input.json.gz'] = plan['input_sha256']
input_data = gzread(CASE/'input.json.gz')
job_states = gzread(CASE/'all_job_states.json.gz')
assert job_states['offered'] == plan['offered'] == 28506
assert job_states['horizon'] == plan['horizon'] == 86400
assert len(input_data['jobs']) == len(job_states['jobs']) == 28506
assert len(input_data['trays']) == 22
completed, on_time, failed, late, restricted_cost = [], 0, 0, 0, 0.
for offered, outcome in zip(input_data['jobs'], job_states['jobs'], strict=True):
    assert offered['business_bag_id'] == outcome['business_bag_id']
    assert offered['arrival'] <= 86400
    if outcome['status'] == 'completed':
        assert outcome['completed_at'] >= offered['arrival']
        completed.append(outcome['business_bag_id'])
        on_time += outcome['completed_at'] <= offered['deadline']
        late += outcome['completed_at'] > offered['deadline']
        end = outcome['completed_at']
    else:
        assert outcome['completed_at'] == -1
        end = 86400
        late += offered['deadline'] < 86400
        failed += outcome['status'] == 'failed'
    restricted_cost += end-offered['arrival']
assert Counter(x['status'] for x in job_states['jobs']) == {'completed': 8, 'waiting_for_tray': 28498}
assert completed == verified['independent_outcomes']['completed']
assert verified['independent_outcomes']['actual_supplies'] == 8
assert len(verified['independent_outcomes']['other_trays_stationary_at_declared_parking']) == 21
proofs = {}
for owner, row in producer['assessment']['owner_proofs'].items():
    assert row['status'] == 'actual_fresh_cap_proof_and_delivered_own_relay'
    relay, proof = row['own_historical_relay'], row['fresh_cap_proof']
    assert relay['status'] == 'delivered_historical_cap_relay' and relay['new_physical_actions_authorized'] is False
    assert relay['request_id'] == row['request_id']
    assert proof['at'] < relay['captured_at'] < relay['delivered_at'] <= relay['ack_delivered_at']
    assert len(row['actual_ack_query_ordinals']) == 1 and row['submit_api_ordinal'] < row['actual_ack_query_ordinals'][0]
    proofs[owner] = {'proof_at': proof['at'], 'captured_at': relay['captured_at'],
        'delivered_at': relay['delivered_at'], 'ack_delivered_at': relay['ack_delivered_at'],
        'submit_api_ordinal': row['submit_api_ordinal'], 'ack_api_ordinal': row['actual_ack_query_ordinals'][0]}
assert len(proofs) == 2
report = {'schema': 'g31.cap_relay.small_result_review.v1', 'status': 'passed_binding_and_outcome_review',
    'recorded_utc': datetime.now(timezone.utc).isoformat(), 'evidence_sha256': pins,
    'sources_checked': 82, 'compiled_sources_checked': 67, 'native_executions_here': 0,
    'full_saved_api_replays_here': 0, 'hash_bound_prior_saved_replay_rows': 24070,
    'scope': 'Read small metadata, full offered input and full28506 final job states; rehash live/archive Python sources, archived026 compiled sources bound to unchanged accepted026 build, and accepted026 binary. Live compiled tree is027 and is not the authority for this026 execution. Prior complete saved API replay is referenced, not performed again.',
    'accepted026_authority_pins': plan['authority_pins'],
    'live027_compiled_differences_from_archived026': live_compiled_differences,
    'horizon': 86400, 'offered': 28506, 'completed': len(completed), 'completed_ids': completed,
    'unfinished': 28506-len(completed), 'completed_on_time': on_time, 'failed': failed,
    'strict_horizon_deadline_violations': late, 'deadline_tolerance': 0,
    'restricted_arrival_to_unload_cost': restricted_cost,
    'restricted_cost_scope': 'Completed use actual unload; unfinished contribute horizon-arrival. This is not mean latency of fully completed jobs.',
    'owner_proofs': proofs, 'whole_application_campaign_wall_seconds': outer['whole_application_campaign_wall_seconds'],
    'producer_native_seal': verified['producer_native_seal'], 'independent_native_replay_performed': False,
    'new_same_policy_cap3_pair': False, 'strict_protection': 'unknown_unfinished_offered_jobs',
    'complete_100ms_certified': False, 'joint_method_necessity_certified': False,
    'review_precheck_corrections': ['Initial review stopped before creating a report because it addressed the compiled archive at campaign root. Corrected to actual per-case archive.', 'Second review stopped before creating a report because it wrongly required the live027 compiled tree to equal archived026. Corrected authority is the unchanged accepted026 build receipt and its67 archived sources. No execution evidence or outcome changed.'],
    'review_wall_seconds': time.perf_counter()-start}
path = OUT/'original_low_wip_cap_relay_actual_review_001.json'
with path.open('x', encoding='utf8') as stream: json.dump(report, stream, indent=2, allow_nan=False)
print(json.dumps({k: report[k] for k in ('status','completed','unfinished','completed_on_time','strict_horizon_deadline_violations','restricted_arrival_to_unload_cost')} | {'sha256': sha(path)}))
