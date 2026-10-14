"""Capture actual new-binding behavior on malformed numeric inputs."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys

root = Path(__file__).absolute().parents[4]
sys.path.insert(0, str(root))
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle

parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
out = args.output.absolute()
out.mkdir(parents=True, exist_ok=False)
native = load_native(args.binary)
rows = {}
cases = {}
s = tiny_cycle(); s['jobs'] = []; s['trays'][0]['node'] = 4
s['options'].update(max_simulation_time=-1, max_events=1000)
s['transfers'][0].update(issued_at=1e308, message_delay=1e308)
cases['finite_message_components_overflow'] = s
s = tiny_cycle(); s['edge_records'][0] = (0, 1, -1.0, 1.0)
cases['negative_edge_length'] = s
s = tiny_cycle(); s['edge_records'][0] = (0, 1, 1.0, 0.0)
cases['zero_edge_speed'] = s
s = tiny_cycle(); s['node_records'][0] = (0, 1, -1.0, 0, 0, [1, 6])
cases['negative_service_time'] = s
s = tiny_cycle(); s['heuristic_time'] = [[0.0]]
cases['wrong_matrix_dimensions'] = s
s = tiny_cycle(); s['heuristic_time'][0][2] = float('nan')
cases['nan_matrix_used_entry'] = s

def nonfinite(value, path=''):
    if isinstance(value, float) and not math.isfinite(value):
        return [{'path': path, 'repr': repr(value)}]
    if isinstance(value, dict):
        return [r for k,v in value.items() for r in nonfinite(v, path+'/'+str(k))]
    if isinstance(value, (list, tuple)):
        return [r for k,v in enumerate(value) for r in nonfinite(v, path+'/'+str(k))]
    return []

for name, data in cases.items():
    (out/(name+'_input.json')).write_text(json.dumps(data, indent=2))
    try:
        result = native.run(data)
        (out/(name+'_result.json')).write_text(json.dumps(result, indent=2))
        rows[name] = {'outcome':'accepted', 'nonfinite_output':nonfinite(result),
                      'jobs':result.get('jobs'), 'physical_clock':repr(result.get('physical_clock'))}
    except Exception as error:
        rows[name] = {'outcome':'rejected', 'error_type':type(error).__name__, 'message':str(error)}
receipt = {'binary_sha256':hashlib.sha256(args.binary.read_bytes()).hexdigest(), 'results':rows,
           'raw_nonfinite_policy':'JSON raw files use Python NaN/Infinity to preserve observed values; receipt explicitly identifies every nonfinite output'}
(out/'receipt.json').write_text(json.dumps(receipt, indent=2, allow_nan=False))
print(json.dumps(receipt, indent=2, allow_nan=False))
