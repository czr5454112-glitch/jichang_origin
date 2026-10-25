"""Prepare an observation-only HCA timing variant; compilation is explicit, never runs full benchmarks."""
from pathlib import Path
import argparse
import difflib
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from scripts.experiments.g31_no_wait import hca

def prepare(parent,out,compile_sources=False):
    hca.verify(parent);out.mkdir(parents=True,exist_ok=False);source=out/'source';shutil.copytree(parent/'source',source)
    shutil.copyfile(Path(__file__).with_name('java')/'HcaPlanningProfile.java',source/'src/App/HcaPlanningProfile.java')
    controller=source/'src/App/ICS_PathFinding.java';old=controller.read_text(encoding='utf-8');new=old
    new=hca.replace_once(new,'ICS.physicalReservations.prune(epoch);','HcaPlanningProfile.prune(ICS.physicalReservations,epoch);')
    new=hca.replace_once(new,'Astar.research(star, end, map, constrains, ICS.getFault_edges(), ICS.physicalReservations);',
        'HcaPlanningProfile.search(star, end, map, constrains, ICS.getFault_edges(), ICS.physicalReservations);')
    new=hca.replace_once(new,'ICS.physicalReservations.commit(path);','HcaPlanningProfile.commit(ICS.physicalReservations,path);')
    controller.write_text(new,encoding='utf-8');(out/'controller.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True))),encoding='utf-8')
    wrapper=source/'benchmarks/LegacyIcsNoFaultWindowBenchmark.java';old=wrapper.read_text(encoding='utf-8');new=old
    new=hca.replace_once(new,'        prepareWorkingFiles();','        prepareWorkingFiles();\n        App.HcaPlanningProfile.reset();\n        long[] profileWindow = App.HcaPlanningProfile.begin();')
    new=hca.replace_once(new,'            newTasks.generate_tasks(taskList, newTasks, epoch, ics, faultProbability, repairProbability, 0.0);',
        '            long[] profileGenerator = App.HcaPlanningProfile.begin();\n'
        '            try { newTasks.generate_tasks(taskList, newTasks, epoch, ics, faultProbability, repairProbability, 0.0); }\n'
        '            finally { App.HcaPlanningProfile.end(App.HcaPlanningProfile.GENERATOR_IO,profileGenerator); }')
    new=hca.replace_once(new,'            ics.ICS_path_finding(newTasks, ics.getMap(), epoch, ics);',
        '            App.HcaPlanningProfile.controller(newTasks, ics.getMap(), epoch, ics);')
    new=hca.replace_once(new,'        result.completedCount = countLines(new File("output.txt"));',
        '        App.HcaPlanningProfile.end(App.HcaPlanningProfile.WINDOW,profileWindow);\n'
        '        App.HcaPlanningProfile.write("planning_profile.json");\n'
        '        result.completedCount = countLines(new File("output.txt"));')
    wrapper.write_text(new,encoding='utf-8');(out/'wrapper.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True))),encoding='utf-8')
    profiling=dict(schema='g31.hca.profile.v1',status='source_prepared_not_compiled_or_validated',
        parent=str(parent),parent_freeze_sha256=hca.sha(parent/'SOURCE_FREEZE.json'),flag='-Dg31.hca.profile=true',default=False,
        scopes=['Astar search with all physical conflict lookup; success/failure/exception counts','controller including search+calendar+legacy IO',
            'generator including epoch file write and read','ledger prune','ledger commit','full window before final telemetry export'],
        cpu='ThreadMXBean current planner thread user+kernel CPU; excludes other JVM/JIT/GC threads; unavailable is null, never zero',
        overlap='Controller contains search/prune/commit and IO. Window contains controller/generator. Do not sum nested scopes.',
        required_validation=['Compile separate classes; disabled and enabled micro old route/release/summary/output bytes exact against frozen002',
            'Same independent full-population physical audit','Warmup and empty-scope timer overhead calibration reported separately',
            'No full rerun without root timing slot; never overwrite physical002 results'],
        allowed_cost_inference='Compare G31 whole event-loop process CPU against HCA Astar cumulative planner-thread CPU, retaining clock resolution and measurement overhead caveats and C++/Java distinction. Do not infer algorithmic complexity or use IO wall ratios.')
    manifest=hca.read(parent/'manifest.json');manifest.update(schema='g31.hca.profile.adapter.v1',
        label='HCA_repaired_uniform_headway2_us_profile',profiling=profiling,
        status='source_prepared_not_compiled_or_validated',parent_freeze_sha256=hca.sha(parent/'SOURCE_FREEZE.json'))
    files=list(source.rglob('*'))
    if compile_sources:
        classes=out/'classes';classes.mkdir()
        command=['C:/PROGRAMING/jdk-18/bin/javac.exe','-encoding','UTF-8','-d',str(classes),
            *map(str,sorted((source/'src/App').glob('*.java'))),str(source/'src/ICS_GUI/ICS_GUI.java'),str(wrapper)]
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
        hca.write(out/'compile_receipt.json',dict(command=command,exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
        if result.returncode:raise RuntimeError(result.stderr)
        manifest.update(classes=str(classes),compile_command=command,status='compiled_pending_semantic_validation')
        files+=list(classes.rglob('*'))
    else:manifest.pop('classes',None)
    manifest['core_files']=[{'path':str(p.relative_to(source)),'parent_sha256':hca.sha(parent/'source'/p.relative_to(source)) if (parent/'source'/p.relative_to(source)).is_file() else None,
        'current_sha256':hca.sha(p),'changed_from_physical002':not (parent/'source'/p.relative_to(source)).is_file() or hca.sha(p)!=hca.sha(parent/'source'/p.relative_to(source))}
        for p in sorted((source/'src').rglob('*.java'))]
    hca.write(out/'manifest.json',manifest)
    hca.write(out/'SOURCE_FREEZE.json',{'files':[{'path':str(p.relative_to(out)),'sha256':hca.sha(p)} for p in sorted(files) if p.is_file()]})
    print(out)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--compile',action='store_true');a=p.parse_args()
    prepare(a.parent.resolve(),a.output.resolve(),a.compile)
