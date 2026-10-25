"""Read-only causal source phase/order diagnostics on existing HCA telemetry."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from scripts.experiments.g31_no_wait import hca


def analyze(canonical,bags):
    canonical=list(canonical);bags=list(bags)
    actual={str(b['segment_id']):b for b in bags}
    if len(actual)!=len(bags) or set(actual)!={str(r['segment_id']) for r in canonical}:
        raise ValueError('full canonical population must match')
    incoming={int(r['task_id']):actual[str(r['segment_id'])] for r in canonical if r['leg']=='storage_in'}
    sources=defaultdict(list)
    same_tick=[];causal_violations=[]
    for index,row in enumerate(canonical):
        bag=actual[str(row['segment_id'])]
        nominal=math.ceil(row['pass_time']);predecessor=None
        if row['leg']=='storage_out':
            predecessor=incoming[int(row['task_id'])].get('observed_finish')
            ready=max(nominal,predecessor) if predecessor is not None else None
            if predecessor is not None and bag.get('release_time') is not None:
                if bag['release_time']<predecessor:causal_violations.append(row['segment_id'])
                if bag['release_time']==predecessor:same_tick.append(row['segment_id'])
        else:ready=nominal
        sources[int(row['start'])].append(dict(segment_id=str(row['segment_id']),index=index,
            nominal=row['pass_time'],ready=ready,predecessor_report=predecessor,
            first_attempt=bag.get('release_time'),admission=bag.get('admission'),leg=row['leg']))
    order_violations=[];blocking=[];strict_ready_inversions=0
    for source,queue in sources.items():
        queue.sort(key=lambda row:(row['nominal'],row['index']))
        previous=None
        for row in queue:
            if previous is not None and row['first_attempt'] is not None:
                if previous['first_attempt'] is None or row['first_attempt']<=previous['first_attempt']:
                    order_violations.append([previous['segment_id'],row['segment_id']])
            previous=row
        suffix=[None]*len(queue);earliest=None
        for i in range(len(queue)-1,-1,-1):
            suffix[i]=earliest
            if queue[i]['ready'] is not None and (earliest is None or queue[i]['ready']<earliest['ready']):earliest=queue[i]
        for i,head in enumerate(queue):
            later=suffix[i]
            if head['ready'] is None or later is None or later['ready']>=head['ready']:continue
            strict_ready_inversions+=1
            previous_success=queue[i-1]['admission'] if i else None
            if head['first_attempt'] is None or (i and previous_success is None):continue
            # The generator runs before the controller in each integer epoch.
            available=previous_success+1 if previous_success is not None else -math.inf
            if head['leg']!='storage_out' or head['predecessor_report'] is None:continue
            if head['predecessor_report']<=max(math.ceil(head['nominal']),available):continue
            start=max(available,later['ready'])
            if start>=head['predecessor_report']:continue
            blocking.append(dict(source=source,head=head['segment_id'],head_nominal=head['nominal'],
                head_predecessor_report=head['predecessor_report'],head_first_attempt=head['first_attempt'],
                prior_same_source_success=previous_success,later_ready_bag=later['segment_id'],
                later_ready_time=later['ready'],later_first_attempt=later['first_attempt'],
                demonstrated_eligibility_block_seconds=head['predecessor_report']-start))
    return dict(schema='g31.hca.source_phase.v1',segments=len(canonical),
        source_order='stable chronological original nominal pass_time, preserving original file order for ties',
        phase='generator before controller; mask predicts same-tick inbound report from saved route.size()==2 and epoch>=goal.t1',
        causal_violations=causal_violations,source_generation_order_violations=order_violations,
        same_epoch_inbound_report_and_outbound_first_attempt=len(same_tick),same_epoch_examples=same_tick[:10],
        source_heads_with_later_strictly_earlier_ready_task=strict_ready_inversions,
        causally_unready_ebs_heads_blocking_a_later_ready_task=len(blocking),
        largest_eligibility_blocks=sorted(blocking,key=lambda r:r['demonstrated_eligibility_block_seconds'],reverse=True)[:20],
        interpretation='Eligibility/order evidence on the observed HCA inbound schedule, not counterfactual route feasibility or recoverable THT. G31 activation-order queue is a different source discipline. Do not sum overlapping pairwise block durations.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--canonical',type=Path,required=True);a=p.parse_args()
    output=a.run/'source_phase_audit.json'
    if output.exists():raise FileExistsError(output)
    result=analyze(hca.audit.read_jsonl(a.canonical),hca.audit.read_jsonl(a.run/'physical_bags.jsonl'))
    result['evidence']={'canonical_sha256':hca.sha(a.canonical),'physical_bags_sha256':hca.sha(a.run/'physical_bags.jsonl'),'script_sha256':hca.sha(__file__)}
    hca.write(output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('largest_eligibility_blocks','evidence')},ensure_ascii=False))


if __name__=='__main__':main()
