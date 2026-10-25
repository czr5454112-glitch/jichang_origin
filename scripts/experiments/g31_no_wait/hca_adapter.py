"""Build separately labelled HCA timestamp repair and optional physical source gates."""
from pathlib import Path
import argparse
import difflib
import json
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from scripts.experiments.g31_no_wait import hca

GATE_HELPER='''
    // Wrapper-only source admission adapter. It never changes the original task's nominal time.
    private static final class PhysicalSourceGate {
        final boolean ceilRelease = Boolean.getBoolean("g31.hca.ceilRelease");
        final boolean causalEbs = Boolean.getBoolean("g31.hca.causalEbs");
        final HashSet<Integer> completedInbound = new HashSet<>();
        long ceilMaskTicks = 0;
        long ebsMaskTicks = 0;

        private boolean inboundReportsThisTick(ICS_PathFinding ics, int id, int goal, double epoch) {
            ArrayList<Node> route = ics.getSaved_routes().get(id);
            return route != null && route.size() == 2
                && route.get(1).getLocation() == goal && epoch >= route.get(1).getT1();
        }
        HashMap<Integer, ArrayList<task>> mask(HashMap<Integer, ArrayList<task>> queues,
                ICS_PathFinding ics, double epoch, int storageInGoal, int storageOutStart) {
            HashMap<Integer, ArrayList<task>> held = new HashMap<>();
            for (int source : queues.keySet()) {
                ArrayList<task> queue = queues.get(source);
                if (queue.isEmpty()) continue;
                task head = queue.get(0);
                boolean tooEarly = ceilRelease && head.getPass_time() > epoch;
                boolean unavailable = causalEbs && source == storageOutStart
                    && !completedInbound.contains(head.getTask_ID())
                    && !inboundReportsThisTick(ics, head.getTask_ID(), storageInGoal, epoch);
                if (tooEarly) ceilMaskTicks++;
                if (unavailable) ebsMaskTicks++;
                if (tooEarly || unavailable) {
                    held.put(source, queue);
                    queues.put(source, new ArrayList<task>());
                }
            }
            return held;
        }
        void observeReports(Tasks tasks, int storageInGoal) {
            for (task t : tasks.getOnpath_tasks_list()) {
                if (t.getGoal() == storageInGoal && t.getPassed_vertex_location() == storageInGoal)
                    completedInbound.add(t.getTask_ID());
            }
        }
    }

'''

def adapter_wrapper(text):
    text=hca.replace_once(text,'        prepareWorkingFiles();',
        '        prepareWorkingFiles();\n        PhysicalSourceGate sourceGate = new PhysicalSourceGate();\n'
        '        if (sourceGate.causalEbs && (!schedule.isEmpty() || faultProbability != 0 || repairProbability != 0))\n'
        '            throw new IllegalArgumentException("causal source adapter is verified only for no-fault execution");')
    text=hca.replace_once(text,'            newTasks.generate_tasks(taskList, newTasks, epoch, ics, faultProbability, repairProbability, 0.0);',
        '            HashMap<Integer, ArrayList<task>> held = sourceGate.mask(taskList, ics, epoch, storageInGoal, storageOutStart);\n'
        '            newTasks.generate_tasks(taskList, newTasks, epoch, ics, faultProbability, repairProbability, 0.0);\n'
        '            for (int source : held.keySet()) taskList.put(source, held.get(source));\n'
        '            sourceGate.observeReports(newTasks, storageInGoal);')
    text=hca.replace_once(text,'        result.completedCount = countLines(new File("output.txt"));',
        '        System.out.println("physical_source_ceil=" + sourceGate.ceilRelease + ",physical_source_causal_ebs=" + sourceGate.causalEbs\n'
        '            + ",ceil_mask_ticks=" + sourceGate.ceilMaskTicks + ",ebs_mask_ticks=" + sourceGate.ebsMaskTicks);\n'
        '        result.completedCount = countLines(new File("output.txt"));')
    text=hca.replace_once(text,'            HashSet<Integer> beforeKeys = new HashSet<>(ics.getSaved_routes().keySet());',
        '            HashSet<Integer> beforeKeys = new HashSet<>(ics.getSaved_routes().keySet());\n'
        '            if (sourceGate.causalEbs) {\n'
        '                for (task completed : newTasks.getOnpath_tasks_list())\n'
        '                    if (completed.getPassed_vertex_location() == completed.getGoal()) beforeKeys.remove(completed.getTask_ID());\n'
        '            }')
    text=hca.replace_once(text,'    private static void configureMapSpeed(ICS_PathFinding ics, double speedMps) {',
        GATE_HELPER+'    private static void configureMapSpeed(ICS_PathFinding ics, double speedMps) {')
    return text

def prepare(output,fix):
    hca.verify(hca.DEFAULT)
    output.mkdir(parents=True,exist_ok=False)
    source=output/'source'; shutil.copytree(hca.DEFAULT/'source',source)
    wrapper=source/'benchmarks/LegacyIcsNoFaultWindowBenchmark.java'
    before=wrapper.read_text(encoding='utf-8'); after=adapter_wrapper(before); wrapper.write_text(after,encoding='utf-8')
    (output/'wrapper.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='original_telemetry_wrapper',tofile='physical_source_gate_wrapper')),encoding='utf-8')
    astar=source/'src/App/Astar.java'
    before=astar.read_text(encoding='utf-8')
    if fix:
        after=hca.replace_once(before,'n.gcost=gcost;\n\t\t\t\t\t\tn.hcost=hcost;',
            'n.gcost=gcost;\n\t\t\t\t\t\tn.t1=t1;\n\t\t\t\t\t\tn.t2=t2;\n\t\t\t\t\t\tn.hcost=hcost;')
        astar.write_text(after,encoding='utf-8')
        (output/'astar.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='original_Astar',tofile='reparent_timestamp_fixed_Astar')),encoding='utf-8')
    classes=output/'classes';classes.mkdir()
    command=['C:/PROGRAMING/jdk-18/bin/javac.exe','-encoding','UTF-8','-d',str(classes),
        *map(str,sorted((source/'src/App').glob('*.java'))),str(source/'src/ICS_GUI/ICS_GUI.java'),str(wrapper)]
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (output/'compile_stdout.txt').write_text(result.stdout,encoding='utf-8');(output/'compile_stderr.txt').write_text(result.stderr,encoding='utf-8')
    if result.returncode: raise RuntimeError(result.stderr)
    originals=hca.read(hca.DEFAULT/'manifest.json')['algorithm_source_files']
    core=[]
    for row in originals:
        original=(hca.DEFAULT/'source'/row['path']).read_text(encoding='utf-8')
        current=(source/row['path']).read_text(encoding='utf-8')
        expected_difference=fix and row['path']=='src/App/Astar.java'
        assert (original!=current)==expected_difference,row['path']
        core.append({'path':row['path'],'original_sha256':hca.sha(hca.DEFAULT/'source'/row['path']),
            'current_sha256':hca.sha(source/row['path']),'changed':expected_difference})
    hca.write(output/'manifest.json',{'schema':'g31.hca_physical_adapter.v1','status':'prepared_no_full_run',
        'label':'HCA_reparent_timestamp_fixed' if fix else 'HCA_original_core_source_adapter',
        'timestamp_fix':fix,'core_files':core,'source_parent_freeze_sha256':hca.sha(hca.DEFAULT/'SOURCE_FREEZE.json'),
        'wrapper_switches':{'g31.hca.ceilRelease':False,'g31.hca.causalEbs':False},
        'final_physical_options':['-Dg31.hca.ceilRelease=true','-Dg31.hca.causalEbs=true'],
        'new_gate':'mask the existing FIFO source queue for this tick only; retain nominal pass_time and original pending/one-per-tick logic',
        'same_tick_inbound':'allow only an already-completed inbound or a current saved route with exactly two nodes whose EBS arrival report is due now; ICS handles completion before new planning',
        'same_tick_telemetry':'with causalEbs enabled, completed IDs are removed from the pre-plan saved-key snapshot so a same-tick same-ID outbound route is recorded; no algorithm mutation',
        'zero_time_source_order':'source queues still use original Java integer-difference stable comparator',
        'scope':'No-fault only; finite edge capacity remains unimplemented in original HCA',
        'classes':str(classes),'compile_command':command})
    hca.write(output/'SOURCE_FREEZE.json',{'files':[{'path':str(p.relative_to(output)),'sha256':hca.sha(p)} for folder in (source,classes) for p in sorted(folder.rglob('*')) if p.is_file()]})
    print(json.dumps({'status':'prepared_no_full_run','output':str(output),'timestamp_fix':fix}))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--fix-reparent-time',action='store_true')
    args=parser.parse_args();prepare(args.output.resolve(),args.fix_reparent_time)

if __name__=='__main__':main()
