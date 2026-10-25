"""Native micro regressions for the explicitly adapted common-headway HCA."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from scripts.experiments.g31_no_wait import hca
from scripts.experiments.g31_no_wait.validate_hca_adapter import execute,JAVA,PROBE

def main():
    p=argparse.ArgumentParser();p.add_argument('--adapter',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    adapter=a.adapter.resolve();out=a.output.resolve();hca.verify(adapter);out.mkdir(parents=True,exist_ok=False)
    classes=adapter/'classes';probe_classes=out/'classes';probe_classes.mkdir()
    source=Path(__file__).with_name('java')/'HcaUniformProbe.java'
    command=['C:/PROGRAMING/jdk-18/bin/javac.exe','-encoding','UTF-8','-cp',str(classes),'-d',str(probe_classes),str(source)]
    r=subprocess.run(command,capture_output=True,text=True,encoding='utf-8');hca.write(out/'compile.json',{'command':command,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    if r.returncode:raise AssertionError(r.stderr)
    result=json.loads(execute([JAVA,'-cp',str(probe_classes)+';'+str(classes),'App.HcaUniformProbe'],out/'native').strip().splitlines()[-1])
    reparent=json.loads(execute([JAVA,'-Djava.awt.headless=true','-cp',str(PROBE/'classes')+';'+str(classes),'App.HcaReparentTimeProbe','fixed'],out/'reparent').strip().splitlines()[-1])
    fixture=out/'fixture';fixture.mkdir();map_file=fixture/'map.txt';raw_file=fixture/'tasks.txt'
    map_file.write_text('4 1 0 4\n0 1 2 0 0 1\n1 4 2 0 0 2\n2 1 0 0 0 3\n3 2 2 0 0\n'
        '0 2 42 44\n99999 0 40 42\n99999 99999 0 2\n99999 99999 99999 0\n0 1 2\n1 2 40\n2 3 2\n',encoding='utf-8')
    raw_file.write_text('ID EntryTime(s) STD(s) star end Unloader Loader\n1 10.75 40 0 3 X A\n2 10.25 12 0 3 Y A\n3 10.25 12 0 3 Z A\n',encoding='utf-8')
    run=out/'wrapper';command=hca.legacy.java_run_command(java=JAVA,classes_dir=classes,map_path=map_file,input_path=raw_file,start_epoch=10,max_epochs=60,max_new_tasks=0,run_dir=run,fault_schedule='none',speed_mps=2,storage_in_goal=2,storage_out_start=2,early_threshold_seconds=5,storage_lead_seconds=20)
    command[1:1]=['-Dg31.hca.ceilRelease=true','-Dg31.hca.causalEbs=true'];execute(command,run)
    releases=hca.csv_rows(run/'release.csv');routes=hca.csv_rows(run/'routes.csv');source=[r for r in releases if r['start']=='0']
    assert [int(r['task_id']) for r in source]==[2,3,1],source
    assert [float(r['release_epoch']) for r in source]==[11,12,14],source
    finish=[float(line.split()[1]) for line in (run/'output.txt').read_text().splitlines() if line.split()[0]=='1']
    outbound=next(float(r['release_epoch']) for r in releases if r['task_id']=='1' and r['start']=='2')
    assert len(finish)==2 and outbound>=finish[0],(finish,outbound)
    assert len(routes)==4 and len((run/'output.txt').read_text().splitlines())==4
    # Replay every committed route independently in integer microseconds.
    node_windows={};edge_windows={};continuity=[]
    services={0:2,1:2,2:0,3:2};travel={(0,1):1,(1,2):20,(2,3):1}
    for row in routes:
        visits=[(int(x.split(':')[0]),round(float(x.split(':')[1])*1e6),round(float(x.split(':')[2])*1e6)) for x in row['node_intervals'].split(';')]
        for i,(node,start,end) in enumerate(visits):
            assert end-start==services[node]*1000000
            if start<end:node_windows.setdefault(node,[]).append((start,end,row['ordinal']))
            if i+1<len(visits):
                nxt=visits[i+1];assert nxt[1]==end+travel[node,nxt[0]]*1000000
                edge_windows.setdefault((node,nxt[0]),[]).append((end,end+2000000,row['ordinal']))
    for windows in [*node_windows.values(),*edge_windows.values()]:
        windows.sort()
        assert all(left[1]<=right[0] for left,right in zip(windows,windows[1:])),windows
    # Exercise the same whole-population analysis entry point used by the full run.
    analysis=out/'analysis_fixture';run_copy=analysis/'micro'/'run_01';shutil.copytree(run,run_copy)
    canonical=[]
    for task_id,start,goal,leg,release,deadline in [(1,0,2,'storage_in',10.75,40),(1,2,3,'storage_out',20,40),(2,0,3,'direct',10.25,12),(3,0,3,'direct',10.25,12),(4,0,3,'direct',1000,2000)]:
        canonical.append(dict(task_id=task_id,start=start,goal=goal,leg=leg,pass_time=release,std=deadline,
            segment_id=f'{task_id}:{leg}',original_entry_time=10.75 if task_id==1 else release))
    canonical_path=analysis/'canonical.jsonl';canonical_path.write_text(''.join(json.dumps(r)+'\n' for r in canonical),encoding='utf-8')
    profile={'nodes':[dict(location=n,node_type=4,service_time=s,outgoing=[v for u,v in travel if u==n]) for n,s in services.items()],
        'edges':[dict(start=u,end=v,length=t*2) for (u,v),t in travel.items()]}
    hca.write(analysis/'profile.json',profile)
    hca.write(analysis/'manifest.json',dict(cells={'micro':dict(canonical=str(canonical_path),map=dict(draft_profile=str(analysis/'profile.json'),draft_raw=str(map_file)))},
        speed_mps=2,physical_adapter=dict(contract=hca.read(adapter/'manifest.json')['physical_contract'])))
    hca.write(analysis/'SOURCE_FREEZE.json',{'files':[]})
    lifecycle=hca.legacy._build_lifecycle(canonical,releases,routes,hca.legacy._parse_completions(run/'output.txt'),hca.legacy._parse_processed_attempts(run/'outputstarttime.txt'))
    hca.legacy._write_csv(run_copy/'segment_lifecycle.csv',hca.legacy.LIFECYCLE_FIELDS,lifecycle)
    hca.analyze(analysis,'micro');full=hca.read(analysis/'micro'/'analysis.json')
    assert full['physical_headway_audit']['passed']
    assert full['physical_headway_audit']['segment_denominator']==5
    assert full['physical_headway_audit']['telemetry_coverage']['unreleased_segments']==1
    assert full['business']['offered']==4 and full['continuous_goal_arrival_business_summary']['offered']==4
    # Missing successful-plan telemetry must fail, rather than silently certify a subset.
    original_routes=(run_copy/'routes.csv').read_text(encoding='utf-8')
    (run_copy/'routes.csv').write_text('\n'.join(original_routes.splitlines()[:-1])+'\n',encoding='utf-8')
    try:
        hca.analyze(analysis,'micro')
    except ValueError as exc:
        assert 'telemetry' in str(exc)
    else:raise AssertionError('missing route telemetry was accepted')
    (run_copy/'routes.csv').write_text(original_routes,encoding='utf-8')
    report={'pass':True,'adapter_freeze_sha256':hca.sha(adapter/'SOURCE_FREEZE.json'),'native':result,'reparent':reparent,
        'full_analysis':{'full_population':5,'unreleased_retained':1,'business_denominator':4,'missing_route_telemetry_rejected':True,'headway_audit_passed':True},
        'wrapper':{'chronological_stable_ties':True,'pending_source_blocks_next':True,'strict_ceil':True,'causal_ebs':True,
            'source_releases':source,'inbound_reported_finish':finish[0],'outbound_release':outbound,'routes':len(routes),
            'independent_integer_replay_node_conflicts':0,'independent_integer_replay_edge_conflicts':0,'route_timing_residuals':0}}
    hca.write(out/'validation.json',report);print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
