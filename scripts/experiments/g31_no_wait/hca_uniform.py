"""Prepare HCA with a persistent half-open node/edge-entry ledger on a 1us comparison grid."""
from pathlib import Path
import argparse
import difflib
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from scripts.experiments.g31_no_wait import hca

PARENT=ROOT/'outputs/experiments/g31_no_wait_20261024/hca_reparent_timestamp_fixed_002'

def prepare(out):
    hca.verify(PARENT);out.mkdir(parents=True,exist_ok=False)
    source=out/'source';shutil.copytree(PARENT/'source',source)
    ledger=source/'src/App/PhysicalReservations.java'
    shutil.copyfile(Path(__file__).with_name('java')/'PhysicalReservations.java',ledger)
    astar=source/'src/App/Astar.java';old=astar.read_text(encoding='utf-8');new=old
    signature='public static ArrayList<Node> research(Node star, Node goal, Map map, \n\t\t\t\tHashMap<Integer, ArrayList<ArrayList<Double>>> constrain_Set, ArrayList<Edge> fault_Edges) {'
    replacement=signature+'\n        return research(star,goal,map,constrain_Set,fault_Edges,null);\n    }\n'\
        +'    public static ArrayList<Node> research(Node star, Node goal, Map map,\n'\
        +'            HashMap<Integer, ArrayList<ArrayList<Double>>> constrain_Set, ArrayList<Edge> fault_Edges, PhysicalReservations physical) {'
    new=hca.replace_once(new,signature,replacement)
    new=hca.replace_once(new,'star.t2=star.t1+findTime(star.getLocation(),map);',
        'star.t2=star.t1+findTime(star.getLocation(),map);\n        if (physical != null) {\n'
        '            star.t1=PhysicalReservations.seconds(PhysicalReservations.ticks(star.t1));\n'
        '            star.t2=PhysicalReservations.add(star.t1,findTime(star.getLocation(),map));\n'
        '            if (!physical.nodeFree(star.getLocation(),star.t1,star.t2)) return list;\n        }')
    new=hca.replace_once(new,'double t2=t1+findTime(i,map);',
        'double t2=t1+findTime(i,map);\n                if (physical != null) {\n'
        '                    t1=PhysicalReservations.add(currNode.t2,edge.length/edge.v);\n'
        '                    t2=PhysicalReservations.add(t1,findTime(i,map));\n'
        '                    if (!physical.nodeFree(i,t1,t2) || !physical.edgeFree(currNode.getLocation(),i,currNode.t2)) continue;\n                }')
    new=hca.replace_once(new,'if (constrain_Set.containsKey(i)&&i!=goal.location) {','if (physical == null && constrain_Set.containsKey(i)&&i!=goal.location) {')
    astar.write_text(new,encoding='utf-8');(out/'astar.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True))),encoding='utf-8')
    controller=source/'src/App/ICS_PathFinding.java';old=controller.read_text(encoding='utf-8');new=old
    new=hca.replace_once(new,'public class ICS_PathFinding {','public class ICS_PathFinding {\n    private final PhysicalReservations physicalReservations = new PhysicalReservations();\n    public PhysicalReservations getPhysicalReservations() { return physicalReservations; }')
    new=hca.replace_once(new,'public void ICS_path_finding(Tasks tasks, Map map, double epoch, ICS_PathFinding ICS) throws IOException {',
        'public void ICS_path_finding(Tasks tasks, Map map, double epoch, ICS_PathFinding ICS) throws IOException {\n        if (!tasks.getFault_edges().isEmpty() || !ICS.getFault_edges().isEmpty()) throw new IllegalArgumentException("uniform physical HCA supports no-fault execution only");\n        ICS.physicalReservations.prune(epoch);')
    new=hca.replace_once(new,'ArrayList<Node>path=Astar.research(star, end, map, constrains, ICS.getFault_edges());',
        'ArrayList<Node>path=Astar.research(star, end, map, constrains, ICS.getFault_edges(), ICS.physicalReservations);')
    new=hca.replace_once(new,'ICS.getSaved_routes().put(curTask.task_ID, path);',
        'ICS.physicalReservations.commit(path);\n                ICS.getSaved_routes().put(curTask.task_ID, path);')
    controller.write_text(new,encoding='utf-8');(out/'controller.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True))),encoding='utf-8')
    wrapper=source/'benchmarks/LegacyIcsNoFaultWindowBenchmark.java';old=wrapper.read_text(encoding='utf-8')
    new=hca.replace_once(old,'return (int) (left.getPass_time() - right.getPass_time());',
        'return Double.compare(left.getPass_time(), right.getPass_time());')
    wrapper.write_text(new,encoding='utf-8');(out/'wrapper.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True))),encoding='utf-8')
    classes=out/'classes';classes.mkdir()
    command=['C:/PROGRAMING/jdk-18/bin/javac.exe','-encoding','UTF-8','-d',str(classes),*map(str,sorted((source/'src/App').glob('*.java'))),str(source/'src/ICS_GUI/ICS_GUI.java'),str(source/'benchmarks/LegacyIcsNoFaultWindowBenchmark.java')]
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (out/'compile_stdout.txt').write_text(result.stdout,encoding='utf-8');(out/'compile_stderr.txt').write_text(result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError(result.stderr)
    manifest=hca.read(PARENT/'manifest.json')
    manifest.update(schema='g31.hca_uniform_physical.v1',status='prepared_no_full_run',label='HCA_repaired_uniform_headway2_us',classes=str(classes),
        parent_freeze_sha256=hca.sha(PARENT/'SOURCE_FREEZE.json'),compile_command=command,
        contract_file=str(ROOT/'outputs/experiments/g31_no_wait_20261024/headway_contract_002.json'),
        contract_sha256=hca.sha(ROOT/'outputs/experiments/g31_no_wait_20261024/headway_contract_002.json'),
        zero_time_source_order='chronological stable FIFO using Double.compare on unchanged nominal pass_time; exact ties keep input order',
        scope='No-fault only. Persistent half-open positive node resources and directed edge-entry headway; whole-edge finite capacity is not imposed.',
        physical_contract={'time_comparison':'long Math.round(seconds*1e6); every physical addition sums quantized integer durations; no epsilon','node_intervals':'half-open [arrival,departure), including positive source and goal; zero service empty',
            'goal_resource':'retained until planned departure even after business arrival completion','edge_resource':'directed edge-entry [departure,departure+2s); permits multiple bags travelling on an edge',
            'source_admission':'chronological stable FIFO; wrapper strict ceil + causal EBS options must both be enabled for final baseline','expiration':'end<=current planning epoch; independent of saved-route cleanup','faults':'rejected'})
    manifest['core_files']=[{'path':str(p.relative_to(source)),'original_sha256':hca.sha(hca.DEFAULT/'source'/p.relative_to(source)) if (hca.DEFAULT/'source'/p.relative_to(source)).is_file() else None,
        'current_sha256':hca.sha(p),'changed':not (hca.DEFAULT/'source'/p.relative_to(source)).is_file() or hca.sha(p)!=hca.sha(hca.DEFAULT/'source'/p.relative_to(source))}
        for p in sorted((source/'src').rglob('*.java'))]
    hca.write(out/'manifest.json',manifest)
    hca.write(out/'SOURCE_FREEZE.json',{'files':[{'path':str(p.relative_to(out)),'sha256':hca.sha(p)} for folder in (source,classes) for p in sorted(folder.rglob('*')) if p.is_file()]})
    print(str(out))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output.resolve())
