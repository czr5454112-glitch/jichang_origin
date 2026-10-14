"""Independent 2-bridge + 24 physical conditional-boundary supplement.

The frozen Round8 helpers supply all restore, physics, timing and durable
per-case recovery. This output-local driver only prepares the fixed grid and
coordinates at most three workers. It never edits the 4352-request main run.
"""
from pathlib import Path
from time import process_time, perf_counter
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import argparse
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'scripts/experiments/ics_circulation_v3').is_dir())
sys.path.insert(0, str(ROOT))
from scripts.experiments.ics_circulation_v3.experiment_protocol import create_output_directory, write_new_json
from scripts.experiments.ics_circulation_v3.model import Bag
from scripts.experiments.ics_circulation_v3.phase4_network_workloads import file_sha
from scripts.experiments.ics_circulation_v3.run_same_zone_supply import read
from scripts.experiments.ics_circulation_v3.run_same_zone_labels import load_payload, failure_detail
from scripts.experiments.ics_circulation_v3.run_same_zone_stability import evaluate
from scripts.experiments.ics_circulation_v3.same_zone_labels import comparison_passes
from scripts.experiments.ics_circulation_v3.same_zone_stability import (
    EVALUATION_CONTRACT, conditional_support, validate_sampled_future, tape_sha, memo_key)

BASE = ROOT/'outputs/experiments/ics_circulation_v3'
HERE = Path(__file__).parent
OUTPUT = HERE/'experiment'
INVENTORY = BASE/'phase4_w3_round8_conditional_boundary_inventory_20261010'
MAIN = BASE/'phase4_w3_same_zone_stability_20261010'
PRIOR = BASE/'phase4_w3_same_zone_labels_20261010'
SOURCE = ROOT/'scripts/experiments/ics_circulation_v3'
WORKERS = 3


def exact_file(path, expected):
    if file_sha(path) != expected:
        raise ValueError('immutable file changed: '+str(path))


def prepare(output):
    cpu, wall = process_time(), perf_counter()
    output = create_output_directory(output)
    inputs = set()

    def bind(path, expected=None):
        path = Path(path).resolve()
        if expected is not None:
            exact_file(path, expected)
        inputs.add(path)
        return read(path)

    main_prep = bind(MAIN/'preparation_manifest.json')
    main_protocol = bind(MAIN/'protocol.json', main_prep['protocol.json'])
    collection_path = PRIOR/'collection_run/manifest.json'
    full_path = PRIOR/'full/manifest.json'
    # Explicit provenance check omitted from the earlier inventory's own
    # read step: this old manifest must equal the already frozen main input.
    collected = bind(collection_path, main_protocol['input_sha256'][str(collection_path)])
    full = bind(full_path, main_protocol['input_sha256'][str(full_path)])
    inventory_manifest = bind(INVENTORY/'manifest.json')
    for name, expected in inventory_manifest.items():
        path = INVENTORY/name
        exact_file(path, expected)
        inputs.add(path)
    inventory = read(INVENTORY/'analysis.json')
    if inventory['failed_checks'] or inventory['physical_calls'] != 0:
        raise ValueError('inventory was not a valid zero-physics selection')
    for path, expected in inventory['bound_inputs'].items():
        path = ROOT/path
        exact_file(path, expected)
        inputs.add(path.resolve())
    for path, expected in main_protocol['input_sha256'].items():
        exact_file(Path(path), expected)
        inputs.add(Path(path).resolve())
    original_inventory = bind(MAIN/'inventory.json', main_prep['inventory.json'])
    attempts = {(a['scene'],a['decision_index']):a for a in original_inventory['attempts']}
    # Selection remains the already fixed inventory, including its four gaps.
    if inventory['counts']['selected_states'] != 2 or inventory['counts']['missing_cells'] != 4:
        raise ValueError('fixed source selection changed')
    bridges, requests, details = [], [], []
    for selected in inventory['selected']:
        original = attempts[(selected['scene'],selected['decision_index'])]
        for stem in ('checkpoint','metadata'):
            path = PRIOR/selected[stem+'_file']
            exact_file(path, collected[str(path.relative_to(PRIOR))])
            if selected[stem+'_sha256'] != original[stem+'_sha256']:
                raise ValueError('selection does not match original attempt')
            inputs.add(path)
        payload, metadata = load_payload(PRIOR, selected)
        state = payload['checkpoint'].state
        original_tape = payload['future']
        target = next(b for b in original_tape if b.bag_id == selected['target']['bag_id'])
        support = conditional_support(target, state.now)
        if support != selected['conditional_support'] or support['total_mass'] != 17:
            raise ValueError('fixed conditional boundary changed')
        tapes = []
        for index, entry in enumerate(selected['finite_outcomes']):
            tape = validate_sampled_future(state, original_tape, tuple(Bag(**b) for b in entry['pending']))
            if tape_sha(tape) != entry['future_sha256']:
                raise ValueError('finite support tape changed')
            if tuple(b for b in tape if b.bag_id != target.bag_id) != tuple(b for b in original_tape if b.bag_id != target.bag_id):
                raise ValueError('non-target tape changed')
            tapes.append({'index':index,'sha256':tape_sha(tape),'bags':[asdict(b) for b in tape],
                'cancel':entry['cancel'],'jitter':entry['jitter'],'mass':entry['mass'],
                'probability_fraction':entry['probability_fraction']})
        future_file = output/'futures'/(selected['state_key']+'.json')
        write_new_json(future_file, {'state_key':selected['state_key'],'target':asdict(target),
            'original_future':[asdict(b) for b in original_tape], 'original_future_sha256':tape_sha(original_tape),
            'conditional_support':support, 'blocks':[{'block':0,'kind':'exhaustive_single_task_slice','tapes':tapes}],
            'scope':'only selected task varies; all others exact original; this is not the main joint future distribution'})
        binding = {k:selected[k] for k in ('state_key','scene','decision_index','time','role','candidate_count',
            'checkpoint_file','checkpoint_sha256','metadata_file','metadata_sha256','continuation_sha256')}
        binding.update(future_file=str(future_file.relative_to(output)),future_file_sha256=file_sha(future_file))
        for entry in tapes:
            tape = tuple(Bag(**b) for b in entry['bags'])
            for candidate, key in enumerate(metadata['candidate_keys']):
                identity = f"{selected['state_key']}_f{entry['index']}_c{candidate}"
                requests.append({**binding,'request_key':identity,'physical_key':identity,'block':0,
                    'future_index':entry['index'],'sampled_future_sha256':entry['sha256'],
                    'candidate':candidate,'candidate_key':key,
                    'memo_key':memo_key(selected['checkpoint_sha256'],candidate,key,tape,selected['continuation_sha256']),
                    'minimum_observation_at':state.now+EVALUATION_CONTRACT['minimum_offset'],
                    'probability_fraction':entry['probability_fraction'],'support_mass':entry['mass'],
                    'support_total_mass':17,'scope':'one-task conditional mechanism slice; independent physical call, no memo reuse'})
        actual = original['actual_chosen_index']
        reference = PRIOR/'full'/f"{selected['state_key']}_c{actual}.json.gz"
        exact_file(reference,full[str(reference.relative_to(PRIOR))])
        inputs.add(reference)
        old = read(reference)
        # Reference outcomes cannot affect selection. Only original stop is
        # needed to make the already selected actual-choice bridge exact.
        if old['status'] != 'controller_quiescent':
            raise ValueError('original bridge reference incomplete')
        bridges.append({**binding,'candidate':actual,'bridge':True,
            'request_key':selected['state_key']+'_original_bridge',
            'physical_key':selected['state_key']+'_original_bridge',
            'reference_file':str(reference),'reference_sha256':file_sha(reference),
            'minimum_observation_at':old['stopped_at']})
        details.append({**binding,'actual_chosen_index':actual,'target':asdict(target),
            'candidate_keys':metadata['candidate_keys'],'three_support_masses':[3,7,7],
            'original_bridge_stop':old['stopped_at']})
    if len(bridges) != 2 or len(requests) != 24 or len({r['physical_key'] for r in requests}) != 24:
        raise ValueError('fixed bridge/full grid changed')
    sources, tests = main_protocol['source_sha256'], main_protocol['test_sha256']
    for kind, mapping, root in (('source',sources,SOURCE),('test',tests,ROOT/'tests')):
        folder=output/(kind+'_snapshot');folder.mkdir()
        for name, expected in mapping.items():
            exact_file(root/name,expected)
            (folder/name).write_bytes((root/name).read_bytes())
    auxiliary={str(path.resolve()):file_sha(path) for path in (Path(__file__),HERE/'test_runner.py',HERE/'validate.py',HERE/'validation.json')}
    protocol={'schema':'ics_round8_conditional_boundary_mechanism_v1','workers':WORKERS,
        'source_sha256':sources,'test_sha256':tests,'auxiliary_sha256':auxiliary,
        'input_sha256':{str(p.resolve()):file_sha(p) for p in sorted(inputs)},
        'selection_inventory':str(INVENTORY/'analysis.json'),'selected_details':details,
        'missing_cells':[c for c in inventory['cells'] if c['selected_state_key'] is None],
        'planned_bridge_physical':2,'planned_full_physical':24,'memo_aliases':0,
        'evaluation':EVALUATION_CONTRACT,'same_frozen_helper':'run_same_zone_stability.evaluate -> same_zone_stability.run_sampled_branch',
        'bridge':'original future and actual choice, compare_bridge at exact original stopped_at; separately billed',
        'full':'three finite one-target tapes x every saved candidate; no pilot, memo or bridge deduction',
        'information':'future queue engine-only; all original public state/forecast/cursor/cache/slow-clock/continuation binding preserved by frozen helper',
        'scope':'separate conditional-boundary mechanism supplement, four missing cells retained; not main 64 draws or a new joint future law',
        'resource_scope':'worker restore/physics/raw-write intervals plus parent measured interval; nested cycle not added; imports/initializer/final receipt writes outside measured worker interval are unknown',
        'preparation_cpu_seconds':process_time()-cpu,'preparation_wall_seconds':perf_counter()-wall}
    for name,value in (('protocol.json',protocol),('bridge_rows.json',bridges),('full_rows.json',requests)):
        write_new_json(output/name,value)
    write_new_json(output/'preparation_manifest.json',{str(p.relative_to(output)):file_sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
    return protocol


def verify(output):
    output=Path(output);protocol=read(output/'protocol.json')
    for path,expected in read(output/'preparation_manifest.json').items():
        exact_file(output/path,expected)
    for key,root in (('source_sha256',SOURCE),('test_sha256',ROOT/'tests')):
        for path,expected in protocol[key].items():exact_file(root/path,expected)
    for key in ('input_sha256','auxiliary_sha256'):
        for path,expected in protocol[key].items():exact_file(Path(path),expected)
    return protocol


def require_bridge(output):
    output=Path(output)
    manifest=read(output/'bridge/manifest.json')
    for path,expected in manifest.items():exact_file(output/path,expected)
    summary=read(output/'bridge/summary.json')
    planned=read(output/'bridge_rows.json')
    expected={(r['request_key'],r['physical_key']) for r in planned}
    observed=[(r.get('request_key'),r.get('physical_key')) for r in summary['rows']]
    required={'result','evaluation_ledger','cache_before','cache_after','searches','search_calls','search_work',
        'stopped_at','event_trace_suffix','selector_history_suffix','actual_slow_trigger_times',
        'slow_history_suffix','physical_tick_trace','forced_intervention'}
    for row in summary['rows']:
        replication=row.get('replication')
        if (not isinstance(replication,dict) or not required.issubset(replication) or not replication['result']
            or not row.get('actual_physical_call') or not row.get('file') or not row.get('sha256')
            or manifest.get(row.get('file')) != row.get('sha256')):
            raise ValueError('full stage requires both exact original bridges')
    if (summary['planned_physical_calls'] != 2 or len(summary['rows']) != 2
        or len(expected)!=2 or len(set(observed))!=2 or set(observed)!=expected
        or not summary['source_input_test_unchanged'] or not summary['complete_resource_accounting']
        or any(r['status'] != 'controller_quiescent' or not comparison_passes(r['replication']) for r in summary['rows'])):
        raise ValueError('full stage requires both exact original bridges')


def worker_failure(row,error):
    return {**row,'status':'worker_failure','actual_physical_call':None,
        'invocation_cpu_seconds':None,'invocation_wall_seconds':None,
        'failure':failure_detail(error),'resource_scope':'worker physical/CPU status unknown, never zero-imputed'}


def submit_requests(pool,output,stage,rows,directory,results):
    jobs={}
    for row in rows:
        try:jobs[pool.submit(evaluate,output,stage,row)]=row
        except Exception as error:
            value=worker_failure(row,error)
            value.update(status='submission_failure',resource_scope='Submission exception may occur after queue registration; physical call and paid worker CPU remain unknown.')
            results.append(value)
            try:write_new_json(directory/(row['physical_key']+'.submission_failure.json'),value)
            except Exception as persistence_error:value['parent_persistence_error']=failure_detail(persistence_error)
    return jobs


def run(output,stage):
    cpu,wall=process_time(),perf_counter();output=Path(output).resolve()
    protocol=verify(output)
    if stage=='full':require_bridge(output)
    directory=create_output_directory(output/stage)
    rows=read(output/(stage+'_rows.json'))
    expected=2 if stage=='bridge' else 24
    if len(rows)!=expected:raise ValueError('planned grid changed')
    write_new_json(directory/'requested_rows.json',rows)
    results=[]
    with ProcessPoolExecutor(max_workers=protocol['workers'],initializer=verify,initargs=(output,)) as pool:
        jobs=submit_requests(pool,output,stage,rows,directory,results)
        for job in as_completed(jobs):
            row=jobs[job]
            try:value=job.result()
            except Exception as error:
                value=worker_failure(row,error)
                try:write_new_json(directory/(row['physical_key']+'.worker_failure.json'),value)
                except Exception as persistence_error:value['parent_persistence_error']=failure_detail(persistence_error)
            results.append(value)
            print({'stage':stage,'recorded':len(results),'planned':expected,
                'status_counts':dict(Counter(r['status'] for r in results))},flush=True)
    immutable_error=None
    try:verify(output)
    except Exception as error:immutable_error=failure_detail(error)
    summary={'stage':stage,'planned_physical_calls':expected,'rows':results,
        'status_counts':dict(Counter(r['status'] for r in results)),
        'actual_physical_calls_recorded':sum(r['actual_physical_call'] is True for r in results),
        'unknown_physical_call_statuses':sum(r['actual_physical_call'] is None for r in results),
        'memo_aliases':0,'case_invocation_cpu_seconds_recorded':sum(r['invocation_cpu_seconds'] or 0 for r in results),
        'complete_resource_accounting':all(r['invocation_cpu_seconds'] is not None for r in results),
        'parent_cpu_seconds':process_time()-cpu,'wall_makespan_seconds':perf_counter()-wall,
        'source_input_test_unchanged':immutable_error is None,'immutable_error':immutable_error,
        'resource_scope':protocol['resource_scope']}
    try:write_new_json(directory/'summary.json',summary)
    except Exception as error:
        summary['summary_write_error']=failure_detail(error)
        write_new_json(directory/'summary.recovery.json',summary)
        raise
    write_new_json(directory/'manifest.json',{str(p.relative_to(output)):file_sha(p) for p in sorted(directory.rglob('*')) if p.is_file()})
    return int(immutable_error is not None or any(r['status']!='controller_quiescent' for r in results))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('prepare','bridge','full'),required=True)
    parser.add_argument('--output',type=Path,default=OUTPUT);args=parser.parse_args()
    cpu,wall=process_time(),perf_counter()
    try:
        if args.stage=='prepare':prepare(args.output)
        else:raise SystemExit(run(args.output,args.stage))
    except Exception as error:
        if args.output.exists():
            receipt={'stage':args.stage,'status':'driver_failure','failure':failure_detail(error),
                'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
                'physical_calls':0 if args.stage=='prepare' else None,
                'resource_scope':'Driver interval; per-case receipts remain separate. Worker work cannot be inferred from this parent timer.'}
            write_new_json(args.output/(args.stage+'_driver_failure.json'),receipt)
        raise
