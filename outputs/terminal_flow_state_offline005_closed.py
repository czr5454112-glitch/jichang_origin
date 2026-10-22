"""Record verified offline closure and the separately registered 600-bin run."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'
CYCLE=ROOT/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'
def read(p): return json.loads(p.read_text(encoding='utf8'))
def bind(p): return dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def checked(ref):
    p=Path(ref['path']); assert hashlib.sha256(p.read_bytes()).hexdigest()==ref['sha256']; return read(p)
out=DATA/'offline_budget_execution_005_005'
execution=read(out/'EXECUTED.json'); started=read(out/'STARTED.json')
assert execution['status']=='all_children_exited_zero'
processes=[]
for ref in execution['process_reports']:
    p=checked(ref['process'])
    assert p['exitcode']==0 and p['direct_child_wait_completed'] and p['job_active_processes_zero_verified']
    assert p['job_final_active_processes']==0 and p['job_handle_closed'] and not p['cleanup_errors']
    processes.append(dict(task=ref['task'],process=ref['process'],wall_seconds=p['wall_seconds']))
assert len(processes)==9
events=[json.loads(line) for line in (CYCLE/'ledger.jsonl').read_text(encoding='utf8').splitlines() if line]
own=[e for e in events if e.get('runner_id')==started['runner_id']]
opened=[e for e in own if e['event']=='runner_open']; closed=[e for e in own if e['event']=='runner_close']
assert len(opened)==len(closed)==1 and not any(e['event']=='native_start' for e in own)
seconds=(datetime.fromisoformat(closed[0]['at'])-datetime.fromisoformat(opened[0]['at'])).total_seconds()
review=dict(status='verified_all_nine_closed',runner_id=started['runner_id'],actual_runner_seconds=seconds,
    runner_open=opened[0],runner_close=closed[0],execution=bind(out/'EXECUTED.json'),processes=processes,
    native_starts=0,tree_closure_verified=True,service_promotion=False,
    figure_visual_review=dict(files=['J_relative_to_C00.png','known_completion_harm.png'],
        reviewed_by='assistant',labels_legible=True,clipping_observed=False,
        scope='both actual PNGs inspected; no scientific inference from appearance'))
review_path=DATA/'offline_budget_success_closure_review_005_005.json'
with review_path.open('x',encoding='utf8') as f: json.dump(review,f,ensure_ascii=False,indent=2);f.write('\n')
reg=CYCLE/'terminal_flow/bins600_full_005/registration.json'
assert read(reg)['method']=='TF-B1-600'
assert (reg.parent/'STARTED.json').exists()
state_path=ROOT/'docs/g31_ics_circulation/RESEARCH_STATE.json'
state=read(state_path); active=state['active_experiment']
assert active['offline_audit005']['status']=='started_pending_completion'
active['offline_audit005'].update(status='complete_all_nine_closed',actual_runner_seconds=seconds,
    closure_review=bind(review_path),remaining_run_audits=0,service_promotion=False)
active['granularity005']['native_600_started']=True
active['bins600005']=dict(status='started_pending_completion',registration=bind(reg),
    method='TF-B1-600',parents=[2201,2202,2203,2204],same_source005=True,
    axis='forecast_bin_edges_seconds',service_result_pending=True,TEST_unlocked=False)
state['current_stage']='Source005: 32 registered native tasks and nine final offline tasks closed. Four-parent 600-bin extension is running under the original budget. Main DEV service gates failed; predictive MAE improved without service gain. TEST/R1 remain locked. Historical timeout and successful verified continuation are retained.'
state_path.write_bytes((json.dumps(state,ensure_ascii=False,indent=2)+'\n').replace('\n','\r\n').encode('utf8'))
p=ROOT/'docs/g31_ics_circulation/README.md'; text=p.read_text(encoding='utf8')
text=text.replace('其余逐袋、订单和预测留出审计仍在进行，尚无服务晋级结论','其余逐袋、订单和预测留出审计现已全部闭合，主DEV服务门槛未通过；600秒分箱四父补充运行已启动')
text=text.replace('正在核验逐袋服务、订单链、时间尺度和预测误差','逐袋服务、订单链、时间尺度和预测误差审计已完成，见[完整source005结果](TERMINAL_FLOW_FULL_SOURCE005_COMPARISON.md)')
p.write_bytes(text.replace('\n','\r\n').encode('utf8'))
p=ROOT/'docs/g31_ics_circulation/TERMINAL_FLOW_FULL_SOURCE005_COMPARISON.md'; text=p.read_text(encoding='utf8')
old='这些报告各自完成不代表整个offline005监督流程已经结束；其余留出评估、图表和总进程闭合以`offline_budget_execution_005_005/`的最终回执为准。'
assert old in text
new=f'整个offline005监督流程的9项任务均已exit0，Job进程归零、句柄关闭和原账本runner_close已逐项核验，计费区间{seconds:.6f}秒、0次新增native。两张实际PNG已目视检查，文字完整可读。闭合凭证见`offline_budget_success_closure_review_005_005.json`。'
text=text.replace(old,new)
text+='\n\n完整TRAIN的580条成熟标签拟合后，固定模型在四父共同C00公开状态的3480个5/15/30分钟标签上评估。B1→监督Poisson的MAE分别为3.589674→3.483116、6.943199→6.558748、11.937100→11.024145；RMSE分别为5.032973→5.006538、9.837984→9.568229、17.064184→16.329512。按充分统计量汇总，不平均RMSE。预测误差改善没有转化为本轮服务收益；不确定性覆盖未校准，非RL，四父不是独立机场日。见`forecast_full_train_DEV_holdout_005_summary_001/COMPLETE.json`。\n'
p.write_text(text,encoding='utf8')
print(json.dumps(dict(status=review['status'],actual_runner_seconds=seconds,review=bind(review_path))))
