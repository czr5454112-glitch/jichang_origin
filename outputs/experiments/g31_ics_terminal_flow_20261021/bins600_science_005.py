"""Complete four-parent 600-bin audit, eight same-source per-bag pairs.

Reads only closed native outputs. Original source005 run-audit equations and
service comparison are unchanged. Existing baseline behavior audits are reused
only through their successful final report. No native/model/ledger operations.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
DATA=Path(__file__).resolve().parent
CYCLE=ROOT/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'
DIRECTORY=CYCLE/'terminal_flow/bins600_full_005'
OLD_DRIVER_SHA='fa3518b68ed3e0c6abea0293752ba58c922c53bc290bfe31ea1a1d9bf96ca6c2'

def audit_module():
    import hashlib
    path=DATA/'final_science_audit_004.py'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=OLD_DRIVER_SHA:
        raise ValueError('bins600_science:original_audit_driver_changed')
    loader=importlib.util.spec_from_file_location('bins600_original_audit',path)
    a=importlib.util.module_from_spec(loader);loader.loader.exec_module(a)
    return a

def inspect(a,source_ref,workflow_ref,h):
    reg_ref=a.bind(DIRECTORY/'registration.json');reg=a.bound_read(reg_ref)
    intent=a.bound_read(reg['intent']);done_ref=a.bind(DIRECTORY/'NATIVE_COMPLETE.json');done=a.bound_read(done_ref)
    a.need(reg['schema']=='g31.terminal_flow.bins600_extension.v1' and reg['source_bundle']==source_ref
        and intent['workflow']==workflow_ref and done['registration']==reg_ref and done['status']=='closed',
        'closed_registered_600_extension')
    a.need(reg['parents']==list(a.PARENTS) and len(reg['task_plans'])==4 and len(done['receipts'])==4,
        'four_full_600_native_tasks')
    marker=a.bound_read(intent['baseline_science']);baseline=a.bound_read(marker['final_report'])
    a.need(marker['status']=='complete' and baseline['status']=='complete' and baseline['source_bundle']==source_ref
        and baseline['workflow']==workflow_ref and baseline['registered_runs']==28, 'same_completed_baseline_science')
    rows={};baseline_runs={}; refs=[reg_ref,reg['intent'],done_ref,intent['baseline_science'],marker['final_report']]
    for item in baseline['runs']:
        key=item['parent'],item['method']
        if key[1] not in ('TF-B1-60','TF-B1-300'): continue
        a.need(key not in baseline_runs,'duplicate_baseline_report')
        report=a.bound_read(item['evidence'])
        a.need((report['parent'],report['method'])==key,'baseline_report_identity')
        baseline_runs[key]=report;refs.append(item['evidence'])
        plan=a.bound_read(report['evidence']['plan.json'])
        rows[key]=dict(plan=plan,directory=Path(report['evidence']['plan.json']['path']).parent)
    for plan_ref,receipt_ref in zip(reg['task_plans'],done['receipts']):
        p=a.bound_read(plan_ref);key=p['parent']['parent_seed'],p['method'];directory=Path(plan_ref['path']).parent
        a.need(key not in rows and key[0] in a.PARENTS and key[1]=='TF-B1-600'
            and p['source_bundle']==source_ref and p['horizon']==59400. and p['activation']==7200.
            and p['parent']['split']=='dev', '600_full_plan_contract')
        a.need(a.bind(directory/'receipt.json')==receipt_ref and not h['campaign'].method_contract_errors(p),
            '600_receipt_and_method_binding')
        h['flow'].closed_run(directory)
        rows[key]=dict(plan=p,directory=directory)
        for method in ('TF-B1-60','TF-B1-300'):
            a.pair_contract(rows[(key[0],method)]['plan'],p,('forecast_bin_edges_seconds',),h['campaign'].comparison_contract)
        refs.extend([plan_ref,receipt_ref])
    a.need(len(rows)==12 and len(baseline_runs)==8,'complete_four_parent_three_method_matrix')
    return rows,baseline_runs,refs

def execute(a,source_ref,workflow_ref,h,output):
    producer=a.bind(__file__);old=a.bind(DATA/'final_science_audit_004.py')
    rows,reports,refs=inspect(a,source_ref,workflow_ref,h)
    a.need(not output.exists(),'fresh_600_science_output')
    output.mkdir(parents=True)
    a.fresh(output/'pending.json',dict(status='in_progress',source_bundle=source_ref,analysis_driver=producer))
    run_refs=[];pair_refs=[];summaries=[]
    for parent in a.PARENTS:
        print(json.dumps(dict(stage='600_run_audit',parent=parent)),flush=True)
        key=(parent,'TF-B1-600');report=a.run_audit(rows[key],h)
        run_refs.append(a.fresh(output/f'P{parent}_TF-B1-600_behavior_timing.json.gz',report))
        reports[key]=report
    for method in ('TF-B1-60','TF-B1-300'):
        for parent in a.PARENTS:
            print(json.dumps(dict(stage='600_per_bag_pair',parent=parent,reference=method)),flush=True)
            left,right=rows[(parent,method)],rows[(parent,'TF-B1-600')]
            result=h['service'].compare_runs(left['directory'],right['directory'])
            a.need(result['population']==28506 and result['population_exclusions']==0,'complete_28506_population')
            result['parent']=parent
            result['registered_pair_axis']=a.pair_contract(left['plan'],right['plan'],('forecast_bin_edges_seconds',),h['campaign'].comparison_contract)
            result['actual_order_and_decision_changes']=a.compare_choices(reports[(parent,method)],reports[(parent,'TF-B1-600')])
            result['local_service_by_original_input_node']=a.local_service(result['per_bag'],a.bound_read(left['plan']['input'])['jobs'])
            result['independent_airport_day_claim']=False
            pair_refs.append(a.fresh(output/f'P{parent}_{method}_to_TF-B1-600_per_bag.json.gz',result))
            summaries.append({k:v for k,v in result.items() if k not in ('per_bag','physical_contract','evidence','physical_progress')})
    aggregates=[dict(reference_method=method,candidate_method='TF-B1-600',
        **a.aggregate_pairs([r for r in summaries if r['reference_method']==method])) for method in ('TF-B1-60','TF-B1-300')]
    for report in reports.values(): a.verify_bindings(list(report['evidence'].values()),'600_input_changed')
    a.verify_sources(source_ref);a.bound_read(workflow_ref)
    a.verify_bindings(refs+run_refs+pair_refs+[producer,old],'600_binding_changed')
    final=dict(schema='g31.terminal_flow.bins600_science.v1',status='complete',source_bundle=source_ref,workflow=workflow_ref,
        analysis_driver=producer,original_science_driver=old,dependencies=refs,runs=run_refs,per_bag_pair_evidence=pair_refs,
        pair_summaries=summaries,aggregates=aggregates,new_native_runs=4,offline_native_starts=0,
        scientific_per_bag_pairs=8,source005_baseline_reports_reused=True,all_inputs_rechecked=True,
        strict_per_bag_nonharm_certified=False,promotion_approved=False,TEST_unlocked=False,R1_enabled=False,
        sampling_scope='four same-template-derived DEV parents; no independent airport-day inference')
    ref=a.fresh(output/'bins600_science_report.json',final)
    a.fresh(output/'COMPLETE.json',dict(status='complete',final_report=ref))
    print(json.dumps(ref),flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest',required=True,type=Path)
    parser.add_argument('--workflow',required=True,type=Path)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args();a=audit_module()
    source=a.bind(args.source_manifest);root=a.verify_sources(source);workflow=a.bind(args.workflow)
    h=a.load_helpers(root)
    if args.execute:
        a.need(args.output_dir is not None,'explicit_output_required')
        execute(a,source,workflow,h,args.output_dir)
    else:
        rows,_,_=inspect(a,source,workflow,h)
        print(json.dumps(dict(status='ready',runs=len(rows),science_executed=False)))

if __name__=='__main__': main()
