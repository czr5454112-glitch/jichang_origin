"""Independent due-now source-protection probe using the real native binding."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import traceback

root = Path(__file__).absolute().parents[4]
sys.path.insert(0, str(root))
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle, audit_result

parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
out = args.output.absolute()
out.mkdir(parents=True, exist_ok=False)
native = load_native(args.binary)
base = tiny_cycle()
base['trays'][0]['node'] = 4
base['jobs'] = []
base['transfers'][0].update(issued_at=0.0)
base['transfers'].append(dict(request_id='second-export', tray_id='T0', source=0,
    destination=4, issued_at=0.1, message_delay=0.0, earliest_departure=0.0, expiry=20.0))

def run(name, data):
    result = native.run(data)
    (out/(name+'_input.json')).write_text(json.dumps(data, indent=2))
    (out/(name+'_result.json')).write_text(json.dumps(result, indent=2, allow_nan=False))
    (out/(name+'_audit.json')).write_text(json.dumps(audit_result(data, result), indent=2))
    return result

receipt = {'binary_sha256': hashlib.sha256(args.binary.read_bytes()).hexdigest(),
           'scope': 'actual native execution, due-now arrival versus chained discretionary export'}
try:
    calibration = run('calibration', base)
    arrival = calibration['transfers'][0]['received_at']
    assert arrival > 0
    case = deepcopy(base)
    job = dict(tiny_cycle()['jobs'][0])
    job.update(business_bag_id='due-now-normal', arrival=arrival, storage_node=-1)
    case['jobs'] = [job]
    observed = run('same_timestamp', case)
    control = deepcopy(case)
    control['transfers'] = control['transfers'][:1]
    control_result = run('without_second_export', control)
    receipt.update(received_at=arrival, arrival=arrival,
        with_export_job=observed['jobs'][0], without_export_job=control_result['jobs'][0],
        second_export=observed['transfers'][1],
        same_timestamp_events=[e for e in observed['receipts'] if abs(e['time']-arrival)<1e-9],
        protection_failed=observed['jobs'][0]['loaded_at'] < 0 and control_result['jobs'][0]['completed_at'] >= 0)
except Exception:
    receipt['exception'] = traceback.format_exc()
(out/'receipt.json').write_text(json.dumps(receipt, indent=2, allow_nan=False))
print(json.dumps(receipt, indent=2, allow_nan=False))
raise SystemExit(2 if 'exception' in receipt else int(receipt['protection_failed']))
