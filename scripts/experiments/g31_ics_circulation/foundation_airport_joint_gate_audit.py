"""Read-only recomputation of the eight native gates and one observed mechanism.

This audit admits pretest execution, never model promotion or test unlock.
"""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import math
from pathlib import Path
from . import foundation_airport_joint_campaign as campaign
from .foundation_airport_inventory_spi_campaign import bound, read_bound
from .foundation_airport_joint_dataset import require, digest
from .foundation_airport_pair_dataset import window_cost


def gz(path):
    with gzip.open(path,'rt',encoding='utf8') as stream:
        return __import__('json').load(stream)


def audit(*, pure_receipt):
    pure=read_bound(pure_receipt)
    require(pure['exit_code']==0 and pure['source_unchanged'] is True,'closed_stable_pure_gates')
    paths=sorted((campaign.CYCLE/'runs').glob('G*/receipt.json'))
    require(len(paths)==8,'exact_eight_native_gate_receipts')
    rows=[]; cached={}
    for path in paths:
        directory=path.parent; receipt=campaign.common.read(path)
        plan=campaign.common.read(directory/'plan.json'); campaign.verify(plan)
        require(receipt['plan_sha256']==campaign.common.sha(directory/'plan.json'),'actual_plan_binding')
        require(receipt['process']['exitcode']==0 and receipt['worker']['scientific_status']=='closed',
            'closed_native_gate')
        data=read_bound(plan['input']); terminal=gz(directory/'terminal_evidence.json.gz')
        trajectory=gz(directory/'trajectory.json.gz')
        require(len(data['jobs'])==len(terminal['jobs'])==28506 and len(data['trays'])==len(terminal['trays'])==22,
            'fixed_full_workload_and_fleet')
        population_source='original_native_population_field'
        if 'population' not in terminal:
            # Gates kept all physical jobs/receipts but omitted this redundant
            # summary. Rebuild only the summary; snapshot_index still requires
            # every status, receipt, time and identity to agree independently.
            terminal['population']=dict(observed=sum(r['status']!='unreleased' for r in terminal['jobs']),
                completed=sum(r['status']=='completed' for r in terminal['jobs']))
            population_source='recomputed_from_preserved_native_job_statuses; original_summary_not_retained'
        cost=window_cost(data,terminal,start=plan['activation'],end=plan['horizon'])
        require(cost==receipt['worker']['cost'],'actual_full_population_cost_recomputed')
        require(math.isclose(cost['backlog_integral_bag_seconds'],trajectory['system_J'],abs_tol=1e-6,rel_tol=1e-12),
            'trajectory_cost_agrees')
        require(trajectory['business_population_complete'] and trajectory['logs_complete'],
            'closed_trajectory_evidence')
        choices=trajectory['rows']
        require(max(Counter((r['owner_id'],r['decision_time']) for r in choices).values(),default=0)<=1,
            'single_choice_per_owner_tick')
        transfers=[r for r in choices if r['requested_action']['kind']=='transfer']
        for row in transfers:
            require(row['actual_submission'] is not None and not row['physical_failure'],'actual_nonfailed_gate_transfer')
            require(row['request_id']==row['actual_submission']['request_id'],'real_request_identity')
            require(row['ack'],'actual_transfer_ack_evidence')
            if row['first_edge_event']:
                require(row['first_leg'] is not None,'edge_requires_actual_leg')
            if row['received_event']:
                require(row['first_edge_event'] is not None,'receipt_requires_actual_departure')
        rows.append(dict(task_id=plan['task_id'],method=plan['method'],seed=plan['parent']['parent_seed'],
            plan=bound(directory/'plan.json'),receipt=bound(path),trajectory=bound(directory/'trajectory.json.gz'),
            terminal=bound(directory/'terminal_evidence.json.gz'),cost=cost,
            wall_seconds=receipt['process']['wall_seconds'],
            peak_memory_bytes=receipt['worker']['peak_memory_bytes'],
            observed_joint_choices=len(choices),submitted_transfers=len(transfers),
            departed_transfers=sum(bool(r['first_edge_event']) for r in transfers),
            received_transfers=sum(bool(r['received_event']) for r in transfers),
            outstanding_transfers_retained=sum(not bool(r['received_event']) for r in transfers),
            funnel=receipt['worker']['funnel'],population_summary_source=population_source))
        if plan['task_id'] in ('G03_P2101_C00','G05_P2101_C10'):
            cached[plan['method']]=(trajectory,terminal)
    left,lterminal=cached['C00']; right,rterminal=cached['C10']
    a=next(r for r in left['rows'] if r['decision_time']==9060 and r['owner_id']=='owner:system_domestic')
    b=next(r for r in right['rows'] if r['decision_time']==9060 and r['owner_id']=='owner:system_domestic')
    require(a['public_observation_ref']==b['public_observation_ref'] and a['legal_catalog_ref']==b['legal_catalog_ref'],
        'same_public_opportunity')
    require(a['requested_action']['kind']=='noop' and b['requested_action']['tray_id']=='initial:149:0',
        'observed_action_difference')
    bag='projected:1x:21'
    arrival=next(e for e in rterminal['receipts'] if e['event']=='BAG_ARRIVAL' and e['business_bag_id']==bag)
    load0=next(e for e in lterminal['receipts'] if e['event']=='LOAD_START' and e['business_bag_id']==bag)
    load1=next(e for e in rterminal['receipts'] if e['event']=='LOAD_START' and e['business_bag_id']==bag)
    require(load1['tray_id']==b['requested_action']['tray_id'] and b['received_event']['time']<arrival['time'],
        'physical_prearrival_tray_used_by_observed_bag')
    mechanism=dict(case_selection='posthoc illustrative gate mechanism, not selection or significance evidence',
        policy='C10 predictive rule; no RL model fitted',owner_id=b['owner_id'],decision_time=b['decision_time'],
        public_observation_ref=b['public_observation_ref'],legal_catalog_ref=b['legal_catalog_ref'],
        requested_action=b['requested_action'],actual_submission=b['actual_submission'],acks=b['ack'],
        first_edge_event=b['first_edge_event'],received_event=b['received_event'],
        bag_arrival=arrival,reference_load=load0,predictive_load=load1,
        prearrival_lead_seconds=arrival['time']-b['received_event']['time'],
        observed_wait_reduction_seconds=load0['time']-load1['time'],
        short_window_J_delta=right['system_J']-left['system_J'],
        full_native_prechoice_state_equality_proven=False,system_service_improvement_proven=False)
    return dict(schema='g31.joint.native_gate_audit.v1',status='passed',approved_for_joint_stage=True,
        test_unlocked=False,pure_receipt=pure_receipt,native_gate_receipts=[bound(p) for p in paths],
        rows=rows,prearrival_mechanism=mechanism,
        limits=['H=18000 implementation gates, not full-day service evidence',
            'G01/G02 precede shared arrival-support contract; no cross-source causal service claim',
            'no learned RL model fit or RL benefit established',
            'posthoc illustration does not establish paired full-state causal attribution'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pure',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    require(not args.output.exists(),'fresh_audit_output')
    result=audit(pure_receipt=bound(args.pure)); result['audit_id']=digest(result)
    campaign.common.write(args.output,result)
    print(__import__('json').dumps(dict(status=result['status'],native_gates=len(result['rows']),
        output=bound(args.output),mechanism_wait_reduction_seconds=result['prearrival_mechanism']['observed_wait_reduction_seconds'])))


if __name__=='__main__': main()
