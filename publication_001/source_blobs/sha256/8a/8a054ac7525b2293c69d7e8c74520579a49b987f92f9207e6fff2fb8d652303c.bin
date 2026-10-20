"""Bounded offline equivalence audit; private as-of reconstruction stays here.

No fit/native calls. The optimized runtime receives only the same public plan
and explicitly synthetic arrived-count snapshots used by frozen B1 evaluation.
"""
from __future__ import annotations
import sys
TOKEN = 'g31_flight_arrays_exact_saved_parity_v1'
if __name__ == '__main__' and '--run' in sys.argv:
    if sys.stdin.readline().strip() != TOKEN:
        raise SystemExit('flight_arrays_validation:bounded_parent_admission_required')

import argparse
import ast
import copy
import gzip
import hashlib
import json
from pathlib import Path
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT/'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001'
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_flight_arrays_validation'


def require(value, reason):
    if not value: raise ValueError('flight_arrays_validation:' + reason)


def read(path): return json.loads(Path(path).read_bytes())


def ref(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def encoded(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def prepare(output):
    output = Path(output).resolve(); require(output.is_relative_to(ROOT) and not output.exists(), 'fresh_output')
    b1 = BASE/'B1_training_001'; old = read(BASE/'B2_public_feature_audit_002/plan.json')
    names = ['foundation_flight_forecaster_arrays.py', 'foundation_flight_arrays_validation.py',
        'foundation_flight_training.py', 'foundation_flight_data.py']
    sources = {**old['source_sha256'], **{str(Path(__file__).with_name(name)): ref(Path(__file__).with_name(name))['sha256'] for name in names}}
    inputs = {name: ref(b1/path) for name, path in {'checkpoint':'flight_forecaster_checkpoint.json',
        'public_plan':'public/static_flight_plan.json', 'split':'flight_split_manifest.json', 'receipt':'receipt.json',
        'forecasts':'forecast_predictions.jsonl', 'private_asof_evaluator_index':'private/flight_label_index.jsonl'}.items()}
    inputs.update(trace=old['inputs']['trace'], mapping=old['inputs']['mapping'])
    plan = {'schema':'g31.flight_arrays_exact_saved_parity.v1', 'status':'prepared_not_executed',
        'sources': sources, 'inputs': inputs, 'output':str(output), 'expected_saved_forecasts':402,
        'B2_sequences':[0,473,945], 'soft_wall_seconds':120, 'native_branches':0, 'fit_calls':0,
        'forecast_outputs_unchanged':True, 'cross_call_cache':False,
        'private_index_scope':'offline exact replay of original synthetic as-of feeds only; never runtime inputs or new training labels'}
    output.mkdir(parents=True); write(output/'plan.json', plan)
    task = {'task_id':output.name, 'module':MODULE, 'args':['--run','--output',str(output)],
        'native_branches':0, 'hard_seconds':150, 'inner_admission':TOKEN,
        'sources':[*sources,*(r['path'] for r in inputs.values()),str(output/'plan.json')], 'requires':[],
        'assessment':{'path':str(output/'receipt.json'),'allowed_statuses':['completed_exact_saved_forecast_and_B2_parity']},
        'next_action':'Use independent per-call array interface only after complete byte-exact old prediction and B2 parity. No B1 fit/selection/native changes.'}
    write(output.parent/(output.name+'_task.json'), task)
    return plan


def structural_parity(old, new):
    before = next(n for n in ast.parse(Path(old.__file__).read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='predict')
    after = next(n for n in ast.parse(Path(new.__file__).read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='predict')
    if isinstance(before.body[0], ast.Expr) and isinstance(before.body[0].value, ast.Constant): before.body.pop(0)
    class Normalize(ast.NodeTransformer):
        def visit_Assign(self,node):
            if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('windows','cdf_edges','cdf_values'):
                return None
            return self.generic_visit(node)
        def visit_Name(self,node):
            if isinstance(node.ctx,ast.Load) and node.id in ('cdf_edges','cdf_values'):
                return ast.Subscript(value=ast.Name(id='params',ctx=ast.Load()),slice=ast.Constant(value=node.id),ctx=ast.Load())
            if isinstance(node.ctx,ast.Load) and node.id=='windows':
                return ast.Call(func=ast.Attribute(value=ast.Name(id='np',ctx=ast.Load()),attr='asarray',ctx=ast.Load()),
                    args=[ast.Name(id='WINDOWS',ctx=ast.Load())],keywords=[])
            return node
        def visit_Attribute(self,node):
            if isinstance(node.value,ast.Name) and node.value.id=='original':
                return ast.Name(id=node.attr,ctx=ast.Load())
            return self.generic_visit(node)
    require(ast.dump(before)==ast.dump(Normalize().visit(after)), 'only_per_call_array_materialization_changed')
    return True


def run(output):
    from . import foundation_flight_forecaster as old
    from . import foundation_flight_forecaster_arrays as new
    from . import foundation_flight_training as training
    from . import foundation_airport_learning_audit as audit
    from . import foundation_airport_learning_public as public
    from . import foundation_action_value as value
    output=Path(output);plan=read(output/'plan.json');started=time.perf_counter();deadline=started+plan['soft_wall_seconds']
    result={'schema':plan['schema'],'status':'failed_exact_saved_forecast_and_B2_parity','plan':ref(output/'plan.json'),
        'native_branches':0,'fit_calls':0,'new_training_labels':0,'completed_saved_forecasts':0,'B2_rows':[]}
    try:
        require(plan['expected_saved_forecasts']==402 and plan['B2_sequences']==[0,473,945]
            and plan['soft_wall_seconds']==120,'fixed_validation_budget')
        require(all(ref(path)['sha256']==sha for path,sha in plan['sources'].items()),'source_pins')
        require(all(ref(r['path'])==r for r in plan['inputs'].values()),'input_pins')
        result['AST_exact_except_array_materialization']=structural_parity(old,new)
        model=read(plan['inputs']['checkpoint']['path']);context=read(plan['inputs']['public_plan']['path'])
        closed=read(plan['inputs']['receipt']['path'])
        require(closed['status']=='completed_forecaster_training_and_causal_evaluation'
            and closed['model_sha256']==model['model_sha256']
            and closed['artifacts']['forecast_predictions.jsonl']==plan['inputs']['forecasts']['sha256']
            and closed['private_label_index_sha256']==plan['inputs']['private_asof_evaluator_index']['sha256'],'frozen_B1_artifact_binding')
        labels=[json.loads(line) for line in Path(plan['inputs']['private_asof_evaluator_index']['path']).read_text().splitlines()]
        saved=[json.loads(line) for line in Path(plan['inputs']['forecasts']['path']).read_text().splitlines()]
        require(len(saved)==402,'all_saved_forecasts')
        methods={}; observed_contexts={}; checks=[]
        for item in saved:
            require(time.perf_counter()<deadline,'saved_replay_wall_budget')
            split=item['split']; refs=frozenset(item['statistical_parent_scope']); now=item['forecast']['forecast_origin']
            key=(split,refs)
            if key not in observed_contexts:
                scoped=copy.deepcopy(context);scoped['source_id']+=':'+split+'_statistical_subpopulation'
                scoped['entries']=[e for e in scoped['entries'] if e['flight_ref'] in refs]
                rows=[r for r in labels if r['parent_flight_ref'] in refs]
                observed_contexts[key]=(scoped,rows)
            scoped,rows=observed_contexts[key];owner=scoped['owner_scope']
            if item['method']=='flight_prior_only':
                forecast=new.predict(scoped,model,now=now,owner=owner)
            else:
                counts,events=training.public_observations(rows,scoped,now=now,owner=owner)
                require(all(e['arrived_at']<=e['received_at']<=now for e in events)
                    and sum(sum(v.values()) for v in counts['counts_by_flight'].values())==len(events),'causal_synthetic_prefix_only')
                forecast=(new.predict(scoped,model,now=now,owner=owner,observed_counts=counts)
                    if item['method']=='flight_synthetic_observed_counts' else
                    old.recent_rate_forecast(model,now=now,owner=owner,arrival_events=events))
            require(encoded(forecast)==encoded(item['forecast']),'exact_saved_float_and_uncertainty_bytes')
            checks.append({'split':split,'method':item['method'],'now':now,'forecast_sha256':hashlib.sha256(encoded(forecast)).hexdigest()})
            methods[item['method']]=methods.get(item['method'],0)+1;result['completed_saved_forecasts']+=1
        result['saved_parity_by_method']=methods;result['saved_prediction_checks']=checks
        result['saved_replay_wall_seconds']=time.perf_counter()-started
        mapping=read(plan['inputs']['mapping']['path'])
        with gzip.open(plan['inputs']['trace']['path'],'rt',encoding='utf8') as stream:
            for line in stream:
                row=json.loads(line)
                if row['sequence'] not in plan['B2_sequences']:continue
                require(time.perf_counter()<deadline,'B2_reference_comparison_wall_budget')
                scoped=copy.deepcopy(context);scoped['owner_scope']=row['owner_id'];forecasts=[];durations=[]
                for function in (old.predict,new.predict):
                    start=time.perf_counter_ns();cpu=time.thread_time_ns()
                    f=function(scoped,model,now=row['now'],owner=row['owner_id'],observed_counts=None)
                    durations.append({'wall_ms':(time.perf_counter_ns()-start)/1e6,'thread_cpu_ms':(time.thread_time_ns()-cpu)/1e6})
                    forecasts.append(f)
                require(encoded(forecasts[0])==encoded(forecasts[1]),'B2_full_forecast_bytes')
                wrapped=[]
                for f in forecasts:
                    projected=audit.project(f,mapping);w,a=public.wrap_record(row,projected,episode_id='C00_cyclic_od_001',episode_end=59400.)
                    actions=public.proposal_actions(row)
                    wrapped.append({'wrapped':w,'accounts':a,'actions':actions,'features':[value.features(w,c['semantic']) for c in actions]})
                require(encoded(wrapped[0])==encoded(wrapped[1]),'B2_whole_wrapped_features_bytes')
                result['B2_rows'].append({'sequence':row['sequence'],'now':row['now'],'owner':row['owner_id'],
                    'exact_forecast_and_features_bytes':True,'original_predict':durations[0],'array_predict':durations[1],
                    'candidate_count':len(wrapped[0]['actions'])})
        require(len(result['B2_rows'])==3,'all_three_actual_B2_rows')
        require(all(ref(path)['sha256']==sha for path,sha in plan['sources'].items()),'source_exit_pins')
        result.update(status='completed_exact_saved_forecast_and_B2_parity',source_exit_pins_passed=True,
            no_training_or_test_selection=True,cross_call_cache=False,native_execution_authority=False,
            private_evaluator_scope='Only this validator reconstructs original synthetic arrived-prefix feeds. Runtime optimized interface performs no file/index/label read.',
            timing_scope='Three sequential offline predict pairs, not native latency or randomized distribution; ordinary background environment uncontrolled.')
    except Exception:result['exception']=traceback.format_exc()
    result['total_wall_seconds']=time.perf_counter()-started;write(output/'receipt.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true');group.add_argument('--run',action='store_true');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();r=prepare(args.output) if args.prepare else run(args.output)
    print(json.dumps({'status':r['status'],'native_branches':0}))
    raise SystemExit(0 if r['status'] in ('prepared_not_executed','completed_exact_saved_forecast_and_B2_parity') else 1)
