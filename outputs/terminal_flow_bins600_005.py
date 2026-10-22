"""Four-parent 600-second bin extension on source005; prepare/run are explicit.

Reuses original INITIAL allocation (not a quota transfer), same paired source,
inputs and interface. No auto retry, TEST, source edit, or model fit.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import secrets
import shutil
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'
CYCLE = ROOT/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'
DIRECTORY = CYCLE/'terminal_flow/bins600_full_005'
SCHEMA = 'g31.terminal_flow.bins600_extension.v1'
PARENTS = (2201,2202,2203,2204)

def need(ok, reason):
    if not ok: raise ValueError('bins600:'+reason)

def load_budget():
    path = ROOT/'outputs/terminal_flow_offline_budget.py'
    loader = importlib.util.spec_from_file_location('bins600_accounting', path)
    module = importlib.util.module_from_spec(loader); loader.loader.exec_module(module)
    return module

def validate_pair(reference, candidate, flow):
    need(reference['method'] == 'TF-B1-60' and candidate['method'] == 'TF-B1-600', 'fixed_method_pair')
    need(not flow.method_contract_errors(candidate), '600_method_contract')
    left, right = flow.comparison_contract(reference), flow.comparison_contract(candidate)
    changes = {key:dict(reference=left[key],candidate=right[key]) for key in left if left[key] != right[key]}
    need(set(changes) == {'forecast_bin_edges_seconds'}, 'only_bin_edges_may_change')
    need(candidate['parent'] == reference['parent'] and candidate['parent']['split'] == 'dev'
         and candidate['parent']['parent_seed'] in PARENTS, 'same_DEV_parent')
    need(candidate['batch'] == 'initial' and candidate['horizon'] == 59400., 'original_initial_quota_full_window')
    return changes

def preflight(w, plans=4, owned_runner=None, overhead=300):
    limits = w.read(CYCLE/'campaign_budget.json')
    holdback = w.read(DATA/'offline_historical_holdback_005_002.json')
    snapshot = w.snapshot(coverage_cutoff=w.instant(holdback['cutoff_utc']))
    result = w.preflight(snapshot, limits, offline_seconds=plans*2400+overhead,
        remaining_seconds=0, holdback_seconds=w.historical_seconds(holdback),
        existing_bytes=w.evidence_bytes([CYCLE,DATA]), reserved_bytes=plans*536870912+16*1024**2,
        free_bytes=shutil.disk_usage(CYCLE).free, owned_runner=owned_runner)
    events = [json.loads(line) for line in (CYCLE/'ledger.jsonl').read_text(encoding='utf8').splitlines() if line.strip()]
    starts = [e for e in events if e['event']=='native_start']
    need(len(starts)+plans <= limits['native_start_limit'], 'shared_native_limit')
    need(sum(e.get('batch')=='initial' for e in starts)+plans <= limits['allocations']['initial'], 'unspent_initial_quota')
    return result

def modules():
    sys.path.insert(0,str(ROOT))
    from scripts.experiments.g31_ics_circulation import foundation_airport_joint_campaign as campaign
    from scripts.experiments.g31_ics_circulation import foundation_airport_transport_campaign as flow
    from scripts.experiments.g31_ics_circulation import foundation_airport_joint_budget as budget
    return campaign,flow,budget

def verify_source(w, source):
    manifest=w.read(w.checked(source))
    for name, sha in manifest['files'].items():
        for root in (ROOT, Path(manifest['root'])):
            path=(root/name).resolve()
            need(path.is_relative_to(root.resolve()) and w.digest(path)==sha, 'same_frozen_and_working_source:'+name)

def prepare():
    w=load_budget(); initial=preflight(w)
    need(not DIRECTORY.exists(), 'fresh_registration_directory')
    source=w.bind(CYCLE/'sources/terminal_flow_runtime_005/source_manifest.json')
    verify_source(w,source)
    workflow=w.bind(CYCLE/'terminal_flow/workflow_005/registration.json')
    completion=w.bind(CYCLE/'terminal_flow/workflow_005/completion.json')
    need(w.read(w.checked(completion))['registration']==workflow, 'completed_workflow_binding')
    trigger=w.bind(DATA/'granularity_005_full_001/granularity_report.json')
    # Trigger interpretation is preserved separately; this extension is four
    # previously registered DEV parents, never a new favorable parent search.
    decision=w.bind(DATA/'GRANULARITY_DECISION_005_001.md')
    completed_science=[p for p in (DATA/'final_science_005_001/COMPLETE.json',
        DATA/'final_science_005_resumed_001/COMPLETE.json') if p.exists()]
    need(len(completed_science)==1, 'one_closed_baseline_science_required')
    baseline_science=w.bind(completed_science[0])
    baseline_marker=w.read(w.checked(baseline_science))
    w.need(baseline_marker['status']=='complete', 'baseline_science_complete')
    baseline_report=w.read(w.checked(baseline_marker['final_report']))
    need(baseline_report['source_bundle']==source and baseline_report['workflow']==workflow, 'same_baseline_science_source')
    campaign,flow,budget=modules()
    baseline_refs=[w.bind(CYCLE/f'runs/TF_bridge_all_005_TF-B1-60_P{p}/plan.json') for p in PARENTS]
    calibration=w.bind(CYCLE/'runtime_calibration_001.json'); cal=w.read(w.checked(calibration))
    need(cal['hard_seconds']==2400. and cal['estimated_evidence_bytes']==536870912, 'unchanged_runtime_calibration')
    DIRECTORY.mkdir()
    intent=dict(schema=SCHEMA+'.intent',driver=w.bind(__file__),accounting=w.bind(ROOT/'outputs/terminal_flow_offline_budget.py'),
        source_bundle=source,workflow=workflow,workflow_completion=completion,trigger_report=trigger,decision=decision,
        baseline_plans=baseline_refs,baseline_science=baseline_science,calibration=calibration,parents=list(PARENTS),method='TF-B1-600',batch='initial',
        original_budget=w.bind(CYCLE/'campaign_budget.json'),historical_holdback=w.bind(DATA/'offline_historical_holdback_005_002.json'),
        preflight=initial,TEST_unlocked=False,R1_enabled=False,native_concurrency=1)
    intent_ref=w.save(DIRECTORY/'intent.json',intent)
    tasks=[]; pair_checks=[]
    for p, ref in zip(PARENTS,baseline_refs):
        baseline=w.read(w.checked(ref))
        directory=campaign.prepare(f'TF_bins600_full_005_TF-B1-600_P{p}',method='TF-B1-600',seed=p,batch='initial',
            source_bundle=source,mapping=baseline['mapping'],calibration=calibration,transport_config=baseline['transport_config'],
            **{k:cal[k] for k in ('horizon','soft_seconds','hard_seconds','estimated_evidence_bytes')})
        plan=w.read(directory/'plan.json')
        pair_checks.append(dict(parent=p,changes=validate_pair(baseline,plan,flow)))
        tasks.append(w.bind(directory/'plan.json'))
    registration=dict(schema=SCHEMA,intent=intent_ref,source_bundle=source,task_plans=tasks,
        baseline_plans=baseline_refs,pair_checks=pair_checks,phase='bins600_extension',parents=list(PARENTS),
        method='TF-B1-600',TEST_unlocked=False,R1_enabled=False,no_service_conclusion=True)
    ref=w.save(DIRECTORY/'registration.json',registration)
    budget.append(CYCLE,'terminal_flow_bins600_registered',registration=ref,original_budget_unchanged=True)
    print(json.dumps(ref),flush=True)

def run():
    w=load_budget(); registration_ref=w.bind(DIRECTORY/'registration.json'); reg=w.read(w.checked(registration_ref))
    intent=w.read(w.checked(reg['intent']))
    need(reg['schema']==SCHEMA and intent['driver']==w.bind(__file__), 'bound_driver_registration')
    for key in ('accounting','workflow','workflow_completion','trigger_report','decision','calibration','original_budget','historical_holdback','baseline_science'):
        w.checked(intent[key])
    verify_source(w,reg['source_bundle'])
    campaign,flow,budget=modules()
    plans=[w.read(w.checked(ref)) for ref in reg['task_plans']]
    need([p['parent']['parent_seed'] for p in plans]==list(PARENTS), 'exact_four_parent_order')
    for plan,baseline in zip(plans,reg['baseline_plans']): validate_pair(w.read(w.checked(baseline)),plan,flow)
    need(all(not (Path(p['output'])/'receipt.json').exists() for p in plans), 'fresh_run_no_implicit_retry')
    admission=preflight(w)
    runner='terminal-flow-bins600-'+secrets.token_hex(12)
    budget.append(CYCLE,'runner_open',runner_id=runner,purpose='four_parent_bins600_extension',registration=registration_ref)
    safe=True; receipts=[]; began=time.monotonic()
    try:
        w.save(DIRECTORY/'STARTED.json',dict(runner_id=runner,registration=registration_ref,preflight=admission))
        for i,plan in enumerate(plans):
            w.checked(registration_ref); w.checked(intent['driver'])
            preflight(w,len(plans)-i,owned_runner=runner)
            safe=False
            receipt=campaign.launch(plan['output'])
            process=receipt['process']
            safe=process.get('windows_job_kill_on_close') is True and process.get('exitcode') is not None
            need(safe and process.get('exitcode')==0 and receipt['worker'].get('scientific_status')=='closed',
                 'native_not_closed_stop_without_retry')
            receipts.append(w.bind(Path(plan['output'])/'receipt.json'))
            print(json.dumps(dict(parent=plan['parent']['parent_seed'],method=plan['method'],status='closed')),flush=True)
        verify_source(w,reg['source_bundle'])
        w.save(DIRECTORY/'NATIVE_COMPLETE.json',dict(status='closed',registration=registration_ref,receipts=receipts,
            actual_driver_seconds=time.monotonic()-began,full_window_native_runs=4,
            service_audit_pending=True,TEST_unlocked=False,R1_enabled=False))
    finally:
        if safe: budget.append(CYCLE,'runner_close',runner_id=runner)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['check','prepare','run'])
    args=parser.parse_args()
    if args.action=='prepare': prepare()
    elif args.action=='run': run()
    else: print(json.dumps(preflight(load_budget()),indent=2))

if __name__=='__main__': main()
