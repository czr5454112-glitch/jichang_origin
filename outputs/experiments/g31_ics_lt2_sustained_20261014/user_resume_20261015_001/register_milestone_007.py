"""Register completed v3 runs and verified chained reconstruction, once only."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
HERE = Path(__file__).resolve().parent
DOC = ROOT / 'docs/g31_ics_circulation'
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

report = HERE/'milestone_007.json'
backup = HERE/'before_milestone_007'
assert not report.exists() and not backup.exists()
delivery = read(OUT/'native_preexisting_v3_run_delivery_prepare_001/receipt.json')
business = read(OUT/'native_preexisting_v3_run_business_001/receipt.json')
parity = read(OUT/'native_preexisting_v3_run_delivery_001_parity.json')
diagnosis = read(OUT/'native_preexisting_v3_run_business_001_endpoint_diagnosis.json')
reconstruction = read(OUT/'full024_chained_2x_20261015_001/reconstruction.json')
heartbeat = read(OUT/'full024_chained_2x_20261015_001/heartbeat.json')
assert delivery['branch_count']==9 and delivery['branch_status_counts']=={'readiness_observed':9}
assert business['branch_count']==60 and business['branch_status_counts']=={'assessed':10,'unknown_incomplete_or_unexecuted':50}
assert all(r['source_changed']==[] and r['source_closure_changed']==[] for r in (delivery,business))
assert parity['status']=='exact_nine_raw_equal' and parity['excluded_fields']==[]
assert diagnosis['later_decision_count']==120 and diagnosis['native_executions']==0 and not diagnosis['native_business_verdict_changed']
assert reconstruction['status']=='verified_against_known_native_seal'
assert reconstruction['native_state_sha256']=='4fd9d542bce156aff6e0cf85bcc293d50fd531e90c18c1f48527fcaeedab4e2f'
assert reconstruction['parts']==397 and heartbeat['physical_time']>=64800
names=['native_preexisting_v3_run_delivery_prepare_001/receipt.json',
       'native_preexisting_v3_run_delivery_001_parity.json',
       'native_preexisting_v3_run_business_001/receipt.json',
       'native_preexisting_v3_run_business_001_endpoint_diagnosis.json',
       'full024_chained_2x_20261015_001/reconstruction.json',
       'user_resume_20261015_001/route_rejection_summary_correction_001/receipt.json']
evidence={name:sha(OUT/name) for name in names}
files=['RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md']
backup.mkdir()
for name in files: (backup/name).write_bytes((DOC/name).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
active['chained_resume_status']='full024_chained_2x_20261015_001 verified397-shard original024 H64800 seal4fd9d542...ab4e2f; reconstruction1904.4055785s plus prior294.1024068s and excluded-tail costs retained. Actual continuation active under original7200s cap. Current tail without a saved seal is not a new native checkpoint.'
active['planning_v3_status']='Run acceptance preserves539 file pins and full44+21 entry/exit validation. Actual9delivery17.6850005s, decoded raw exactly equal toold003 with0excludedfields. Actual60business120.7778219s:10assessed/50unknown; allsourceclosureunchanged.120latercollections returnedearly because client request ID was compared to native message ID. Offline corrected endpoint-binding replay only; no historical native business verdict upgraded. New isolated adapter/runner and negatives being prepared.'
active['regional_path_cache_candidate']='Candidate2 exact-key bucket lookup once perhandle;52pure passed. Puremicro003 faster on repeatedfacts but slower on uniqueoccupancy; both retained. Separate bounded600s paired026 original-cut driver/verifier under review, not yet actual. No full-request100ms claim.'
state['current_stage']='Original1x full-day negative audited;2x knownH64800 native seal reconstructed and continuation active. LowWIP005 one original actual completed/empty token established; new second-supply invitation gate being prepared.027 v3 actual60 yields10assessed/50unknown; endpoint ID mismatch diagnosed without rewriting failed results. Corrected adapter and exact regional-cache native pair pending. All three overall requirements remain unmet.'
state['next_actions']=[
 'Continue same024 2x after verifiedH64800 seal within original7200s; at most2 native workers and49 frozen source identities preserved.',
 'Run separate same-token second-supply gate after true delivered completion selfcopy/current ownempty and fresh peer FIFOhead; preserve firstphase API/all28506/22trays/600s cap.',
 'Correct independent v3 adapter command-to-endpoint-to-ACK.result_id-to-capture.message_id identity; preserve age,action-union,current-view and unsupported-state guards. Run fresh9 then60 within180s. Keep old60 unknown verdicts.',
 'Continue route-preference model correction against actual shield dispatch and equally informed strong references. Updated preference ACK is not an edge reservation; retain45initial+5later rejections and14mismatches.',
 'Finish independent cachepair review then two fresh026 sessions replay original10shards toknownseal, each1000activations with exact ordered API/ACK/state/endseal,600s total; diagnostic fork explicitly distinct from maincut.',
 'Record actual results/failures/source identities and perform current zero-skip regression at coherent source freeze. No commit,push or GPTPro send without instruction.'
]
active['pending']=state['next_actions'];write(DOC/'RESEARCH_STATE.json',state)
nextdoc=(DOC/'NEXT_ACTION.md').read_text(encoding='utf-8')
start=nextdoc.index('## 最新执行次序');end=nextdoc.index('## 恢复初期队列')
new='''## 最新执行次序（milestone007）

1. `full024_chained_2x_20261015_001`已实际重建397片并匹配H64800原生seal `4fd9d542...ab4e2f`，重建1904.4055785秒；正在续跑。既有294.1024068秒祖先重建、被排除尾部和历史控制/导出成本保留。7200秒原上限、最多2个原生worker、024来源冻结不变。
2. `original_low_wip_prepare_005`实际133.534547秒完成：22次跨区停车、1次供盘、job2真实UNLOAD/HOLD后同盘返空，10305条API独立回放通过。完整28506输入保留，H22200实际到达3998件。下一独立实验通过返空邀请和送达的当前队首消息选择第二次供盘；尚未证明第二次复用、逐件保护或全天有效性。
3. 1×全天保存证据审计通过：H86400、28506件、0完成、18在途、28488等盘。原生产worker仍为hard_timeout，最终seal未独立native重放。429次owner activation超过100ms、最大344.0266ms；完整请求账务仍待闭合。
4. 新run级验收保留539文件身份和44+21入口/退出全验收。实际九消息门17.6850005秒，全部raw与旧003逐字段一致、没有排除字段。实际60业务120.7778219秒：10assessed、50unknown。已定位120次后续采集都把client request ID与native message ID错误比较；离线修正身份链仅作诊断，旧业务结论不升级。独立新adapter需保留age/ACK-union/状态限制，再运行新九门与60。
5. 路由偏好语义仍需解决：45条初始R1、5条后续R1被receiving_full拒绝；14个后续选择3却实际走8，其中9个updated后竞争回退、5个已被拒。偏好ACK不是路径保留。纯模型修正与实际可执行策略均须对照同等信息强参考。
6. regional路径缓存候选2在纯重复图微测改善、唯一占用图微测变慢，全部保留。实际配对driver/verifier正独立审查：026两独立进程各重放10片至原已知seal，再各1000owner；完整有序API/状态/seal一致才验收。600秒总预算；离线fork诊断不能冒充主session切点。尚无缓存实际流性能或100ms结论。

最新证据见`user_resume_20261015_001/milestone_007.json`；45/5与9/5统计勘误见`route_rejection_summary_correction_001/receipt.json`，旧摘要保留。三项总目标均未达标；继续本地执行与问题记录，未提交或推送。

'''
(DOC/'NEXT_ACTION.md').write_text(nextdoc[:start]+new+nextdoc[end:],encoding='utf-8')
note='''

## milestone007：已验证恢复与接口诊断

2×原流397片已匹配H64800已知原生seal，实际续跑中，所有历史成本及7200秒上限保留。027 run级验收九消息实际17.6850005秒且与旧raw完全一致，60业务实际120.7778219秒仍10assessed/50unknown。120次后续采集因请求ID与消息ID混淆提前返回；保存端点的离线修正身份链仅证明可解析性，不能改变旧实际策略与失败结论。新独立适配器将保留下游age/ACK-union/状态限制后实际重跑。低WIP005的一次真实完成返空已确立，第二供盘仍在准备；缓存只有纯微测，实际配对待运行。三项整体要求仍未达标。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf-8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf-8') as f:
 f.write('\n\n## 37. v3 后续采集身份接口错误与独立重跑边界\n\n实际60业务仍为10assessed/50unknown。全部120次采集把客户端请求ID与native生成的message_id直接比较，导致提前返回。正确关系需逐级核对command.request_id、实际端点和ACK.result_id==capture.message_id，同时保持时间、动作ACK并集与当前视图限制。保存端点纯回放中A60/B50能通过条件输入，B10仍因stationary loaded E未知；这不是新原生执行、当前状态认证或联合效益。旧60结果不得升级。run级539文件身份验收缩减重复验证成本，九门raw零字段排除完全一致；该实现优化本身不构成方法创新。\n')
write(report,{'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':evidence,'heartbeat_snapshot':heartbeat,'reconstruction':reconstruction,
 'v3_business_status_counts':business['branch_status_counts'],'offline_binding_counts':diagnosis['new_binding_replay_counts'],
 'before_sha256':{n:sha(backup/n) for n in files},'after_sha256':{n:sha(DOC/n) for n in files},
 'scope':'Actual results recorded without upgrading historical failures, full-request timing, strict protection, joint utility or whole-day business success.'})
print(json.dumps({'state_updated':True,'milestone_sha256':sha(report)}))
