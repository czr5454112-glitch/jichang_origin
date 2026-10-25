"""Frozen original HCA, common positive-service=2s input, and append-only route telemetry."""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]
from scripts.eval import run_g4irsf24_fresh_hca as legacy
from scripts.experiments.g31_deadline_research import audit

DEFAULT = ROOT/'outputs/experiments/g31_no_wait_20261024/hca_service2_001'
DRAFT = ROOT/'outputs/experiments/g31_nonstop_contract_20261024_draft001'
ORIGINAL = ROOT/'outputs/experiments/g31_feng_alignment_map2_20261023/java_native_1x'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path, value): Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream: return list(csv.DictReader(stream))

def replace_once(text, before, after):
    if text.count(before)!=1: raise ValueError('wrapper anchor drift: '+before[:90])
    return text.replace(before,after)

def instrument_wrapper(text):
    text=replace_once(text,'        final ArrayList<Integer> path;','        final ArrayList<Integer> path;\n        final String nodeIntervals;')
    text=replace_once(text,'            ArrayList<Integer> path\n','            ArrayList<Integer> path,\n            String nodeIntervals\n')
    text=replace_once(text,'            this.path = path;','            this.path = path;\n            this.nodeIntervals = nodeIntervals;')
    text=replace_once(text,'            ArrayList<Integer> path = new ArrayList<>();\n            for (Node node : route) {\n                path.add(node.getLocation());\n            }',
        '            ArrayList<Integer> path = new ArrayList<>();\n            StringBuilder intervals = new StringBuilder();\n            for (Node node : route) {\n                path.add(node.getLocation());\n                if (intervals.length() > 0) intervals.append(";");\n                intervals.append(node.getLocation()).append(":").append(node.getT1()).append(":").append(node.getT2());\n            }')
    text=replace_once(text,'                path\n            );','                path,\n                intervals.toString()\n            );')
    text=replace_once(text,'"ordinal,task_id,start,goal,epoch,finish_time,path"','"ordinal,task_id,start,goal,epoch,finish_time,path,node_intervals"')
    text=replace_once(text,'+ route.epoch + "," + route.finishTime + "," + pathText(route.path)',
        '+ route.epoch + "," + route.finishTime + "," + pathText(route.path) + "," + route.nodeIntervals')
    return text

def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    original=read(ORIGINAL/'source_input_manifest.json')
    draft=read(DRAFT/'contract_manifest.json')
    frozen=out/'source'
    for row in original['source_comparison']:
        source=Path(original['original_project'])/row['path']
        assert sha(source)==row['original_sha256']
        target=frozen/row['path']; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,target)
    base_wrapper=ROOT/'benchmarks/java/LegacyIcsNoFaultWindowBenchmark.java'
    wrapper=frozen/'benchmarks/LegacyIcsNoFaultWindowBenchmark.java'
    wrapper.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(base_wrapper,frozen/'benchmarks/LegacyIcsNoFaultWindowBenchmark.original.java')
    wrapper.write_text(instrument_wrapper(base_wrapper.read_text(encoding='utf-8')),encoding='utf-8')
    classes=out/'classes'; classes.mkdir()
    command=['C:/PROGRAMING/jdk-18/bin/javac.exe','-encoding','UTF-8','-d',str(classes),
             *map(str,sorted((frozen/'src/App').glob('*.java'))),str(frozen/'src/ICS_GUI/ICS_GUI.java'),str(wrapper)]
    started=time.perf_counter(); compiled=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (out/'compile_stdout.txt').write_text(compiled.stdout,encoding='utf-8')
    (out/'compile_stderr.txt').write_text(compiled.stderr,encoding='utf-8')
    if compiled.returncode: raise RuntimeError('javac failed')
    for item in read(ORIGINAL/'compile_receipt.json')['classes']:
        if item['path'].startswith('App') or item['path'].startswith('ICS_GUI'):
            assert sha(classes/item['path'])==item['sha256'],item['path']
    inputs=out/'inputs'; inputs.mkdir()
    maps={}
    for name,row in draft['maps'].items():
        maps[name]={}
        for kind in ('draft_raw','draft_profile'):
            source=Path(row[kind]['path']); assert sha(source)==row[kind]['sha256']
            target=inputs/source.name.replace('_draft',''); shutil.copyfile(source,target)
            maps[name][kind]=str(target)
    cells={}
    for label,row in draft['cells'].items():
        cells[label]={k:row[k] for k in ('business_denominator','segment_denominator','temporal_identity_sha256','storage_in_goal','storage_out_start')}
        for kind in ('raw','canonical'):
            source=Path(row[kind]['path']); assert sha(source)==row[kind]['sha256']
            target=inputs/f'{label}_{kind}{source.suffix}'; shutil.copyfile(source,target)
            cells[label][kind]=str(target)
        cells[label]['map']=maps[label.split('_')[0]]
    manifest={'schema':'g31.no_wait.hca2s.frozen.v1','status':'prepared','service_contract':'original service > 0 -> 2s; original 0 remains 0',
        'core_java_source_unchanged':True,'core_java_classes_exact_original':True,'wrapper_append_only_node_intervals':True,
        'source_original_manifest_sha256':sha(ORIGINAL/'source_input_manifest.json'),'draft_manifest_sha256':sha(DRAFT/'contract_manifest.json'),
        'speed_mps':2.0,'classes':str(classes),'maps':maps,'cells':cells,'compile_command':command,
        'compile_wall_seconds':time.perf_counter()-started,'algorithm_source_files':original['source_comparison'],
        'route_columns':['ordinal','task_id','start','goal','epoch','finish_time','path','node_intervals'],
        'timing_caveat':'Java wall time includes original per-epoch file I/O and added interval snapshot output; compare physical results separately.',
        'physical_caveats':draft['physical_scope_not_yet_selected']}
    write(out/'manifest.json',manifest)
    write(out/'SOURCE_FREEZE.json',{'files':[{'path':str(p.relative_to(out)),'sha256':sha(p)}
        for folder in (frozen,classes,inputs) for p in sorted(folder.rglob('*')) if p.is_file()]})
    print(json.dumps({'status':'prepared','output':str(out),'classes_exact_original':True}),flush=True)

def verify(out):
    for item in read(out/'SOURCE_FREEZE.json')['files']:
        if sha(out/item['path'])!=item['sha256']: raise ValueError('frozen file changed: '+item['path'])

def observation_window(manifest):
    """An extended window is explicit; legacy prepared runs retain 98259."""
    window=manifest.get('observation_window',{})
    start=window.get('start_epoch',8260);end=window.get('end_epoch',98259)
    if any(not isinstance(v,int) or isinstance(v,bool) for v in (start,end)) or start<0 or end<start:
        raise ValueError('observation window requires nonnegative integer start <= end')
    return start,end,end-start+1

def analyze(out,label):
    manifest=read(out/'manifest.json'); cell=manifest['cells'][label]; run=out/label/'run_01'
    start_epoch,end_epoch,max_epochs=observation_window(manifest)
    if 'observation_window' in manifest:
        observed_windows=csv_rows(run/'summary.csv')
        if not observed_windows or any(float(r['last_epoch'])!=end_epoch or int(r['epochs_run'])!=max_epochs
            or int(r['start_epoch'])!=start_epoch for r in observed_windows):
            raise ValueError('executed observation window differs from the explicit manifest')
    canonical=audit.read_jsonl(cell['canonical']); lifecycle=csv_rows(run/'segment_lifecycle.csv'); routes=csv_rows(run/'routes.csv')
    profile=read(cell['map']['draft_profile']); service={int(n['location']):float(n['service_time']) for n in profile['nodes']}
    edge={(int(e['start']),int(e['end'])):float(e['length'])/manifest['speed_mps'] for e in profile['edges']}
    schedules={}; violations=[]; gap_examples=[]; gap_count=0; max_gap=0.0; node_count=0
    for row in routes:
        path=[int(x) for x in row['path'].split(';')]
        intervals=[[int(s.split(':')[0]),float(s.split(':')[1]),float(s.split(':')[2])] for s in row['node_intervals'].split(';')]
        if path!=[n[0] for n in intervals]: raise ValueError('interval path mismatch')
        key=(int(row['task_id']),int(row['start']),int(row['goal']))
        if key in schedules: raise ValueError('ambiguous planned route identity')
        gaps=[]
        for j,(node,t1,t2) in enumerate(intervals):
            node_count+=1
            if abs(t2-t1-service[node])>1e-7: violations.append({'task_id':key[0],'node':node,'kind':'service_duration','delta':t2-t1-service[node]})
            if j:
                previous=intervals[j-1]
                gap=t1-(previous[2]+edge[previous[0],node]); gaps.append(gap); max_gap=max(max_gap,abs(gap))
                if abs(gap)>1e-7:
                    gap_count+=1
                    if len(gap_examples)<30: gap_examples.append({'task_id':key[0],'edge':[previous[0],node],'residual_seconds':gap})
        schedules[key]={'travel':sum(edge[u,v] for u,v in zip(path,path[1:])),
            'service':sum(service[n] for n in path[:-1]),'continuous':all(abs(g)<1e-7 for g in gaps),
            'planned_goal_arrival':intervals[-1][1],'planned_goal_t2':intervals[-1][2],
            'route':intervals,'commit_epoch':float(row['epoch']),'commit_ordinal':int(row['ordinal'])}
    bags=[]
    for row in lifecycle:
        key=(int(row['task_id']),int(row['start']),int(row['goal'])); scheduled=schedules.get(key)
        def val(k): return float(row[k]) if row.get(k) else None
        plan,release,finish=val('processed_attempt_epoch'),val('release_epoch'),val('finish_epoch')
        bag={'segment_id':row['segment_id'],'task_id':key[0],'start':key[1],'goal':key[2],
             'release_time':release,'admitted_time':plan,'completed':str(row['complete']).lower()=='true','finish_time':finish,
             'source_queue_delay':plan-release if plan is not None and release is not None else None}
        if scheduled:
            bag.update(edge_travel_time_seconds=scheduled['travel'],node_service_time_seconds=scheduled['service'])
            if scheduled['continuous']: bag['junction_queue_wait_seconds']=0.0
        bags.append(bag)
    request={'max_simulation_time':float(end_epoch),'minimum_service_seconds':0.0,'complete_on_goal_arrival':True,
        'node_records':[[n['location'],n['node_type'],n['service_time'],n.get('x',0),n.get('y',0),n['outgoing']] for n in profile['nodes']],
        'edge_records':[[e['start'],e['end'],e['length'],manifest['speed_mps']] for e in profile['edges']]}
    result=audit.analyze(canonical,bags,request)
    result['hca_schedule_audit']={'route_count':len(routes),'node_interval_count':node_count,'service_violations':violations,
        'edge_timing_discontinuity_count':gap_count,'max_abs_edge_timing_residual_seconds':max_gap,'examples':gap_examples,
        'no_explicit_wait_action_in_original_core':True,'every_planned_edge_continuous':gap_count==0,
        'discontinuity_is_not_automatically_physical_wait':'Astar may retain stale timestamps on reparenting; report residual without attributing a queue.',
        'completion':'observed integer-epoch goal arrival, not planned goal t2; possible report quantization retained'}
    result['identity']={'canonical_sha256':sha(cell['canonical']),'map_sha256':sha(cell['map']['draft_raw']),
        'freeze_sha256':sha(out/'SOURCE_FREEZE.json'),'routes_sha256':sha(run/'routes.csv'),'lifecycle_sha256':sha(run/'segment_lifecycle.csv')}
    if manifest.get('physical_adapter',{}).get('contract'):
        from scripts.experiments.g31_no_wait.headway_audit import audit_headway
        expected={str(r['segment_id']):r for r in canonical};observed={str(b['segment_id']):b for b in bags}
        if len(observed)!=len(bags) or not observed.keys()<=expected.keys(): raise ValueError('lifecycle identity changed')
        canonical_keys={(int(r['task_id']),int(r['start']),int(r['goal'])) for r in canonical}
        if not schedules.keys()<=canonical_keys: raise ValueError('planned route is outside canonical population')
        successful_plans=[b for b in bags if b['admitted_time'] is not None]
        if len(successful_plans)!=len(schedules): raise ValueError('route telemetry does not cover every successful plan')
        for bag in successful_plans:
            scheduled=schedules.get((bag['task_id'],bag['start'],bag['goal']))
            if scheduled is None or scheduled['commit_epoch']!=bag['admitted_time']: raise ValueError('plan telemetry identity/epoch mismatch')
        for sid,row in expected.items():
            if sid not in observed:
                observed[sid]={'segment_id':sid,'task_id':row['task_id'],'start':row['start'],'goal':row['goal'],
                    'release_time':None,'admitted_time':None,'completed':False,'finish_time':None,'source_queue_delay':None}
        bags=list(observed.values());physical=[];continuous=[]
        for bag in bags:
            scheduled=schedules.get((int(bag['task_id']),int(bag['start']),int(bag['goal'])))
            row=dict(bag);row.update(route=scheduled['route'] if scheduled else [],admission=bag['admitted_time'],
                finish=scheduled['planned_goal_arrival'] if scheduled else None,observed_finish=bag['finish_time'],
                commit_ordinal=scheduled['commit_ordinal'] if scheduled else None)
            physical.append(row)
            adjusted=dict(bag)
            if scheduled:
                adjusted['completed']=scheduled['planned_goal_arrival']<=request['max_simulation_time']
                adjusted['finish_time']=scheduled['planned_goal_arrival'] if adjusted['completed'] else None
            continuous.append(adjusted)
        physical_result=audit_headway(canonical,physical,profile,time_grid_seconds=1e-6,strict_endpoint_resources=True,edge_entry_headway_seconds=2)
        physical_result['telemetry_coverage']={'canonical_segments':len(canonical),'lifecycle_released_segments':len(lifecycle),
            'unreleased_segments':len(canonical)-len(lifecycle),'successful_plan_records':len(successful_plans),
            'full_route_snapshots':len(routes),'one_route_per_successful_plan':True,
            'node_intervals_and_edge_entries_reconstructed_from_complete_committed_routes':True}
        physical_result['source_commit_order']={'ordinals_unique':len({s['commit_ordinal'] for s in schedules.values()})==len(schedules),
            'commit_epochs_nondecreasing':all(float(a['epoch'])<=float(b['epoch']) for a,b in zip(routes,routes[1:]))}
        early_generated=[b['segment_id'] for b in bags if b['release_time'] is not None and b['release_time']<math.ceil(float(expected[str(b['segment_id'])]['pass_time']))]
        inbound={int(r['task_id']):observed[str(r['segment_id'])] for r in canonical if r['leg']=='storage_in'}
        causal_release=[]
        for raw in canonical:
            b=observed[str(raw['segment_id'])]
            if raw['leg']=='storage_out' and b['release_time'] is not None:
                prior=inbound[int(raw['task_id'])]
                if not prior['completed'] or prior['finish_time']>b['release_time']:causal_release.append(b['segment_id'])
        physical_result['source_gates']={'early_generated_count':len(early_generated),'early_generated_examples':early_generated[:20],
            'outbound_generated_before_inbound_report_count':len(causal_release),'outbound_generated_before_inbound_report_examples':causal_release[:20]}
        physical_result['passed']=physical_result['passed'] and not early_generated and not causal_release and all(physical_result['source_commit_order'].values())
        report_delays=[row['observed_finish']-math.ceil(row['finish']) for row in physical if row['completed'] and row['route']]
        physical_result['completion_observer']={'completed_routes':len(report_delays),'different_from_ceiling_goal_arrival':sum(d!=0 for d in report_delays),
            'max_delay_beyond_ceiling_seconds':max(report_delays,default=0),
            'definition':'Actual original Java node report sequence; continuous goal arrival also reported. Multiple sub-tick zero-service hops may delay reports, so equality with ceil is explicitly audited.'}
        continuous_result=audit.analyze(canonical,continuous,request)
        result['continuous_goal_arrival_business_summary']=continuous_result['business']
        result['physical_headway_audit']=physical_result
        write(out/label/'physical_headway_audit.json',physical_result)
        write(out/label/'continuous_analysis.json',continuous_result)
        with (out/label/'physical_bags.jsonl').open('w',encoding='utf-8') as stream:
            for bag in physical:stream.write(json.dumps(bag,separators=(',',':'))+'\n')
    write(out/label/'analysis.json',result)
    with (out/label/'audit_bags.jsonl').open('w',encoding='utf-8') as stream:
        for bag in bags: stream.write(json.dumps(bag,separators=(',',':'))+'\n')
    if result.get('physical_headway_audit',{}).get('passed') is False:
        raise ValueError('Uniform physical HCA failed the full-population physical/source audit; evidence saved.')
    print(json.dumps({'cell':label,'analysis':str(out/label/'analysis.json'),'summary':result.get('business',result.get('business_summary')),
        'schedule':result['hca_schedule_audit']},ensure_ascii=False),flush=True)

def run(out,label):
    verify(out); manifest=read(out/'manifest.json'); cell=manifest['cells'][label]
    start_epoch,end_epoch,max_epochs=observation_window(manifest)
    args=argparse.Namespace(profile='full',map_path=Path(cell['map']['draft_raw']),input_path=Path(cell['raw']),
        canonical_input=Path(cell['canonical']),classes_dir=Path(manifest['classes']),output_root=out/label,
        java='C:/PROGRAMING/jdk-18/bin/java.exe',javac='C:/PROGRAMING/jdk-18/bin/javac.exe',start_epoch=start_epoch,
        max_epochs=max_epochs,max_new_tasks=0,repeats=1,timeout_seconds=0,speed_mps=2.0,
        storage_in_goal=cell['storage_in_goal'],storage_out_start=cell['storage_out_start'],early_threshold_seconds=4800.0,
        storage_lead_seconds=2700.0,fault_schedule='none',cleanup_epoch_files=False,skip_compile=True,force=False,dry_run=False)
    print(json.dumps({'status':'starting_full_population','cell':label,'output':str(args.output_root)}),flush=True)
    code=legacy.run_campaign(args)
    if code: raise RuntimeError(f'HCA failed {code}')
    analyze(out,label)

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('action',choices=['prepare','run','analyze'])
    parser.add_argument('--output',type=Path,default=DEFAULT); parser.add_argument('--cell',choices=['map2_1x','nanning_1x','map2_2x','nanning_2x'])
    args=parser.parse_args(); out=args.output.resolve()
    if args.action=='prepare': prepare(out)
    elif not args.cell: parser.error('--cell required')
    elif args.action=='run': run(out,args.cell)
    else: analyze(out,args.cell)

if __name__=='__main__': main()
