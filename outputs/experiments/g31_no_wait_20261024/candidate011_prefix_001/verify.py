"""Compare real short/drain executions with future-reservation-aware state.

No native execution or synthetic short-run output is produced. Ledger prefixes
are compared exactly, then the short-run final bag state is reconstructed solely
from that run's events through H. Drain final routes/counters never stand in for
the short-run state, because suffixes may change after H.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import legacy_prefix_base as base

AUDITS = ('headway_audit.json','rolling_replay.json','source_policy_audit.json','tht_audit.json','business_audit.json')
FUTURE_CLOCKS = ('reservation_time','planned_admission','planned_finish','planned_resource_cleanup_epoch')
FUTURE_ARRAYS = ('reserved_route','reserved_node_reservation_ids','reserved_edge_reservation_ids')


class PrefixState:
    """Clock/certificate lifecycle reconstruction, not another physics solver."""
    def __init__(self):
        self.states = {}
        self.commit_counter = 0
        self.kinds = Counter()
        self.last_order = 0

    @staticmethod
    def ids(state):
        return {x for x in state['node_ids']+state['edge_ids'] if x not in (0,None)}

    def apply(self,e):
        sid=e['segment_id'];kind=e['kind'];now=e['time'];order=e['ledger_order']
        if order!=self.last_order+1:raise ValueError('prefix ledger has missing or reordered records')
        self.last_order=order;self.kinds[kind]+=1
        s=self.states.get(sid)
        if kind in ('source_commit','source_reserve'):
            if s is not None:raise ValueError('second source certificate')
            route=e['committed_route']
            if not route or e['old_generation']!=0 or e['new_generation']!=1 or e['removed_ids']:
                raise ValueError('invalid initial certificate')
            pending=kind=='source_reserve'
            if e['current_index']!=(-1 if pending else 0):raise ValueError('wrong initial physical index')
            if pending:
                if e.get('current_node','missing') is not None or e['planned_admission']!=route[0][1] or not now<route[0][1]:
                    raise ValueError('future reserve misstates admission')
            elif route[0][1]!=now:raise ValueError('source commit is not physical admission')
            s=dict(route=route,node_ids=e['node_reservation_ids'],edge_ids=e['edge_reservation_ids'],
                   generation=1,index=-1 if pending else 0,admission=None if pending else now,
                   actual_finish=now if not pending and len(route)==1 else None,
                   cleanup=e['resource_cleanup_epoch'],cleaned=False,
                   reserve=dict(e) if pending else None,commit_order=None)
            if not pending:
                self.commit_counter+=1;s['commit_order']=self.commit_counter
            self.states[sid]=s
        elif kind=='source_launch':
            if s is None or s['reserve'] is None or s['admission'] is not None or s['cleaned']:
                raise ValueError('launch without pending reserve')
            if (e['reference_reservation_order']!=s['reserve']['ledger_order'] or e['generation']!=s['generation']
                    or e['index']!=0 or e['node']!=s['route'][0][0] or now!=s['route'][0][1]):
                raise ValueError('launch differs from reserved physical certificate')
            if any(e.get(k) for k in ('removed_ids','node_reservation_ids','edge_reservation_ids','committed_route')):
                raise ValueError('launch cannot mutate resource IDs')
            self.commit_counter+=1
            s.update(index=0,admission=now,actual_finish=now if len(s['route'])==1 else None,
                     commit_order=self.commit_counter)
        elif kind=='arrival':
            if s is None or s['admission'] is None or s['cleaned']:raise ValueError('arrival without active physical certificate')
            i=e['index']
            if (e['generation']!=s['generation'] or i!=s['index']+1 or i>=len(s['route'])
                    or [e['node'],now]!=s['route'][i][:2]):raise ValueError('arrival not on current prefix certificate')
            s['index']=i
            if i==len(s['route'])-1:s['actual_finish']=now
        elif kind=='replace_commit':
            if s is None or s['admission'] is None or s['cleaned']:raise ValueError('replacement without physical admission')
            i=e['current_index'];route=e['committed_route']
            if (i!=s['index'] or i<=0 or i>=len(s['route'])-1 or now!=s['route'][i][1]
                    or e['old_generation']!=s['generation'] or e['new_generation']!=s['generation']+1
                    or route[:i+1]!=s['route'][:i+1]):raise ValueError('replacement changed an executed prefix')
            self.commit_counter+=1
            s.update(route=route,node_ids=e['node_reservation_ids'],edge_ids=e['edge_reservation_ids'],
                     generation=e['new_generation'],cleanup=e['resource_cleanup_epoch'])
        elif kind=='cleanup':
            if s is None:raise ValueError('cleanup without certificate')
            if e['valid'] is True:
                if (s['admission'] is None or s['actual_finish'] is None or s['cleaned'] or
                        e['current_generation']!=s['generation'] or e['event_generation']!=s['generation'] or
                        now!=s['cleanup'] or set(e['removed_ids'])!=self.ids(s)):
                    raise ValueError('cleanup removed unexecuted or wrong-generation rights')
                s['cleaned']=True
            elif e['valid'] is not False or e['removed_ids']:
                raise ValueError('stale cleanup mutated rights')
        else:raise ValueError('unknown event kind')

    def compare_short_bag(self,b,horizon):
        sid=b['segment_id'];s=self.states.get(sid);problems=[]
        def eq(field,expected):
            if field not in b or base.normalized(b[field])!=base.normalized(expected):problems.append('short_ledger_state:'+field)
        admitted=s is not None and s['admission'] is not None
        reserved=s is not None and s['reserve'] is not None
        eq('admitted',admitted);eq('future_reserved',reserved);eq('future_pending',reserved and not admitted)
        eq('admission',s['admission'] if admitted else None)
        eq('actual_finish',s['actual_finish'] if s else None)
        eq('completed',s is not None and s['actual_finish'] is not None)
        if admitted:
            for field,value in (('route',s['route']),('finish',s['route'][-1][1]),('node_reservation_ids',s['node_ids']),
                                ('edge_reservation_ids',s['edge_ids']),('actual_arrived_index',s['index']),
                                ('route_generation',s['generation']),('resource_cleanup_epoch',s['cleanup']),
                                ('resource_cleanup_time',s['cleanup']),('commit_time',s['admission']),
                                ('planning_time',s['admission']),('commit_order',s['commit_order'])):eq(field,value)
            if s['index']+1<len(s['route']) and s['route'][s['index']+1][1]<=horizon:problems.append('missing_due_arrival')
            if s['cleanup']<=horizon and not s['cleaned']:problems.append('missing_due_cleanup')
        else:
            for field in ('route','node_reservation_ids','edge_reservation_ids'):eq(field,[])
            for field in ('finish','resource_cleanup_epoch','resource_cleanup_time','commit_time','planning_time','commit_order'):eq(field,None)
            if reserved:
                eq('actual_arrived_index',-1);eq('route_generation',1)
                if s['route'][0][1]<=horizon:problems.append('missing_due_launch')
            else:
                eq('actual_arrived_index',0);eq('route_generation',0)
        if reserved:
            e=s['reserve']
            for field,value in (('reservation_time',e['time']),('reservation_order',e['ledger_order']),
                                ('planned_admission',e['planned_admission']),('planned_finish',e['goal_arrival']),
                                ('planned_resource_cleanup_epoch',e['resource_cleanup_epoch']),
                                ('reserved_route',e['committed_route']),('reserved_node_reservation_ids',e['node_reservation_ids']),
                                ('reserved_edge_reservation_ids',e['edge_reservation_ids'])):eq(field,value)
        else:
            for field in FUTURE_CLOCKS+('reservation_order',):eq(field,None)
            for field in FUTURE_ARRAYS:eq(field,[])
        return problems


def compare_future_evidence(original,drained,horizon):
    problems=[]
    for b in (original,drained):
        if type(b.get('future_reserved')) is not bool or type(b.get('future_pending')) is not bool:
            return ['missing_future_lifecycle_telemetry']
    t=drained.get('reservation_time')
    if t is not None and not base.finite_clock(t):return ['invalid_reservation_time']
    seen=drained['future_reserved'] and t is not None and t<=horizon
    if original['future_reserved']!=seen:problems.append('reservation_set_changed_before_cutoff')
    if original['future_pending']!=(seen and base.clock_prefix(drained,'admission',horizon) is None):
        problems.append('pending_set_changed_at_cutoff')
    for field in FUTURE_CLOCKS+('reservation_order',)+FUTURE_ARRAYS:
        expected=drained.get(field) if seen else ([] if field in FUTURE_ARRAYS else None)
        if field not in original or base.normalized(original[field])!=base.normalized(expected):
            problems.append('initial_reserved_evidence_changed:'+field)
    return problems


def stream_ledger(original_path,drain_path,horizon):
    original,drained=base.LedgerPrefix(original_path,horizon),base.LedgerPrefix(drain_path,horizon)
    state=PrefixState();errors=records=0;raw_exact=True;examples=[]
    for line,(left,right) in enumerate(itertools.zip_longest(original,drained),1):
        records+=1
        raw_exact &= left is not None and right is not None and left[0]==right[0]
        changed=left is None or right is None or base.normalized(left[1])!=base.normalized(right[1])
        if changed:
            errors+=1
            if len(examples)<20:examples.append(dict(prefix_line=line,original=left[1] if left else None,drain=right[1] if right else None))
        if left is not None:state.apply(left[1])
    if original.after_cutoff_records:raise ValueError('short ledger executed beyond its cutoff')
    return dict(passed=errors==0 and raw_exact,prefix_records=records,changed_records=errors,
                serialized_prefix_bytes_exact=raw_exact,examples=examples,
                original=original.evidence(),drain=drained.evidence()),state


def stream_bags(original_path,drain_path,horizon,state):
    hashes=[hashlib.sha256(),hashlib.sha256()];counts=Counter();examples=[];seen=set()
    with Path(original_path).open('rb') as left,Path(drain_path).open('rb') as right:
        for line,pair in enumerate(itertools.zip_longest(left,right),1):
            counts['records']+=1
            for digest,raw in zip(hashes,pair):
                if raw is not None:digest.update(raw)
            if None in pair:problems=['population_record_count_changed']
            else:
                old,new=(base.decode(raw) for raw in pair)
                sid=old['segment_id']
                if sid in seen:raise ValueError('duplicate short-run segment')
                seen.add(sid)
                problems=base.compare_bag_prefix(old,new,horizon)
                problems+=compare_future_evidence(old,new,horizon)
                problems+=state.compare_short_bag(old,horizon)
                for field in ('admitted','completed','future_reserved','future_pending'):
                    counts[field]+=old.get(field) is True
                counts['first_attempted']+=old.get('first_planning_attempt_time') is not None
                if old.get('admission') is not None and old.get('commit_order')!=new.get('commit_order'):
                    problems.append('immutable_actual_source_commit_order_changed')
            if problems:
                counts['changed_records']+=1
                if len(examples)<20:examples.append(dict(line=line,problems=problems))
    if set(state.states)-seen:raise ValueError('ledger contains a task missing from final short-run population')
    return dict(passed=counts['changed_records']==0,**dict(counts),examples=examples,
                original_sha256=hashes[0].hexdigest(),drain_sha256=hashes[1].hexdigest())


def run(original_dir,drain_dir,horizon):
    original_dir,drain_dir=Path(original_dir).resolve(),Path(drain_dir).resolve()
    if original_dir==drain_dir or not base.finite_clock(horizon):raise ValueError('two real distinct runs and finite cutoff required')
    files=[d/n for d in (original_dir,drain_dir) for n in ('manifest.json','native_summary.json','bags.jsonl','rolling_events.jsonl')+AUDITS]
    stamps={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in files}
    manifests=[base.read(d/'manifest.json') for d in (original_dir,drain_dir)]
    summaries=[base.read(d/'native_summary.json') for d in (original_dir,drain_dir)]
    end=base.validate_metadata(*manifests,*summaries,horizon)
    # A valid short run can be censored. Performance availability is not required.
    audit_evidence={}
    contracts=[];controls=[]
    for d,m in zip((original_dir,drain_dir),manifests):
        checks={}
        for name in AUDITS:
            p=d/name;check=base.read(p)
            if check.get('passed') is not True:raise ValueError('saved independent audit did not pass: '+str(p))
            checks[name]=dict(path=str(p),sha256=base.file_sha(p),passed=True)
        audit_evidence[str(d)]=checks
        for name,expected in m['source_sha256'].items():
            p=d/'standard_sources'/name
            if base.file_sha(p)!=expected:raise ValueError('frozen source identity changed: '+str(p))
            stamps[p]=(p.stat().st_size,p.stat().st_mtime_ns)
        controls.append(base.read(d/'standard_sources/controls.json'))
        contracts.append(base.read(d/'standard_sources/contract.json'))
        effective=m['selection']['effective_controls']
        if any(k not in effective or base.normalized(v)!=base.normalized(effective[k]) for k,v in controls[-1].items()):
            raise ValueError('frozen raw controls differ from actual effective controls')
        if effective.get('enable_inroute_replanning') is not True or effective.get('future_source_reservation_horizon_seconds',0)<=0:
            raise ValueError('future reservation and complete rolling ledger must be enabled')
    if base.only_end_time_changed(*controls,horizon)!=end or base.validate_contract_change(*contracts,horizon)!=end:
        raise ValueError('contract/control window disagreement')
    ledger,state=stream_ledger(original_dir/'rolling_events.jsonl',drain_dir/'rolling_events.jsonl',horizon)
    for summary,label in zip(summaries,('original','drain')):
        if summary.get('rolling_ledger_records')!=ledger[label]['records']:
            raise ValueError('native ledger record count differs from actual bytes: '+label)
    bags=stream_bags(original_dir/'bags.jsonl',drain_dir/'bags.jsonl',horizon,state)
    for m,key in zip(manifests,('original_sha256','drain_sha256')):
        if m['bags_sha256']!=bags[key]:raise ValueError('finished-run bag bytes changed')
    if bags['records']!=manifests[0]['selection']['segment_denominator']:raise ValueError('canonical denominator mismatch')
    k=ledger['original']['kinds']
    if bags.get('admitted',0)!=k.get('source_commit',0)+k.get('source_launch',0):raise ValueError('actual admissions differ from commit+launch')
    if bags.get('future_reserved',0)!=k.get('source_reserve',0):raise ValueError('future reservation population mismatch')
    if bags.get('future_pending',0)!=k.get('source_reserve',0)-k.get('source_launch',0):raise ValueError('pending source rights population mismatch')
    if any((p.stat().st_size,p.stat().st_mtime_ns)!=stamp for p,stamp in stamps.items()):raise ValueError('evidence changed during verification')
    return dict(schema='g31.future_source.real_short_drain_prefix.v1',passed=bags['passed'] and ledger['passed'],
                original_run=str(original_dir),drain_run=str(drain_dir),cutoff=horizon,drain_horizon=end,
                bags=bags,rolling_events=ledger,
                prefix_state=dict(certificates=len(state.states),physical_commit_counter=state.commit_counter,
                                  live_rights=sum(len(state.ids(s)) for s in state.states.values() if not s['cleaned'])),
                independent_audits=audit_evidence,
                tool_sha256=base.file_sha(__file__),metadata_helper_sha256=base.file_sha(Path(base.__file__)),
                manifest_sha256=dict(original=base.file_sha(original_dir/'manifest.json'),drain=base.file_sha(drain_dir/'manifest.json')),
                boundary='Both inputs are actual independently executed short/drain runs with passed physical audits. Exact ledger prefix includes all cutoff-time events and entire future rights committed before cutoff. Short final route/state comes only from its ledger. Drain final routes, cumulative attempts/retries, later reserve/launch/replans and future completions never substitute for short observations. No synthetic short run or short runtime is produced.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original',required=True,type=Path);p.add_argument('--drain',required=True,type=Path)
    p.add_argument('--cutoff',type=float,default=98259);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    result=run(args.original,args.drain,args.cutoff)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(passed=result['passed'],bags=result['bags']['records'],events=result['rolling_events']['prefix_records'],pending=result['bags'].get('future_pending',0))))
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
