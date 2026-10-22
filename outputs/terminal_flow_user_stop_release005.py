"""Seal user-requested stop and release metadata; no experiments or native starts."""
from pathlib import Path
import importlib.util
import hashlib
import json
import subprocess
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'
CYCLE=ROOT/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def bind(p): return dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def save(p,d):
    assert not p.exists(),p
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
    loader=importlib.util.spec_from_file_location('release005_accounting',ROOT/'outputs/terminal_flow_bins600_offline005.py')
    w=importlib.util.module_from_spec(loader);loader.loader.exec_module(w)
    stopped=DATA/'horizon_probe_execution_005_001'
    process=read(stopped/'horizon_probe/process_closed.json')
    assert process['closure_verified'] and process['direct_child_wait_completed']
    assert process['job_active_processes_zero_verified'] and process['job_final_active_processes']==0
    assert process['job_handle_closed'] and not process['cleanup_errors']
    events=[json.loads(x) for x in (CYCLE/'ledger.jsonl').read_text().splitlines() if x]
    start=read(stopped/'STARTED.json');runner=start['runner_id']
    opened=[e for e in events if e['event']=='runner_open' and e.get('runner_id')==runner]
    closed=[e for e in events if e['event']=='runner_close' and e.get('runner_id')==runner]
    assert len(opened)==len(closed)==1
    hold=read(DATA/'offline_historical_holdback_005_002.json')
    snapshot=w.snapshot(coverage_cutoff=w.instant(hold['cutoff_utc']))
    assert not snapshot['open_runners'] and not snapshot['unfinished_native_tasks']
    assert not (DATA/'projection_horizon_probe_005_001/COMPLETE.json').exists()
    assert not (CYCLE/'sources/terminal_flow_runtime_006').exists()
    limits=read(CYCLE/'campaign_budget.json')
    total=snapshot['active_seconds']+w.historical_seconds(hold)+snapshot['post_cutoff_uncovered_calendar_seconds']
    record=dict(status='user_requested_stop_all_processes_closed',at_utc=datetime.now(timezone.utc).isoformat(),
        instruction='先停止吧 整理证据 做好推送 写好给gptpro的 md 在md中仔细分析原因',
        reason='User stopped further research; not a budget exhaustion or successful service claim.',
        interrupted_diagnostic=bind(stopped/'PARTIAL.json'),process_closure=bind(stopped/'horizon_probe/process_closed.json'),
        runner_open=opened[0],runner_close=closed[0],snapshot=snapshot,
        original_limits=limits,historical_holdback_seconds=w.historical_seconds(hold),
        conservative_total_seconds=total,conservative_remaining_seconds=limits['active_seconds_limit']-total,
        gap_holdback_includes_idle_calendar_time_not_measured_CPU=True,
        evidence_bytes=w.evidence_bytes([CYCLE,DATA]),source006_activated=False,
        horizon_probe_complete=False,no_further_experiments_authorized_by_this_record=True,
        TEST_unlocked=False,R1_enabled=False,service_improvement_certified=False)
    save(DATA/'USER_STOP_CLOSURE_005_001.json',record)
    # Completed 600 audit closure is independently checked, not inferred from a marker.
    directory=DATA/'bins600_science_execution_005_001'
    p=read(directory/'bins600/process_closed.json')
    assert w.child_succeeded(p)
    r=read(directory/'STARTED.json')['runner_id']
    assert sum(e['event']=='runner_close' and e.get('runner_id')==r for e in events)==1
    save(DATA/'BINS600_CLOSURE_REVIEW_005_001.json',dict(status='complete_closed',process=bind(directory/'bins600/process_closed.json'),
        complete=bind(DATA/'bins600_science_005_001/COMPLETE.json'),runner_id=r,closure_verified=True))
    statep=ROOT/'docs/g31_ics_circulation/RESEARCH_STATE.json';state=read(statep)
    state['current_stage']='User stopped further research on 2026-10-22. Source005 main and bins600 native/science closed; service gates failed. Horizon probe interrupted and all owned processes closed; source006 never activated. Preparing evidence and GPT Pro handoff; TEST/R1 locked.'
    state['active_experiment']['status']='stopped_by_user_no_active_runner'
    state['active_experiment']['user_stop']=bind(DATA/'USER_STOP_CLOSURE_005_001.json')
    state['active_experiment']['bins600005']=dict(status='complete_closed',report=bind(DATA/'bins600_science_005_001/bins600_science_report.json'))
    state['active_experiment']['next_action']='Review TERMINAL_FLOW_GPT_PRO_HANDOFF_20261022.md; no automatic experiment restart.'
    statep.write_bytes((json.dumps(state,ensure_ascii=False,indent=2)+'\n').replace('\n','\r\n').encode())
    readme=ROOT/'docs/g31_ics_circulation/README.md'
    text=readme.read_text(encoding='utf-8').replace('600秒分箱四父补充运行已启动。','600秒分箱四父补充运行及8组逐袋审计已完成，未获得服务增益。用户于2026-10-22要求停止继续实验；窗口诊断已安全中止，当前无活动进程。')
    text+='\n最终交接：[给 GPT Pro 的完整证据与原因分析](TERMINAL_FLOW_GPT_PRO_HANDOFF_20261022.md)。停止原因是用户指示；未宣称通过服务验收，未启动 source006。\n'
    readme.write_bytes(text.replace('\n','\r\n').encode())
    index=ROOT/'docs/g31_ics_circulation/RESULT_INDEX.jsonl'
    row=dict(id='TERMINAL-FLOW-20261022-user-stop-source005',artifacts='docs/g31_ics_circulation/TERMINAL_FLOW_GPT_PRO_HANDOFF_20261022.md',
        scope='32 source005 main native tasks plus four bins600 tasks closed; 36 per-bag pairs audited; service gates failed; horizon probe user-stopped, source006 not activated.',
        closure=bind(DATA/'USER_STOP_CLOSURE_005_001.json'),main_science=bind(DATA/'final_science_005_resumed_001/final_science_report.json'),bins600_science=bind(DATA/'bins600_science_005_001/bins600_science_report.json'))
    with index.open('ab') as f:f.write((json.dumps(row,ensure_ascii=False)+'\n').encode())
    novelty=ROOT/'docs/g31_ics_circulation/NOVELTY_LEDGER.md'
    with novelty.open('ab') as f:f.write(('\n## 83. Terminal flow 完整开发对照与用户停止交接\n\n来源/目标/数量分配、统一订单与预测接口已有真实闭环证据；四父DEV仍有逐袋损害，600分箱相对300无服务增益，预测MAE改善不构成服务增益。未实现真实RL训练，不宣称相对GRAND的方法新颖性、严格服务保护、100ms或R1联合效果。来源机会成本窗口缺失是有证据支持的待验假设；1800秒窗口诊断经用户指示中止，候选修复从未激活。详见 TERMINAL_FLOW_GPT_PRO_HANDOFF_20261022.md。\n').encode())
    registration=CYCLE/'terminal_flow/workflow_005/registration.json'
    reviews={}
    for p in (index,novelty):
        relative=p.relative_to(ROOT).as_posix();old=subprocess.check_output(['git','show','HEAD:'+relative],cwd=ROOT)
        current=p.read_bytes();assert current.startswith(old)
        reviews[relative]=dict(sha256=hashlib.sha256(current[len(old):]).hexdigest(),reason='Append only verified negative outcomes and explicit user-stop scope; preserve all historical rows.')
    save(CYCLE/'terminal_flow/workflow_005/release_disposition.json',dict(schema='g31.terminal_flow.release.v1.disposition',
        registration_sha256=bind(registration)['sha256'],outcome='complete',
        reason='Registered workflow005 native work is complete; this disposition is not research-goal success. User stopped follow-up after completed bins600 audit; horizon diagnostic is safely interrupted. TEST/R1 locked.',
        research_stop='user_requested',nonclosed_tasks={},unprepared_stages={},research_record_appends=reviews))
    print(json.dumps(dict(snapshot=snapshot,conservative_remaining_seconds=record['conservative_remaining_seconds']),indent=2))
if __name__=='__main__':main()
