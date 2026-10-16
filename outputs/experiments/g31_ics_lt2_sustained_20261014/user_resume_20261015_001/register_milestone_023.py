"""Record closed96 audit, closed shard experiment, and original bridge dispatch."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = HERE.parent
DOC = ROOT / 'docs/g31_ics_circulation'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_bytes())

pins = {
    'live_obligation_native_domain_prepare_001/preregistered_protocol.json': 'dc9cc27b6a04eae5eb8ce5d97b9ef844e00657b2cec34004bafb41f952586c04',
    'live_obligation_native_domain_prepare_001/external_application_wall.json': '75881d89c9bc5bbab0e32c15a36bc4e6973daf3a896ed7f32d4ccd0d851fe007',
    'live_obligation_native_domain_saved_review_001.json': '76c2c3c9a11c8e7f4a31b9d25dd498e5305b8f041292b30402ca0a81959bbdb7',
    'json_prediction_shards_RPC_prepare_002/preregistered_protocol.json': '6960f3205c5eef7fbb8ec4f772defadbaac682e5e859f6433a5c3f4ee5ea92e1',
    'json_prediction_shards_RPC_prepare_002/external_application_wall.json': '3b23889227989741ff9c6010b128fb5eb62f6d15386e412aaae87ab22fac8ba7',
    'json_prediction_shards_independent_actual_review_002.json': 'ac9ba3840225c1cb48d5d1efd43ab2a56a5e45da370085e93aee1ba83317903b',
    'json_shards_next_structural_assessment_002.json': '77fc8a869e129b6134b6d902b5a85ae6fc7e59c05694567842fef192f5ee670c',
    'original_cooperative_bridge_prepare_001/campaign.json': '406c5e2ef785805888be33e0d6e79812cc4d0a64f3c18d1bcaea33eb7cbc3655',
    'original_cooperative_bridge_prepare_001/ready.json': '3c2c30e1eb0928ca01c69af67667bce615473135889b558bc6da48125ca37498',
    'original_cooperative_bridge_prepare_001/independent_source_review_r1_001.json': 'd4d41f686f66bc941859680c0d57a7fe1136106227608d4e492068e81400e142',
    'original_cooperative_bridge_prepare_001/root_prelaunch_review_001.json': '277acee4bccc0d389703c5a7c487eb7cd3103ea972f40b7dbe5e489ca07c8fc1',
    'user_resume_20261015_001/invoke_original_cooperative_bridge_001_measured.ps1': '6a7c7c546b60f1f814aecb9f4827b5ef8b66f550e1efc99643feac278b93cb38',
}
for name, digest in pins.items():
    assert sha(OUT / name) == digest, name

audit = read(OUT / 'live_obligation_native_domain_saved_review_001.json')
assert audit['denominator'] == 96
assert audit['status_counts'] == {'assessed': 34, 'unknown_missing_input_or_unexecuted_counterfactual': 62}
assert audit['all_pins_entry_exit_match']
assert audit['all96_full40_physical_audit'] and audit['all480_job_terminal_times_validated']
assert audit['source_pins'] == 75 and audit['closure_pins'] == 654
assert audit['pure_time_conformance']['all_exact'] == 58
assert audit['pure_time_conformance']['assessed_exact'] == 32
assert all(family['status'] == 'unknown_incomplete_reference' for case in audit['comparisons_recomputed']['cases'].values() for family in case['references'].values())
bridge = OUT / 'original_cooperative_bridge_prepare_001'
heartbeat = read(bridge / 'bridge/heartbeat.json')
assert heartbeat['offered'] == 28506 and heartbeat['tick'] > 0
literature = OUT / 'realtime_control_literature_boundary_001.json'
pins[str(literature.relative_to(OUT)).replace('\\', '/')] = sha(literature)
parent = ROOT.parent / 'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent) == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'

backup = HERE / 'before_milestone_023'
receipt = HERE / 'milestone_023.json'
assert not backup.exists() and not receipt.exists()
backup.mkdir()
names = ('RESEARCH_STATE.json', 'NEXT_ACTION.md', 'RESUMPTION_20261015.md', 'NOVELTY_LEDGER.md')
for name in names:
    (backup / name).write_bytes((DOC / name).read_bytes())

state = read(DOC / 'RESEARCH_STATE.json')
active = state['active_experiment']
state['current_stage'] = 'Fully resumed. Full native96 executed and independently audited:34assessed/62unknown, all6 strong16-reference families remain unknown. Shard002 exact fixedABBA completed but0/12 split requests<=100ms; both cold start and duplicated work increased. Original bridge001 fresh full28506/H86400 experiment dispatched once with shared2400s ownedJob and external wall wrapper; running, no final business result. Complete owner-A finite2-candidate native request source/pure work in progress. Full-day original effectiveness, complete100ms and strong-method joint effectiveness remain unmet.'
active['joint_protection_design_status'] = 'Native96 one600s bounded run closed in239.2389025s wholePython.75source/654closure pins,44+21 native gates,96 fullH40 physical runs,480 terminals and192 later endpoints independently rechecked.34assessed/62unknown (16/16 mechanism;8/24 no_overlap;10/22 insufficient_advance).6complete16-member reference families unknown; no native optimum.58/96 all5pure times exact;32/34 assessed exact. Assessed no_overlap28/29 have actual+.001 timing discrepancy and strict noepsilon remains. Original004 mechanism12/24/25 exact15 remains valid. Method results are fixed pure-selection action mapping to actual rows, not online native optimization.'
active['native_domain_unknown_status'] = '62unknown contain66 failing stages:B62,A4.30 actual owner-capture-to-current changes must stay unknown, requiring fresh collection/barrier rather than weakened guard.36 typed-model failures:4 P_stable_storage,8 E_stable_loading,20 complete_delivered_prefix,4 unsupported_tray_available_epoch. Saved-only detailed classification and exact physical clock diagnosis are next; old001 immutable and unknowns never promoted retrospectively.'
active['json_prediction_sharding_status'] = 'Shard002 one-expression path fix plus realcampaign-to-firstconstructor wiring test:61pure; fixedABBA24logical/36physical RPC+fullbaselines/768candidate queries;6 normally closed workers.396full+372original partial labels byte-exact to frozen old six outcomes,88+85pins. WholePython63.1886045s. Onlywithin-new-pipeline median single381.44275->split313.20965ms;split156.7714..405.3314ms,0/12<=100. Coldfirst single1159.8655..1165.427 versus split2033.8744..2065.5155ms;close347.1716..366.1964 versus707.9209..713.1605ms. Summed worker compute WALL+14.30%;postreply merge/codec/ledger median156.82ms and slowest shardkernel122.1045ms.001 failure retained.002 dispatched byroot fromplan/rootreview before late readyfinalizer; latefinalizer refusedexistingclaim, no backfilled prepared_ready and minor nonprediction process overlap retained.'
active['original_bridge_status'] = 'Bridge001 dispatched once under root externalStopwatch wrapper; one accepted026 native worker,76live/archive+67compiled pins,109pure and independent source review; whole ownedJob2400s includes allnative/policy/codec/tape and fullsavedpolicy+physicalaudit/export. Fresh original28506/22/H86400/R1false with21parked,39completed/78postparkingempty/100physical/8722perowner publication stop budgets. Uses current source-owned FIFOhead identities joined to delivered owncontracts; empty bridge only after actual tokenUNLOAD, then direct only. FullH and capcertificate distinct; heartbeat deliveredcompleted islowerbound only. Experiment inprogress, no business or100ms result. Oldcap8 immutable.'
active['complete_native_request_status'] = 'Source/pure only: initialownerA supported public model, default baseline as firstcandidate and prefer2 assecond, fixed public continuation, no newlater model/no32-search claim. Realnative collection,guards,selection,finalsource+receiver validation,submit,immutableACK retry,actualfirsthop+mandatorydrain allcharged; missingACK/atomicbaselineoverrun unknown, updatedACKalone insufficient. Cold/setup/acceptance separate unamortized. Await code/pure/independent review and fixedplan; no performance benchmark concurrentwithoriginalbridge.'
active['realtime_literature_boundary'] = 'Reviewed Diehl2005 real-timeiterations,Zeilinger2014 robustMPC andSu2013delaycompensation. Preparation/feedback split and feasibleincumbent/delay modeling are design inspirations only; their smooth/linear/stability hypotheses do not certify discreteFIFO,strict perjob protection,distributedACK orour100ms request. Source/access limitations and inference boundaries saved in realtime_control_literature_boundary_001.json.'
state['next_actions'] = [
    'Monitor original bridge001 to its fixed completion/timeout and full saved audit. Preserve every offered job and partial artifact; do not restart samepackage, alter its76pins, equate cap39 with alloffered success, or treat heartbeat lowerbound as fullmetrics.',
    'Finish saved96 failure classification. Keep genuine capture-current changes unknown; design lawful recollection separately from typed lifecycle expansions and diagnose exact+.001 timing semantics. New module/plan/pure review before any freshnative comparison; old001 preserved.',
    'Complete finite2 initialownerA native request source and pure boundary tests. Review fixed continuation obligations, fresh captures, complete ACK/firsthop/drain closure and deadline unknowns, then prepare one fixed native experiment. Avoid timing run while originalbridgeactive.',
    'Keep all3 overall gates open: fulloriginal workload effectiveness, complete100ms and strong-method joint validity. Smallcase physical feedback and partialRPC speedup are not fullsuccess ornovelty.',
    'Continue recording issues, failed attempts, corrective evidence and research limitations. User has not authorized commit,push,externalmessage orGPTPro transmission.'
]
active['pending'] = state['next_actions']
(DOC / 'RESEARCH_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
(DOC / 'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone023\n\n全面恢复继续有效。完整96已经执行并完成独立保存审计：34可评估、62未知，六组强参考仍未知。双进程分片有部分提速，但完整caller仍0/12达到100ms。原始全天流bridge001已派发，尚无终局；有限双候选完整native请求在源代码/纯测试阶段。\n\n' + '\n'.join(f'{i+1}. {v}' for i, v in enumerate(state['next_actions'])) + '\n', encoding='utf8')
note = '''

## milestone023：完整96闭合审计、分片性能未达标、原流桥接实际启动

完整96按原3case×32动作固定顺序执行，600秒总界内整Python239.2389025秒结束。独立保存审计核75源码/654闭包及入出门、96完整H40物理过程、480终态、192 later端点；34 assessed、62 unknown。mechanism16/16、no_overlap8/24、insufficient_advance10/22；六组16成员强参考均因成员未知保持unknown，best为null。不能用所有作业物理完成替代信息/执行合法性，也不能把纯模型选出的固定动作事后映射到native称作在线优化。

62未知涉及B62/A4，共66阶段。30次是真实own capture到current变化，不能放宽guard，需独立设计新鲜采集/屏障；其余36是受支持模型状态范围：P_stable_storage4、E_stable_loading8、complete_delivered_prefix20、未来available4。完整96仅58条五件完成时刻与纯003全等；34可评估中32全等，no_overlap28/29实际有+0.001差异，继续零epsilon，必须按实际事件语义诊断。004正机制三分支15个时刻仍全等，原2.3收益/单独前段blocker+0.8证据不变。旧96结果和未知状态不可事后升级。

分片002修复001路径下标错误并加入真实campaign入口接线测试，61纯测试通过。固定ABBA24逻辑请求、36实际RPC/全基线、768候选、6个正常退出worker；396完整与372原部分结果标签精确匹配，独立核88+旧85源码。新公共caller增加隔离/codec/ledger，只允许本次单worker与双worker相比：中位381.44275→313.20965ms，双worker范围156.7714–405.3314ms，0/12≤100。冷启动约1160→2050ms，关闭约350→710ms，合计worker计算墙时+14.30%；回复后合并/codec/ledger中位156.82ms，最慢分片kernel122.1045ms。整Python63.1886045秒。002由root从计划与rootreview派发后，晚到readyfinalizer正确拒绝已执行claim，保留轻微非预测进程重叠，不补造prepared_ready，不筛掉慢项。下一优先真实完整请求，而非继续扩大微基准。

bridge001完成76源码/67编译来源、109纯测试、R1独立源审和root外部计时wrapper后实际派发。新鲜026单native，完整28506请求/22盘/H86400/R1false，21其他盘停放；39完成/78停车后空盘请求等只是停机预算，不是业务达标。共享2400秒包括启动、策略、全API tape、独立策略和物理重放、全部28506终态导出。当前仍运行，heartbeat已送达完成回执仅为下界；全天观测与两owner cap证书分别核，不把全局实验halt冒充合法分布式协调。

完整100ms新方向限定原受支持模型的初始ownerA双候选，默认基线算一次并作默认候选，prefer2为第二候选；后续策略是预先公开合同，不冒充当前capture认证未来承诺。源代码/纯测试中，尚未native执行，要求采集、全部guard/预测、提交、最终源和接收方校验、不可变重试、真实ACK/第一跳及同刻drain全计入；只有updatedACK不足以结束，漏ACK/原子基线超时保持unknown。阅读实时迭代MPC/鲁棒MPC/延迟补偿文献并记录适用边界，不能移植其连续/线性稳定性定理到当前离散FIFO和逐件保护。三个总目标继续未达标。
'''
with (DOC / 'RESUMPTION_20261015.md').open('a', encoding='utf8') as stream:
    stream.write(note)
with (DOC / 'NOVELTY_LEDGER.md').open('a', encoding='utf8') as stream:
    stream.write('\n\n## 53. 完整96仍无强参考闭合，分片仅局部性能改善\n\n完整96的34可评估/62未知不能构成六组强参考优势；真实capture变化和+0.001语义偏差分别保留。双进程固定分片精确保持输出，中位381→313ms但0/12达100ms，且冷启动与重复计算更贵。原流bridge刚启动，完整双候选请求尚未执行；均无总体达标或新颖性主张。\n')
with receipt.open('x', encoding='utf8') as stream:
    json.dump({'schema': 'g31.resume_milestone.v1', 'recorded_utc': datetime.now(timezone.utc).isoformat(), 'immutable_evidence': pins, 'before_sha256': {n: sha(backup/n) for n in names}, 'after_sha256': {n: sha(DOC/n) for n in names}, 'parent_user_file_sha256': sha(parent), 'bridge_status': 'dispatched_once_in_progress', 'bridge_heartbeat_observed': {key: heartbeat[key] for key in ('tick', 'physical_time', 'delivered_actual_completed_count', 'physical_requests_submitted', 'api_rows')}, 'overall_goal_achieved': False, 'new_native_dispatched_here': 0}, stream, ensure_ascii=False, indent=2)
print(json.dumps({'state_updated': True, 'milestone_sha256': sha(receipt)}))
