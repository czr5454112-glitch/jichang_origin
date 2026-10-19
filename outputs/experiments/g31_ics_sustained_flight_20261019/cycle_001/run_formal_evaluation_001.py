"""Run the ten frozen branches once, sequentially, through the bounded ledger."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
EXPECTED = '6ede398fcf64bd74fd2d79c30ad701bd056b787f6480e8d11eafa832f25b837b'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    contract = ROOT / 'A_formal_evaluation_001.json'
    assert sha(contract) == EXPECTED
    plan = json.loads(contract.read_text(encoding='utf-8'))
    assert len(plan['rows']) == plan['native_branch_budget'] == 10
    sources = list((ROOT.parents[3] / 'scripts/experiments/g31_ics_circulation').glob('foundation_repeated_*.py'))
    frozen = {str(p): sha(p) for p in sources}
    assert frozen
    output = ROOT / 'A_formal_execution_001.jsonl'
    with output.open('x', encoding='utf-8') as log:
        for row in plan['rows']:
            assert sha(contract) == EXPECTED
            assert all(sha(p) == s for p, s in frozen.items()), 'source_changed_during_formal_evaluation'
            if row['model']:
                assert sha(row['model']['path']) == row['model']['sha256']
            command = [sys.executable, str(ROOT / 'run_registered_branch.py'),
                       '--name', row['task_id'], '--case', row['case'],
                       '--mode', row['mode'], '--selection', row['selection'],
                       '--contract', contract.name]
            if row['reference']:
                command += ['--reference', row['reference']]
            if row['model']:
                command += ['--model', str(Path(row['model']['path']).relative_to(ROOT))]
            print(json.dumps({'start': row['task_id'], 'at': time.time()}), flush=True)
            started = time.time()
            process = subprocess.run(command, check=False)
            record = {'task': row['task_id'], 'exitcode': process.returncode,
                      'started_at': started, 'finished_at': time.time(), 'automatic_retries': 0}
            log.write(json.dumps(record) + '\n'); log.flush()
            print(json.dumps(record), flush=True)
            if process.returncode:
                return process.returncode
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
