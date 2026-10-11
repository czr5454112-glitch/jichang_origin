"""Pure artifact analysis; deliberately imports no controller implementation."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import gzip
from hashlib import sha256
import json
from pathlib import Path
import random
from time import perf_counter, process_time

ROOT = Path('outputs/experiments/ics_circulation_v3')
POLICIES = ('point', 'scenario8_s17', 'scenario8_s29', 'scenario8_s43')


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(path):
    if str(path).endswith('.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
    return json.loads(path.read_text(encoding='utf-8-sig'))


def key(seq):
    return tuple(sorted((p['tray_id'], p['destination_node'],
        tuple((l['edge_id'], l['depart'], l['arrive']) for l in p['legs']), p['usable_at']) for p in seq))


def physical(result):
    result = deepcopy(result)
    result['policy_stats'] = {k: v for k, v in result['policy_stats'].items() if not k.endswith('_ms')}
    return result


def sample_from_public(diag):
    pending = sorted(diag['proxy_bags'], key=lambda b: b['bag_id'])
    now, config = diag['snapshot_time'], diag['scenario_settings']
    seed = int(digest({'schema': 'public_synthetic_uncertainty_v1', 'seed': config['seed'],
        'time': now, 'proxy': pending})[:16], 16)
    rng, tapes = random.Random(seed), []
    for _ in range(config['count']):
        tape = []
        for original in pending:
            event, jitter = rng.randrange(8), rng.choice((-2, 0, 2))
            if event == 0 and not original['protected']:
                continue
            b = dict(original)
            b['arrival'] = max(now + 1, original['arrival'] + jitter)
            b['deadline'] += b['arrival'] - original['arrival']
            if event == 1 and not original['protected']:
                b['origin'], b['destination'] = b['destination'], b['origin']
            tape.append(b)
        tapes.append(sorted(tape, key=lambda b: (b['arrival'], b['bag_id'])))
    return tapes


def weighted(c):
    return c['tray_wait'] + c['nonprotected_tardiness'] + .1*c['empty_distance'] + 10*c['terminal_backlog'] + 2*c['terminal_inflight']


def analyze(source, target):
    started, cpu = perf_counter(), process_time()
    target.mkdir(parents=True, exist_ok=False)
    (target/'analyze.py').write_bytes(Path(__file__).read_bytes())
    checks, errors, bound = 0, [], {}
    def check(ok, where):
        nonlocal checks
        checks += 1
        if not ok:
            errors.append(where)
    def close(a, b):
        return abs(a-b) < 1e-8
    def bind(path):
        bound[str(path.resolve())] = sha256(path.read_bytes()).hexdigest()
    manifest, protocol, summary = read(source/'manifest.json'), read(source/'protocol.json'), read(source/'summary.json')
    for name, expected in manifest.items():
        p = source/name
        bind(p)
        check(bound[str(p.resolve())] == expected, 'manifest:'+name)
    bind(source/'manifest.json')
    for name, expected in protocol['source_sha256'].items():
        p = source/'source_snapshot'/name
        check(sha256(p.read_bytes()).hexdigest() == expected, 'source:'+name)
    inputs = {(x['si'],x['ti']):x for x in read(source/'inputs.json')}
    units = [tuple(u) for u in protocol['units']]
    expected = {f's{s}_t{t}_{p}' for s,t in units for p in POLICIES}
    rows = {r['identity']:r for r in summary['rows']}
    check(len(rows)==len(summary['rows']) and set(rows)==expected, 'complete_request_grid')
    check(not summary['source_changed'], 'source_unchanged')
    records, by_policy, paired = {}, defaultdict(list), []
    totals = Counter()
    for identity, r in rows.items():
        path = source/'cases'/r.get('file', identity+'.failure.json')
        if r['status'] != 'controller_quiescent':
            check(False, identity+':unresolved:'+r['status'])
            continue
        d = read(path)
        records[identity] = d
        by_policy[r['policy']].append(r)
        check(sha256(path.read_bytes()).hexdigest()==r['sha256'], identity+':record_sha')
        check(d['identity']==identity and not d['source_changed'], identity+':identity_source')
        si, ti = map(int, [identity.split('_')[0][1:],identity.split('_')[1][1:]])
        inp = inputs[si,ti]
        bags = dict(inp['initial']['bags'])
        bags.update({b['bag_id']:b for b in inp['actual_tasks_event_engine_only']})
        for endpoint in ('h80','final'):
            e, m = d['endpoints'][endpoint], d['metrics'][endpoint]
            result = e['result']
            check(e['metrics']==m and r[endpoint]==m, identity+':'+endpoint+':metrics_equal')
            check(m['scheduled']==len(bags), identity+':'+endpoint+':denominator')
            complete = result['completed']
            check(set(complete).issubset(bags) and m['completed']==len(complete), identity+':'+endpoint+':completed')
            check(m['on_time']==sum(time<=bags[bid]['deadline'] for bid,time in complete.items()), identity+':'+endpoint+':ontime')
            check(set(m['unfinished'])==set(bags)-set(complete), identity+':'+endpoint+':unfinished')
            check(close(weighted(result['cost_components']),result['total_cost']) and close(result['total_cost'],m['total_cost']),identity+':'+endpoint+':objective')
        c = d['endpoints']['final']['cycle']
        check(c['task_complete'] and c['transport_drained'] and c['forecast_expired'],identity+':drain')
        check(d['endpoints']['final']['time']-d['quiet_since']>=2 and d['final_slow_trigger_count']>d['quiet_start_slow_trigger_count'],identity+':quiet_cycle')
        count = Counter()
        for hi,h in enumerate(d['slow_history']):
            where = f'{identity}/h{hi}'
            diag = h['diagnostics']
            scores = diag['scored_actions']
            count['changed_actions'] += bool(diag['actual_sequence_changed'])
            count['fallbacks'] += bool(diag['fallback_to_greedy'])
            count['unscored_actions'] += diag['unscored_enumerated_actions']
            count['unsearched_requests'] += diag['proposal_unsearched_requests']
            count['pool_discarded'] += diag['proposal_pool_discarded_valid']
            check(len(scores)<=12, where+':action_budget')
            check(all(f['published_at']<=diag['snapshot_time'] for f in diag['published_forecasts']),where+':publication_gate')
            check(all(b['arrival']>diag['snapshot_time'] for b in diag['proxy_bags']),where+':public_proxy_future')
            count['internal_query_calls'] += diag['greedy_diagnostics']['search_calls']+diag['proposal_search_calls']
            count['internal_query_work'] += diag['greedy_diagnostics']['search_expansions']+diag['proposal_search_work']
            expected_tapes = sample_from_public(diag) if r['policy']!='point' and scores else None
            for ai,s in enumerate(scores):
                loc = where+f'/a{ai}'
                count['action_evaluations'] += 1
                ps = s.get('physical_scenarios',[s])
                count['physical_proxy_calls'] += len(ps)
                count['requested_scenarios'] += s.get('requested_scenarios',1)
                count['duplicate_reuses'] += s.get('exact_duplicate_reuses',0)
                count['internal_query_calls'] += sum(v['search_calls'] for v in ps)
                count['internal_query_work'] += sum(v['search_work'] for v in ps)
                for pi,p in enumerate(ps):
                    check(p['proposals']==s['proposals'],loc+f'/p{pi}:same_action')
                    check(p['search_calls']==len(p['searches']) and p['search_work']==sum(q['work'] for q in p['searches']),loc+f'/p{pi}:query_ledger')
                    if p['status']=='complete':
                        check(p['ticks']==40 and close(p['proxy_cost'],weighted(p['cost_components'])),loc+f'/p{pi}:score')
                    else:
                        count['incomplete_physical'] += 1
                if expected_tapes is None:
                    continue
                req = s['scenarios']
                check(len(req)==8 and s['requested_scenarios']==8,loc+':8_denominator')
                check([q['future_sha256'] for q in req]==[digest(t) for t in expected_tapes],loc+':independent_public_draws')
                check(len(ps)==len({q['future_sha256'] for q in req}) and len(ps)+s['exact_duplicate_reuses']==8,loc+':physical_memo_count')
                seen = set()
                for qi,q in enumerate(req):
                    p = ps[q['physical_index']]
                    check(q['cache_hit']==(q['future_sha256'] in seen),loc+f'/r{qi}:memo_order')
                    seen.add(q['future_sha256'])
                    check(p['public_scenario_tape']==expected_tapes[qi] and digest(p['public_scenario_tape'])==q['future_sha256']==p['public_scenario_sha256'],loc+f'/r{qi}:tape_hash')
                    check(q['proxy_cost']==p['proxy_cost'] and q['status']==p['status'],loc+f'/r{qi}:physical_reference')
                complete = all(p['status']=='complete' for p in ps)
                check((s['status']=='complete')==complete,loc+':no_partial_ranking')
                if complete:
                    check(close(s['proxy_cost'],sum(q['proxy_cost'] for q in req)/8),loc+':multiplicity_mean')
                    for k,v in s['cost_components'].items():
                        check(close(v,sum(ps[q['physical_index']]['cost_components'][k] for q in req)/8),loc+':component_mean:'+k)
                else:
                    check(s['proxy_cost'] is None,loc+':invalid_partial_mean')
            if scores and not diag['fallback_to_greedy']:
                eligible = [s for s in scores if s['status']=='complete']
                best = eligible[0]
                for s in eligible[1:]:
                    if s['proxy_cost'] < best['proxy_cost']-1e-9 or (abs(s['proxy_cost']-best['proxy_cost'])<=1e-9 and (len(s['proposals']),key(s['proposals']),s['ordinal'])<(len(best['proposals']),key(best['proposals']),best['ordinal'])):
                        best=s
                check(diag['selected_action_index']==best['ordinal'] and close(diag['selected_proxy_cost'],best['proxy_cost']),where+':selection')
                check(key(h['proposals'])==key(best['proposals']),where+':selected_physical_sequence')
        for k in ('action_evaluations','physical_proxy_calls','requested_scenarios','duplicate_reuses','internal_query_calls','internal_query_work','fallbacks'):
            check(count[k]==d['metrics'][k]==r[k],identity+':accounting:'+k)
        totals.update(count)
    table=[]
    old=read(ROOT/'phase4_w3_empty_improvement_20261010'/'summary.json')
    bind(ROOT/'phase4_w3_empty_improvement_20261010'/'summary.json')
    oldrows={r['identity']:r for r in old['rows']}
    fac=ROOT/'phase4_w3_empty_factorial_complete_20261010'
    frows={r['identity']:r for r in read(fac/'summary.json')['rows']}
    bind(fac/'summary.json')
    for p in POLICIES:
        rs=by_policy[p]
        row={'policy':p,'resolved':len(rs),'planned':len(units),'J':sum(r['final']['total_cost'] for r in rs),
            'on_time':sum(r['final']['on_time'] for r in rs),'completed':sum(r['final']['completed'] for r in rs),
            'scheduled':sum(r['final']['scheduled'] for r in rs),
            **{k:sum(r[k] for r in rs) for k in ('invocation_cpu_seconds','process_cpu_seconds','physical_proxy_calls','requested_scenarios','duplicate_reuses','action_evaluations','internal_query_calls','internal_query_work')}}
        for baseline in ('point','legacy_empty12','greedy'):
            diffs=[]
            for s,t in units:
                own=rows[f's{s}_t{t}_{p}']
                base=rows[f's{s}_t{t}_point'] if baseline=='point' else oldrows[f's{s}_t{t}_{baseline}']
                delta=own['final']['total_cost']-base['final']['total_cost']
                diffs.append(delta)
                paired.append({'si':s,'ti':t,'policy':p,'baseline':baseline,'delta_J':delta,
                    'delta_on_time':own['final']['on_time']-base['final']['on_time']})
            row['vs_'+baseline]={'better':sum(v < -1e-8 for v in diffs),'equal':sum(abs(v)<=1e-8 for v in diffs),'worse':sum(v>1e-8 for v in diffs),'sum_delta_J':sum(diffs)}
        table.append(row)
    for s,t in units:
        ident=f's{s}_t{t}_point'
        fr=frows[f's{s}_t{t}_timed_greedy__fewest_physical']
        path=fac/'cases'/fr['file']
        bind(path)
        check(sha256(path.read_bytes()).hexdigest()==fr['sha256'],ident+':factorial_reference_sha')
        fd=read(path)
        for ep in ('h80','final'):
            check(physical(records[ident]['endpoints'][ep]['result'])==physical(fd['endpoints'][ep]['result']),ident+':factorial_physical_reproduction:'+ep)
    report={'schema':'public_scenario_artifact_analysis_v1','checks':checks,'errors':errors,'table':table,
        'paired':paired,'totals':dict(totals),'resources':{k:v for k,v in summary.items() if k!='rows'},
        'bound_before':bound,'source_scope':'Pure JSON/gzip audit, independent public RNG reconstruction, no simulation or controller imports',
        'limits':['36 reused synthetic development tapes; three sampling seeds are not independent operating days',
          'Prior uncalibrated, scenario sampling error does not bound model error',
          'Actions still generated from point public demand, scenario count does not enlarge action family',
          'Inherited generic claim says one_public_proxy; scenario-specific action_objective and nested physical records define the actual eight-draw mean',
          'Proxy row CPU excludes sampling/hash overhead; deployment and invocation CPU include it']}
    report['bound_files_unchanged']=all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in bound.items())
    report['analysis_cpu_seconds']=process_time()-cpu
    report['analysis_wall_seconds']=perf_counter()-started
    (target/'analysis.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    lines=['# Public-forecast scenario control: full development result','',
        f'Audit: {checks:,} checks, {len(errors)} errors; {len(bound)} bound files unchanged: {report["bound_files_unchanged"]}.','',
        '|Policy|J|On time|Completed|vs point better/equal/worse|vs legacy better/equal/worse|Invocation CPU s|Physical proxy calls|',
        '|---|---:|---:|---:|---|---|---:|---:|']
    for r in table:
        signs=lambda b:'/'.join(str(r['vs_'+b][k]) for k in ('better','equal','worse'))
        lines.append(f'|{r["policy"]}|{r["J"]:.3f}|{r["on_time"]}|{r["completed"]}/{r["scheduled"]}|{signs("point")}|{signs("legacy_empty12")}|{r["invocation_cpu_seconds"]:.2f}|{r["physical_proxy_calls"]}|')
    lines += ['', 'All three fixed seeds are reported. Each comparison uses all 36 paired existing tapes in a formal run, four nominal tapes in a pilot. No selection of best seed or efficacy subset.', '',*['- '+s for s in report['limits']]]
    (target/'SCENARIO_RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    manifest={p.name:sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file()}
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'checks':checks,'errors':errors[:20],'table':table,'unchanged':report['bound_files_unchanged']},ensure_ascii=False))
    return bool(errors or not report['bound_files_unchanged'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    raise SystemExit(analyze(args.source,args.output))
