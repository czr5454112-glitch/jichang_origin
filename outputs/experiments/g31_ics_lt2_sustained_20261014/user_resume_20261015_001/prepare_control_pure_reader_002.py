"""Fix only the reader's incorrect assumed parent journal count; no test rerun."""
from pathlib import Path
import hashlib
import json
HERE=Path(__file__).resolve().parent
original=HERE/'verify_control_style_pure_001.py'
text=original.read_text(encoding='utf8')
old="('parent_stages.jsonl',20)"
assert text.count(old)==1
text=text.replace(old,"('parent_stages.jsonl',14)")
target=HERE/'verify_control_style_pure_002.py'
with target.open('x',encoding='utf8',newline='\n') as f:f.write(text)
with (HERE/'control_pure_reader_001_failure.json').open('x',encoding='utf8') as f:
    json.dump({'status':'reader_failed_before_review_write','outputs':['lorp1','oimp1'],
        'reason':'Expected20 copied from another harness; this harness emits14 parent events: source2+archive2+check4+child2+check4.',
        'original_reader_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
        'corrected_reader_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'unchanged_worker_expected_events':10,'unchanged_balance_order_and_artifact_checks':True,
        'new_test_runs':0},f,indent=2)
print(hashlib.sha256(target.read_bytes()).hexdigest())
