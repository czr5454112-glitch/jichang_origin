"""Independent artifact-only audit: never fits, simulates, or imports experiment code."""
from pathlib import Path
from hashlib import sha256
from collections import Counter, defaultdict
import argparse
import json


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


checks, errors = Counter(), []


def check(ok, label, detail=None):
    checks[label] += 1
    if not ok:
        errors.append({'check': label, 'detail': detail})


def approx(a, b):
    return abs(a-b) <= 1e-8


def hash_map(root, hashes):
    for name, expected in hashes.items():
        check(sha(root/name) == expected, 'artifact_sha', str(root/name))


def source_map(root, hashes):
    hash_map(root/'source_snapshot', hashes)


def unit_manifest(root, name):
    m = read(root/name)
    check({p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()} == set(m['files_sha256']) | {name},
          'frozen_file_set', str(root))
    hash_map(root, m['files_sha256'])


def cost(components):
    weights = {'tray_wait': 1., 'nonprotected_tardiness': 1., 'empty_distance': .1,
               'terminal_backlog': 10., 'terminal_inflight': 2.}
    return sum(v*weights[k] for k,v in components.items())


def physics_projection(value):
    if isinstance(value, dict):
        return {k:physics_projection(v) for k,v in value.items() if not k.endswith('_ms') and k not in ('wall_seconds','cpu_seconds')}
    if isinstance(value, list):
        return [physics_projection(v) for v in value]
    return value


def destination(root):
    s, p, manifest = read(root/'summary.json'), read(root/'protocol.json'), read(root/'manifest.json')
    source = read(root/'source_manifest.json')
    source_map(root, source['source_sha256'])
    check(sha(root/'source_manifest.json') == manifest['source_manifest_sha256'], 'destination_source_manifest')
    check(sha(root/'summary.json') == manifest['summary_sha256'], 'destination_summary_sha')
    for reference in read(root/'input_manifest.json').values():
        hash_map(Path(reference['directory']), reference['files_sha256'])
        source_map(Path(reference['directory']), reference['archived_source_sha256'])
    records, old_comparisons, override_count, budget_status = [], 0, 0, Counter()
    for unit, checksum in manifest['unit_manifest_sha256'].items():
        folder = root/'units'/unit
        check(sha(folder/'manifest.json') == checksum, 'destination_unit_manifest_sha')
        unit_manifest(folder, 'manifest.json')
        us = read(folder/'summary.json')
        check(us['episodes'] == 52 and len(us['records']) == 52, 'destination_unit_52', unit)
        check(not us['failures'] and not us['original_physics_mismatches'], 'destination_unit_failures', unit)
        old_comparisons += len(us['original_physics_comparisons'])
        inputs = read(folder/'inputs.json')
        for row in us['records']:
            artifact = read(folder/(row['policy']+'__'+row['variant']+'.json'))
            check(artifact['metrics'] == row, 'destination_metrics_original', unit)
            check(approx(cost(row['cost_components']),row['total_cost']), 'destination_cost_components', unit)
            check(row['completed'] + len(row['uncompleted']) == row['scheduled_bags'], 'destination_bag_denominator', unit)
            if row['variant']=='original':
                comparison=artifact['old_physics_comparison']
                previous_path=Path(comparison['old_record'])
                check(sha(previous_path)==comparison['old_record_sha256'],'destination_old_record_sha')
                previous=read(previous_path)
                for field in ('result','boundaries','route_history','slow_history','slow_trigger_times'):
                    a,b=physics_projection(artifact[field]),physics_projection(previous[field])
                    if field=='slow_history':
                        for history in (a,b):
                            for event in history: event.get('diagnostics',{}).pop('search_expansions',None)
                    check(a==b,'destination_independent_old_physics_'+field,(unit,row['policy']))
            history = artifact['destination_first_history']
            route_history = artifact['route_history']
            check(len(history) == row['selector_calls'] == len(route_history), 'destination_selector_denominator', unit)
            check(sum(h['overridden'] for h in history) == row['overrides'], 'destination_override_count', unit)
            for h,r in zip(history,route_history):
                eligible = [v['index'] for v in h['unload_validation'] if v['accepted']]
                expected = eligible[0] if h['enabled'] and eligible else h['delegate_index']
                check(h['chosen_index'] == expected, 'destination_rule_choice', (unit,row['policy'],h['time']))
                check(len(h['delegate_records']) == 1, 'destination_delegate_once', (unit,row['policy'],h['time']))
                check(h['chosen'] == r['chosen'] and h['chosen'] == r['candidates'][expected], 'destination_logged_pool_choice', unit)
                check(h['delegate_choice']==r['candidates'][h['delegate_index']],'destination_delegate_normal_pool',unit)
                if h['overridden']:
                    override_count += 1
                    check(h['chosen_action_key']!=h['delegate_action_key'],'destination_override_physical_key_changed',unit)
                    c=h['chosen']
                    bag=artifact['result']['final_snapshot']['bags'][h['bag_id']]
                    check(h['at_destination'] and h['source_node']==bag['destination'] and not c['legs'] and not c['prefix_only'],
                          'destination_override_zero_edge', (unit,row['policy'],h['time']))
            budget_status.update(o['search_status'] for o in artifact['loaded_opportunities'])
            records.append(row)
    check(len(records)==s['episodes']==1872, 'destination_total_1872')
    check(old_comparisons==s['original_physics_comparisons']==936, 'destination_old_936')
    check(not s['source_changed_during_run'] and not s['failures'] and not s['original_physics_mismatches'], 'destination_final_status')
    indexed={(r['stream'],r['realization'],r['policy'],r['variant']):r for r in records}
    check(len(indexed)==1872, 'destination_unique_cells')
    groups=defaultdict(lambda:dict(pairs=0,cost_original=0.,cost_rule=0.,completed_original=0,completed_rule=0,
        ontime_original=0,ontime_rule=0,better=0,equal=0,worse=0))
    for key,row in indexed.items():
        if key[-1]!='original': continue
        other=indexed[key[:-1]+('destination_first',)]
        group=groups[(row['policy'], 'nominal' if row['realization']=='nominal' else 'stress')]
        group['pairs']+=1
        for suffix, value in [('original',row),('rule',other)]:
            group['cost_'+suffix]+=value['total_cost']; group['completed_'+suffix]+=value['completed']; group['ontime_'+suffix]+=value['on_time']
        diff=other['total_cost']-row['total_cost']
        group['equal' if abs(diff)<=1e-8 else 'better' if diff<0 else 'worse']+=1
    return {'episodes':len(records),'original_physics_comparisons':old_comparisons,'overrides':override_count,
        'search_status_counts':dict(budget_status),'paired_tables':[{'policy':key[0],'realization':key[1],**value} for key,value in sorted(groups.items())]}


def horizon(root):
    p, inputs = read(root/'protocol.json'), read(root/'input_manifest.json')
    source_map(root,p['source_sha256'])
    prior=Path(p['prior_path'])
    old_protocol=read(prior/'protocol.json')
    for name in ('runtime.py','model.py','phase4_control.py','prebalance.py','learning.py','nonlinear_learning.py','evaluation.py','role_features.py'):
        check(p['source_sha256'][name]==old_protocol['source_sha256'][name], 'horizon_controller_model_source_unchanged', name)
    for relative, key in [('r0/frozen_models.json','frozen_models_sha256'),('r0/folds_and_bounds.json','folds_bounds_sha256')]:
        check(sha(prior/relative)==inputs[key], 'horizon_model_input_unchanged', relative)
    selected={(r['owner'],r['identity']):r for r in inputs['selected']}
    check(len(selected)==208,'horizon_selected208')
    expected_raw=26624
    seen=set(); requests=actual=reused=unexecuted=matches=0; nodes=Counter(); owner_counts=Counter(); decisions=[]
    for owner_folder in sorted((root/'owners').iterdir()):
        unit_manifest(owner_folder,'stage_manifest.json')
        us=read(owner_folder/'summary.json')
        check(not us['failures'] and not us['source_changed_during_run'],'horizon_owner_status',owner_folder.name)
        owner_counts[owner_folder.name]=len(us['records'])
        for record in us['records']:
            key=(owner_folder.name,record['identity']); seen.add(key)
            entry=selected[key]
            for kind in ('sample','label'):
                check(sha(prior/entry[kind])==entry[kind+'_sha256'],'horizon_old_input_sha')
            old=read(prior/entry['label'])
            old_rows={(r['group'],r['candidate'],r['future_index']):r for r in old['raw_branches']}
            label_path=owner_folder/record['label_file']; label=read(label_path)
            nodes[label['source_node']]+=1
            requests+=label['requested_branches']; actual+=label['actual_branches']; reused+=label['cache_reused']; unexecuted+=label['not_executed_requests']
            check(len(label['raw_branches'])==label['requested_branches']==128,'horizon_sample128',key)
            check(label['actual_branches']+label['cache_reused']+label['not_executed_requests']==128,'horizon_branch_ledger',key)
            check(label['endpoint_reads']==384 and label['actual_unique_endpoint_reads']==label['actual_branches']*3
                  and label['actual_unique_endpoint_reads_exact'], 'horizon_requested_and_physical_endpoints', key)
            check(label['future_groups_offline_only']==old['future_groups_offline_only'],'horizon_fixed_tapes',key)
            evidence_keys={}; cellset=set(); means=defaultdict(list)
            for row in label['raw_branches']:
                cell=(row['group'],row['candidate'],row['future_index']); cellset.add(cell)
                previous=old_rows[cell]
                check(not row['failed'] and not row['not_executed'],'horizon_branch_success',(key,cell))
                check(row['future_sha256']==previous['future_sha256'],'horizon_future_sha',(key,cell))
                endpoint=row['endpoints']['20']
                equal=approx(endpoint['total_cost'],previous['total_cost']) and all(endpoint[k]==previous[k] for k in ('cost_components','completed','uncompleted'))
                matches+=equal
                check(equal and row['twenty_matches_historical'],'horizon_exact_old20',(key,cell))
                emap=(row['candidate'],row['future_sha256'])
                if row['evidence'] in evidence_keys:
                    check(evidence_keys[row['evidence']]==emap,'horizon_short_name_unambiguous',(key,cell))
                evidence_keys[row['evidence']]=emap
                for h in (20,40,80):
                    e=row['endpoints'][str(h)]
                    check(approx(cost(e['cost_components']),e['total_cost']),'horizon_cost_accounting',(key,cell,h))
                    check(approx(e['terminal_cost']+e['nonterminal_cost_same_trajectory'],e['total_cost']),'horizon_terminal_accounting',(key,cell,h))
                    for metric in ('total_cost','nonterminal_cost_same_trajectory'):
                        means[h,metric,row['candidate']].append(e[metric])
            check(len(cellset)==128,'horizon_unique_cells',key)
            check(len(evidence_keys)==label['actual_branches'],'horizon_unique_evidence_count',key)
            for h in (20,40,80):
                for metric in ('total_cost','nonterminal_cost_same_trajectory'):
                    values=[sum(means[h,metric,c])/32 for c in range(4)]
                    opt=[c for c,v in enumerate(values) if abs(v-min(values))<=1e-9]
                    decisions.append({'owner':key[0],'identity':key[1],'horizon':h,'metric':metric,'means':values,'optimal_indices':opt})
    check(seen==set(selected),'horizon_sample_coverage')
    check(requests==matches==expected_raw and actual+reused==expected_raw and unexecuted==0,'horizon_full_denominator')
    unit_manifest(root/'analysis','stage_manifest.json')
    s=read(root/'analysis/summary.json')
    check(not s['failures'] and not s['source_changed_during_run'],'horizon_summary_status')
    for name,value in [('requested_branches',requests),('actual_branches',actual),('cache_reused',reused),('not_executed_requests',unexecuted)]:
        check(s[name]==value,'horizon_summary_'+name)
    indexed={(r['owner'],r['identity'],r['horizon'],r['metric']):r for r in s['decisions']}
    for r in decisions:
        other=indexed[r['owner'],r['identity'],r['horizon'],r['metric']]
        check(r['optimal_indices']==other['optimal_indices'] and all(approx(a,b) for a,b in zip(r['means'],other['means'])),'horizon_decision_analysis')
    return {'selected':len(seen),'owners':len(owner_counts),'nonempty_owners':sum(bool(n) for n in owner_counts.values()),
        'nodes':dict(nodes),'requested':requests,'actual':actual,'reuse':reused,'old20_matches':matches,'tables':s['tables'],'paired_endpoint_tables':s['paired_endpoint_tables']}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--destination',type=Path); parser.add_argument('--horizon',type=Path); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result={}
    if args.destination: result['destination']=destination(args.destination)
    if args.horizon: result['horizon']=horizon(args.horizon)
    result.update(checks_by_kind=dict(checks),checks=sum(checks.values()),errors=errors,source_sha256=sha(__file__),scope='read-only artifact/hash/arithmetic audit; no reruns or model fitting')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f: json.dump(result,f,indent=2)
    print(json.dumps({'checks':result['checks'],'errors':errors,'output':str(args.output)}))
    raise SystemExit(bool(errors))
