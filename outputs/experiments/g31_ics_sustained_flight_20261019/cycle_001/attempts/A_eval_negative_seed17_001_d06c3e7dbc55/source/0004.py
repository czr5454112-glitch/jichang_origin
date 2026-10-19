"""First execution of the four remaining frozen cases after reference clarification."""
from pathlib import Path
import json
import subprocess
import sys
import time
from scripts.experiments.g31_ics_circulation import run_sustained_learning as ledger

ROOT = Path(__file__).resolve().parent
ADDENDUM_SHA = 'f7c862a828f2fbb0ac354ba5a997de40ed657289b6cb5b1271b964f8e06ff3bd'

def main():
    add_path = ROOT / 'A_formal_reference_eligibility_addendum_001.json'
    assert ledger.sha(add_path) == ADDENDUM_SHA
    add = ledger.read(add_path)
    contract = Path(add['formal_contract']['path'])
    assert ledger.sha(contract) == add['formal_contract']['sha256']
    formal = ledger.read(contract)
    rows = formal['rows'][6:]
    assert [r['task_id'] for r in rows] == add['first_attempt_tasks_after_change']
    expected_sources = ledger.read(ROOT / formal['rows'][0]['task_id'] / 'plan.json')['source_sha256']
    for source, change in add['allowed_source_changes'].items():
        assert expected_sources[source] == change['before_sha256']
        expected_sources[source] = change['after_sha256']
    assert all(ledger.sha(source) == value for source, value in expected_sources.items())
    state = ledger.read(ROOT / 'manifest.json')
    assert not any(r['task_id'] in state['tasks'] for r in rows), 'no_automatic_retry'
    module = 'scripts.experiments.g31_ics_circulation.foundation_repeated_campaign'
    with (ROOT / 'A_formal_execution_002.jsonl').open('x', encoding='utf-8') as log:
        for row in rows:
            assert ledger.sha(add_path) == ADDENDUM_SHA
            assert ledger.sha(contract) == add['formal_contract']['sha256']
            assert all(ledger.sha(source) == value for source, value in expected_sources.items())
            output = ROOT / row['task_id']
            command = [sys.executable, '-m', module, '--prepare', '--case', row['case'],
                       '--mode', row['mode'], '--selection', row['selection'], '--output', str(output),
                       '--reference', str(ROOT / row['reference'] / 'raw.json.gz')]
            if row['model']:
                assert ledger.sha(row['model']['path']) == row['model']['sha256']
                command += ['--model', row['model']['path']]
            subprocess.run(command, check=True, cwd=ledger.ROOT)
            plan = ledger.read(output / 'plan.json')
            assert plan['source_sha256'] == expected_sources
            sources = [*expected_sources, str(output / 'plan.json'), str(contract), str(add_path), str(Path(__file__).resolve())]
            if row['model']:
                sources.append(row['model']['path'])
            spec = dict(task_id=row['task_id'], module=module, args=['--launch', '--output', str(output)],
                        native_branches=1, hard_seconds=180, sources=sources, requires=[row['reference']],
                        assessment={'path': str(output / 'receipt.json'), 'allowed_statuses': ['completed_native_branch']},
                        next_action='Audit frozen model consumption, actual guard/effect and every original business outcome')
            ledger.write_new(ROOT / (row['task_id'] + '_task.json'), spec)
            ledger.register(ROOT / 'manifest.json', spec)
            print(json.dumps({'start': row['task_id'], 'at': time.time()}), flush=True)
            result = ledger.run_task(ROOT / 'manifest.json', row['task_id'])
            record = {'task': row['task_id'], 'status': result['status'], 'process': result.get('process')}
            log.write(json.dumps(record) + '\n'); log.flush()
            print(json.dumps(record), flush=True)
            if result['status'] != 'completed':
                return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
