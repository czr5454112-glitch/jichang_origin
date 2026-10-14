"""Read the immutable executed runs; no native or policy execution."""
from pathlib import Path
from collections import Counter,defaultdict
import gzip,hashlib,json,statistics
ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/'outputs/experiments/g31_ics_long_term_20261013/event_protocol_original24_015_001/original24'
def dist(xs):
    xs=sorted(xs)
    return dict(n=len(xs),sum_ms=sum(xs),mean_ms=statistics.mean(xs) if xs else 0,
        p50_ms=xs[len(xs)//2] if xs else 0,p95_ms=xs[int((len(xs)-1)*.95)] if xs else 0,
        max_ms=max(xs,default=0),over100=sum(x>100 for x in xs))
summary={}
for policy in ['periodic_predictive','event_predictive','event_reactive','event_joint']:
    path=BASE/policy/'run.json.gz'
    with gzip.open(path,'rt',encoding='utf-8') as f:run=json.load(f)
    owner_rows=defaultdict(list);prep=[]
    for row in run['control_records']:
        if 'owner_id' in row:owner_rows[row['owner_id']].append(row)
        else:
            prep.append(row['preparation_compute_ms'])
            for decision in row['owner_decisions']:owner_rows[decision['owner_id']].append(dict(decision,at=row['at']))
    owners={owner:dict(compute=dist([r.get('compute_wall_ms',r.get('compute_ms')) for r in rows]),
        causes=dict(Counter(key for r in rows for key in r.get('causes',{})))) for owner,rows in owner_rows.items()}
    bins=[]
    for lo,hi in [(0,24000),(24000,36000),(36000,45000),(45000,86401)]:
        rows=[r for values in owner_rows.values() for r in values if lo<=r['at']<hi]
        bins.append(dict(start=lo,end=hi,compute=dist([r.get('compute_wall_ms',r.get('compute_ms')) for r in rows]),
            empty_actions=sum(not r.get('attempts') and not r.get('publications') and not r.get('service_actions') for r in rows)))
    rows=[r for values in owner_rows.values() for r in values]
    slow=[dict(owner_id=r['owner_id'],at=r['at'],compute_ms=r.get('compute_wall_ms',r.get('compute_ms')),
        causes=r.get('causes'),refreshed=len(r.get('refreshed',[]))) for r in rows if r.get('compute_wall_ms',r.get('compute_ms'))>100]
    costs=sum(x['compute']['sum_ms'] for x in owners.values())+sum(prep)
    native=sum(r['wall_ms'] for r in run['native_batches'])
    summary[policy]=dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),wall_seconds=run['wall_seconds'],
        owner_activations=len(rows),owner_and_preparation_sum_ms=costs,native_batches=dist([r['wall_ms'] for r in run['native_batches']]),
        submit_subset=dist([r['submit_compute_ms'] for r in run['client_calls']]),
        unpartitioned_wall_ms=1000*run['wall_seconds']-costs-native,
        preparation=dist(prep),owners=owners,time_bins=bins,over100_owner_calls=slow,
        requests=[dict(kind=kind,retry=retry,count=n) for (kind,retry),n in Counter((r['kind'],r['retry']) for r in run['client_calls']).items()],
        final_outbox=len(run['controller_state']['client']['outbox']))
receipt=dict(schema='g31.event_control_existing_timing_breakdown.v1',scope='diagnostic captured under concurrent compilation; no fair P7 timing claim; submit is a subset of owner time, not additive',policies=summary)
target=Path(__file__).with_name('existing_run_breakdown.json')
target.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(target)
