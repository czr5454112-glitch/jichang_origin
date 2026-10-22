"""Record supervisor cancellation of an unstarted workflow; no native action."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_budget as budget
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_campaign as campaign
from scripts.experiments.g31_ics_circulation.foundation_airport_inventory_spi_campaign import bound

directory = campaign.CYCLE/'terminal_flow/workflow_004'
dispatch = directory/'dispatch_001.jsonl'
rows = [json.loads(line) for line in dispatch.read_text(encoding='utf8').splitlines()]
assert len(rows) == 1 and rows[0]['event'] == 'waiting_for_frozen_predecessor'
assert not any((campaign.CYCLE/'terminal_flow'/name/'block.json').exists() for name in
    ('export_gate_004','full_train_004','bridge_all_004','bins_all_004','period_all_004','predictor_all_004'))
record = dict(event='dispatch_failed', at=budget.now(), exception_type='SupervisorSupersededBeforeDispatch',
    reason='Confirmed stale cross-owner current-tray capture could release a RECEIVED destination claim before capture time dominated receipt time. Freeze corrected runtime005 before any successor native start.',
    supervisor_action='Stopped only exact waiting dispatcher PID 9484 after command-line and dispatch-tail identity checks.',
    predecessor_native_untouched=True, native_starts_in_workflow=0,
    registration=bound(directory/'registration.json'),
    frozen_runtime004_unchanged=True, recorder=bound(__file__))
with dispatch.open('a', encoding='utf8') as stream:
    stream.write(json.dumps(record, ensure_ascii=False)+'\n')
budget.append(campaign.CYCLE, 'terminal_flow_unstarted_workflow_superseded',
    registration=record['registration'], dispatch=bound(dispatch), native_starts=0,
    reason=record['reason'], predecessor_native_untouched=True)
print(json.dumps(record, ensure_ascii=False))
