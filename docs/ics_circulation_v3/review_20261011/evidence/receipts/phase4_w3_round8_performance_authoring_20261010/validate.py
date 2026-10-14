from pathlib import Path
import json,subprocess,sys
from time import process_time,perf_counter

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from scripts.experiments.ics_circulation_v3.run_terminal_screen_performance import final_process_cpu
from scripts.experiments.ics_circulation_v3.phase4_network_workloads import file_sha

cpu,wall=process_time(),perf_counter()
out=Path(__file__).parent
name=sys.argv[1]
tests=sys.argv[2:]or['tests/test_ics_circulation_v3_terminal_screen_performance.py']
sources=[ROOT/'scripts/experiments/ics_circulation_v3'/n for n in('terminal_screen_performance.py','run_terminal_screen_performance.py')]
bindings={str(p):file_sha(p)for p in sources+[ROOT/t for t in tests]}
command=[sys.executable,'-m','pytest',*tests,'-q','--basetemp',str(out/(name+'_tmp'))]
with(out/(name+'.log')).open('x',encoding='utf8')as log:
    with subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)as process:
        code=process.wait();child_cpu,reason=final_process_cpu(process)
parent_cpu=process_time()-cpu
result={'command':command,'exit_code':code,'parent_cpu_seconds':parent_cpu,'child_complete_process_cpu_seconds':child_cpu,
        'cpu_seconds':None if child_cpu is None else parent_cpu+child_cpu,'wall_seconds':perf_counter()-wall,
        'child_cpu_unknown_reason':reason,'source_test_sha256':bindings,
        'source_tests_unchanged':all(file_sha(p)==h for p,h in bindings.items()),
        'scope':'Known parent measurement interval plus complete pytest child OS CPU; parent imports and final JSON output excluded. Nested tiny CPU-probe child CPU is not included by OS pytest CPU and is an explicitly unmetered validation auxiliary.',
        'new_original_network_physical_calls':0}
(out/(name+'.json')).write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result,indent=2))
print((out/(name+'.log')).read_text(encoding='utf8'))
raise SystemExit(code)
