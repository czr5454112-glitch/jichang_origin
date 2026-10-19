"""Validate the wall-budget-only preparation without native execution."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CYCLE = HERE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def main():
    plan = read(HERE/'plan.json')
    previous_dir = CYCLE/'C00_receiver_recorded_v2_001'
    old = read(previous_dir/'plan.json')
    audit_dir = CYCLE/'C00_receiver_recorded_v2_review_001'
    prior_audit = read(audit_dir/'report.json')
    assert prior_audit['closure']['actual_clock'] == prior_audit['closure']['last_complete_snapshot_time'] == 54240
    assert prior_audit['public_observations']['reconstructable_records'] == 2717
    assert not prior_audit['C10_guard']['eligible_for_same_contract_C10_preparation']
    assert all(plan['source_sha256'][p] == h for p,h in old['source_sha256'].items())
    new_sources = set(plan['source_sha256'])-set(old['source_sha256'])
    assert len(new_sources)==1 and next(iter(new_sources)).endswith('foundation_airport_recorded_budget_campaign.py')
    for path,digest in plan['source_sha256'].items():
        assert sha(path)==digest and sha(HERE/plan['source_archive'][path])==digest
    assert Path(plan['input']['path']).read_bytes() == Path(old['input']['path']).read_bytes()
    same = ['controller','physical_start','warmup_end','window_boundaries','warmup_segment_seconds',
        'physical_input_horizon','business_contract_version','business_semantic_sha256',
        'protocol_input_semantic_sha256','non_business_semantic_sha256','binary','receiver_admission_policy',
        'resource_contract','policy_observation_contract','planner_activate_at','observed_counts',
        'inventory','offered_business_count','node_count','edge_count']
    assert all(plan[k]==old[k] for k in same)
    assert plan['soft_stop_seconds']==600 and plan['hard_process_seconds']==660
    assert plan['automatic_retries']==0 and plan['native_branch_budget']==1
    basis=plan['soft_checkpoint_contract']['measured_wall_resource_basis']
    for item in basis['references']:
        assert sha(item['path'])==item['sha256']
    spec=read(CYCLE/'C00_receiver_recorded_v2_001_task.json')
    spec.update(task_id=HERE.name,module='scripts.experiments.g31_ics_circulation.foundation_airport_recorded_budget_campaign',
        args=['--launch','--output',str(HERE)],hard_seconds=720)
    refs=[HERE/'plan.json']+[Path(plan[k]['path']) for k in ['input','mapping','business_contract','business_audit','crosswalk','native_contract_reference','semantic_gate_reference']]
    refs += [Path(x['path']) for x in basis['references']]
    refs += [audit_dir/'report.json',audit_dir/'binding_and_cost.json']
    spec['sources']=list(plan['source_sha256'])+list(map(str,refs))
    spec['assessment']['path']=str(HERE/'receipt.json')
    spec['next_action']='Audit same complete population/input/control prefix and source archives, actual stop versus last snapshot, warmup native-state hash, remaining failures, receiving reservations, all reconstructed public records and post57660 actual forecast guards. Prepare same-resource C10 only after a closed successful59400 C00 and real eligible callback. Preserve every earlier censored/failed attempt; no automatic retry.'
    task=CYCLE/(HERE.name+'_task.json');save(task,spec)
    report={'status':'prepared_not_executed','native_sessions':0,'plan_sha256':sha(HERE/'plan.json'),
        'task_spec':str(task),'task_spec_sha256':sha(task),'task_source_count':len(spec['sources']),
        'original106_source_files_unchanged':True,'source_and_archive_count':len(plan['source_sha256']),
        'new_entry_point_only':sorted(new_sources),'unchanged_input_bytes':True,'input_sha256':plan['input']['sha256'],
        'unchanged_contract_fields':same,'budgets_seconds':{'soft':600,'inner_hard':660,'outer_hard':720},
        'native_branch_budget':1,'automatic_retries':0,'budget_evidence':basis,
        'pure_tests_passed':3,'pure_test_command':'python -m pytest tests/test_g31_airport_recorded_budget_campaign.py --basetemp outputs/airport_recorded_budget_tests_002 -q -x',
        'previous_closed_prefix_audit':{'path':str(audit_dir/'report.json'),'sha256':sha(audit_dir/'report.json')},
        'previous_binding_and_cost_audit':{'path':str(audit_dir/'binding_and_cost.json'),'sha256':sha(audit_dir/'binding_and_cost.json')},
        'C10_prepared':False}
    save(HERE/'preparation_audit.json',report)
    print(json.dumps({k:report[k] for k in ['status','plan_sha256','task_spec','task_source_count','source_and_archive_count','budgets_seconds']}))


if __name__=='__main__':main()
