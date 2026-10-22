"""Explicit, finite same-source projection-horizon repair; not active on import.

activate edits only two prepared method-contract files, after source005 closes.
prepare registers eight DEV runs. run admits only that fixed block, serially.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import secrets
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'
CYCLE=ROOT/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'
WORKFLOW=CYCLE/'terminal_flow/workflow_006'
BLOCK=CYCLE/'terminal_flow/horizon_repair_006'
SOURCE=CYCLE/'sources/terminal_flow_runtime_006/source_manifest.json'
PARENTS=(2201,2202,2203,2204)
METHODS=('TF-B1-60','TF-B1-60-H1800')
AUDIT_RESERVE=6000

def need(ok,reason):
    if not ok:raise ValueError('horizon006:'+reason)

def accounting():
    p=ROOT/'outputs/terminal_flow_bins600_offline005.py'
    s=importlib.util.spec_from_file_location('horizon006_accounting',p)
    w=importlib.util.module_from_spec(s);s.loader.exec_module(w);return w

def preflight(w,remaining=None,owned_runner=None):
    remaining=[2400.,3600.]*4 if remaining is None else remaining
    limits=w.read(CYCLE/'campaign_budget.json');hold=w.read(DATA/'offline_historical_holdback_005_002.json')
    snapshot=w.snapshot(coverage_cutoff=w.instant(hold['cutoff_utc']))
    result=w.preflight(snapshot,limits,offline_seconds=sum(remaining)+300,
        remaining_seconds=AUDIT_RESERVE,holdback_seconds=w.historical_seconds(hold),
        existing_bytes=w.evidence_bytes([CYCLE,DATA]),reserved_bytes=len(remaining)*536870912+256*1024**2,
        free_bytes=shutil.disk_usage(CYCLE).free,owned_runner=owned_runner)
    events=[json.loads(x) for x in (CYCLE/'ledger.jsonl').read_text().splitlines() if x]
    starts=[e for e in events if e['event']=='native_start']
    need(len(starts)+len(remaining)<=limits['native_start_limit'],'original_native_limit')
    need(sum(e.get('batch')=='initial' for e in starts)+len(remaining)<=limits['allocations']['initial'],'unspent_initial_quota')
    return result

def source_matches(w,ref):
    m=w.read(w.checked(ref))
    for relative,sha in m['files'].items():
        for root in (ROOT,Path(m['root'])):
            p=(root/relative).resolve()
            need(p.is_relative_to(root.resolve()) and w.digest(p)==sha,'source_changed:'+relative)
    return m

def closed_dependencies(w):
    refs={key:w.bind(path) for key,path in dict(
        main_science=DATA/'final_science_005_resumed_001/COMPLETE.json',
        bins600_science=DATA/'bins600_science_005_001/COMPLETE.json',
        horizon_probe=DATA/'projection_horizon_probe_005_001/COMPLETE.json',
        diagnosis=DATA/'PROJECTION_HORIZON_REPAIR_DECISION_006.md').items()}
    for key in ('main_science','bins600_science','horizon_probe'):
        need(w.read(w.checked(refs[key]))['status']=='complete','closed_dependency:'+key)
    probe=w.read(w.checked(w.read(w.checked(refs['horizon_probe']))['report']))
    need(probe['only_axis']=='projection_horizon_seconds' and probe['counts']['first_action_changed']>0,
        'actionable_same_state_horizon_diagnosis_required')
    return refs

def activate():
    w=accounting();admission=preflight(w);deps=closed_dependencies(w)
    need(not WORKFLOW.exists() and not SOURCE.exists(),'fresh_workflow_and_source')
    before=w.bind(CYCLE/'sources/terminal_flow_runtime_005/source_manifest.json');source_matches(w,before)
    prep_ref=w.bind(DATA/'horizon_repair_preparation_006/PREPARATION.json');prep=w.read(w.checked(prep_ref))
    need(prep['status']=='candidate_copies_only_not_applied' and len(prep['files'])==2,'two_prepared_files')
    expected={'scripts/experiments/g31_ics_circulation/foundation_airport_joint_campaign.py',
        'scripts/experiments/g31_ics_circulation/foundation_airport_transport_campaign.py'}
    need({r['relative'] for r in prep['files']}==expected,'exact_method_contract_files')
    changes=[]
    for row in prep['files']:
        destination=(ROOT/row['relative']).resolve();candidate=Path(row['candidate']).resolve()
        need(destination.is_relative_to(ROOT) and candidate.is_relative_to(DATA),'prepared_paths')
        need(w.digest(destination)==row['before_sha256'] and w.digest(candidate)==row['candidate_sha256'],'prepared_source_binding')
        data=candidate.read_bytes();compile(data,str(destination),'exec');changes.append((destination,data))
    WORKFLOW.mkdir()
    w.save(WORKFLOW/'ACTIVATION_INTENT.json',dict(driver=w.bind(__file__),source005=before,preparation=prep_ref,
        dependencies=deps,preflight=admission,production_changes=sorted(expected),no_native_started=True))
    for destination,data in changes:destination.write_bytes(data)
    w.save(WORKFLOW/'ACTIVATED.json',dict(status='method_arm_implemented_pending_tests_and_freeze',
        files=[w.bind(p) for p,_ in changes],native_starts=0))
    print('Activated only the prepared method-contract files; run core regression, then prepare.')

def modules():
    sys.path.insert(0,str(ROOT))
    from scripts.experiments.g31_ics_circulation import foundation_airport_joint_campaign as campaign
    from scripts.experiments.g31_ics_circulation import foundation_airport_transport_campaign as flow
    from scripts.experiments.g31_ics_circulation import foundation_airport_joint_budget as budget
    return campaign,flow,budget

def validate_pair(left,right,flow):
    need(left['method']==METHODS[0] and right['method']==METHODS[1],'fixed_pair')
    need(not flow.method_contract_errors(left) and not flow.method_contract_errors(right),'method_contract')
    a,b=flow.comparison_contract(left),flow.comparison_contract(right)
    changes={k:dict(reference=a[k],candidate=b[k]) for k in a if a[k]!=b[k]}
    need(set(changes)=={'projection_horizon'} and a['projection_horizon']==600. and b['projection_horizon']==1800.,'only_projection_axis')
    need(left['parent']==right['parent'] and left['parent']['split']=='dev'
        and left['parent']['parent_seed'] in PARENTS,'same_fixed_DEV_parent')
    need(left['horizon']==right['horizon']==59400. and left['batch']==right['batch']=='initial','fixed_window_quota')
    return changes

def prepare():
    w=accounting();admission=preflight(w);deps=closed_dependencies(w)
    activation=w.read(WORKFLOW/'ACTIVATED.json')
    for ref in activation['files']:w.checked(ref)
    intent=w.read(WORKFLOW/'ACTIVATION_INTENT.json');need(intent['driver']==w.bind(__file__),'unchanged_driver')
    tests=w.bind(DATA/'horizon_repair_core_pure_006.xml')
    import xml.etree.ElementTree as ET
    tree=ET.parse(tests['path']);suites=list(tree.getroot().iter('testsuite'))
    need(suites and sum(int(s.get('tests','0')) for s in suites)>=462
        and all(int(s.get('failures','0'))==int(s.get('errors','0'))==int(s.get('skipped','0'))==0 for s in suites),
        'full_core_pure_gate')
    need(not SOURCE.exists() and not BLOCK.exists() and not (WORKFLOW/'registration.json').exists(),'fresh_registration')
    campaign,flow,budget=modules();source=campaign.freeze_sources('terminal_flow_runtime_006')
    manifest=source_matches(w,source);old=w.read(w.checked(intent['source005']))
    changed=[k for k in manifest['files'] if manifest['files'][k]!=old['files'].get(k)]
    need(set(changed)==set(intent['production_changes']) and set(manifest['files'])==set(old['files']),'only_two_source_changes')
    calibration=w.bind(CYCLE/'runtime_calibration_001.json');baseline_cal=w.read(w.checked(calibration))
    candidate_cal=dict(baseline_cal,soft_seconds=3420.,hard_seconds=3600.,
        basis='Conservative longer projection runtime allowance registered before any source006 native; no forecast refit or parameter search.')
    candidate_cal_ref=w.save(WORKFLOW/'candidate_calibration.json',candidate_cal)
    tasks=[];pair_checks=[]
    for parent in PARENTS:
        baseline=w.read(CYCLE/f'runs/TF_bridge_all_005_TF-B1-60_P{parent}/plan.json');pair=[]
        for method,cal_ref in zip(METHODS,(calibration,candidate_cal_ref)):
            cal=w.read(w.checked(cal_ref))
            path=campaign.prepare(f'TF_horizon_repair_006_{method}_P{parent}',method=method,seed=parent,batch='initial',
                source_bundle=source,mapping=baseline['mapping'],calibration=cal_ref,transport_config=baseline['transport_config'],
                **{k:cal[k] for k in ('horizon','soft_seconds','hard_seconds','estimated_evidence_bytes')})
            tasks.append(w.bind(path/'plan.json'));pair.append(w.read(path/'plan.json'))
        pair_checks.append(dict(parent=parent,changes=validate_pair(*pair,flow)))
    BLOCK.mkdir()
    block=w.save(BLOCK/'block.json',dict(schema='g31.terminal_flow.projection_horizon_block.v1',phase='projection_horizon',
        source_bundle=source,parents=list(PARENTS),methods=list(METHODS),task_plans=tasks,batch='initial',pair_checks=pair_checks))
    reg=w.save(WORKFLOW/'registration.json',dict(schema='g31.terminal_flow.projection_horizon_workflow.v1',
        source_bundle=source,driver=w.bind(__file__),accounting=w.bind(ROOT/'outputs/terminal_flow_bins600_offline005.py'),
        dependencies=deps,pure_tests=tests,stages=[dict(name=BLOCK.name,phase='projection_horizon')],block=block,
        campaign_budget=w.bind(CYCLE/'campaign_budget.json'),historical_holdback=w.bind(DATA/'offline_historical_holdback_005_002.json'),
        source005=intent['source005'],changed_source_files=changed,preflight=admission,new_native_starts=8,
        audit_reserved_seconds=AUDIT_RESERVE,TEST_unlocked=False,R1_enabled=False,no_parameter_search=True))
    budget.append(CYCLE,'terminal_flow_projection_horizon_registered',registration=reg,original_budget_unchanged=True)
    print(json.dumps(reg),flush=True)

def dispatch(event,**values):
    with (WORKFLOW/'dispatch_001.jsonl').open('a',encoding='utf8') as f:
        f.write(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(),event=event,**values))+'\n')

def run():
    w=accounting();reg_ref=w.bind(WORKFLOW/'registration.json');reg=w.read(w.checked(reg_ref))
    need(reg['driver']==w.bind(__file__),'unchanged_registered_driver')
    for ref in reg['dependencies'].values():w.checked(ref)
    for key in ('accounting','pure_tests','campaign_budget','historical_holdback'):w.checked(reg[key])
    source_matches(w,reg['source_bundle']);campaign,flow,budget=modules()
    block=w.read(w.checked(reg['block']));plans=[w.read(w.checked(r)) for r in block['task_plans']]
    need([(p['parent']['parent_seed'],p['method']) for p in plans]==[(p,m) for p in PARENTS for m in METHODS],'fixed_eight_order')
    for i in range(0,8,2):validate_pair(plans[i],plans[i+1],flow)
    need(all(not (Path(p['output'])/'receipt.json').exists() for p in plans),'no_implicit_retry')
    admission=preflight(w,[p['hard_seconds'] for p in plans]);runner='terminal-flow-horizon006-'+secrets.token_hex(12)
    budget.append(CYCLE,'runner_open',runner_id=runner,purpose='eight_run_projection_horizon_repair',registration=reg_ref)
    safe=True;receipts=[];began=time.monotonic()
    try:
        dispatch('successor_process_started',registration=reg_ref,preflight=admission)
        for i,plan in enumerate(plans):
            w.checked(reg_ref);w.checked(reg['driver']);preflight(w,[p['hard_seconds'] for p in plans[i:]],owned_runner=runner)
            safe=False;receipt=campaign.launch(plan['output']);process=receipt['process']
            safe=process.get('windows_job_kill_on_close') is True and process.get('exitcode') is not None
            need(safe and process.get('exitcode')==0 and receipt['worker'].get('scientific_status')=='closed','native_not_closed_no_retry')
            receipts.append(w.bind(Path(plan['output'])/'receipt.json'))
            print(json.dumps(dict(parent=plan['parent']['parent_seed'],method=plan['method'],status='closed')),flush=True)
        source_matches(w,reg['source_bundle'])
        w.save(WORKFLOW/'completion.json',dict(status='closed',registration=reg_ref,blocks=[reg['block']],receipts=receipts,
            all_registered_development_tasks_closed=True,actual_driver_seconds=time.monotonic()-began,
            service_audit_pending=True,TEST_unlocked=False,R1_enabled=False))
        dispatch('successor_process_finished',registration=reg_ref,exitcode=0)
    except BaseException as exc:
        dispatch('dispatch_failed',registration=reg_ref,exception_type=type(exc).__name__,reason=str(exc));raise
    finally:
        if safe:budget.append(CYCLE,'runner_close',runner_id=runner)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['check','activate','prepare','run']);args=p.parse_args()
    if args.action=='check':print(json.dumps(preflight(accounting()),indent=2))
    else:globals()[args.action]()

if __name__=='__main__':main()
