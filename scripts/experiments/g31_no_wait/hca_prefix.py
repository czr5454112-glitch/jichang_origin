"""Reconstruct a labelled observation-window prefix of a completed HCA run.

This never runs Java. Only plans committed by the cutoff are retained. Their
already-known future route/finish is still a prediction, not observed completion.
Actual goal reports, first attempts and admissions after cutoff are censored.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from scripts.experiments.g31_no_wait import hca
from scripts.experiments.g31_no_wait.headway_audit import audit_headway,input_ticks
from scripts.experiments.g31_no_wait.source_policy_audit import audit_source_policy
from scripts.experiments.g31_no_wait.tht_metrics import audit_tht


def _finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def prefix_bags(canonical,bags,cutoff):
    """Project complete canonical identities to information available at cutoff.

    ``finish`` retains the goal prediction of an already committed route, as in
    the original physical_bags schema. ``actual_finish`` is null until an actual
    goal report has occurred. No outcome or plan of a later admission is copied.
    """
    if not _finite(cutoff) or cutoff<0:raise ValueError('invalid cutoff')
    canonical=list(canonical);bags=list(bags)
    expected={str(r['segment_id']):r for r in canonical};actual={str(b['segment_id']):b for b in bags}
    if len(expected)!=len(canonical) or len(actual)!=len(bags) or expected.keys()!=actual.keys():
        raise ValueError('full canonical identity must be exact')
    result=[]
    for sid,row in expected.items():
        original=actual[sid]
        if any(original.get(k)!=row[k] for k in ('task_id','start','goal')):
            raise ValueError('canonical identity differs')
        if 'first_planning_attempt_time' not in original:
            raise ValueError('verified first planning attempt required; no fallback')
        first=original['first_planning_attempt_time'];admission=original.get('admission')
        finish=original.get('finish');observed=original.get('observed_finish')
        for clock in (first,admission,finish,observed):
            if clock is not None and not _finite(clock):raise ValueError('invalid source clock')
        if original.get('release_time')!=first:raise ValueError('first attempt differs from proved release trace')
        if admission is not None and (first is None or admission<first):raise ValueError('invalid admission ordering')
        if finish is not None and (admission is None or finish<admission):raise ValueError('invalid planned goal ordering')
        if observed is not None and (finish is None or observed<finish):raise ValueError('invalid actual goal report')
        if (original.get('completed') is True)!=(observed is not None):raise ValueError('completion/report mismatch')
        first=first if first is not None and first<=cutoff else None
        admission=admission if admission is not None and admission<=cutoff else None
        completed=observed is not None and observed<=cutoff
        if completed and admission is None:raise ValueError('completed prefix without prior admission')
        route=copy.deepcopy(original.get('route',[])) if admission is not None else []
        if admission is not None and (not route or finish is None):raise ValueError('missing committed route evidence')
        bag=dict(segment_id=sid,task_id=row['task_id'],start=row['start'],goal=row['goal'],
            release_time=first,admitted_time=admission,completed=completed,
            finish_time=observed if completed else None,
            source_queue_delay=admission-first if admission is not None else None)
        if admission is not None:
            for field in ('edge_travel_time_seconds','node_service_time_seconds','junction_queue_wait_seconds'):
                if field in original:bag[field]=original[field]
        bag.update(route=route,admission=admission,finish=finish if admission is not None else None,
            observed_finish=observed if completed else None,
            commit_ordinal=original.get('commit_ordinal') if admission is not None else None,
            first_planning_attempt_time=first,
            preplanning_source_hold_seconds=(input_ticks(first,1000000)-input_ticks(row['pass_time'],1000000))/1000000 if first is not None else None,
            first_planning_attempt_evidence='release.csv.release_epoch; same-tick no-fault planning-list append and first attempt',
            actual_finish=finish if completed else None)
        result.append(bag)
    return result


def clip_csv_rows(rows,clock,cutoff):
    """Retain original order/fields; future successful plans remain excluded."""
    result=[]
    for row in rows:
        stamp=float(row[clock])
        if not math.isfinite(stamp):raise ValueError('nonfinite event time')
        if stamp<=cutoff:result.append(dict(row))
    return result


def clip_report_lines(raw,cutoff):
    result=[]
    for line in raw.splitlines(keepends=True):
        if not line.strip():continue
        stamp=float(line.split()[-1])
        if not math.isfinite(stamp):raise ValueError('nonfinite report epoch')
        if stamp<=cutoff:result.append(line)
    return ''.join(result)


def _write_jsonl(path,rows):
    with path.open('w',encoding='utf-8') as stream:
        for row in rows:stream.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')


def _write_csv(path,rows,fields):
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def _request(profile,cutoff,speed):
    return {'max_simulation_time':float(cutoff),'minimum_service_seconds':0.0,'complete_on_goal_arrival':True,
        'node_records':[[n['location'],n['node_type'],n['service_time'],n.get('x',0),n.get('y',0),n['outgoing']] for n in profile['nodes']],
        'edge_records':[[e['start'],e['end'],e['length'],speed] for e in profile['edges']]}


def project(run,output,cutoff,reference=None):
    run=Path(run).resolve();output=Path(output).resolve()
    if output.exists():raise FileExistsError('prefix output must be new')
    if not isinstance(cutoff,int) or isinstance(cutoff,bool):raise ValueError('cutoff must be an integer controller epoch')
    manifest=hca.read(run.parent/'manifest.json');status=hca.read(run/'run_01/run_status.json')
    source_horizon=hca.read(run/'continuous_analysis.json')['horizon']
    if status.get('status')!='complete':raise ValueError('source Java run is not complete')
    if status.get('fault_schedule','none')!='none':raise ValueError('prefix helper is limited to no-fault fixed routes')
    if not status['start_epoch']<=cutoff<=source_horizon:raise ValueError('cutoff outside executed source window')
    if not manifest.get('physical_adapter',{}).get('contract'):raise ValueError('uniform physical HCA required')
    hca.verify(run.parent)
    cell=manifest['cells'][run.name];canonical=Path(cell['canonical']);rows=hca.audit.read_jsonl(canonical)
    input_bags=run/'annotated_physical_bags.jsonl';source_bags=hca.audit.read_jsonl(input_bags)
    original_fields={k for b in source_bags for k in b}-{'first_planning_attempt_time','preplanning_source_hold_seconds','first_planning_attempt_evidence','actual_finish'}
    bags=prefix_bags(rows,source_bags,cutoff);del source_bags
    profile=hca.read(cell['map']['draft_profile']);request=_request(profile,cutoff,manifest['speed_mps'])
    output.mkdir(parents=True);(output/'run_01').mkdir()
    provenance={'schema':'g31.hca.derived_prefix.v1','status':'building','independent_java_run':False,
        'source_run':str(run),'source_horizon':source_horizon,'horizon':cutoff,
        'canonical_sha256':hca.sha(canonical),'source_annotated_bags_sha256':hca.sha(input_bags),
        'helper_sha256':hca.sha(__file__),'source_population_segments':len(rows),
        'timing':{'prefix_runtime_available':False,'source_profile':str(run/'run_01/planning_profile.json'),
            'rule':'Source full-run CPU/wall cannot be allocated to this prefix without per-epoch timing telemetry.'},
        'finish_semantics':'finish is the previously committed route prediction and can exceed cutoff; completed/observed_finish/actual_finish require a goal report by cutoff.',
        'scope':'No-fault HCA once-committed full routes only. This helper cannot project a rolling planner from only its final routes.',
        'max_epoch_reasoning':'Frozen wrapper uses maxEpochs only for the controller loop bound and metadata; it is not passed into Astar or physical reservations.'}
    hca.write(output/'manifest.json',provenance)
    _write_jsonl(output/'annotated_physical_bags.jsonl',bags)
    _write_jsonl(output/'physical_bags.jsonl',[{k:v for k,v in b.items() if k in original_fields} for b in bags])
    events={};event_hashes={}
    for name,clock in (('release.csv','release_epoch'),('routes.csv','epoch')):
        source=run/'run_01'/name
        with source.open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream);fields=reader.fieldnames;filtered=clip_csv_rows(reader,clock,cutoff)
        _write_csv(output/'run_01'/name,filtered,fields);events[name]=filtered;event_hashes[name]=hca.sha(source)
    text_events={}
    for name in ('output.txt','outputstarttime.txt'):
        source=run/'run_01'/name;filtered=clip_report_lines(source.read_text(encoding='utf-8'),cutoff)
        (output/'run_01'/name).write_text(filtered,encoding='utf-8');text_events[name]=filtered;event_hashes[name]=hca.sha(source)
    # Cross-check the clipped clocks against independent original event streams.
    if len(events['release.csv'])!=sum(b['first_planning_attempt_time'] is not None for b in bags):raise ValueError('release prefix coverage mismatch')
    if len(events['routes.csv'])!=sum(b['admission'] is not None for b in bags):raise ValueError('committed route prefix coverage mismatch')
    if len(text_events['output.txt'].splitlines())!=sum(b['completed'] for b in bags):raise ValueError('goal report prefix coverage mismatch')
    physical=audit_headway(rows,bags,profile,time_grid_seconds=1e-6,strict_endpoint_resources=True,edge_entry_headway_seconds=2)
    physical['prefix_plan_scope']='All and only routes committed by cutoff, including their future reservations known at commit; future admissions excluded.'
    source_policy=audit_source_policy(rows,bags,source_generation_interval=1,release_quantum=1,source_fifo_order='canonical')
    metrics=audit_tht(rows,bags,horizon=cutoff)
    observed=hca.audit.analyze(rows,bags,request)
    continuous=[]
    for bag in bags:
        item=dict(bag);done=bag['admission'] is not None and bag['finish']<=cutoff
        item['completed']=done;item['finish_time']=bag['finish'] if done else None;continuous.append(item)
    continuous_analysis=hca.audit.analyze(rows,continuous,request)
    for name,value in [('physical_headway_audit.json',physical),('source_policy_audit_001.json',source_policy),
                       ('tht_metrics.json',metrics),('analysis.json',observed),('continuous_analysis.json',continuous_analysis)]:hca.write(output/name,value)
    comparison=None
    if reference is not None:
        reference=Path(reference).resolve()
        if hca.read(reference/'continuous_analysis.json')['horizon']!=cutoff:raise ValueError('reference horizon mismatch')
        checks={name:events[name]==hca.csv_rows(reference/'run_01'/name) for name in events}
        checks.update({name:text_events[name]==(reference/'run_01'/name).read_text(encoding='utf-8') for name in text_events})
        reference_bags=prefix_bags(rows,hca.audit.read_jsonl(reference/'annotated_physical_bags.jsonl'),cutoff)
        mismatch=[a['segment_id'] for a,b in zip(bags,reference_bags) if a!=b]
        checks['all_bag_fields_exact']=not mismatch
        checks['continuous_business_summary_exact']=continuous_analysis['business']==hca.read(reference/'continuous_analysis.json')['business']
        checks['observed_business_summary_exact']=observed['business']==hca.read(reference/'analysis.json')['business']
        comparison={'passed':all(checks.values()),'reference':str(reference),'checks':checks,'bag_mismatch_count':len(mismatch),'bag_mismatch_examples':mismatch[:20],
            'event_comparison':'Original ordered CSV fields and text report lines exactly equal, not just aggregate counters.'}
        hca.write(output/'reference_parity.json',comparison)
    passed=physical['passed'] and source_policy['passed'] and metrics['passed'] and (comparison is None or comparison['passed'])
    provenance.update(status='complete' if passed else 'audit_failed',passed=passed,
        source_event_hashes=event_hashes)
    hca.write(output/'manifest.json',provenance)
    hca.write(output/'run_01/run_status.json',{'schema':'g31.hca.derived_prefix.v1','status':'derived_prefix','independent_java_run':False,
        'source_run':str(run),'source_horizon':source_horizon,'horizon':cutoff,'wall_seconds':None})
    if not passed:raise ValueError('prefix audit/parity failed; evidence retained')
    return {'output':str(output),'passed':passed,'segments':len(bags),'attempted':sum(b['first_planning_attempt_time'] is not None for b in bags),
        'admitted':sum(b['admission'] is not None for b in bags),'completed':sum(b['completed'] for b in bags),
        'user_tht_full_population_available':metrics['user_tht_full_population_available'],'reference_parity':comparison}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--cutoff',required=True,type=int)
    parser.add_argument('--reference',type=Path);args=parser.parse_args()
    print(json.dumps(project(args.run,args.output,args.cutoff,args.reference),ensure_ascii=False))


if __name__=='__main__':main()
