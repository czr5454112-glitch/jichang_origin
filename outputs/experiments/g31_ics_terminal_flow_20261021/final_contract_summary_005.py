"""Summarize completed, SHA-bound audits; never infer promotion or run native."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

def need(ok,reason):
    if not ok:raise ValueError('contract_summary:'+reason)

def bind(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),sha256=sha)

def read(path):
    path=Path(path)
    with (gzip.open(path,'rt',encoding='utf8') if path.suffix=='.gz' else path.open(encoding='utf8')) as stream:
        return json.load(stream)

def bound_read(ref):
    need(bind(ref['path'])['sha256']==ref['sha256'],'bound_bytes_changed')
    return read(ref['path'])

def first_batches(report):
    """One actual first submission per multi-item plan, including failed/censored.

    A later successful item is never substituted for an unsuccessful first item.
    Replanned plans and repeated methods remain separate descriptive observations.
    """
    lifecycle={}
    for row in report['selected_transfer_lifecycle']:
        request=row['request_id']
        if request is not None:
            need(request not in lifecycle,'duplicate_lifecycle_request')
            lifecycle[request]=row
    rows=[]
    plans=report['plan_order_chain']['plans'];chains=report['plan_order_chain']['order_chains']
    for plan in plans:
        if plan['item_count']<=1:continue
        proposed=[r for r in chains if r['plan_id']==plan['plan_id']]
        submitted=[r for r in proposed if r.get('actual_submission') is not None and r.get('request_id') is not None]
        submitted.sort(key=lambda r:(r['actual_submission']['issued_at'],r['request_id']))
        base=dict(plan_id=plan['plan_id'],plan_created_at=plan['information_asof'],item_count=plan['item_count'],
            proposed_order_count=len(proposed),actual_submissions=len(submitted),first_actual_submission=None)
        if submitted:
            chain=submitted[0];request=chain['request_id'];need(request in lifecycle,'first_submission_without_lifecycle')
            life=lifecycle[request];actual=chain['actual_submission']['issued_at']
            base['first_actual_submission']=dict(request_id=request,decision_id=chain['decision_id'],
                source=chain['source'],destination=chain['destination'],tray_id=chain['physical_tray_id'],
                submitted_at=actual,plan_to_submission_seconds=actual-plan['information_asof'],
                nominal_arrival=life['nominal_arrival'],first_edge_event=life['first_edge_event'],
                received=life['received'],failed=life['failed'],right_censored=life['right_censored'],
                eta_error_seconds=life['eta_error_seconds'],
                actual_arrival=(life['final_native']['received_at'] if life['received'] else None),
                unreceived_eta_lateness_lower_bound_seconds=life.get('unreceived_eta_lateness_lower_bound_seconds'))
        rows.append(base)
    return rows

def advisory_timing(report, horizon):
    """Describe original recommendations without changing order attribution."""
    need(type(horizon) in (int,float) and horizon>0, 'positive_projection_horizon')
    rows=[]
    for plan in report['plan_order_chain']['plans']:
        profile=plan['dispatch_profile']
        need(len(profile)==plan['item_count'], 'complete_original_dispatch_profile')
        need(len({r['tray_id'] for r in profile})==len(profile), 'unique_advisory_trays')
        for item in profile:
            later=item['submit_at']>plan['information_asof']
            rows.append(dict(plan_id=plan['plan_id'], owner=plan['owner_scope'],
                information_asof=plan['information_asof'], valid_until=plan['valid_until'],
                projection_end=plan['information_asof']+horizon,
                tray_id=item['tray_id'],source=item['source'],destination=item['destination'],
                submit_at=item['submit_at'],estimated_arrival=item['estimated_arrival'],later_slot=later,
                submit_at_or_after_plan_expiry=item['submit_at']>=plan['valid_until'],
                arrival_after_projection_end=item['estimated_arrival']>plan['information_asof']+horizon))
    return dict(scope='Unique plan advisory items, not new native orders or independent scenes.',
        profile_kind='original_solver_dispatch_profile; not the adapter execution_dispatch_profile',
        items=len(rows),later_slot_items=sum(r['later_slot'] for r in rows),
        at_or_after_expiry=sum(r['submit_at_or_after_plan_expiry'] for r in rows),
        arrival_after_projection_end=sum(r['arrival_after_projection_end'] for r in rows),
        item_rows=rows, future_suggestions_require_fresh_replanning=True,
        original_order_attribution_unchanged=True)

def summarize(complete):
    producer=bind(__file__)
    marker_ref=bind(complete);marker=bound_read(marker_ref)
    need(marker['status']=='complete','complete_science_required')
    report=bound_read(marker['final_report'])
    need(report['status']=='complete' and report['registered_runs']==28 and report['scientific_per_bag_pairs']==24,
        'complete_registered_science_matrix')
    rows=[];seen=set();references=[marker_ref,marker['final_report']]
    for entry in report['runs']:
        key=entry['parent'],entry['method'];need(key not in seen,'duplicate_run');seen.add(key)
        run=bound_read(entry['evidence']);references.append(entry['evidence'])
        need((run['parent'],run['method'])==key,'run_identity')
        plan_ref=run['evidence']['plan.json']; native_plan=bound_read(plan_ref);references.append(plan_ref)
        need(native_plan['parent']['parent_seed']==key[0] and native_plan['method']==key[1], 'native_plan_identity')
        multi=first_batches(run)
        counts=Counter('unsubmitted' if r['first_actual_submission'] is None else
            'received' if r['first_actual_submission']['received'] else
            'failed' if r['first_actual_submission']['failed'] else
            'right_censored' if r['first_actual_submission']['right_censored'] else 'other_unresolved'
            for r in multi)
        rows.append(dict(parent=key[0],method=key[1],evidence=entry['evidence'],
            decision_counts=run['behavior']['decision_counts'],plan_counts=run['behavior']['plan_counts'],
            cache=run['behavior'].get('cache'),timing_counts=run['timing']['counts'],
            ranking_rows=run['timing']['ranking_rows'],ranking_rows_truncated=run['timing']['ranking_rows_truncated'],
            multiple_plan_first_batches=multi,multiple_plan_first_outcomes=dict(counts),
            advisory_timing=advisory_timing(run,native_plan['projection_horizon_seconds']),
            selected_transfer_lifecycle=run['selected_transfer_lifecycle'],runtime=run['runtime'],
            measured_callback=run['timing']['measured_callback']))
    need(len(seen)==28,'all_runs_required')
    for ref in references:bound_read(ref)
    need(bind(__file__)==producer,'producer_changed_during_summary')
    return dict(schema='g31.terminal_flow.contract_summary.v1',status='descriptive_completed_audit_summary',
        analysis_driver=producer,inputs=references,runs=rows,pair_summaries=report['pair_summaries'],
        aggregates=report['aggregates'],native_starts=0,raw_native_or_observation_files_reparsed=False,
        original_audit_reports_not_modified=True,posthoc_evaluator_only=True,
        temporal_trigger_judgment='requires explicit interpretation of full denominators and coverage',
        conditional_release_or_time_varying_receiver_counterfactual='not established by these summaries',
        repeated_methods_and_shifted_parents_are_not_independent_airport_days=True,
        promotion_approved=False,TEST_unlocked=False,R1_enabled=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--complete',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();need(not args.output.exists(),'fresh_summary_output')
    result=summarize(args.complete)
    with args.output.open('x',encoding='utf8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(bind(args.output)))

if __name__=='__main__':main()
