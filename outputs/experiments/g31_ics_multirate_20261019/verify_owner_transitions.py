"""Export the actual v2 episode, without training or native execution."""
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_later_learning as learning

directory = Path(__file__).parent / 'owner_transition_001'
rows, sources = learning.load_manifest(directory / 'episode_manifest.json')
assert len(rows) == 2
raw = json.loads(gzip.decompress(Path(sources[0]['raw_path']).read_bytes()))
records = []
for transition in raw['later_transitions']:
    assert transition['schema'] == 'g31.foundation.later_transition.v2'
    assert transition['next_observation'] is None and transition['terminated'] is True
    assert transition['delta_sim_time_s'] == raw['result']['physical_clock'] - transition['selected_at']
    records.append({key: transition[key] for key in ('schema', 'owner', 'phase', 'selected_at',
        'next_observation', 'delta_sim_time_s', 'terminated', 'truncated', 'ACK_status')})
assert all(row['eligible_for_local_td'] is True for row in rows)
report = {'status': 'passed', 'sources': sources, 'transitions': records,
    'saved_baseline_comparison': raw['saved_baseline_comparison'],
    'extracted_rows': len(rows), 'training_performed': False,
    'same_owner_multi_decision_support': False, 'rl_support': learning.rl_support(rows)}
with (directory / 'transition_export_validation.json').open('x', encoding='utf8') as stream:
    json.dump(report, stream, indent=2, allow_nan=False)
print(json.dumps({key: report[key] for key in ('status', 'transitions', 'extracted_rows')}))
