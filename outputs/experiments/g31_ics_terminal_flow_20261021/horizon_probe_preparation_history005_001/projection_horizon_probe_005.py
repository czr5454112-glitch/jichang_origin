"""Bounded same-public-observation 600/1800 projection diagnosis; no native.

Uses the consumed 60-second B1 forecast unchanged. Excludes untimed claims,
retains every valid/excluded denominator, and never treats replay as service.
"""
from __future__ import annotations
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path

HORIZONS=(600.,1800.)

def load_support():
    p=Path(__file__).with_name('streaming_granularity_audit_005.py')
    spec=importlib.util.spec_from_file_location('horizon_probe_granularity_support',p)
    g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
    a,ref=g.load_support()
    return g,a,[g.bind(__file__),g.bind(p),ref]

def replay(decision,observation,forecast,plan,support,receipts,h,g):
    saved=decision['selection']['flow_plan']
    claims=saved.get('receiver_claims_deducted')
    g.need(type(claims) is dict,'receiver_claim_evidence_required')
    import math
    g.need(all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in claims.values()),'invalid_claim')
    if any(claims.values()): return dict(excluded='uncredited_claims')
    g.need(saved['config']==plan['transport_config'],'same_allocator')
    baseline=h['r0'].r0_priority_planner(observation)
    if baseline['intents']: return dict(excluded='priority_not_exhausted')
    prepared=h['opportunities'].prepare_current(observation,baseline,message_delay=2.)
    catalog=h['opportunities'].build_joint_catalog(prepared)
    g.need(catalog['catalog_id']==decision['legal_catalog_ref'],'same_legal_catalog')
    candidates={r['action_id']:r for r in catalog['candidates']}
    results={}
    for horizon in HORIZONS:
        projection=h['projection'].prepare_inventory_projection(observation,forecast=forecast,
            prepared_current=prepared,supply_mode='committed_only',horizon_seconds=horizon,
            arrival_support_contract=support,arrival_support_receipt=receipts[decision['owner_id']])
        selection=h['control'].TransportPolicy(config=saved['config'],recompute_period_seconds=60.).select(
            prepared,catalog,projection,policy_state={},decision_context=dict(decision_id=decision['decision_id'],tick=0))
        fp=selection['flow_plan']
        results[str(int(horizon))]=dict(action=g.choice_signature(candidates[selection['action_id']]),
            action_id=selection['action_id'],quantity=len(fp['chosen']),flows=fp['flows'],
            marginal_gain_profile=fp.get('marginal_gain_profile'),dispatch_profile=fp.get('dispatch_profile'),
            exact_verification=selection.get('verification'),source_offers=fp.get('source_offers'))
    left,right=results['600'],results['1800']
    return dict(owner=decision['owner_id'],at=decision['decision_time'],decision_id=decision['decision_id'],
        public_state_sha256=decision['public_observation_ref'],catalog_id=catalog['catalog_id'],
        observed_action=g.choice_signature(decision['requested_action']),
        baseline_replay_matches_observed=left['action']==g.choice_signature(decision['requested_action']),
        first_action_changed=left['action']!=right['action'],quantity_changed=left['quantity']!=right['quantity'],
        allocation_changed=left['flows']!=right['flows'],horizons=results)

def audit_run(row,a,h,g):
    directory=row['directory'];evidence={name:g.bind(directory/name) for name in g.EVIDENCE_FILES}
    plan,receipt,trajectory=h['flow'].closed_run(directory)
    g.need(evidence['plan.json']['sha256']==row['plan_binding']['sha256'],'registered_plan_changed')
    support=a.read(directory/'arrival_support_contract.json');receipts=a.read(directory/'arrival_support_receipts.json')
    decisions=a.DecisionJoin(trajectory['rows'],plan['activation'],plan['horizon'])
    observations=a.ObservationJoin(directory,[],h,plan['horizon']);counts=Counter();replays=[]
    try:
        for decision in h['stream'].iter_json_array_gz(directory/'decisions.json.gz'):
            counts['recorded_decisions']+=1
            if not decisions.accept(decision): counts['outside_evaluation_window']+=1;continue
            observation=observations.get(decision);counts['valid_decisions']+=1
            forecast=g.validate_forecast(decision,plan,h)
            if forecast is None: counts['missing_consumed_forecast']+=1;continue
            result=replay(decision,observation,forecast,plan,support,receipts,h,g)
            if 'excluded' in result: counts['excluded_'+result['excluded']]+=1;continue
            counts['replayed']+=1
            for key in ('first_action_changed','quantity_changed','allocation_changed','baseline_replay_matches_observed'):
                counts[key]+=result[key]
            for mode in ('600','1800'):
                counts['selected_transfers_'+mode]+=result['horizons'][mode]['action_id']!='a_noop'
                counts['nonzero_plans_'+mode]+=result['horizons'][mode]['quantity']>0
            replays.append(result)
        decisions.finish()
    finally: observations.finish()
    return dict(parent=plan['parent']['parent_seed'],counts=dict(counts),replays=replays,evidence=evidence,
        observations_read=observations.count,all_valid_decisions_joined=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest',type=Path,required=True)
    parser.add_argument('--workflow',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();g,a,producers=load_support()
    source=g.bind(args.source_manifest);root=a.verify_sources(source)
    g.need(root.name=='terminal_flow_runtime_005','source005_required')
    h=g.load_helpers(root,a);rows,status=g.inspect_runs(args.workflow,source,a,h)
    g.need(status['status']=='ready','four_closed_fine_DEV_required')
    if not args.execute:
        print(json.dumps(dict(status='ready',native_starts=0,science_executed=False)));return
    g.need(not args.output_dir.exists(),'fresh_output');args.output_dir.mkdir(parents=True)
    a.fresh(args.output_dir/'STARTED.json',dict(source=source,producers=producers,status='in_progress'))
    refs=[];counts=Counter()
    for parent,row in sorted(rows.items()):
        print(json.dumps(dict(parent=parent,stage='projection_horizon_probe')),flush=True)
        result=audit_run(row,a,h,g);counts.update(result['counts'])
        refs.append(a.fresh(args.output_dir/f'P{parent}_horizon_probe.json',result))
    a.verify_sources(source);a.verify_bindings(producers,'producer_changed')
    for ref in refs:a.verify_bindings(a.bound_read(ref)['evidence'].values(),'input_changed')
    _,end=g.inspect_runs(args.workflow,source,a,h);g.need(end==status,'registration_changed')
    final=a.fresh(args.output_dir/'projection_horizon_probe.json',dict(status='complete',counts=dict(counts),runs=refs,
        source_bundle=source,workflow=status['workflow'],analysis_producers=producers,
        only_axis='projection_horizon_seconds',horizons=list(HORIZONS),forecast_bins_seconds=60,
        forecast_horizon_seconds=1800,recompute_period_seconds=60,supply_mode='committed_only',
        model_fits=0,native_starts=0,TEST_opened=False,native_service_gain_measured=False,
        excluded_claims_not_unknown_zero=True,all_replayed_opportunities_saved=True,
        scope='Same observed policy state; alternative horizon is not a closed-loop native result. No horizon selected by this tool.'))
    a.fresh(args.output_dir/'COMPLETE.json',dict(status='complete',report=final,input_producer_source_rechecked=True))
    print(json.dumps(dict(report=final,counts=dict(counts))),flush=True)

if __name__=='__main__':main()
