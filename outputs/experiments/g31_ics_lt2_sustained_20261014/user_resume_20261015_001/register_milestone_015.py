"""Record actual online utility, retained unknowns and separate saved audits."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
DOC=ROOT/'docs/g31_ics_circulation';HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
backup=HERE/'before_milestone_015';report=HERE/'milestone_015.json'
assert not backup.exists() and not report.exists()
pins={
 'original_low_wip_repeat_independent_actual_review_001.json':'179b81b26812478820abfcb7c087e8559a066448405704b29577802b0a807db9',
 'original_low_wip_repeat_independent_actual_review_001_process.json':'61a4771cfee00ad09f84eb0ca2f17e4edcae7cb604d667809ba28145874a802a',
 'original_route_native027_phase_prepare_002/powershell_launch_receipt.json':'ccc3821062bd53271062678b115acd340191221f970f9e20b2293ab52b711df9',
 'native_public_preference_delivery_001/powershell_launch_receipt.json':'0772e6d3b0eff369bc7fc6ec8e2ea98dfdb36a86374348908571237fe4771e08',
 'native_public_preference_business_001/powershell_launch_receipt.json':'4459ecee86b18eda9455bc7e7464bf16fb3f8dbcd86ce47bbe99cdf7fda46074',
 'native_public_preference_business_001_saved_audit.json':'37b6ae7924533acb74fb75b9ee1a7128ba17ae989389a920bb9b9db281a15501',
 'native_public_preference_business_001_diagnosis.json':'a6ddb59468f06856e3184ee3e2884f6eee7b7cd5138f1a722bc152eda2bb728b',
 'original_low_wip_quiescent_prepare_001/independent_source_review_001.json':'e7a21c41f3b3d9771849d26db8e62b6e7b43b9911b6ab3f1c461e2cd3b294f59',
 'user_resume_20261015_001/active_process_identity_009.json':'3aa6607b720de2e37218c87d61371abe7188399c6321b860b785751a7a067898',
 'route_native027_saved_audit_prepare_001/ready.json':'221746e42f6988c0b62d7ac68292191afd206e3e9417716659bd17f24247c8c4',
}
for n,h in pins.items():assert sha(OUT/n)==h,n
for n in ('native_public_preference_delivery_001/receipt.json','native_public_preference_business_001/receipt.json',
          'native_public_preference_saved_audit_parent_001.json'):
    pins[n]=sha(OUT/n)
r=read(OUT/'native_public_preference_business_001/receipt.json')
assert r['source_changed']==r['source_closure_changed']==[] and r['branch_count']==60
assert r['branch_status_counts']=={'assessed':52,'unknown_initial_asymmetry_or_missing_ledger':6,
                                 'unknown_missing_input_or_unexecuted_online_action':2}
backup.mkdir();files=['RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md']
for n in files:(backup/n).write_bytes((DOC/n).read_bytes())
s=read(DOC/'RESEARCH_STATE.json');a=s['active_experiment']
a['repeating_low_wip_status']='Original cap3 corrected independent saved review passed34971API/25physicalrequests/actualjob2,6,8same-tokencycles;H86400 all28506arrived,3complete/28503unfinished,other21parked. Original verifier1 and campaign2400timeout/cap8unknown retained. Review initially had no external preregistered deadline/fulllaunchwall; later exactprocessobserver imposedremaining300s, naturallyexit0 with creation-to-first-absenceupper700.909s, not exactwall. Quiescent001exec43312 started16:09:59.796605, shared2400s deadlineabout16:50,82sourcesfrozen; no resultyet.'
a['public_preference_projection_status']='Actual same-source9gatepassed; actual60business finishedwithin180s worker152.2899644/outer153.3654357,52assessed+6initialmodel-admissionunknown+2laterunsupportedunknown. Independent600s saved audit50.0098562s exit0,2230publicprojections and full actualguards/actions/physical/fixedfamilies rechecked. Foursearches and laterdefaultablation give identical five-job vectors all6cases. Onlyblock1_load0/2complete4fixedfamilies;strict all-job improvement about4.1s total versus strongest fixed. No independent joint necessity. Initial6unknown are bothowners agreeing toreject allfixed2/3actions under model-strictpredicate, not actual asymmetry;2laterunknown receiverstate staysunsupported.'
a['route_phase_status']='Sixactualphase002workers allclosed0 but campaign600.1512597s timedoutduringverification. Workersfinished+298.4890967 leaving301.5109033s. Separate exactguard rowwise saved auditexec84544 with1800s ownedJob running from16:16:26.952715; old97unchanged. No native rerun, no100ms certificate.'
s['next_actions'][1]='Finish actualquiescent001 cap3/cap8 underoriginal2400s, all28506/H86400/22trays/onecirculatingtoken. Preserve originalcap3 failure+corrected independent success and originalcap8unknown separately.'
s['next_actions'][2]='New60independentaudit complete, nojointnecessity shown. Preregister separate public interaction discovery domain with full denominator and separate unseenvalidation; keep original6cases and strongbaselines. In parallel prepare source-only per-request context reuse preserving32/4 caps/guards/fullcost.'
s['next_actions'][3]='Finish separate1800s savedphase002audit; exact API/controller/commonH comparisons and allphasecosts. Then prepare actualpendingACK-onlyfaultpair with real querychronology; old600stimeout not repaired.'
a['pending']=s['next_actions']
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(s,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
note='''

## milestone015：在线60完成并独立复核；联合必要性仍未证明

同源9交付门实际通过（6正常、3负例），随后60业务分支在180秒上限内完成：worker152.290秒、外层153.365秒，52可评估、6初始模型准入未知、2later状态未知。独立保存审计在600秒限内用50.010秒完成，重算2230个公开预测及真实capture/ACK/动作/物理结果。六个初始未知并非A/B实际分歧，而是双方同样拒绝fixed2/3全部四个动作；原宽泛标签保留、另立原因更正。另两项仍是接收端状态不在模型支持域。

四种搜索和后续路线默认消融在六个场景的五件完成向量完全相同。只有block1_load0/2的四固定窗口家族完整，允许确认逐件不变慢且总完成时刻较强固定窗口减少约4.1秒。其余固定家族不完整，比较仍未知；不能把已有实际收益当成联合机制不可替代证据。下一步独立登记交互发现域及未见验证，保留当前六例与强基线。

旧cap3修正版独立审核通过34971条API与25物理请求，核实job2/6/8同盘完成并返空到46；H86400全部28506已到达，3完成、28503未完，另21盘仍停原位。旧校验失败与整组超时不改，cap8未知。该独立审核启动时未预注册外部硬限和完整启动墙钟，后来按精确进程身份补充剩余300秒界；自然exit0，700.909秒是创建至首次确认消失的上界，不是精确退出耗时。此计费缺口如实保留。

六格原图计时模拟均exit0，原600秒整组在保存核验阶段超时。新的逐行保存审计保留全部原guard，单独1800秒Job并记录外层完整Python墙钟，不重跑native、不覆盖原失败。quiescent cap3/cap8已于16:09:59.796605启动，两臂和核验仍共享2400秒，82来源冻结。当前最多两个native worker；离线审核另列。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NEXT_ACTION.md').open('a',encoding='utf8') as f:f.write('\n\n## 最新执行次序（milestone015）\n\n'+'\n'.join(f'{i+1}. {x}' for i,x in enumerate(s['next_actions'][:4]))+'\n')
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 45. 新在线60仍未显示联合独立必要性\n\n独立审核确认52可评估、8未知。四搜索与后续默认消融在六例完成向量相同；两个完整固定家族约4.1秒严格保护改进支持方法有效性局部证据，但普通坐标同样解释该收益。其余四族不完整，不宣称强基线全面胜出。下轮交互域发现与验证分开预登记，当前例和负结论不改。\n')
with report.open('x',encoding='utf8') as f:json.dump({'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in files},'after_sha256':{n:sha(DOC/n) for n in files},
 'active_native_sessions':[40149,43312],'scope':'Actual online60 and independent audit; originalcap3 independentlychecked; allunknowns/timeouts/accountinglimits retained. Overallgoal remains unachieved.'},f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(report)}))
