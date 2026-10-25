"""Tiny native Java tests for the separately labelled HCA adapter and timestamp repair."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from scripts.experiments.g31_no_wait import hca

CAMPAIGN=ROOT/'outputs/experiments/g31_no_wait_20261024'
PROBE=ROOT/'outputs/experiments/g31_deadline_research_20261024/hca_wait_contract_audit_001'
JAVA='C:/PROGRAMING/jdk-18/bin/java.exe'

def execute(command,directory):
    directory.mkdir(parents=True,exist_ok=False)
    result=subprocess.run(command,cwd=directory,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (directory/'stdout.txt').write_text(result.stdout,encoding='utf-8');(directory/'stderr.txt').write_text(result.stderr,encoding='utf-8')
    hca.write(directory/'command.json',command)
    if result.returncode: raise AssertionError(result.stderr)
    return result.stdout

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--version',default='002');args=parser.parse_args()
    out=CAMPAIGN/f'hca_adapter_validation_{args.version}';out.mkdir(exist_ok=False)
    original=hca.DEFAULT/'classes'
    adapter=CAMPAIGN/f'hca_original_source_adapter_{args.version}/classes'
    repaired=CAMPAIGN/f'hca_reparent_timestamp_fixed_{args.version}/classes'
    for directory in (hca.DEFAULT,adapter.parent,repaired.parent): hca.verify(directory)
    results={}
    for name,classes,mode in [('reparent_original',original,[]),('reparent_fixed',repaired,['fixed'])]:
        stdout=execute([JAVA,'-Djava.awt.headless=true','-cp',str(PROBE/'classes')+';'+str(classes),'App.HcaReparentTimeProbe',*mode],out/name)
        results[name]=json.loads(stdout.strip().splitlines()[-1])
    for name,klass in [('reservation_rejection','App.HcaWaitProbe'),('reservation_lifecycle','App.HcaReservationLifecycleProbe')]:
        stdout=execute([JAVA,'-Djava.awt.headless=true','-cp',str(PROBE/'classes')+';'+str(repaired),klass],out/name)
        results[name]=json.loads(stdout.strip().splitlines()[-1])
    fixture=out/'fixture';fixture.mkdir()
    # One early bag requires EBS after a long inbound route; a direct bag follows at the same source.
    # Raw nominal times remain fractional and unchanged in all arms.
    map_file=fixture/'map.txt';raw_file=fixture/'tasks.txt'
    map_file.write_text('4 1 0 4\n0 1 2 0 0 1\n1 4 2 0 0 2\n2 1 0 0 0 3\n3 2 2 0 0\n'
        '0 2 42 44\n99999 0 40 42\n99999 99999 0 2\n99999 99999 99999 0\n0 1 2\n1 2 40\n2 3 2\n',encoding='utf-8')
    raw_file.write_text('ID EntryTime(s) STD(s) star end Unloader Loader\n1 10.25 40 0 3 X A\n2 10.75 12 0 3 Y A\n',encoding='utf-8')
    cases=[('legacy',original,False,False),('adapter_off',adapter,False,False),('ceil_only',adapter,True,False),
        ('causal_only',adapter,False,True),('both',adapter,True,True),('repaired_both',repaired,True,True)]
    for name,classes,ceil,causal in cases:
        run=out/name
        command=hca.legacy.java_run_command(java=JAVA,classes_dir=classes,map_path=map_file,input_path=raw_file,
            start_epoch=10,max_epochs=60,max_new_tasks=0,run_dir=run,fault_schedule='none',speed_mps=2,
            storage_in_goal=2,storage_out_start=2,early_threshold_seconds=5,storage_lead_seconds=20)
        command[1:1]=[f'-Dg31.hca.ceilRelease={str(ceil).lower()}',f'-Dg31.hca.causalEbs={str(causal).lower()}']
        execute(command,run)
        release=hca.csv_rows(run/'release.csv');routes=hca.csv_rows(run/'routes.csv')
        inbound=next(r for r in release if r['task_id']=='1' and r['start']=='0')
        outbound=next(r for r in release if r['task_id']=='1' and r['start']=='2')
        first=float(inbound['release_epoch']);out_release=float(outbound['release_epoch'])
        assert first==(11 if ceil else 10),(name,first)
        inbound_observed_finish=None
        if causal:
            completions=[float(s.split()[1]) for s in (run/'output.txt').read_text().splitlines() if s.split()[0]=='1']
            assert len(completions)==2,(name,completions)
            inbound_observed_finish=completions[0]
            assert out_release>=inbound_observed_finish
            assert out_release==inbound_observed_finish,'same-tick verified report permits a causal handoff without an invented extra tick'
            assert len(routes)==3,'all three planned segments, including same-ID same-tick EBS handoff, must be recorded'
        else:
            assert out_release==20
        assert next(float(r['release_epoch']) for r in release if r['task_id']=='2')==(12 if ceil else 11)
        results[name]={'first_fractional_release':first,'storage_out_release':out_release,
            'storage_in_actual_finish':inbound_observed_finish,'source_fifo_and_one_per_tick':True,
            'release_rows':release,'planned_routes':len(routes),'completed_lines':len((run/'output.txt').read_text().splitlines())}
    exact={file:(out/'legacy'/file).read_bytes()==(out/'adapter_off'/file).read_bytes()
        for file in ('routes.csv','release.csv','summary.csv','output.txt','outputstarttime.txt')}
    assert all(exact.values()),exact
    results['adapter_flags_off_byte_exact_original']=exact
    results['pass']=True
    hca.write(out/'validation.json',results)
    print(json.dumps({'pass':True,'output':str(out),'old_gap':results['reparent_original']['positive_schedule_residual'],
        'fixed_gap':results['reparent_fixed']['positive_schedule_residual'],'both':results['both'],
        'flags_off_exact':exact},ensure_ascii=False))

if __name__=='__main__':main()
