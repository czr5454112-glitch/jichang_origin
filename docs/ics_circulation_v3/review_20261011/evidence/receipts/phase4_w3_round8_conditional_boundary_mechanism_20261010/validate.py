from pathlib import Path
from time import process_time,perf_counter
import json,subprocess,sys

ROOT=next(p for p in Path(__file__).resolve().parents if(p/'scripts/experiments/ics_circulation_v3').is_dir())
sys.path.insert(0,str(ROOT))
from scripts.experiments.ics_circulation_v3.run_terminal_screen_performance import final_process_cpu
from scripts.experiments.ics_circulation_v3.phase4_network_workloads import file_sha
HERE=Path(__file__).parent
cpu,wall=process_time(),perf_counter()
cmd=[sys.executable,'-m','pytest',str(HERE/'test_runner.py'),'-q','--basetemp',str(HERE/'pytest_tmp_v3')]
with (HERE/'validation_v3.log').open('x',encoding='utf8') as stream:
    process=subprocess.Popen(cmd,stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT)
    code=process.wait()
    child,cpu_error=final_process_cpu(process)
parent=process_time()-cpu
receipt={'exit_code':code,'tests':10,'cpu_seconds':None if child is None else parent+child,
    'cpu_error':cpu_error,
    'parent_cpu_seconds':parent,'child_os_cpu_seconds':child,'wall_seconds':perf_counter()-wall,
    'physical_calls':0,'resource_scope':'Output-local tests only; parent measured interval plus full test child OS CPU. Imports/final receipt writes outside parent interval.',
    'source_sha256':{p.name:file_sha(p) for p in(HERE/'runner.py',HERE/'test_runner.py',Path(__file__))}}
(HERE/'validation.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
print(json.dumps(receipt));raise SystemExit(code)
