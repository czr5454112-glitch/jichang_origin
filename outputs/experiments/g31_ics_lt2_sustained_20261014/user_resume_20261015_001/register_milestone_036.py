from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'live_lazy_six_profile_prepare_001/report.json':'ca2c4e875ef32600aaf861a892ef115f8ae874d033d71f435fba94978d9b135d',
 'live_lazy_six_profile_prepare_001/external_application_wall.json':'c68f54511aad5a2bbd799f59d608328a004687d8182481b501c8d7b4b1a5ee8e',
 'scoped_public_inputs_six_cost_prepare_001/report.json':'f6c8c0ebda0a87d727196bd9afffda795b0267fd492a6e9679ea5a3204fd0f55',
 'scoped_public_inputs_six_cost_prepare_001/external_application_wall.json':'3faeae996f772f4ed88a02981e3f2fcb39b99b7d082118414fc55b4107d436c4',
 'scoped_inputs_saved_review_prepare_001/report.json':'02e5feaafbada1f2879518e7412bccbaddeb5a636f3d999d2c32785574ccfe52',
 'scoped_inputs_saved_review_prepare_001/external_application_wall.json':'fbae0d3cd896ca93e565fb3c2e24a73f1ed06ef70ec10a1a0cf7a864ab614b00',
 'planning_v2_digest_prepare_002/result.json':'79d1f44742232a5ba46ecf967d84b602da95a03dfed48daaaae1d680a5e7ddce',
 'planning_v2_digest_prepare_002/external_application_wall.json':'fb6754615e3184ac6f934bcaaebbaed0472f9ac0530a6ed1803bbe8ca93a6c59',
 'initial_owner_route_single_capture_campaign_prepare_001/campaign.json':'5ac870bdd01f09eefdf4b5e552238abc3a730745daeb04590acbb6ac3a539ddc',
 'initial_owner_route_single_capture_campaign_prepare_001/verification.json':'f8255ca3e9a6a989221c4c13673bebe195e9e3b1dfdee624435c9a4b1912fe6a',
 'initial_owner_route_single_capture_campaign_prepare_001/external_application_wall.json':'e4cdca415f71af162649e1e8d9bfd1973989d04c290ad04ca7b5ce05f3534e5b',
 'user_resume_20261015_001/single_capture_changed_choices_readback_001.json':'c42f84691be2d00c23246e56bf14ee7505adce9785d92957e52710f9b40e4809'}
for p,d in pins.items():assert sha(OUT/p)==d,p
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_036';backup.mkdir(exist_ok=False)
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());active=state['active_experiment']
state['current_stage']='Fully resumed, all3 goals unmet. Fresh per-prediction public inputs passed6ABBA24 and independent saved24; model median356.3493to127.83865ms, stillabove100. Actual18 singlecapture passed complete failure-aware audit16closed2unknown0under100. Originaldigest32 hotspot measured; newbatched writer75pure only. Full96 scoped and future-later fork validation preparing; no overall/native full32/joint efficacy certificate.'
active['scoped_public_inputs']='Current lazy fixed6 cProfile passed whole16.7201899/120;44/55 repeated inputs construction calls per prediction. New fresh request-local public3input scope retains every guard and fresh deepcopy per read, original model code/context class and fullglobals.16pure, then fixed6 ABBA24 passed whole11.5947326/120: all24 complete output bytes/typed/floathex/chronology exact,12A/12B,median356.3493to127.83865ms(-64.125466%),all6paired improve. Independent saved24 reader49pure and actual readback passed whole1.9026381/120,report02e5feaafbada1f2879518e7412bccbaddeb5a636f3d999d2c32785574ccfe52. DefaultGC,scope cycles may be collected after sample return; source-only save-before-target proof,no runtime target-read journal. No full96/full32/complete100ms claim yet.'
active['single_capture_actual18']='Campaign190sources/67compiled,27campaign+117verifier pure passed; native027 actual18 whole165.8442781/600,oneworker. Saved passed_saved_with_complete_unknown_denominator,16closed2unknown,0invalid/error,8RPC;normal6all5strictprotected,2improve4equal. Closedroot434.0144–975.6799ms,median631.84315,0under100. Predictorstartup757.7453ms,close230.664ms separately retained. No C normalizer orscopedmodel combined. Receipt afae7a01523600a83aab92bfb6cec8c427abe93c3d23c88c80a7a6d30f5841b0; verificationf8255ca3e9a6a989221c4c13673bebe195e9e3b1dfdee624435c9a4b1912fe6a.'
active['single_capture_choice_timing']='Four changed historical choices read from8raw: same predictor snapshot and baseline prediction in everypair; worker prefers2 inboth runs, but caller return crosses original60ms cutoff. block0load1/2 new replies51.6037/57.3286vsold70.3434/67.6706;block1load0/1 new62.3595/63.0816vsold57.9071/59.1428. Postdecision final revalidation remains separate. No causal ABBA speedup or full getter-effect equivalence inferred from these separate native runs; wholeclosed median didnot improve.'
active['planning_v2_digest_attribution']='Original32calls/2actualqueryrows/8ABBA batches/4profiles passed whole26.0628415/120. Aoriginal median perrow28.79885/49.98325ms;Bsameoriginal+cProfile,notoptimization. Original local typed writer ~98.5–99.1%instrumented cumulative,SHA~0.6–0.7%. Diagnostic own guard/check median477.18765/723.15075ms is not production policy guard. No600-policyfrequency or closure attribution. Batched numeric writer75pure passed,actualfixed2cost pending; no newfullbridge rerun.'
active['single_capture_integration']='Actual18 source153/integration59pure+endpoint89+failure-aware117+campaign27 gate nowcompleted as separate frozen190source campaign. Endpointfailed/missing/invalid/auditerror stayin3slot/18row denominator;RPCfailedsubtotals excluded. Sourceproof first marshal instability andfixturepath errors preserved; verified unknowns never upgraded. See single_capture_actual18.'
actions=[
 'Finish and review scoped full96 candidate source/pure/prepare; execute one originalshared360 conformance only after review. Same96fixedactions,allguards/226later/192known,fullold96 outputs,earlysave-before-return; partialcalls remain unboundordinal and unknown.',
 'Review batched typed-v2 writer75pure and fixed2actual ABBA plan. Allbytes/IEEE/uint64/text/order/customhook/exception fallback semantics and preflight costs retained; no optimistic fullbridge600 extrapolation.',
 'Finish future-only later-action fork focused pure and fixed6 paired-suffix plan. Old sameaction API unchanged,strict known/current phaseB and pastaction guards; no opaqueIDrelation/actual observation filter orhiddenstatecoverage claim.',
 'Complete-request100ms remains434–976ms for16closed native roots. Preserve60ms decisionreturn cutoff and100ms deadline; optimize real overhead, never borrow postdecision time or omit output/cleanup costs.',
 'Full original all28506offered bridge600 audit remainsfailed. Accepted39 completion proof stillrequired beforelawful completion-baton rollout; preserve all normalprotection/failures/topology/FIFO/trays.',
 'All3 overall goals remainopen. Record failures and negative cases forlater user-commanded GPTProreview; no external send/push/commit.'
]
state['next_actions']=actions;active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone036\n\n全面恢复继续有效，三项目标均未达标。六输入模型ABBA中位改善64.13%并经独立保存结果复核；实际18请求仍0个达到100ms。全天原流复核仍未完成。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone036：公共输入作用域提速、真实18仍超时限、摘要热点已定位

当前lazy模型六输入profile全部精确通过（whole16.7201899s），发现每预测重复构造3个公开固定输入44或55次。改为每次预测新建私有scope，所有读取仍返回完整deepcopy、全部原guard及model代码保留，没有缓存端点/判断/预测。16pure通过；固定6×ABBA24实际完整输出均精确，whole11.5947326s；12A中位356.3493ms，12B中位127.83865ms，减少64.125466%，六组均改善。独立保存复核49pure及实际24/6读回通过，whole1.9026381s。仍全部B超过100ms；自然GC保留但scope循环可能在return后回收，不能称每样本完整cleanup。先保存再读target仅有冻结源码证据，未伪称运行时读日志。全96候选尚在准备。

singlecapture实际18已跑完（whole165.8442781/600，1nativeworker，190源码/67编译源；117验收pure及27campaign pure）。原生027完整H40/all5检查，16闭合、2故障未知、无invalid/auditerror；正常6pair全部逐件保护，2改善4相同。闭合根434.0144–975.6799ms，中位631.84315ms，0个100ms；启动757.7453ms、关闭230.664ms单列保留。没有合并C normalizer或scoped模型。完整失败验收保留三端点槽与18分母；失败RPC不算已验证预测。

新旧4个选择变化的8raw只读核查：同snapshot和基准预测，worker均推荐prefer2，caller是否在原60ms决策截止前返回决定回退。block0load1/2新51.6037/57.3286ms、旧70.3434/67.6706ms；block1load0/1新62.3595/63.0816ms、旧57.9071/59.1428ms。最终重读在决策后，不能混入决策预算。历史两次运行不是ABBA，完整请求中位未改善，不能宣称单采集整体收益或完整query副作用等价。

摘要诊断2实际query×ABBA32原函数调用完成，whole26.0628415/120。两row原digest中位28.79885/49.98325ms，profile主要在typed字段writer，SHA只约0.6–0.7%；B只是原函数插桩。诊断自身全body守卫477/723ms不是生产policy守卫，不外推600秒全天。初次prepare因误设extension schema失败保留；新v2严格按实际g31.planning_extension.v2。新批量numeric writer75pure通过，实际对照尚未执行。

future-later fork新62pure第一轮56pass/6fail已保留，原因是scalar误传只接受dict的原encoded；按整past-field dict修复再检，不放松旧sameaction API/known/currentcut标准。全96、后缀分叉、批量digest对照准备中。三项目标未达标，无GPTPro外发、无推送提交；父目录用户C++文件不变。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 66. 局部模型提速有独立证据，完整请求与联合方法仍未达标\n\n每预测新公共输入scope在6×ABBA24中位改善64.1255%，独立24完整输出复核通过；这是执行成本改进，不是方法新颖性。singlecapture实际18保留16闭合2未知、正常逐件保护，0个达到100ms；60ms决策返回边界仍造成选择变化。digest32仅定位typed writer热点。全96新候选与未来动作分叉未验收，全天600失败继续有效。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'root_sessions_active_at_checkpoint':[],
 'new_native_branches_since035':18,'external_messages_sent':0}
with (HERE/'milestone_036.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_036.json')}))
