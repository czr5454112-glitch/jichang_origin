"""Close fixed96 and two receiver-cut trials; retain remaining obligations."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT, OUT = HERE.parents[3], HERE.parent
DOC = ROOT / 'docs/g31_ics_circulation'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
pins = {
 'live_obligation_saved96_independent_review_001.json':'57682f41ab05b6c7987e6d6b76da73c14b5b13640751b4fc7e0dcc3a26ba9bb1',
 'live_obligation_projection_prepare_003/external_application_wall.json':'0328cabbac6958c57a871719c5f92b65e75725665a1a2359aab50264d5c510b7',
 'preference_receiver_bound_pair_001_independent_review.json':'01cc43eaf1ebf4c7ed7ad6c4c0df63a079111050efcbd02b2eda85046d0f62e6',
 'receiver_bound_fixed_profile_001_analysis.json':'3b82548409836115e835b39f1259b56cfe4a3ec74531c90902030e8ab7538ecd',
 'preference_receiver_vector_pair_001/external_application_wall.json':'4a567129185409a4cc7d97a2fec75a789f57567418d4f5ef2d74bb2e94d9177e',
 'preference_receiver_vector_pair_001/root_prelaunch_review_001.json':'61018ee4484e0be0809bf6ff64e49c3e266c25cbe5c335c1a287d0487d573cf0',
 'original_recirculation_screen_001/report.json':'8a67822c5db2d749258e9109ce48e75971f49c065f51713679169355fabc7a1c',
}
for name, digest in pins.items(): assert sha(OUT / name) == digest, name
joint = read(OUT / 'live_obligation_saved96_independent_review_001.json')
assert joint['status'] == 'passed_saved96_conditional_model_checks'
assert joint['row_count'] == 96 and joint['all96_five_jobs_complete'] and joint['all6_full_reference_families']
assert joint['all4_method_query_sequences_recomputed'] and joint['native_executions'] == 0
vector = read(OUT / 'preference_receiver_vector_pair_001/receipt.json')
assert vector['source_changed'] == vector['input_changed'] == []
assert vector['candidate_queries'] == 768 and vector['full_baselines'] == 24
assert all(r['status'] == 'completed' for r in vector['timing_samples'])
parent = ROOT.parent / 'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent) == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup, receipt = HERE / 'before_milestone_020', HERE / 'milestone_020.json'
assert not backup.exists() and not receipt.exists()
backup.mkdir()
names = ('RESEARCH_STATE.json', 'NEXT_ACTION.md', 'RESUMPTION_20261015.md', 'NOVELTY_LEDGER.md')
for name in names: (backup / name).write_bytes((DOC / name).read_bytes())
state = read(DOC / 'RESEARCH_STATE.json'); active = state['active_experiment']
state['current_stage'] = 'Resumed; all native campaigns currently closed. Fixed new96 conditional model completed and independently checked: ordinary pair repair/MPC find protected mechanism improvement but actual online readiness is unproved. Receiver bound and immutable reference-vector benchmarks remain mixed and all>100ms. Dedicated JSON code-only worker is in pure-gate repair, no benchmark yet. Original graph recirculation bridge is only an offline relaxed path screen. Full-day throughput, full100ms and joint method effectiveness remain unmet.'
active['receiver_bound_status'] = 'Fixed24ABBA/768queries/24fullbaselines complete and independently reread. Total2427.4588->2400.102ms(-1.127%); median203.8136->205.5808ms worse; B125.9504-275.9841ms and0/12<=100. Per19299full+45prefix+48lower-bound rejects, all exact/strict. Fixed12-profile diagnosis found48 needless full-baseline copies; Dijkstra small and GC does not explain block1 regressions. No native protection.'
active['receiver_vector_status'] = 'New immutable five-time reference has56pure/192exact outputs and45pinned sources. Fixed24ABBA actual exit0 external9.560643s; totals2201.5563->2151.2165ms(-2.287%), median177.77965->179.15925ms worse. B115.503-247.1064ms,0/12<=100; all3block1 cases slower. Full baseline/setup/32/encoding charged; no benchmark rerun or further blind micro-tuning. Independent additional readback pending; in-worker full saved check passed.'
active['joint_protection_design_status'] = 'Frozen new003 fixed96 ran once, fullPython4.9430985s;47sources unchanged, all96 assessed conditional and all5jobs complete. Independent saved96 reconstructs Storage/loaded/empty/received/route ACK+edge and reservation-OR occupancy, all4method query orders and6 complete16-member references. Mechanism pair/MPC57.761 versus coordinate/fixed-initial/later-default60.061; all5 strictly non-worse. Known pair repair explains result; no novelty or original graph benefit. Later command8.69 precedes modeled receivedACK8.89; exact native/online admissibility under existing pending/capture guards must be resolved without retiming or weakening. All future readiness hypothetical; native certification false.'
active['original_recirculation_screen'] = 'Original graph/all28506/22trays/zero-capacity edge unchanged. From saved actual8-completion token42, offline greedy direct-only screen adds6 and stops at85; allowing one opposite-zone nonloader/nonStorage bridge per supply yields paths for remaining31 safe FIFO-prefix jobs with12bridges. This is not actual continuation of terminalcap8, not a time/capacity/native/online feasibility or optimum proof. All global heads are offline evidence. v2/v3 action rows omit tray/destination; must not infer them from IDs. New owner-local empty-arrival authority requires separate source review.'
active['json_prediction_worker_status'] = 'Separate JSON-only fixed-source-image worker, code-only startup guard cache, fresh dynamic snapshot/baseline/all32 each request. Pure001 failed5 cases due deep Windows fixture path and omitted src closure; firstfailure retained, in-process192parity passed. Repair in progress, no performance campaign/native. Root required full caller ledger tail and close/reclamation cost, separate bounded artifact serialization, and real timeout treatment. No perrequest full code inventory reintroduced.'
state['next_actions'] = [
 'Resolve frozen mechanism later-action online admissibility from accepted026 source and real capture/pending semantics; preserve8.69/8.89 discrepancy and all96 results. Only dispatch a bounded fixed native probe if source uncertainty requires one; no timing/parameter search.',
 'Finish JSON-worker pure gate after recorded first failures and full caller/cleanup cost corrections. Root source review and fixed120s ABBA RPC benchmark only after exact guards/isolation/version/frame/failure tests pass. Cold/queue/IPC/source initialization and shutdown remain visible.',
 'Independently close immutable receiver-vector saved results, then stop this mixed micro-optimization line without case gating or new profile.',
 'Review original single-token bridge authority and offline path screen. No implicit restart of terminalcap8, no opaque-ID payload inference; any new policy requires fresh declared owner-local protocol and pure gate before native.',
 'Keep original1x28506/2x57012,H86400,FIFO,capacity0,mandatoryStorage and originalR1false. Actual8completed is limited progress;39/371 are conditional necessary bounds, not achieved schedules. Full100ms, strict all-job protection and independent joint efficacy remain open.',
 'Preserve histories/failures and review material; do not commit,push or sendGPTPro without user instruction.'
]
active['pending'] = state['next_actions']
(DOC / 'RESEARCH_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')
intro = '''# 当前执行入口 — milestone020

用户“全面恢复”仍有效。当前没有运行中的native worker，所有总体标准不变。

固定96模型及独立复核已闭合：合成正例中pair repair/MPC得到57.761，逐坐标和两个完整强参考族60.061，五件均未变差；普通成对修复解释收益，不能宣称方法创新。后续改路8.69早于模型received ACK8.89，必须先核对实际在线准入，不能调时刻保住正例。

receiver-bound与五时间向量两次固定ABBA均是混合结果。最新总时间下降2.287%，中位数变差，全部B批115.503—247.1064ms；完整100ms未达标。独立JSON代码缓存worker仍在修复纯门，不曾跑性能实验。

原图实际仍是全天28506件中8件完成、3件按时。新离线筛查仅给出通过12次两段跨区中转连接剩余31个安全FIFO前缀任务的路径，未证明协议、时间或容量可执行。原cap8已终止，不能直接恢复它增加动作。

按序推进：

'''
(DOC / 'NEXT_ACTION.md').write_text(intro + '\n'.join(f'{i+1}. {v}' for i,v in enumerate(state['next_actions'])) + '\n\n证据根：`outputs/experiments/g31_ics_lt2_sustained_20261014`；最新注册`user_resume_20261015_001/milestone_020.json`。原026归档与live027继续分开。\n', encoding='utf8')
note = '''

## milestone020：固定96闭合，计算微调混合，新的原图路径筛查

固定96模型003首次且唯一执行exit0，整Python4.9430985秒。47源码未变，三组各32候选全部5件完成。独立审核0.5235秒、0新预测/0native，逐一检查动作顺序、Storage、载货/空盘路径、received和route ACK、目标边及预约发布OR占用；四方法查询顺序与六个完整16成员参考族重算一致。机制正例普通pair repair与有限MPC同为57.761，逐坐标和固定初始/后续default参考最佳60.061，严格五件无回归。该收益不是新求解器创新，原机场图没有改变。关键未决是模型后续命令8.69早于received ACK8.89，未来完整观察仍是假设；转入accepted026源码准入检查，禁止改变固定时间或容忍度维持正例。

更早receiver下界ABBA总2427.4588→2400.102ms，中位203.8136→205.5808ms变差，所有批次超100。一次固定profile定位48个证书不必要复制完整baseline；剖析下baseline复制累计286.975对35.877ms，Dijkstra累计14.594ms很小，不能把重叠profile类别相加，也不能解释无早剪枝block1退化。新独立五时间不可变向量56纯测/192输出精确，45源码绑定；实际24ABBA和保存核验整Python9.560643秒，总2201.5563→2151.2165ms下降2.287%，中位177.77965→179.15925ms变差。B115.503—247.1064ms、0/12达标、三block1均更慢。封存混合结果，不按case挑选或继续盲调。

原图路径筛查使用accepted026归档、实际cap8全28506状态与39安全FIFO前缀。direct-only贪心可再连接6件后到85，加入一个非loader/Storage的异区中转节点可连接剩余31件，需12次中转。只证明松弛正容量路径和端点许可，不证明原生路由、动态容量、时限或在线消息。v2/v3不公开transfer的tray/destination，不能由opaque ID猜出；原单盘UNLOAD receipt permit不能自动覆盖空盘中转到达，新的接管条件待独立源码审查。实际8件与39/371条件上界不混淆。

过程中根预检两次在执行前停止：原生artifact键使用Windows反斜线，改为Path生成精确键；独立预检作为额外__main__被动态inventory正确拒绝，复核器仅明确单列自身哈希后比对45个正式源，实际launcher原guard完全不变。JSON纯门001另有Windows深路径/遗漏src依赖5失败，保留原失败修复，不是性能运行。后续worker必须计caller记录尾部、cleanup与RPC，不把文件总artifact误用2MiB单帧限额。所有实际失败/成本及unknown保留。
'''
with (DOC / 'RESUMPTION_20261015.md').open('a', encoding='utf8') as f: f.write(note)
with (DOC / 'NOVELTY_LEDGER.md').open('a', encoding='utf8') as f:
    f.write('\n\n## 50. 合成联合保护障碍通过模型复核，在线时序仍未通过\n\n固定96在一正两负输入上完成。正例57.761优于逐坐标及两完整参考族60.061，但已知pair repair也达到同值，不能提出求解器新颖性。后续改路先于received ACK，真实在线可执行性仍待证。原图两段跨区路径筛查只说明可研究的单盘策略扩展；不改变39/371条件界，不产生全天吞吐证书。两轮receiver微调净收益小且中位退化，不属于联合方法证据。\n')
with receipt.open('x', encoding='utf8') as f:
    json.dump({'schema':'g31.resume_milestone.v1', 'recorded_utc':datetime.now(timezone.utc).isoformat(),
               'immutable_evidence':pins, 'before_sha256':{n:sha(backup/n) for n in names},
               'after_sha256':{n:sha(DOC/n) for n in names}, 'parent_user_file_sha256':sha(parent),
               'overall_goal_achieved':False, 'new_native_dispatched_here':0}, f, ensure_ascii=False, indent=2)
print(json.dumps({'state_updated':True, 'milestone_sha256':sha(receipt)}))
