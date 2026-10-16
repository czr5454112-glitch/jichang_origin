#!/usr/bin/env python3
"""Read-only saved-evidence recheck and three narrow Python contract probes.
This does not rerun the saved Windows-native campaigns or certify full coverage.
Usage: python recompute_and_probe.py --repo PATH --output PATH
"""
from __future__ import annotations
import argparse, collections, copy, gzip, hashlib, json, math, platform, runpy, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import xml.etree.ElementTree as ET


def load(p: Path):
    with (gzip.open(p, 'rt', encoding='utf-8') if p.suffix == '.gz' else p.open(encoding='utf-8')) as f:
        return json.load(f)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', required=True, type=Path)
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args(); r = args.repo.resolve(); out = args.output.resolve()
    if out == r or r in out.parents:
        raise ValueError('Write the audit outside the frozen repository.')
    if out.exists():
        raise FileExistsError(out)
    base = r / 'outputs/experiments/g31_ics_long_term_20261013'
    rels = ['scripts/experiments/g31_ics_circulation/protocol_control.py',
            'scripts/experiments/g31_ics_circulation/event_protocol_control.py',
            'scripts/experiments/g31_ics_circulation/p5_handoff.py',
            'cpp/ics_core/bindings/circulation_session_binding.hpp',
            'tests/test_g31_circulation_p5_handoff.py']
    before = {p: sha(r/p) for p in rels}
    report = {'scope': 'saved-artifact recomputation plus narrow pure-Python interface probes; NOT native campaign replay',
              'environment': {'python': sys.version, 'platform': platform.platform()},
              'files_hashed_before': before, 'policies': {}}
    root = base/'event_protocol_original24_016_001/original24'
    inp = load(root/'input.json'); inp_jobs = {j['business_bag_id']: j for j in inp['jobs']}
    report['original24_input'] = {'offered': len(inp_jobs), 'trays': len(inp['trays']),
        'allow_suffix_reroute': sum(bool(j.get('allow_suffix_reroute', False)) for j in inp['jobs'])}
    runs = {}
    for policy in ['periodic_reactive','periodic_predictive','event_reactive','event_predictive','event_joint']:
        run = load(root/policy/'run.json.gz'); result = run['result']; ledger = load(root/policy/'request_ack_ledger.json.gz')
        records = result['receipts']; jobs = result['jobs']; costs = {}
        for j in jobs:
            assert j['status'] == 'completed', 'Do not apply completed-only cost to unfinished cases.'
            costs[j['business_bag_id']] = j['completed_at'] - inp_jobs[j['business_bag_id']]['arrival']
        assert set(costs) == set(inp_jobs)
        timers = [c['compute_wall_ms'] for c in run['control_records'] if 'compute_wall_ms' in c]
        req_counts = collections.Counter(q['kind'] for q in ledger['requests'])
        forecasts = collections.Counter((q.get('last_delivered_ack') or {}).get('status', 'unknown')
            for q in ledger['requests'] if q['kind']=='service_forecast')
        report['policies'][policy] = {'status':run['status'], 'physical_clock':result['physical_clock'],
            'completed':len(costs), 'cost_seconds':sum(costs.values()),
            'late':sum(j['completed_at']>inp_jobs[j['business_bag_id']]['deadline'] for j in jobs),
            'empty_received':sum(e['event']=='EMPTY_RECEIVED' for e in records),
            'route_requests':req_counts.get('route',0), 'forecasts':dict(forecasts),
            'owner_samples':len(timers), 'owner_over_100ms':sum(t>100 for t in timers),
            'owner_max_ms':max(timers,default=None),
            'receipt_clock_regressions':sum(b['time']<a['time'] for a,b in zip(records,records[1:])),
            'cost_by_job':costs}
        runs[policy] = run
    ep = report['policies']['event_predictive']; pp = report['policies']['periodic_predictive']
    diffs = {j:pp['cost_by_job'][j]-ep['cost_by_job'][j] for j in inp_jobs}
    report['event_vs_periodic_predictive'] = {'improvement_seconds':sum(diffs.values()),
        'faster_jobs':sum(v>1e-8 for v in diffs.values()), 'same_jobs':sum(abs(v)<=1e-8 for v in diffs.values()),
        'slower_jobs':sum(v < -1e-8 for v in diffs.values())}
    report['event_joint_equals_predictive_receipts'] = runs['event_joint']['result']['receipts']==runs['event_predictive']['result']['receipts']
    report['event_joint_equals_predictive_jobs'] = runs['event_joint']['result']['jobs']==runs['event_predictive']['result']['jobs']
    views = load(root/'event_predictive/delivered_views.json.gz')
    all_messages = {m['message_id']:m for v in views.values() for m in v.get('delivered_messages',[]) if m['kind']=='service_forecast'}
    ledger = load(root/'event_predictive/request_ack_ledger.json.gz')
    delivered_forecast_ids = {(q.get('last_delivered_ack') or {})['result_id']
        for q in ledger['requests'] if q['kind']=='service_forecast'
        and (q.get('last_delivered_ack') or {}).get('status')=='delivered'}
    # Withdrawals also use kind=service_forecast; tie records to successful original requests.
    missing_publications = sorted(delivered_forecast_ids - all_messages.keys())
    assert not missing_publications, missing_publications
    messages = {mid:all_messages[mid] for mid in sorted(delivered_forecast_ids)}
    assert all(m['status']=='conditional' for m in messages.values())
    entry = collections.defaultdict(list)
    for e in runs['event_predictive']['result']['receipts']:
        if e['event']=='EDGE_ENTER': entry[(e['tray_id'],e['business_bag_id'],e['from'],e['to'])].append(e['time'])
    lead = []; unmatched = []
    for mid,m in messages.items():
        times = [t for t in entry[(m['tray_id'],m['business_bag_id'],m['from'],m['next'])] if t >= m['observed_at']-1e-8]
        if times: lead.append(m['delivered_at']-min(times))
        else: unmatched.append(mid)
    report['forecast_delivery_after_actual_entry'] = {'delivered_unique':len(messages),'matched':len(lead),
        'unmatched':unmatched, 'selection':'successful original service_forecast ACK result_ids; excludes withdrawn messages', 'min_lag_seconds':min(lead,default=None),'max_lag_seconds':max(lead,default=None),
        'interpretation':'Entry is not the empty-release/next-decision deadline; this alone does NOT prove forecasts useless.'}
    p5 = []
    for p in sorted((base/'p5_handoff_015_001').rglob('assessment.json')):
        d = load(p); f = p.parent/'native_branches.jsonl.gz'
        with gzip.open(f,'rt',encoding='utf-8') as fh: rows = sum(1 for line in fh if line.strip())
        p5.append({'domain':str(p.parent.relative_to(base/'p5_handoff_015_001')),'saved_branch_rows':rows,
            'strong_cost':d['policies']['strong_service_assignment']['metrics']['cost'],
            'joint_cost':d['policies']['joint_handoff']['metrics']['cost'],
            'strong_reference':d['reference']['strong_service_assignment'],
            'global_optimality':d['global_optimality']})
    report['p5_saved_domains'] = p5
    report['p5_saved_branch_rows'] = sum(v['saved_branch_rows'] for v in p5)
    jroot = ET.parse(base/'live_validation_012/junit.xml').getroot()
    suites = [jroot] if jroot.tag=='testsuite' else list(jroot.iter('testsuite'))
    report['author_saved_junit_not_reexecuted'] = {k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    sys.path[:0] = [str(r),str(r/'src')]
    from scripts.experiments.g31_ics_circulation import protocol_control as pc, event_protocol_control as ec, p5_handoff as ph
    probe = {}; projection = runpy.run_path(str(r/'tests/test_g31_circulation_p5_handoff.py'))['public_projection']()
    original = ph.build_domain(projection)
    projection.pop('version')
    try:
        ph.build_domain(projection)
        bridge = {'raised':False}
    except KeyError as exc:
        bridge = {'raised':True,'exception':repr(exc)}
    probe['p5_versionless_interface'] = {'original_status':original['status'],**bridge,
        'interpretation':'Finite evaluator uses a legacy projection. Directly wiring it to the versionless protocol observation is not supported; do not restore truth-derived version.'}
    class Client:
        def __init__(self):
            self.session=SimpleNamespace(physical_time=0.)
            self.state={'outbox':{}}
        def view(self, owner):
            return {'now':self.session.physical_time,'node_contracts':[{'node':0,'zone':'A','resource_owner':'A'}, {'node':1,'zone':'B','resource_owner':'B'}],
                'jobs':[{'business_bag_id':'J','destination':1,'storage_node':-1}],
                'trays':[{'tray_id':'T','business_bag_id':'J','mode':'loaded','edge_to':-1,'node':0,'generation':1,'traversal_id':0}]}
        def submit(self, owner, kind, payload):
            rid=f'probe:{len(self.state["outbox"])}'
            self.state['outbox'][rid]={'terminal':True,'next_retry':self.session.physical_time+1.,'payload':copy.deepcopy(payload),
                'submission_reply':{'status':'pending'},'client_view':{'last_delivered_ack':{'status':'delivered','result_id':rid}}}
            return rid,{'status':'pending'}
    c=Client(); state={'forecasts':{},'routes':{}}
    with patch.object(pc,'public_astar',return_value=[0,1]):
        first=pc._publish_services(c,'A',state,command_delay=0.,publication_delay=.5,routes=False,forecasts=True,lease_seconds=120.)
        c.session.physical_time=1000.
        second=pc._publish_services(c,'A',state,command_delay=0.,publication_delay=.5,routes=False,forecasts=True,lease_seconds=120.)
    probe['same_stage_successful_forecast_refresh']={'first_publications':len(first),'publications_after_time_1000':len(second),
        'scope':'Mock control-client API only; does not create or run a native physical scenario.'}
    fake=SimpleNamespace(state={'outbox':{'rejected':{'terminal':True,'next_retry':5.}}})
    timer=ec._retry_time(fake)
    probe['terminal_cooldown_timer']={'next_retry':5.,'returned':str(timer), 'is_infinite':math.isinf(timer),
        'scope':'Proves this timer index excludes terminal rows, not that every live scenario deadlocks.'}
    report['executed_python_contract_probes']=probe
    after={p:sha(r/p) for p in rels}
    report['hashed_source_changed']=[p for p in rels if before[p]!=after[p]]
    assert not report['hashed_source_changed']
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'policies':{p:{k:v for k,v in d.items() if k!='cost_by_job'} for p,d in report['policies'].items()},
        'p5_domains':len(p5),'p5_rows':report['p5_saved_branch_rows'],'probes':probe},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
