"""Small native semantic parity for profiling on/off against frozen physical HCA002."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from scripts.experiments.g31_no_wait import hca
from scripts.experiments.g31_no_wait.validate_hca_adapter import JAVA,execute,PROBE

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',type=Path,required=True);p.add_argument('--profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    parent=a.parent.resolve();profile=a.profile.resolve();out=a.output.resolve();hca.verify(parent);hca.verify(profile);out.mkdir(parents=True,exist_ok=False)
    classes=out/'classes';classes.mkdir();src=Path(__file__).with_name('java')
    command=['C:/PROGRAMING/jdk-18/bin/javac.exe','-encoding','UTF-8','-cp',str(profile/'classes'),'-d',str(classes),str(src/'HcaUniformProbe.java'),str(src/'HcaProfileClockProbe.java')]
    r=subprocess.run(command,capture_output=True,text=True,encoding='utf-8');hca.write(out/'compile_receipt.json',dict(command=command,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr))
    if r.returncode:raise RuntimeError(r.stderr)
    probes={}
    for label,base,enabled in [('parent002',parent,False),('profile_off',profile,False),('profile_on',profile,True)]:
        stdout=execute([JAVA,f'-Dg31.hca.profile={str(enabled).lower()}','-cp',str(classes)+';'+str(base/'classes'),'App.HcaUniformProbe'],out/(label+'_physical'))
        probes[label]=json.loads(stdout.strip().splitlines()[-1]);assert probes[label]['pass'] and probes[label]['assertions']==30
    assert probes['parent002']==probes['profile_off']==probes['profile_on']
    fixture=ROOT/'outputs/experiments/g31_no_wait_20261024/hca_uniform_validation_004/fixture'
    for label,base,enabled in [('parent002',parent,False),('profile_off',profile,False),('profile_on',profile,True)]:
        run=out/label;command=hca.legacy.java_run_command(java=JAVA,classes_dir=base/'classes',map_path=fixture/'map.txt',input_path=fixture/'tasks.txt',start_epoch=10,max_epochs=60,max_new_tasks=0,run_dir=run,fault_schedule='none',speed_mps=2,storage_in_goal=2,storage_out_start=2,early_threshold_seconds=5,storage_lead_seconds=20)
        command[1:1]=['-Dg31.hca.ceilRelease=true','-Dg31.hca.causalEbs=true',f'-Dg31.hca.profile={str(enabled).lower()}'];execute(command,run)
    files=['routes.csv','release.csv','summary.csv','output.txt','outputstarttime.txt']
    # Actual original generator epoch files are part of the equality check too.
    files+=sorted(str(p.relative_to(out/'parent002')) for p in (out/'parent002'/'task').rglob('*.txt'))
    parity={}
    for name in files:
        hashes={label:hca.sha(out/label/name) for label in ('parent002','profile_off','profile_on')}
        assert len(set(hashes.values()))==1,(name,hashes)
        parity[name]=hashes['parent002']
    assert not (out/'profile_off'/'planning_profile.json').exists()
    counters=hca.read(out/'profile_on'/'planning_profile.json');scopes=counters['scopes']
    assert scopes['astar_search']['calls']==counters['search_success']+counters['search_failure']+counters['search_exceptions']
    assert counters['search_success']==len(hca.csv_rows(out/'profile_on'/'routes.csv'))==4
    assert counters['search_failure']>0 and counters['search_exceptions']==0
    assert scopes['calendar_commit']['calls']==4
    assert scopes['window']['calls']==1
    assert all(scopes[name]['calls']==60 for name in ('controller_including_search_calendar_and_io','generator_including_epoch_file_write_read','calendar_prune'))
    assert all(value['elapsed_ns']>=0 for value in scopes.values())
    assert all(value['thread_cpu_ns'] is None or value['thread_cpu_ns']>=0 for value in scopes.values())
    stdout=execute([JAVA,'-Dg31.hca.profile=true','-cp',str(classes)+';'+str(profile/'classes'),'App.HcaProfileClockProbe'],out/'clock_calibration')
    calibration=json.loads(stdout.strip().splitlines()[-1]);empty=hca.read(out/'clock_calibration'/'empty_scope_profile.json')
    assert empty['scopes']['calendar_commit']['calls']==20000
    report=dict(pass_all=True,scope='Native small cases; no full population rerun performed.',parent_freeze_sha256=hca.sha(parent/'SOURCE_FREEZE.json'),profile_freeze_sha256=hca.sha(profile/'SOURCE_FREEZE.json'),
        physical_probes=probes,semantic_files_byte_exact=parity,semantic_file_count=len(parity),profiling=counters,calibration=calibration,
        caution='CPU values have observed timer resolution, not nanosecond precision. Empty-scope overhead is measured, not a universal bound. Nested scopes must not be summed; CPU excludes other JVM threads.')
    hca.write(out/'validation.json',report);print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
