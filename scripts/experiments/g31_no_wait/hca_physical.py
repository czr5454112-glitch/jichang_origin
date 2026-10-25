"""Explicit runner for separately labelled repaired HCA source-adapter experiments."""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from scripts.experiments.g31_no_wait import hca

def prepare(out,adapter,ceil,causal,end_epoch=None):
    hca.verify(hca.DEFAULT);hca.verify(adapter)
    out.mkdir(parents=True,exist_ok=False)
    manifest=copy.deepcopy(hca.read(hca.DEFAULT/'manifest.json'))
    adapted=hca.read(adapter/'manifest.json')
    uniform=adapted.get('physical_contract')
    if uniform and not (ceil and causal):
        raise ValueError('The uniform physical comparator requires both strict ceil release and causal EBS gates.')
    manifest.update(schema='g31.no_wait.hca_physical_run.v1',status='prepared_no_full_run',classes=adapted['classes'])
    manifest.update(core_java_source_unchanged=False,core_java_classes_exact_original=False,
        original_algorithm_source_files=manifest.pop('algorithm_source_files'),adapted_core_files=adapted['core_files'],
        wrapper_append_only_node_intervals=False,wrapper_source_gates=True)
    manifest['physical_adapter']={'path':str(adapter),'manifest_sha256':hca.sha(adapter/'manifest.json'),
        'label':adapted['label'],'timestamp_fix':adapted['timestamp_fix'],'ceil_release':ceil,'causal_ebs':causal,
        'interval_boundary':'half_open_us' if uniform else 'original_closed','node_headway_override':2 if uniform else None,
        'contract':uniform,'source_order':adapted.get('zero_time_source_order'),
        'profiling':adapted.get('profiling'),
        'warning':'This is a separately labelled adaptation, not the unchanged original HCA baseline. Whole-edge exclusive capacity is not imposed.'}
    if uniform:
        manifest['physical_caveats'].update(node_reservations=uniform['node_intervals'],edge_reservations=uniform['edge_resource'],
            resource_cleanup=uniform['expiration'],time_grid_seconds=0.000001,source_order=adapted['zero_time_source_order'],
            edge_capacity='Directed edge-entry 2s headway, not exclusive occupancy of a whole edge; independent replay required.',
            source_calendar='All positive initial-source intervals checked and reserved; no task-ID exemption.',
            goal_calendar='All positive goal intervals checked and retained through planned departure, independent of business completion.',
            interval_endpoints='Half-open intervals on an exact 1us time grid; 2s equality is allowed.',
            zero_service='Original zero-service nodes remain empty intervals; incident edges still enforce entry headway.')
    manifest['physical_caveats']['ebs']='causal wrapper source gate enabled' if causal else 'original independent EBS releases remain'
    if end_epoch is not None:
        manifest['observation_window']={'start_epoch':8260,'end_epoch':end_epoch,
            'reference_end_epoch':98259,'label':'explicit_separate_observation_window',
            'canonical_arrivals_and_deadlines_unchanged':True,
            'completion_rule':'An extended observation window is not proof of complete drainage; full-population THT remains null if any business is incomplete.'}
        hca.observation_window(manifest)
        manifest['runner_source_identity']=[{'path':str(Path(p).resolve()),'sha256':hca.sha(p)} for p in (hca.__file__,__file__)]
    hca.write(out/'manifest.json',manifest)
    frozen=[]
    for base in (hca.DEFAULT,adapter):
        for item in hca.read(base/'SOURCE_FREEZE.json')['files']:
            frozen.append({'path':str((base/item['path']).resolve()),'sha256':item['sha256']})
    frozen.extend(manifest.get('runner_source_identity',[]))
    hca.write(out/'SOURCE_FREEZE.json',{'external_frozen_inputs':True,'files':frozen})
    print(json.dumps({'status':'prepared_no_full_run','output':str(out),'configuration':manifest['physical_adapter']}))

def run(out,cell):
    options=hca.read(out/'manifest.json')['physical_adapter']
    original=hca.legacy.java_run_command
    def command(**kwargs):
        result=original(**kwargs)
        result[1:1]=[f'-Dg31.hca.ceilRelease={str(options["ceil_release"]).lower()}',
            f'-Dg31.hca.causalEbs={str(options["causal_ebs"]).lower()}']
        if options.get('profiling'):result.insert(1,'-Dg31.hca.profile=true')
        return result
    hca.legacy.java_run_command=command
    try: hca.run(out,cell)
    finally: hca.legacy.java_run_command=original

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run','analyze']);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--adapter',type=Path);parser.add_argument('--ceil-release',action='store_true');parser.add_argument('--causal-ebs',action='store_true')
    parser.add_argument('--cell',choices=['map2_1x','nanning_1x','map2_2x','nanning_2x'])
    parser.add_argument('--end-epoch',type=int,help='Preparation only: explicit separate observation window; original arrival/STD inputs remain unchanged')
    args=parser.parse_args();out=args.output.resolve()
    if args.action=='prepare':
        if not args.adapter:parser.error('--adapter required to prepare')
        prepare(out,args.adapter.resolve(),args.ceil_release,args.causal_ebs,args.end_epoch)
    elif not args.cell:parser.error('--cell required')
    elif args.end_epoch is not None:parser.error('--end-epoch is only accepted during preparation of a new output')
    elif args.action=='run':run(out,args.cell)
    else:hca.analyze(out,args.cell)

if __name__=='__main__':main()
