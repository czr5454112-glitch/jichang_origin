import json,sys
from hashlib import sha256
from pathlib import Path
from time import process_time,perf_counter
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
cpu,wall=process_time(),perf_counter()
files=['scripts/experiments/ics_circulation_v3/same_zone_query_probe.py',
       'tests/test_ics_circulation_v3_same_zone_query_probe.py']
before={p:sha256((ROOT/p).read_bytes()).hexdigest()for p in files}
import pytest
code=pytest.main(['-q',str(ROOT/files[1]),'--basetemp='+str(ROOT/'.tmp/round7_query_probe_authoring')])
after={p:sha256((ROOT/p).read_bytes()).hexdigest()for p in files}
target=Path(__file__).resolve().parent/(sys.argv[1]+'.json')
if target.exists():raise FileExistsError(target)
result={'exit_code':int(code),'source_before':before,'source_after':after,'source_unchanged':before==after,
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'resource_scope':'Pytest host/import through hash verification; final serialization and external child CPU excluded.'}
target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False));raise SystemExit(code)
