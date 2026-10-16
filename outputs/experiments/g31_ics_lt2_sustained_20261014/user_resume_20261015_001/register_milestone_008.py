"""Record actual two-job token reuse, corrected v3 run and negative cache pair."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
DOC=ROOT/'docs/g31_ics_circulation'
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
report=HERE/'milestone_008.json';backup=HERE/'before_milestone_008'
assert not report.exists() and not backup.exists()
reuse=read(OUT/'original_low_wip_reuse_prepare_002/receipt.json')
business=read(OUT/'native_preexisting_v3_bound_business_001/receipt.json')
cache=read(OUT/'regional_path_pool_native_001/receipt.json')
assert reuse['status']=='worker_finished' and reuse['source_changed']==[] and reuse['wall_seconds']<600
assert reuse['assessment']['second_reuse_proved'] and reuse['verification']['api_rows']==14321
assert reuse['verification']['status']=='passed_saved_raw_replay'
for n,h in reuse['artifact_sha256'].items():assert sha(OUT/'original_low_wip_reuse_prepare_002'/n)==h
assert business['branch_status_counts']=={'assessed':14,'unknown_incomplete_or_unexecuted':46}
assert business['source_changed']==business['source_closure_changed']==[] and business['wall_seconds']<180
assert cache['status']=='verified_exact_pair' and cache['process_wall_seconds']<600
arms=cache['verification']['arms']
assert arms[0]['ordered_api_hashes']==arms[1]['ordered_api_hashes']
assert arms[0]['controller_window_ms']<arms[1]['controller_window_ms']
files=['RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md']
backup.mkdir()
for n in files:(backup/n).write_bytes((DOC/n).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
active['startup_low_wip_candidate']='Separate reuse002 actual227.8734606s<600 shared budget;14321 API saved replaypassed. Sameinitial:0:0 job2 UNLOAD19772.592/HOLD19773.592, second supply19800 from116to26 thenjob6 UNLOAD20812.397/HOLD20813.397. All24physicalreceivedACK,22parked,380completedtraversals/0open,finalempty,H28800. Original28506/R1false/22trays retained;8740arrived=2complete+8738waiting,19766unreleased. No strictprotection/full-day/100ms or jointR1 claim. Additional independentactual audit pending.'
active['planning_v3_status']='New bound actual9allpassed20.5858517s then60business139.6785276s,14assessed/46unknown,62sourceclosureunchanged,fullrunacceptanceclosed. RequestID→actualcommand→ACK.result_id→capture.message_id fixed in separateadapter; allage/union/modelguards retained. Detailed actual60 diagnosis pending. Old10/50 run untouched; no jointutility/protection/current-state/100ms claim.'
active['regional_path_cache_candidate']='Actual pair00164.0224655s:two separate026 sessions eachknownoriginal10shard replay+1000owners;24571 orderedAPI each,raw0010/11/mainseal/full28506diagnosticfork exactlymatched. Controller10.633849→11.539014s and ownermax28.641→32.1996ms:negative,not promoted. Pureactual-API replay identifies key construction as dominant (1000handles,only5owner/source/goal pairs),new isolated candidate investigation only.'
state['current_stage']='Original1x full-day negative audited;2x same024 continuation active afterverifiedH64800. Original reuse002 establishes two actual complete/empty cycles on one finite tray under unchangedinput; strictprotection andfull-daybusiness remainopen. Corrected v3 actual60 improves eligibleassessments14/60 but46unknown; detailed mechanism diagnosispending. Exact regionalcache nativepair slower,negativepreserved. Threeoverallrequirements stillunmet.'
state['next_actions'][1]='Independently audit actualreuse002 exactfirstphase/onlinecompletion-currentempty-peerFIFO and bothlifecycles; then choose next original-business experiment from evidence, no weakeningFIFO/physicalcontract.'
state['next_actions'][2]='Diagnose corrected actualv3 bound60 (14assessed/46unknown) includingactualinputs/edges/perjobdeltas. Prepare predeclared192 fixed-action preference matrix onlyas counterfactual execution/model calibration, samefaircandidates; no onlineoracle.'
state['next_actions'][4]='Keep slower regionalcache opt-in. Use savedAPI pureprofile to test exactkey cost reduction on realquery distribution; preserveallnegativecases. Separately clarify original finitebusiness request admission/probe boundary and fullwarm/cold/setup/retry/ACKcosts.'
active['pending']=state['next_actions'];write(DOC/'RESEARCH_STATE.json',state)
text=(DOC/'NEXT_ACTION.md').read_text(encoding='utf-8')
start=text.index('## 最新执行次序');end=text.index('## 恢复初期队列')
current='''## 最新执行次序（milestone008）

1. `full024_chained_2x_20261015_001`已重建397片并匹配H64800原生seal，正在同024续跑。7200秒上限、历史成本及最多2个原生worker不变；冻结原来源。
2. `original_low_wip_reuse_prepare_002`实际227.8734606秒完成，模拟与独立验收共用600秒。14321条API回放通过：同一initial:0:0在19772.592和20812.397真实卸载job2/job6，分别完成HOLD后返空；24物理请求均received ACK、22盘停车、380物理越边/0open。原28506/R1false/22盘保留，H28800已有8740件到达（2完成、8738等待），另19766未释放。下一步另做独立实际复核；不宣称逐件保护、全天有效性或联合R1。
3. 1×全天保存证据审计：H86400、28506件、0完成、18在途、28488等盘。原worker仍hard_timeout，最终seal未独立native重放。429次owner超过100ms、最大344.0266ms；完整business请求账务仍待闭合。
4. 新bound身份适配器实际九消息门20.5858517秒全过，随后60业务139.6785276秒：14assessed、46unknown，62源及run级44+21验收闭合。旧错误ID比较的60结果10/50保留。新60逐条动作兑现/输入/逐件差异正在诊断；身份修复不等于联合有效。下一192固定动作矩阵先完整预注册，作为执行性及模型校准证据。
5. 旧025统计仍为45初始+5后续receiving_full，14个later选择3/实际8中9updated后回退+5已拒。新动作域明确native_default不承诺next1，偏好ACK不是资源预约；所有强参考保持同候选/信息/预算。
6. 路径缓存actual001两独立026臂各1000owner/24571有序API与原0010/11及终点seal精确一致，但控制窗口10.633849→11.539014秒，负例保留，不用于全天默认。纯真实API profile定位完整构key开销超过每次2–3种path查询的收益，新独立候选先纯测。短区段有限盘跨段模型已有20261014参考，机械合同缺口见`LT2_SHORT_LINK_RECHECK_20261015.md`；不重复造模型或自动0→1。

最新证据索引`user_resume_20261015_001/milestone_008.json`。三项总目标仍未达标；继续本地优化、执行及问题记录，未提交或推送。

'''
(DOC/'NEXT_ACTION.md').write_text(text[:start]+current+text[end:],encoding='utf-8')
note='''

## milestone008：原图同盘两次复用与保留负结果

reuse002实际227.8734606秒，14321API独立回放通过。同盘job2/job6两次UNLOAD/HOLD和最终返空、24receivedACK、22盘/380越边完整审计成立；H28800仅8740件已到达，原28506输入均保留。新bound60真实139.6785276秒得到14assessed/46unknown，详细机制审计待完成。regional缓存实际两臂原始行为完全一致但10.633849→11.539014秒变慢，不推广。原全天/逐件保护/完整请求100ms/联合创新均未因此通过；继续针对失败原因而非降低验收。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf-8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf-8') as f:f.write('''

## 38. 原图同一有限盘第二次完成与优化负例

原R1false输入的两次实际完成/返空是循环执行性推进，仍非R1→R2→R1双向机制、逐件保护或CONWIP创新。新bound60的14assessed/46unknown属于接口修正后的实际结果，需逐条机制与强参考比较；不能以通过分支数证明收益。Regional缓存即便2574跨activation命中且仅5miss，真实控制窗口仍慢8.51%；全key成本支配纯真实调用重放，暂不推广。所有原负例、旧ID错误结果及未执行reuse001保持原件。
''')
names=['original_low_wip_reuse_prepare_002/receipt.json','original_low_wip_reuse_prepare_002/independent_verification.json',
 'native_preexisting_v3_bound_delivery_001/receipt.json','native_preexisting_v3_bound_business_001/receipt.json',
 'native_preexisting_v3_bound_independent_source_review_001.json','regional_path_pool_native_001/receipt.json',
 'regional_path_pool_actual_pure_001/receipt.json']
write(report,{'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':{n:sha(OUT/n) for n in names},'before_sha256':{n:sha(backup/n) for n in files},
 'after_sha256':{n:sha(DOC/n) for n in files},'reuse_assessment':reuse['assessment'],
 'v3_business_counts':business['branch_status_counts'],'cache_arms':arms,
 'scope':'Finite actual gates; no whole-daybusiness,strictprotection,jointmethod or complete100ms certification.'})
print(json.dumps({'state_updated':True,'milestone_sha256':sha(report)}))
