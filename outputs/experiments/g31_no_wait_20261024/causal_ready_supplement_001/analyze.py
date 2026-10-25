"""Supplement only: common nominal-feed/causal-ready to actual goal duration.

Does not change primary first-planning THT, clocks, policies, or prior auditors.
CLI performs a population scan and must only be run in the authorized analysis slot.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from decimal import Decimal,ROUND_HALF_UP
import gzip
import hashlib
import json
import math
from pathlib import Path

US=1000000
HERE=Path(__file__).resolve().parent
PROFILE_SHA='9b1a78344ec89aaac377feb05afccd48d9b957174286b29eedfe57a73a93c426'
CANONICAL_CONTENT={1:'f167648ca524770b48465c66eaa7a548390f31e35815fb9c73accff68520c3a1',2:'55538837011a1ed31eb272cc170fdc9fefb3b40ec14e2ae0574877a8c465a115'}
FIELDS=('causal_ready_elapsed','raw_predecessor_ready_elapsed','ready_to_first_planning','first_planning_tht',
        'network_elapsed','planning_retry_wait','canonical_elapsed','nominal_feed_delay',
        'canonical_release_q1_rounding','source_nominal_feed_queue',
        'own_predecessor_gate_delay','q1_rounding_excluded','ebs_storage_excluded')


def ticks(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('invalid finite clock')
    d=Decimal(str(value))*US;n=int(d.to_integral_value(rounding=ROUND_HALF_UP))
    # This accepts floating serialization noise, not a fraction of a physical tick.
    if abs(d-n)>Decimal('0.0001'):raise ValueError('clock is not on the common microsecond grid')
    return n


def ceil_second(value):return ((value+US-1)//US)*US


def stats(values):
    values=sorted(values);n=len(values)
    def q(p):
        if not n:return None
        k=(n-1)*p;i=int(k);j=min(i+1,n-1)
        return (values[i]+(k-i)*(values[j]-values[i]))/US
    return dict(count=n,sum=sum(values)/US if n else None,mean=sum(values)/n/US if n else None,
                min=values[0]/US if n else None,p50=q(.5),p95=q(.95),p99=q(.99),max=values[-1]/US if n else None)


def population_metric(values):
    known=[v for v in values if v is not None]
    full=stats(known) if len(known)==len(values) else {**dict.fromkeys(('sum','mean','min','p50','p95','p99','max')), 'count':len(values)}
    return dict(denominator=len(values),observed_count=len(known),censored_or_unavailable_count=len(values)-len(known),full_population=full)


def common_supply(rows):
    """Stable raw canonical sort, then ceil-q1 and a static 1s feed recurrence."""
    queues=defaultdict(list);expected={}
    for i,r in enumerate(rows):
        sid=str(r['segment_id'])
        if sid in expected:raise ValueError('duplicate canonical segment')
        if r['leg'] not in ('direct','storage_in','storage_out'):raise ValueError('unknown leg')
        expected[sid]=r;ticks(r['pass_time'])
        queues[r['start']].append((r['pass_time'],i,sid))
    generated={};order=hashlib.sha256()
    for source,q in queues.items():
        q.sort(key=lambda x:(x[0],x[1]));previous=None
        order.update(json.dumps([source,[x[2] for x in q]],separators=(',',':')).encode())
        for _,_,sid in q:
            g=ceil_second(ticks(expected[sid]['pass_time']))
            if previous is not None:g=max(g,previous+US)
            generated[sid]=g;previous=g
    return generated,order.hexdigest()


def analyze(rows,bags,*,kind,horizon):
    if kind not in ('native','hca'):raise ValueError('explicit native or hca required')
    h=ticks(horizon)
    if h<0:raise ValueError('negative horizon')
    rows=list(rows);actual={};expected={str(r['segment_id']):r for r in rows}
    for b in bags:
        sid=str(b['segment_id'])
        if sid in actual:raise ValueError('duplicate actual segment')
        actual[sid]=b
    if len(expected)!=len(rows) or set(actual)!=set(expected):raise ValueError('exact full canonical population required, including incomplete rows')
    supply,orderhash=common_supply(rows);groups=defaultdict(dict);failures=Counter();examples=[];records={};activation_checks=0
    def fail(sid,reason,*details):
        failures[reason]+=1
        if len(examples)<30:examples.append([sid,reason,*details])
    for sid,row in expected.items():
        group=groups[str(row['task_id'])]
        if row['leg'] in group:raise ValueError('duplicate business leg')
        group[row['leg']]=sid;b=actual[sid];valid=True
        for key in ('task_id','leg','start','goal'):
            # Frozen HCA physical_bags has no leg field. Exact segment_id plus
            # required task/start/goal binds its leg to the canonical record.
            # A present wrong/null leg still fails; native leg remains required.
            if kind=='hca' and key=='leg' and key not in b:continue
            if b.get(key)!=row[key]:fail(sid,'identity_mismatch',key);valid=False
        clocks={}
        for key in ('admission','finish','first_planning_attempt_time','activation_time','generated_release','precomputed_source_eligibility'):
            v=b.get(key)
            try:clocks[key]=ticks(v) if v is not None else None
            except ValueError:fail(sid,'invalid_clock',key);clocks[key]=None;valid=False
        admission=clocks['admission'];finish=clocks['finish'];first=clocks['first_planning_attempt_time']
        if first is not None and (first>h or first<supply[sid]):fail(sid,'invalid_first_attempt');valid=False
        if admission is not None and (admission>h or first is None or admission<first):fail(sid,'invalid_admission');valid=False
        if admission is not None and finish is not None and finish<admission:fail(sid,'finish_before_admission');valid=False
        done=b.get('completed') is True and admission is not None and finish is not None and finish<=h and valid
        if b.get('completed') is True and not done:fail(sid,'invalid_completed_record')
        if kind=='native':
            for key in ('generated_release','precomputed_source_eligibility'):
                if key not in b or clocks[key]!=supply[sid]:fail(sid,'native_supply_mismatch',key)
        records[sid]=dict(sid=sid,row=row,clocks=clocks,done=done,valid=valid,G=supply[sid])
    for task,legs in groups.items():
        if sorted(legs) not in (['direct'],['storage_in','storage_out']):raise ValueError('business must have direct or exactly both EBS legs')
    for sid,item in records.items():
        row=item['row'];cl=item['clocks'];g=item['G'];ready=rawready=g;storage=0
        if row['leg']=='storage_out':
            inbound=records[groups[str(row['task_id'])]['storage_in']]
            if inbound['done']:
                pred=inbound['clocks']['finish'];rawready=max(g,pred);ready=max(g,ceil_second(pred));storage=max(0,g-pred)
            else:ready=rawready=storage=None
        # Known future G does not mean the source activation has happened.
        expected_activation=ready if ready is not None and ready<=h else None
        if kind=='native':
            activation_checks+=1
            if 'activation_time' not in actual[sid] or cl['activation_time']!=expected_activation:fail(sid,'native_activation_not_common_causal_ready',cl['activation_time'],expected_activation)
        first=cl['first_planning_attempt_time'];admission=cl['admission'];finish=cl['finish']
        valid=item['valid']
        if first is not None and (ready is None or first<ready):fail(sid,'first_attempt_before_causal_ready');valid=False
        if item['done'] and (ready is None or finish<ready):fail(sid,'completion_before_causal_ready');valid=False
        done=item['done'] and valid;item['done']=done;item['ready']=ready;item['rawready']=rawready
        item['values']={
          'causal_ready_elapsed':finish-ready if done and ready is not None else None,
          'raw_predecessor_ready_elapsed':finish-rawready if done and rawready is not None else None,
          'ready_to_first_planning':first-ready if first is not None and ready is not None and valid else None,
          'first_planning_tht':finish-first if done and first is not None else None,
          'network_elapsed':finish-admission if done else None,
          'planning_retry_wait':admission-first if admission is not None and first is not None and valid else None,
          'canonical_elapsed':finish-ticks(row['pass_time']) if done else None,
          'nominal_feed_delay':g-ticks(row['pass_time']),
          'canonical_release_q1_rounding':ceil_second(ticks(row['pass_time']))-ticks(row['pass_time']),
          'source_nominal_feed_queue':g-ceil_second(ticks(row['pass_time'])),
          'own_predecessor_gate_delay':ready-g if expected_activation is not None else None,
          'q1_rounding_excluded':ready-rawready if expected_activation is not None else None,
          'ebs_storage_excluded':storage if expected_activation is not None else None}
        v=item['values']
        if done and v['first_planning_tht'] is not None and v['causal_ready_elapsed']!=v['first_planning_tht']+v['ready_to_first_planning']:fail(sid,'decomposition_mismatch')
    businesses=[]
    for task,legs in groups.items():
        items=[records[sid] for sid in legs.values()];v={k:sum(x['values'][k] for x in items) if all(x['values'][k] is not None for x in items) else None for k in FIELDS}
        if 'storage_in' in legs and all(x['done'] for x in items):
            inside=records[legs['storage_in']];outside=records[legs['storage_out']]
            # Independent telescoping check, including q1 readiness rounding.
            elapsed=outside['clocks']['finish']-inside['G']-v['ebs_storage_excluded']-v['q1_rounding_excluded']
            if elapsed!=v['causal_ready_elapsed']:fail(task,'nonoverlap_telescoping_mismatch')
        businesses.append(dict(task_id=task,kind='direct' if 'direct' in legs else 'ebs',done=all(x['done'] for x in items),values=v))
    def metrics(items):return {k:population_metric([x['values'][k] for x in items]) for k in FIELDS}
    full=metrics(businesses);passed=not failures
    by_kind={k:metrics([x for x in businesses if x['kind']==k]) for k in ('direct','ebs')}
    by_leg={k:metrics([x for x in records.values() if x['row']['leg']==k]) for k in ('direct','storage_in','storage_out')}
    # Fail closed: do not expose an apparently usable full-pop metric after a clock/identity violation.
    if not passed:
        for group in [full,*by_kind.values(),*by_leg.values()]:
            for metric in group.values():
                for k in ('sum','mean','min','p50','p95','p99','max'):metric['full_population'][k]=None
    largest=sorted((b for b in businesses if passed and b['values']['causal_ready_elapsed'] is not None),key=lambda b:(-b['values']['causal_ready_elapsed'],b['task_id']))[:20]
    return dict(schema='g31.nanning.causal_ready_supplement.v1',passed=passed,kind=kind,horizon=h/US,
      definition='Common nominal-feed/causal-ready to actual continuous goal arrival: sum per business transport leg of finish-ready; supplemental, not replacement primary THT.',
      common_supply='Per source, stable raw canonical pass_time/input row order; G_i=max(ceil_q1(pass_i),G_previous+1s). This is precomputed nominal-feed eligibility, not actual HCA generation or first planning.',
      readiness='direct/storage_in ready=G; storage_out ready=max(G_out,ceil_q1(actual completed inbound finish)). Pending/planned inbound finish never supplies readiness.',
      leg_identity_source='Exact canonical segment_id plus required task_id/start/goal; HCA may omit leg, but any present leg must match. Native leg is required.',
      segment_denominator=len(rows),business_denominator=len(groups),completed_segments=sum(x['done'] for x in records.values()),completed_businesses=sum(x['done'] for x in businesses),
      full_population_available=passed and full['causal_ready_elapsed']['full_population']['sum'] is not None,
      metrics=full,by_business_kind=by_kind,by_leg=by_leg,
      native_activation_checks=activation_checks,canonical_source_order_sha256=orderhash,
      violations=sum(failures.values()),violation_counts=dict(failures),examples=examples,
      largest_observed_business_diagnostic=[dict(task_id=b['task_id'],kind=b['kind'],seconds=b['values']['causal_ready_elapsed']/US) for b in largest],
      boundaries=['Full-population statistics remain null if any member is incomplete or readiness/clock evidence is unavailable. Tail examples alone are not full-population results.',
        'EBS storage excluded=max(0,G_out-actual inbound finish); q1 causal readiness rounding is excluded separately. EBS leg intervals cannot overlap under this anchor.',
        'G depends on common canonical supply and static feed; out readiness additionally depends on each algorithm actual inbound arrival, so this is not a shared fixed treatment start or a causal effect estimate.',
        'HCA release_epoch is actual planning-list generation and may be delayed by a blocked canonical head. It is not substituted for G or causal ready.',
        'Physical safety and original primary THT remain the responsibility of existing independent audits. This supplemental accounting changes no algorithm or frozen result.'])


def read_json(path,evidence):
    p=Path(path);s=p.stat()
    if s.st_size>2*1024*1024:raise ValueError('metadata unexpectedly large')
    raw=p.read_bytes();evidence[str(p.resolve())]=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    return json.loads(raw.decode('utf-8-sig'))


def read_rows(path,evidence,*,skim=False):
    p=Path(path);before=p.stat();rawhash=hashlib.sha256();contenthash=hashlib.sha256();rows=[]
    # Canonical compressed identity is distinct from decompressed temporal identity.
    if p.suffix=='.gz':
        with p.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):rawhash.update(chunk)
    opener=gzip.open if p.suffix=='.gz' else open
    keys={'segment_id','task_id','leg','start','goal','admission','finish','completed','first_planning_attempt_time','activation_time','generated_release','precomputed_source_eligibility'}
    with opener(p,'rb') as f:
        for line in f:
            contenthash.update(line)
            if p.suffix!='.gz':rawhash.update(line)
            if not line.strip():continue
            b=json.loads(line)
            rows.append({k:v for k,v in b.items() if k in keys} if skim else b)
    after=p.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('population file changed during read')
    evidence[str(p.resolve())]=dict(sha256=rawhash.hexdigest(),content_sha256=contenthash.hexdigest(),bytes=before.st_size,records=len(rows))
    return rows


def run(directory,canonical,kind,horizon):
    d=Path(directory).resolve();evidence={};gates={}
    if kind=='native':
        man=read_json(d/'manifest.json',evidence);sel=man['selection'];cfg=sel['effective_controls']
        if man.get('status')!='complete' or man.get('audits_passed') is not True or sel.get('map')!='nanning':raise ValueError('completed audited Nanning native run required')
        for k,want in dict(release_quantum=1,completion_quantum=1,source_generation_interval=1,source_fifo_order='canonical',enable_ebs_predecessor_gate=True,time_grid_seconds=1e-6).items():
            if cfg.get(k)!=want:raise ValueError('common readiness contract mismatch '+k)
        if cfg.get('end_time')!=horizon or sel['profile']['sha256']!=PROFILE_SHA:raise ValueError('horizon/profile mismatch')
        for name in ('headway_audit','rolling_replay','source_policy_audit','tht_audit','business_audit'):
            gates[name]=read_json(d/(name+'.json'),evidence).get('passed') is True
        ns=read_json(d/'native_summary.json',evidence)
        if ns.get('event_budget_exhausted') is not False or ns.get('executed_horizon')!=horizon:raise ValueError('unexecuted/censored runtime horizon')
        expected_bag_sha=man['bags_sha256'];bagfile=d/'bags.jsonl';expected_canonical_sha=sel['canonical']['sha256'];scale=sel['scale']
    else:
        final=read_json(d/'final_summary_001.json',evidence);man=read_json(d.parent/'manifest.json',evidence);status=read_json(d/'run_01/run_status.json',evidence)
        if final.get('cell')!='nanning_2x' or status.get('status')!='complete' or status.get('returncode')!=0 or final.get('horizon')!=horizon or final.get('frozen_inputs_and_classes_postrun_exact') is not True:raise ValueError('completed identity-verified HCA2x run required')
        for name in ('physical_headway_audit','source_policy_audit_001','tht_metrics'):
            gates[name]=read_json(d/(name+'.json'),evidence).get('passed') is True
        gates['final_physical']=final.get('physical_passed') is True
        ann=read_json(d/'annotated_physical_bags_receipt.json',evidence);gates['annotation_original_fields_exact']=ann.get('original_fields_exact') is True
        expected_bag_sha=ann['evidence']['output_sha256'];bagfile=d/'annotated_physical_bags.jsonl';expected_canonical_sha=None;scale=2
        if ann['evidence']['canonical_sha256']!=CANONICAL_CONTENT[scale]:raise ValueError('HCA canonical identity mismatch')
    if not all(gates.values()):raise ValueError('prior independent audit failed/missing')
    rows=read_rows(canonical,evidence);cid=evidence[str(Path(canonical).resolve())]
    if cid['content_sha256']!=CANONICAL_CONTENT[scale] or (expected_canonical_sha and cid['sha256']!=expected_canonical_sha):raise ValueError('actual canonical identity mismatch')
    bags=read_rows(bagfile,evidence,skim=True)
    if evidence[str(bagfile)]['sha256']!=expected_bag_sha:raise ValueError('actual bag evidence changed')
    result=analyze(rows,bags,kind=kind,horizon=horizon)
    if result['segment_denominator']!=43603*scale or result['business_denominator']!=28506*scale:raise ValueError('wrong full population')
    result.update(run=str(d),prior_independent_gates=gates,evidence_files=evidence,tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,required=True);ap.add_argument('--canonical',type=Path,required=True);ap.add_argument('--kind',choices=('native','hca'),required=True);ap.add_argument('--horizon',type=float,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    if a.output.exists():raise FileExistsError('append-only receipt required')
    result=run(a.run,a.canonical,a.kind,a.horizon);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=result['passed'],full_population_available=result['full_population_available'],mean=result['metrics']['causal_ready_elapsed']['full_population']['mean'],output=str(a.output))))
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
