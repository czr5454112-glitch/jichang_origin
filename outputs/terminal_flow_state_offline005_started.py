"""One-shot truthful status update after the registered continuation starts."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'
def read(path):return json.loads(path.read_text(encoding='utf8'))
def bind(path):return dict(path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
review=read(DATA/'offline_budget_failure_closure_review_005_004.json')
started=read(DATA/'offline_budget_execution_005_005/STARTED.json')
spec=DATA/'offline_budget_spec_005_ready_005.json'
assert started['spec']['sha256']==hashlib.sha256(spec.read_bytes()).hexdigest()
assert review['status']=='verified_closed_timeout' and review['tree_closure_verified'] is True
state_path=ROOT/'docs/g31_ics_circulation/RESEARCH_STATE.json'
state=read(state_path);active=state['active_experiment']
assert active['offline_audit004']['status']=='started_pending_completion' and 'offline_audit005' not in active
active['offline_audit004'].update(status='failed_closed_registered_audit_timeout',
    completed_tasks=['full_train_time_scale','granularity'],partial_completed_run_reports=11,
    failed_task='final_science',reason='registered 3600-second audit limit',
    actual_runner_seconds=review['actual_runner_seconds'],closure_review=bind(DATA/'offline_budget_failure_closure_review_005_004.json'))
active['offline_audit005']=dict(status='started_pending_completion',tasks=9,native_starts=0,
    ready_spec=bind(spec),runner_id=started['runner_id'],reused_completed_run_reports=11,
    remaining_run_audits=17,completed_prior_tasks_not_rerun=True,
    output='outputs/experiments/g31_ics_terminal_flow_20261021/offline_budget_execution_005_005',
    remaining_bins600_native_and_audit_reserved_seconds=13200,
    same_original_budget=True,TEST_unlocked=False)
active['full_train_time_scale005']=dict(status='complete',report=bind(DATA/'full_train_time_scale_005_001/full_train_time_scale_report.json'))
active['granularity005']=dict(status='complete',report=bind(DATA/'granularity_005_full_001/granularity_report.json'),
    recorded_decisions=6968,in_window=6960,replayed_opportunities=430,excluded_uncredited_claims=6530,
    first_action_changes_600_vs_60=5,native_600_required=True,native_600_started=False)
state['current_stage']+=(' Offline004 completed full TRAIN timing and full DEV granularity, then closed on its '
    'registered final-science timeout. Offline005 now continues under the original ledger, reusing 11 verified '
    'run reports; 17 run audits and later per-bag/order/forecast evidence remain pending. Four-native 600-bin '
    'comparison and audit have 13200 seconds reserved but have not started.')
state_path.write_bytes((json.dumps(state,ensure_ascii=False,indent=2)+'\n').replace('\n','\r\n').encode('utf8'))
readme=ROOT/'docs/g31_ics_circulation/README.md'
text=readme.read_text(encoding='utf8')
old='11项离线科学审计已启动，尚无服务晋级结论'
new='完整TRAIN时间尺度和粒度审计已完成；逐运行审计达到登记时限后已闭合并续行，11份完成报告经校验复用，其余逐袋、订单和预测留出审计仍在进行，尚无服务晋级结论'
assert old in text
readme.write_bytes(text.replace(old,new).replace('\n','\r\n').encode('utf8'))
print('Recorded closed timeout004, running continuation005, and completed TRAIN/granularity results.')
