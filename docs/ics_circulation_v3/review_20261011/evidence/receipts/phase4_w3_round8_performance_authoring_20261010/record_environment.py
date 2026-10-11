from pathlib import Path
import json,os,platform,sys
from time import get_clock_info,process_time,perf_counter
import psutil

cpu,wall=process_time(),perf_counter()
row={'python_version':sys.version,'python_executable':sys.executable,'platform':platform.platform(),
     'machine':platform.machine(),'cpu_logical':psutil.cpu_count(),'cpu_physical':psutil.cpu_count(logical=False),
     'memory_total_bytes':psutil.virtual_memory().total,'memory_available_bytes_at_observation':psutil.virtual_memory().available,
     'process_cpu_clock':vars(get_clock_info('process_time')),'elapsed_clock':vars(get_clock_info('perf_counter')),
     'recording_phase':'During fixed formal execution, after pilot; descriptive environment evidence, not a pre-run load guarantee.',
     'configured_performance_children_max':3,'configured_mainline_workers_max':6,
     'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
     'scope':'Read-only local machine/interpreter/clock metadata after imports; output serialization excluded. No CPU affinity, priority, clock frequency or other machine setting changed. No physics/search.'}
p=Path(__file__).with_name('environment_receipt.json')
with p.open('x',encoding='utf8')as f:json.dump(row,f,indent=2)
print(json.dumps(row))
