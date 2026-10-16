from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'C_publisher_pair_prepare_001/report.json':'19f4c29ce1f5ffa1897a3ccab62b3e1d522714c873adb5819f0863f902624f01',
 'C_publisher_pair_prepare_001/external_application_wall.json':'b0f515ce77c809c182435bbe8946783fc99a9f6c56cfb9db7811ddf653a59047',
 'C_publisher_saved_review_prepare_001/report.json':'b30aad460157f09bfa32d5482a3da1b027c3072b7e284a5b3fff4096c287ca72',
 'C_publisher_saved_review_prepare_001/external_application_wall.json':'ad58b0057af2afb15e1c3fe02ff2a7ae952c1da57d27a8a80475f581ccab0ba1',
 'conditional_continuation_six_prepare_001/receipt.json':'30ab6972140d8411d8c9d301c6d1690906112a18e350c7dccb2811b31e8705db',
 'conditional_continuation_six_prepare_001/external_application_wall.json':'8988784c696dce2c9f9682a9a63583891281c48e97601ebc442187d0068fa40d',
 'bridge_copy_scopes_cost_prepare_001/result.json':'64e8d19f4b87c1440db576fd33f782463b4bd5d73adcff4fb66c93fd415bb0ae',
 'bridge_copy_scopes_cost_prepare_001/external_application_wall.json':'a0be27af7815b45c1f09625394b2b52ff29e8b03de4d7f00c7d762c7ef027133',
 'initial_single_capture_integration_source_prepare_001/plan.json':'b3043d1fc5170da7aa1a139fb0479c8d4f5134a6d3d7c174849482de1cfa81d2',
 'initial_single_capture_endpoint_source_prepare_001/plan.json':'ecc78936817d981eb7818e8edc79cade55a1618b159fb023d77b38e2d05e85b8',
}
for p,d in pins.items():assert sha(OUT/p)==d,(p,sha(OUT/p),d)
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup=HERE/'before_milestone_035';backup.mkdir(exist_ok=False)
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());active=state['active_experiment']
state['current_stage']='Fully resumed; all3 goals unmet. Complete C publisher18ABBA72 and independent saved72 review passed; real6 fourframe same-action continuation passed; private copy scopes synthetic256 passed. Singlecapture integration59pure and endpoint89pure passed; full failure-aware verifier preparing. Current lazy-model fixed6 profile and typed-v2 digest cost attribution preparing, not executed.'
active['normalization_c_helper']='C publisher72 actual-entrycodec18 mock ABBA passed whole76.6456392/240. A36 median196.6025ms B36 median133.77485ms (-31.95668926%), sum-28.54788562%; all18paired B better. Direct18supported preflight11.9601658s included whole. Complete original clocks/codec/hashledger/return retained. Independent author saved72/18 readback passed whole41.6834004/120, reportb30aad460157f09bfa32d5482a3da1b027c3072b7e284a5b3fff4096c287ca72; original145/169/135+6124toolchain/runtime/raw guards,147auditor sources unchanged. DirectC/alias facts remain producer attestation; independent0Cload. Historical16closed2unknown retained. Mockunder100 A10/36 B12/36 is not complete native100ms or full32.'
active['rolling_conditional_continuation']='Fourframe same-action real6 passed whole18.6451326/120:6initial engines/6advances,14cuts,14main+25suffix resumes=39,14retention+14suffixforks=28,20terminal outputs saved before targetreads/later audits. All6 exact,unknown0;14suffix paths/point metadata/full modelgraphs exact to main, no prefixrestart. ActualopaqueIDrelation/observationfilter/hiddenstatecoverage and changed-action continuation not established. Saved graphdigest does not independently reprove runtime aliases.'
active['bridge_private_copy_scope_cost']='Synthetic64jobs/16revision,2families ABBA32each=256calls/8batches passed whole50.0943897/120. Discardrefresh isolated1632.44195to1070.58470ms(-34.418207%),whole6200.8101to5557.0864(-10.381284%). Temporaryowncapture isolated90.93545to28.1534(-69.040237%),whole3190.7188to3074.16625(-3.652862%). Original retainedclientview/ACK/retry/query/index/guards and PossessionGate durablecopies remain. Synthetic gain cannot extrapolate to raw replay or add to prior gains. Fullbridge600timeout remains; no newfullrun dispatched.'
active['single_capture_integration']='Source153pins59pure passed whole10.5754857/120; sourceplanb3043d1fc5170da7aa1a139fb0479c8d4f5134a6d3d7c174849482de1cfa81d2. Same freshwrapper Ainitial/Afinal/B, nativechainMRO/exacttype retained. First56/58failure preserved: marshal codehash referenceflags unstable, replaced deterministic typedcode fields; bytes-test assertion fixed. Endpointdispatch131pins89pure passed9.8197/120: unique actualimmutable planningcreation IDs, explicit attemptenvelope, all3slots/missing/invalid/auditerror preserved; oldsuccess checker unchanged. B incomplete/rawfailureNone/reportedclosed counterexample certifiesunknown. Full branch/saved verifier inprogress; noactualcampaign/native/performance here.'
actions=[
 'Review complete failure-aware branch/saved verifier and pure source package. Then prepare one actual18 singlecapture campaign retaining every row, original physical/RPC/root/query/lifetime checks, reported facts separate from certified root; no unknown promoted.',
 'Review and run bounded current-lazy fixed6 cProfile diagnostic with complete savedprediction equality,0native. Use measured self/cumulative call evidence to choose next optimization; overlapping cumulative costs never summed.',
 'Investigate typedv2 digest direct cost before considering data-only C bytewriter. Source loops are a hypothesis, not measured hotspot. Preserve every digest byte/type/order/guard and failure semantics.',
 'Fullbridge600 failure remains; local synthetic gains alone do not justify blindrerun or limit extension. Obtain measured relevant cost and retain all28506 offered/normalprotection/failures.',
 'Extend legal retained-cut work toward evidence-constrained opaque-ID relations and actual delivered observation filtering;6sameaction examples are not hiddenstatecoverage or fair joint efficacy.',
 'Overall goals unchanged: all-day original stream strict normalprotection, full32 complete request100ms, fair strong-online jointmethod efficacy. Preserve history for later user-commanded GPTPro review; no send/push/commit.'
]
state['next_actions']=actions;active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone035\n\n全面恢复继续有效，三项目标均未达标。C完整发布环节72次对照及独立读回通过；六输入四帧续演通过；两处复制优化只有合成数据收益。全天复核仍未完成。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone035：发布计时独立核验、四帧真实续演及副本成本

C完整publisher18输入×ABBA72通过，whole76.6456392秒；A36中位196.6025ms、B36中位133.77485ms，减少31.95668926%，18配对全改善。实际C支持预检18包含在whole，默认GC，原codec/严格decode/hashledger/return全部保留。独立作者saved-only读回whole41.6834004秒通过72完整记录/18原fixture/36每臂统计/全部负例分母/时钟，145/169/135与6124工具链/运行库原守卫保留；直接builtin及容器alias事实仍是生产者观测，独立未加载C。历史16closed2unknown保留。不是完整native100ms，full32未做。

四帧same-action真实6通过whole18.6451326秒，14cut、39resume、28fork、20terminal提前保存，6exact0unknown；14独立后缀与主路径完整图/预测一致，无prefixrestart。尚无真实opaqueID关系、收到观测筛选、隐藏状态覆盖或联合在线有效性。

副本优化合成64job/16revision固定256调用通过whole50.0943897秒。discardrefresh调用span约快34.42%，整批约10.38%；临时owncapture约69.04%，整批约3.65%。保留client_view和PossessionGate持久拷贝及全部guards；收益不可相加/外推全天。全天复核600超时原件继续有效，不盲跑。

singlecapture私有接线59pure和端点89pure通过。首轮56/58失败原件保留：marshal code hash受引用状态影响，改显式typed code字段确定性编码；测试bytes先独立比较。接线保留A最终重读和B包装器，sourceproof不误取原函数源码。端点从真实immutable calls/outbox唯一创建绑定ID，显式branch envelope，malformed留invalid，资源错误留audit_error，缺失与失败不缩分母；B incomplete/raw.failure=None时保留reportedclosed物理事实但certifiedunknown。完整验收接线尚在准备，无本轮实际native。

继续当前lazy模型六输入profile及typedv2 digest归因准备，尚未执行或假称瓶颈。未外发GPTPro、未推送/提交。父目录用户C++文件校验不变。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 65. 完整发布优化与真实续演通过，仍无整体达标证据\n\nC发布72对照中位改善31.9567%且独立72读回通过；六输入四帧sameaction续演通过。复制scope合成256仅支持局部收益。单次采集59pure及失败分派89pure通过，完整失败验收与实际campaign待做。无完整100ms/full32/隐藏状态覆盖/全天证书，所有失败和分母保留。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,
 'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'root_sessions_active_at_checkpoint':[],
 'native_dispatched_here':0,'external_messages_sent':0}
with (HERE/'milestone_035.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_035.json')}))
