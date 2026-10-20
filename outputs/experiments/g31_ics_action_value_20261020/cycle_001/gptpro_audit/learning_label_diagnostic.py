"""Read-only 13cf behavior-label identifiability diagnostics. Standard library only.

Closed-form descriptive regressions use the same 81 training rows. They are not
independent validation, policy fitting, project imports, or native experiments.
"""
from pathlib import Path
import ast
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
import statistics

import argparse
_parser = argparse.ArgumentParser(description=__doc__)
_parser.add_argument('--root', required=True, type=Path)
_parser.add_argument('--output', type=Path, default=Path('learning_label_diagnostic.json'))
_args = _parser.parse_args()
ROOT = _args.root.resolve()
OUT = _args.output.resolve()
OUT.parent.mkdir(parents=True, exist_ok=True)
CYCLE = ROOT / 'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001'


def json_gz(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def jsonl_gz(path):
    with gzip.open(path, 'rt', encoding='utf8') as stream:
        return [json.loads(line) for line in stream]


def fit_line(xs, ys):
    xm, ym = statistics.fmean(xs), statistics.fmean(ys)
    den = math.fsum((x-xm)**2 for x in xs)
    slope = math.fsum((x-xm)*(y-ym) for x,y in zip(xs,ys)) / den if den else 0.
    intercept = ym-slope*xm
    predicted = [intercept+slope*x for x in xs]
    return {'intercept':intercept, 'slope':slope, **metrics(predicted,ys)}


def metrics(pred, ys):
    error = [p-y for p,y in zip(pred,ys)]
    mse = statistics.fmean(e*e for e in error)
    ym = statistics.fmean(ys)
    variance = statistics.fmean((y-ym)**2 for y in ys)
    return {'mse_bag_seconds_squared':mse, 'rmse_bag_seconds':math.sqrt(mse),
            'mae_bag_seconds':statistics.fmean(abs(e) for e in error),
            'training_descriptive_r_squared':1-mse/variance if variance else None}


def main():
    materials = jsonl_gz(CYCLE/'B2_behavior_training_001/materialized_training_rows.jsonl.gz')
    eligible = jsonl_gz(CYCLE/'B2_behavior_readiness_003/eligible_behavior_rows.jsonl.gz')
    classified = jsonl_gz(CYCLE/'B2_behavior_readiness_003/classifications.jsonl.gz')
    raw = json_gz(CYCLE/'C00_receiver_recorded_v2_001/C00/raw.json.gz')['final_result']
    arrivals = {r['business_bag_id']:r['time'] for r in raw['receipts'] if r['event']=='BAG_ARRIVAL'}
    completions = {r['business_bag_id']:r['time'] for r in raw['receipts'] if r['event']=='UNLOAD_COMPLETE'}
    by_request = {r['submission']['actual_request']['request_id']:r for r in eligible}
    module_path = ROOT/'scripts/experiments/g31_ics_circulation/foundation_action_value.py'
    parsed = ast.parse(module_path.read_text())
    allowed_functions = {'require','number','detached','digest','_identity','_waiting_count',
        '_inbound_ack','validate_accounts','wrap_observation','_mass','_account_counts','features'}
    allowed_constants = {'OBSERVATION_SCHEMA','MODEL_SCHEMA','FEATURE_SCHEMA','WINDOWS','ACCOUNT_NAMES'}
    nodes = [n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name in allowed_functions
             or isinstance(n,ast.Assign) and all(isinstance(t,ast.Name) and t.id in allowed_constants for t in n.targets)]
    scope = {'json':json,'math':math,'hashlib':hashlib}
    exec(compile(ast.Module(nodes,type_ignores=[]),str(module_path),'exec'),scope)
    items = []
    for item in materials:
        row = item['row']; obs = row['observation']; t = obs['now']; end = t+300.
        origin = by_request[item['evidence']['request_id']]
        assert row['target_value'] == origin['target_value']
        features = scope['features'](obs,row['action'])
        actual = math.fsum(max(0.,min(end,completions.get(b,end))-max(t,a))
                          for b,a in arrivals.items() if a<end)
        n = sum(a<=t and completions.get(b,end)>t for b,a in arrivals.items())
        new_mass = math.fsum(end-a for a in arrivals.values() if t<a<end)
        completion_relief = math.fsum(end-c for c in completions.values() if t<c<end)
        assert abs(actual-(300*n+new_mass-completion_relief))<1e-7
        assert abs(-actual-row['target_value'])<1e-7
        waiting = obs['circulation_accounts']['known_waiting_jobs']
        public_waiting = sum(r.get('count',0) or 0 for r in waiting)
        items.append({'request_id':item['evidence']['request_id'],'owner':obs['owner_id'],
            'decision_id':obs['decision_id'],'at':t,'target':row['target_value'],
            'global_backlog_asof':n,'backlog_constant_300s':300*n,
            'new_arrival_bag_seconds':new_mass,'completion_relief_bag_seconds':completion_relief,
            'global_backlog_area_to_actual_ratio':300*n/actual,
            'public_observed_waiting_sum':public_waiting,
            'public_waiting_any_missing':any(r.get('count') is None for r in waiting),
            'action':row['action'],'features':features,
            'first_edge_delay':origin['execution']['first_edge']['time']-t,
            'ack_delay':origin['execution']['positive_ack']['delivered_at']-t,
            'received_within_300s':origin['execution']['received_within_label_window']})
    targets = [r['target'] for r in items]
    by_t = defaultdict(list)
    for row in items: by_t[row['at']].append(row)
    assert all(len({r['target'] for r in group})==1 for group in by_t.values())
    feature_names = sorted(items[0]['features'])
    varying = [k for k in feature_names if len({r['features'][k] for r in items})>1]
    ratios = [r['global_backlog_area_to_actual_ratio'] for r in items]
    summary = {
      'scope':'same-81-row train-only descriptive identifiability diagnostic; no heldout or control benefit claim',
      'project_imports':0,'native_runs':0,'policy_or_predictor_training_runs':0,
      'closed_form_scalar_descriptive_regressions_only':True,
      'source_sha256':hashlib.sha256(module_path.read_bytes()).hexdigest(),
      'rows':len(items),'unique_starts':len(by_t),'multirow_starts':sum(len(g)>1 for g in by_t.values()),
      'rows_at_multirow_starts':sum(len(g) for g in by_t.values() if len(g)>1),
      'shared_target_at_every_same_start':True,'owners':dict(Counter(r['owner'] for r in items)),
      'labels_min_max':[min(targets),max(targets)],'global_current_backlog_min_max':[min(r['global_backlog_asof'] for r in items),max(r['global_backlog_asof'] for r in items)],
      'global_backlog_area_to_actual_ratio':{'min':min(ratios),'mean':statistics.fmean(ratios),'max':max(ratios)},
      'simple_baselines':{
        'constant_train_mean':metrics([statistics.fmean(targets)]*len(targets),targets),
        'time_only_train_ols':fit_line([r['at'] for r in items],targets),
        'global_current_backlog_train_ols_PRIVILEGED_DIAGNOSTIC':fit_line([r['global_backlog_asof'] for r in items],targets),
        'negative_300_times_global_backlog_no_fit_PRIVILEGED_DIAGNOSTIC':metrics([-300*r['global_backlog_asof'] for r in items],targets),
        'public_observed_waiting_sum_train_ols':fit_line([r['public_observed_waiting_sum'] for r in items],targets),
        'destination_waiting_train_ols':fit_line([r['features']['destination_known_waiting'] for r in items],targets),
      },
      'feature_count':len(feature_names),'varying_feature_count':len(varying),'varying_features':varying,
      'all_missing_deficit_source':all(r['features']['source_estimated_deficit_missing']==1 for r in items),
      'all_missing_deficit_destination':all(r['features']['destination_estimated_deficit_missing']==1 for r in items),
      'received_within_300s':sum(r['received_within_300s'] for r in items),
      'public_arrival_delay_gt_300s':sum(r['features']['arrival_delay_s']>300 for r in items),
      'first_edge_delay_min_max':[min(r['first_edge_delay'] for r in items),max(r['first_edge_delay'] for r in items)],
      'actual_classifications':dict(Counter(r['status'] for r in classified)),
      'first_same_clock_example':[{k:v for k,v in r.items() if k!='features'} for r in by_t[min(by_t)]],
    }
    receipt = json.loads((CYCLE/'B2_behavior_training_001/receipt.json').read_bytes())
    summary['saved_network_training_mse'] = {str(m['seed']):m['training_mse'] for m in receipt['models']}
    OUT.write_text(json.dumps({'summary':summary,'rows':items},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
