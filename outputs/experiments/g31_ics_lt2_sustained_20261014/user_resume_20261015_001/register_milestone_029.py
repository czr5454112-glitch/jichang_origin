"""Record independently verified historical94/2 and preserve both audit failures."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE.parent;DOC=ROOT/'docs/g31_ics_circulation'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
pins={
 'live_obligation_historical_terminal_summary_001.json':'b122bd70d657a6641f0812c401b0c88a6998e5560949c207b597962058ba04c0',
 'live_obligation_historical_native_saved_review_001.json':'3ea06f5867e916bca10936c28134003e91a8cd0b0cb1f41b3a93c1eaa3321728',
 'live_obligation_historical_native_prepare_001/preregistered_protocol.json':'bc3bc04e8c81e496120cfd7760e83c6274bd7e92f287fe68ba8d1e206737fcd5',
 'live_obligation_historical_native_prepare_001/receipt.json':'145e96e33a39fd3a1dea29f4163babf11c5fc48911db45c82cc9740beb14903b',
 'live_obligation_historical_native_prepare_001/external_application_wall.json':'c56a630b1fa7ad34f0799967ed3a6e28260b5767f2cb41c0b292c95c2d83a0f4',
 'bridge_saved_audit_terminal_review_001/report.json':'2d90e03051f13a8f1095e68a03d495bde4d2e1239e8b00a20eedf6e90b1d65bd',
 'bridge_saved_audit_terminal_review_001/optimization_design.json':'1eb48b626084d8193577a874e7c8a6c2f70fd82f7c760bf894dc111f30f51ff0',
 'action_dependency_diagnostic_001/report.json':'16b70d834bf9e957a38a0796ed18556ce741747e71c337b63bc22b0480b4b685',
 'historical_online_method_requirements_001.json':'75f7e6013971a88c463856eaab4f7fe3f716f0562470a0ef96f2c93c5901dd04',
}
for p,h in pins.items():assert sha(OUT/p)==h,p
summary=read(OUT/'live_obligation_historical_terminal_summary_001.json')
assert summary['status_counts']['assessed']==94 and summary['complete16_families']==5
assert summary['physical_counts']=={'full_H40':96,'all_five_complete':96}
assert summary['independent_replay_errors']==0
for ref in summary['references'].values():assert sha(ref['path'])==ref['sha256']
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup=HERE/'before_milestone_029';receipt=HERE/'milestone_029.json'
assert not backup.exists() and not receipt.exists();backup.mkdir()
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
state['current_stage']='Fully resumed. Fresh historical-own-ACK native96 completed within600 (whole262.6999121s), independently audited:94assessed/2unknown,96fullH40/all5 complete,0 replayerrors,5/6 complete16 referencefamilies. Mechanism25 protects all5 against both complete family best12, completion-sum gain2.3000000000000114. This is a fixed-action finite mechanism, not an online solver or whole-airport efficacy. Separate full-day saved audit600 also timed out with no full certificate; instrumented equivalent audit optimization is being prepared. Actual18 one-build plus observation gate integration remains unexecuted. All3overallgoals remain unmet.'
active['historical_service_support']='Fresh actual96 independently verified94/2; old80/16 remains frozen.14 newlyassessed use deciding-owner own delivered selfACK on firstcollection (E4/P10), no fabricated terminal facts;32actualfresh pairs allverified (B28/A4).224collections190known34unknown. Actualold→new completions89exact/7different. All96 H40/all5complete is distinct from informationassessed. insufficient_advance/vector16/17 remainunknown across unloading; no missing-family promotion.'
active['historical_native_comparison']='5of6 complete16families. Mechanism32complete optimum25 sum57.76099999999998; bothfamilybest12 sum60.06099999999999; exactperjobdelta loaded-0.9999999999999991,receiver-1.0999999999999979,reuse1/reuse2-0.10000000000000497,blocker0. Vector24 blocker+0.7999999999999954 rejected despite aggregate gain. No_overlap32complete/default00 best58.711999999999996; insufficient30/2, laterdefaultfamily15/16 andfull32unknown. Offlinefixed actions notonlineMPC/LNSnovelty.'
active['bridge_saved_audit_status']='bridge_serialize_saved_audit_prepare_002 separately failed at external600.2022067s. Onlystage_started; no report/failure/all_job_states or stdout/stderr content; exact stuck stage unknown.84live/archive unchanged in0.131s smallterminalreview,0raw/APIdecoded. Source exposes duplicate1.34GB rawparse, doubleAPI resultcopy, oldprefix dualencode. New version source-only implements single local shareddecode only afterreadonly proof, keepsactorcopy, removesobservercopy, exactordered comparator and boundedstage progress. All37270+27218hash/args/policy/physical/FIFO/Storage/cap/28506denominator remain. Original2400 andseparate600 failures immutable.'
active['action_dependency_diagnostic']='A bounded5.265s pure6x32 diagnostic instrumented four semantic actionreads with exactrestorable runAST, retainedconstructor emptydeparturedependency; independently ran192full+192cut predictions and6baselines. Existing93strictcuts remain; only10priorclause reuses possible,allcase0,otherfive0. Allhypotheticalmatches exactwitness andfulloutcome verified. No implementation/cache/native/benchmark/100msclaim. Do not prioritize this narrow potential or repeat failedstate-prefix cloning. Prior art links retained; no noveltyclaim.'
actions=[
 'Complete source/pure/frozen preparation and root review for instrumented equivalent saved-only bridge audit; execute at most one fixed600 attempt after readiness. Keep allhashes/ordered actualargs/physical guards and both historical timeoutfailures. No finalwriter change mixed in.',
 'Complete actual18 one-build evidence plus actual notification/outbox gate, preserve .05 background/activationIDs/firsthop and all18 faultrows. Review full source/pure before exclusive native timing window; current actual18 remains16closed2unknown0under100.',
 'Investigate only the two remaining unloading-transition raw endpoints for actual delivered terminal facts or a justified observation contract. Do not fabricate UNLOAD_COMPLETE, loosen epsilon, add endless retries, or rerun96 merely to fill a family.',
 'Prepare source-level predictor/information conformance for actual historical communication policy and fair online coordinate/plateau/pair-repair/MPC/LNS comparisons. Sameinformation/domain32/budget32 and phaseB<=4, protected deployment, allfive actual receipts; fixed finite optimum is not online solver superiority.',
 'Separate firsthop realEDGE_ENTER entryprefix[0] fix from current gate because earlyrootclosure changes backgroundIDs; full32typed port and finalwriter remain separately scoped. Threeoverallgoals unmet; no commit/push/externalmessage/GPTProsend.'
]
state['next_actions']=actions;active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone029\n\n全面恢复持续有效。新实际96已独审94/2、五个完整16参照族，机制25相对两完整族最优12逐件不恶化、总完成时间改善约2.3秒。它仍是有限固定动作证据。全天600独审再次超时，完整请求100ms及在线强方法目标仍开放。\n\n'+'\n'.join(f'{i+1}. {x}' for i,x in enumerate(actions))+'\n',encoding='utf8')
note='''

## milestone029：实际94/96与完整机制参照成立，全天独审600失败继续保留

fresh historical own-ACK固定96原生运行262.6999121秒完成（91冻结源、82纯门、600整体预算）。新独立saved审计外Python43.685081秒/owned worker42.85073秒，小于180秒；195入口/出口pins一致，0重放错误。94assessed/2unknown；全96到H40且五件物理完成。旧80全部保持、旧16中14变为assessed，2仍unknown；这是新实际结果，不重写旧80/16。14次历史服务证据全部在首次采集使用（E4/P10），决定者B自己的已送达ACK与不可变发布历史，无历史服务失败；另32次实际补采全验证（B28/A4）。224次采集中190known/34unknown。与旧实际终态比较89完全相同、7至少一件改变，因此未把旧纯模型94/2冒充新执行。

六个完整16成员参照族中五个成立。mechanism全部32可评估，最优25合计57.76099999999998；固定initial-native-default族及later-native-default族各16均齐，最优都是12合计60.06099999999999。25相对12的逐件差：blocker0，loaded约-1，receiver约-1.1，reuse1/reuse2各约-.1；严格全五件非恶化，合计改善2.3000000000000114。负消融24虽然总和更好却使blocker约+.8，保护规则拒绝。no_overlap全部32/两族齐，默认00最优58.711999999999996，没有强造联合增益。insufficient_advance仍30/2，vector16/17卸载跨界缺合规终态事实；later-default族15/16及full32最优保持unknown。固定动作反事实执行不是online优化器，更不是新solver优于MPC/LNS的结论；新strong-method要求明确同信息、同32预算、后期至多4、暂时不保护提案可被强方法搜索但部署仍严保护。

全天另行saved-only600审计也超时：外600.2022067秒，仅有stage_started，无report/failure/all_job_states及stderr内容。小终态审0.131秒核实84live/archive不变，未重读raw/API。具体卡点未知；源码确认外内两次解码约1.34GB最终raw、每API双deepcopy、旧27218前缀双JSON编码及巨大owner规范化。新版本正实现有界进度和等价减少重复开销，保留全部37270新hash/27218旧hash、实际参数有序校验、policy/physical/FIFO/Storage/cap及28506分母；不扩大600、不掩盖原2400失败、不升级39/H证书。

补做一个5.265秒有界纯诊断，研究严格完成反例之前尚未读取的动作字段是否可形成同context复用条件。四个run语义读取点完整AST可还原，constructor empty_departure依赖保留，每6x32候选分别完整预测及带观察cut预测。原93个strictcut中仅10个有先前同依赖反例，全部集中case0，其余五case为0；所有假设复用反例与独立完整预测精确相同。这只是狭窄潜力，未实现cache/online算法，未测加速，不优先再做前缀共享微调。参考依赖回溯与动态依赖文献（报告内链接）是既有方法，不宣称新颖。三个总目标均未达标，持续推进。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 59. 五个完整有限参照族与保护机制证据，不冒充在线方法优越\n\n新actual94/2及mechanism25对两complete16族best12的全五件严格非恶化、约2.3总时间改善已独审。负消融24的blocker+.8仍拒绝，no_overlap默认最优如实保留；insufficient两未知不补造。该结论是有限固定动作协同机制，尚非在线MPC/LNS优越或全天业务结果。动态动作依赖仅10/192潜在复用，且属于既有依赖/记忆化思想；不把它包装成solver创新。全天600审计失败及完整请求100ms失败不改。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},
 'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),
 'overall_goal_achieved':False,'new_native_dispatched_here':0}
with receipt.open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt)}))
