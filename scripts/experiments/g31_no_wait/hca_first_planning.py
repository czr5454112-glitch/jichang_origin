"""Reconstruct HCA first planning eligibility from existing exact release telemetry.

For the no-fault frozen Java controller every generated new task is appended to
the planning list, and the fixed-size loop attempts every member once that tick.
Thus release_epoch is the first eligibility AND first attempt, independently of
the later successful admission. Original results and frozen code remain intact.
"""
from pathlib import Path
import argparse
from collections import defaultdict
import json
import sys

ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from scripts.experiments.g31_no_wait import hca
from scripts.experiments.g31_no_wait.headway_audit import input_ticks

def reconstruct(canonical,bags,releases):
    expected={str(r['segment_id']):r for r in canonical};actual={str(b['segment_id']):b for b in bags}
    keys={(int(r['task_id']),int(r['start']),int(r['goal'])):str(r['segment_id']) for r in canonical}
    if len(keys)!=len(canonical) or len(expected)!=len(canonical) or len(actual)!=len(bags) or actual.keys()!=expected.keys():
        raise ValueError('full canonical identity must be unique and exact')
    generated={}
    for event in releases:
        key=tuple(int(event[k]) for k in ('task_id','start','goal'))
        if key not in keys or keys[key] in generated:raise ValueError('release identity duplicate or unknown')
        generated[keys[key]]=float(event['release_epoch'])
    result=[]
    for sid,row in expected.items():
        bag=actual[sid];first=generated.get(sid)
        if any(int(bag[k])!=int(row[k]) for k in ('task_id','start','goal')):
            raise ValueError('physical bag identity disagrees with canonical segment')
        if bag.get('release_time')!=first:raise ValueError('physical bag release disagrees with original release trace')
        admitted=bag.get('admission',bag.get('admitted_time'));finish=bag.get('finish')
        if admitted is not None and (first is None or admitted<first):raise ValueError('successful plan precedes first attempt')
        canonical_time=input_ticks(row['pass_time'],1000000)
        if first is not None and input_ticks(first,1000000)<canonical_time:raise ValueError('generated before canonical release')
        result.append(dict(segment_id=sid,task_id=row['task_id'],leg=row['leg'],start=row['start'],goal=row['goal'],
            canonical_pass_time=row['pass_time'],first_planning_eligibility=first,first_attempt_time=first,
            successful_admission_time=admitted,finish=finish,observed_finish=bag.get('observed_finish',bag.get('finish_time')),
            completed=bag['completed'],
            canonical_hold_seconds=(input_ticks(first,1000000)-canonical_time)/1000000 if first is not None else None,
            planning_retry_wait_seconds=admitted-first if admitted is not None else None,
            tht_from_first_planning_seconds=finish-first if bag['completed'] and first is not None else None,
            network_after_success_seconds=finish-admitted if bag['completed'] and admitted is not None else None,
            evidence='release.csv; all new tasks appended and attempted once in same no-fault controller tick'))
    return result

def annotate(canonical,bags,releases):
    """Append explicit first-attempt evidence without changing original fields."""
    first_rows=reconstruct(canonical,bags,releases)
    by_segment={row['segment_id']:row for row in first_rows}
    result=[]
    for bag in bags:
        if 'first_planning_attempt_time' in bag:
            raise ValueError('input already has first planning attempt annotation')
        first=by_segment[str(bag['segment_id'])]
        result.append(dict(bag,
            first_planning_attempt_time=first['first_attempt_time'],
            preplanning_source_hold_seconds=first['canonical_hold_seconds'],
            first_planning_attempt_evidence='release.csv.release_epoch; same-tick no-fault planning-list append and first attempt'))
    return result

def annotate_run(run,canonical):
    output=run/'annotated_physical_bags.jsonl';receipt=run/'annotated_physical_bags_receipt.json'
    if output.exists() or receipt.exists():raise FileExistsError('append-only annotated output already exists')
    original=hca.audit.read_jsonl(run/'physical_bags.jsonl')
    rows=annotate(hca.audit.read_jsonl(canonical),original,hca.csv_rows(run/'run_01/release.csv'))
    with output.open('w',encoding='utf-8') as stream:
        for row in rows:stream.write(json.dumps(row,separators=(',',':'))+'\n')
    report=dict(schema='g31.hca.first_planning_annotation.v1',segments=len(rows),
        first_attempt_known=sum(r['first_planning_attempt_time'] is not None for r in rows),
        first_attempt_unknown=sum(r['first_planning_attempt_time'] is None for r in rows),
        original_fields_exact=all(all(new[k]==v for k,v in old.items()) for old,new in zip(original,rows)),
        activation_time_not_inferred=True,
        definitions={'first_planning_attempt_time':'release.csv.release_epoch: first same-tick planning-list append and attempt, never successful admission',
                     'preplanning_source_hold_seconds':'first planning attempt minus unchanged canonical pass_time; null for unreleased'},
        evidence={'canonical_sha256':hca.sha(canonical),'physical_bags_sha256':hca.sha(run/'physical_bags.jsonl'),
            'release_trace_sha256':hca.sha(run/'run_01/release.csv'),'output_sha256':hca.sha(output),'script_sha256':hca.sha(__file__)})
    hca.write(receipt,report);return report

def full_population_means(rows):
    by_task=defaultdict(list)
    for row in rows:by_task[int(row['task_id'])].append(row)
    complete=bool(by_task) and all(row['completed'] for row in rows)
    return {name:sum(row[name] for row in rows)/len(by_task)
        if complete and all(row[name] is not None for row in rows) else None
        for name in ('canonical_hold_seconds','planning_retry_wait_seconds','tht_from_first_planning_seconds','network_after_success_seconds')}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--canonical',type=Path,required=True)
    p.add_argument('--annotate-only',action='store_true',help='Write annotated_physical_bags and receipt, preserving original reconstruction outputs');a=p.parse_args()
    run=a.run.resolve();canonical=a.canonical.resolve();output=run/'first_planning_eligibility.jsonl';receipt=run/'first_planning_eligibility_receipt.json'
    if a.annotate_only:
        print(json.dumps(annotate_run(run,canonical),ensure_ascii=False));return
    if output.exists() or receipt.exists():raise FileExistsError('append-only reconstruction output already exists')
    rows=reconstruct(hca.audit.read_jsonl(canonical),hca.audit.read_jsonl(run/'physical_bags.jsonl'),hca.csv_rows(run/'run_01/release.csv'))
    with output.open('w',encoding='utf-8') as stream:
        for row in rows:stream.write(json.dumps(row,separators=(',',':'))+'\n')
    by_task=defaultdict(list)
    for row in rows:by_task[int(row['task_id'])].append(row)
    complete=[legs for legs in by_task.values() if all(r['completed'] for r in legs)]
    report=dict(schema='g31.hca.first_planning_eligibility.v1',segments=len(rows),businesses=len(by_task),generated=sum(r['first_planning_eligibility'] is not None for r in rows),
        completed_businesses=len(complete),successful_after_failed_attempts_segments=sum((r['planning_retry_wait_seconds'] or 0)>0 for r in rows),
        first_planning_equals_first_attempt_in_no_fault_controller=True,
        definitions={'first_planning_eligibility':'release.csv.release_epoch; same-tick append and fixed-count processing of every new planning-list member',
            'successful_admission':'later first successful full route; never substituted for first attempt',
            'canonical_hold':'first planning eligibility minus unchanged canonical pass_time; includes source-head blocking, ceil and causal gates before generation',
            'planning_retry_wait':'successful admission minus first attempt; included in revised THT',
            'THT':'sum over each business transport leg of continuous physical goal arrival minus first planning eligibility; excludes time between separate EBS legs'},
        full_population_business_mean_seconds=full_population_means(rows),
        largest_retry_examples=sorted([r for r in rows if r['planning_retry_wait_seconds'] is not None],key=lambda r:r['planning_retry_wait_seconds'],reverse=True)[:10],
        evidence={'canonical_sha256':hca.sha(canonical),'physical_bags_sha256':hca.sha(run/'physical_bags.jsonl'),
            'release_trace_sha256':hca.sha(run/'run_01/release.csv'),'output_sha256':hca.sha(output),'script_sha256':hca.sha(__file__)})
    hca.write(receipt,report);print(json.dumps({k:v for k,v in report.items() if k not in ('largest_retry_examples','definitions','evidence')},ensure_ascii=False))

if __name__=='__main__':main()
