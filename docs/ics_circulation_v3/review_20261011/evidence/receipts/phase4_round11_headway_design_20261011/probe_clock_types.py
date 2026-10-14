"""Independent-review finding: strict clock types at actual-entry boundary."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import json
import time
from headway_ledger_prototype import EntryEvent, record_actual_entry

base=Path(__file__).resolve().parent
index=1
while (base/f'clock_probe_{index:03d}').exists():
    index+=1
out=base/f'clock_probe_{index:03d}'
out.mkdir()
source=base/'headway_ledger_prototype.py'
raw=source.read_bytes()
(out/source.name).write_bytes(raw)
cpu,wall=time.process_time(),time.perf_counter()
rows=[]
for entered,now in ((False,True),(True,-1),(True,None)):
    event=EntryEvent('t','e',1,5,entered)
    try:
        record_actual_entry((event,),event.event_id,now=now)
        rejected=False
    except ValueError:
        rejected=True
    rows.append(dict(entered=entered,now=now,invalid_clock_rejected=rejected))
result=dict(status='passed' if all(r['invalid_clock_rejected'] for r in rows) else 'failed',
            failure_kind='prototype_input_validation' if not all(r['invalid_clock_rejected'] for r in rows) else None,
            rows=rows,source_sha256=sha256(raw).hexdigest(),physics_calls=0,standalone_routing_queries=0,
            cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall)
(out/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['status']=='passed' else 1)
