from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT,OUT=HERE.parents[3],HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'live_initial_six_seam_v2_prepare_001/plan.json':'e555fe2ac3b74a87e8bfc5e246b2dc62ef61546a5c6f1b6aca7661e23651d0de',
 'live_initial_six_seam_v2_prepare_001/receipt.json':'85149c5a3535b59835304e8f32d550616abc9eafe7e639c587280e82055f4750',
 'live_initial_six_seam_v2_prepare_001/external_application_wall.json':'4c2db1443958fc83832f12cc93dcb6f6f7ec3ae31767e25b26b1845af41792a7',
 'owned_initial_bundle_six_cost_prepare_001/plan.json':'c61c19fcf0d5464a8102a368d8f1b86e4f8e8a91980bcd97ab3d71fd6e45fa64',
 'owned_initial_bundle_six_cost_prepare_001/report.json':'5976f31c78e475df83f42a28021e30a551ce1934ab4aca14a4ca98e5030d70f2',
 'owned_initial_bundle_six_cost_prepare_001/receipt.json':'3ebaed38fde55fcc8fcc4ec471ddc03d0fb1a6fc40ce03e6dadef6502a601694',
 'owned_initial_bundle_six_cost_prepare_001/external_application_wall.json':'e87407e1a5a7f57517a4a863894347e6993fecc916e9f9b8ca790e5d8ad91101',
 'planning_v2_C_encoder_gate_prepare_002/plan.json':'4df2e3fa3f122effb56b0468d685b58b9f742232eb714123ce31013f23732b7a',
 'planning_v2_C_encoder_gate_prepare_002/root_build_review_001.json':'a7ce0aefd67628493c482ab6efc47aeee35749764ce9cc4603a871bbe9acde54',
 'planning_v2_C_encoder_gate_prepare_002/review_submission_001.json':'3d7b9cad31472ad8b378a6434a3a4d9742f38769f913b55d7d138eefbc37b642'}
for p,d in pins.items():assert sha(OUT/p)==d,p
r=json.loads((OUT/'live_initial_six_seam_v2_prepare_001/receipt.json').read_bytes())
assert r['status']=='six_actual_initial_seams_validated' and r['known_initial_domains']==6 and r['unknown_initial_domains']==0
assert r['run_acceptance_status']=='closed_run_acceptance_passed' and r['source_changed']==[]
assert r['model_predictions']==r['physical_requests_submitted']==0
r=json.loads((OUT/'owned_initial_bundle_six_cost_prepare_001/report.json').read_bytes())
assert r['exact']==24 and r['unknown']==0 and r['source_changed']==[]
assert r['summary_ms']['A']['count']==r['summary_ms']['B']['count']==12
for p in ('planning_v2_C_encoder_gate_prepare_001/bounded_execution.json',
          'owned_initial_bundle_cost_pure_001/tests.xml','owned_initial_bundle_cost_pure_002/receipt.json'):
    pins[p]=sha(OUT/p)
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_041';backup.mkdir(exist_ok=False)
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());a=state['active_experiment']
state['current_stage']='All3 goals open. Initial actual6v2 passed6known0unknown25.967149/120 after strict public loading-bound correction; original3unknown retained. Ownedbundle ABBA24 exact0unknown but totalgain1.06percent and1/6pairedregression; not default promotion. Typed-C metadata002 passed samefile closure77.797s after preserved001timeout; build001 authorized/inprogress, no functional success inferred. New runtime32 diagnostic separation source/fakepure work ongoing. No root child active.'
a['actual_initial_six_v2']='180sources/81pure passed33.2276765/120; same3accepted027 actualsessions6owner domains whole25.967149/120,6known0unknown,44+21entryexit acceptance closed/source[]. A strict now+.01<finish+publicservice bound established only by exact validated owncapture/current job+tray/ACK/generation/traversal identity. No absent observe fields fabricated, no tolerance/currentpermission claim. Old3unknown unchanged. Zero model/provider/physicalsubmit/protection/100ms.'
a['owned_initial_bundle_ABBA24']='26componentpure+25costpure002;181sources. Pure0018pass17fail preserved (unusedSCHEMA global and testclone keyworddefaults), explicit barehelper closure fixed before run. Fixed6ABBA24 whole7.2145636/120,24exact0unknown/source[]/12each. Amedian154.09455 min133.1291 max206.7047 sum1865.6961ms;Bmedian142.6357 min130.0416 max218.7902 sum1845.9013.5/6pairedmedianimprove; insufficient_advance/vector_17 worsens189.8785->206.7796ms.Only1.06percent totalgain and worsenedmax, not default promotion/stablegain/complete100ms. Originalrevalidationdeepcopy/protocolcopy/allguards remain; no cache.'
a['typed_C_encoder']='Original7source/root/legal reviews unchanged. Metadata001 hard_timeout120 retained, no build/load inthatattempt. v2 inverseAST only prunes alreadyexcluded stdlib directories;22syntheticpass, metadata00277.797s/120,13project+7779toolchain+3082runtime withfullbeforeafterhashes. Sourceplan4df2e3fa...32b7a rootbuildreviewa7ce0aef...cde54 authorizes build001 once120, no load. Functional requires separate exact buildreceipt/externalclock andmodule/DLL provenance,159tests126directCbytes10fallback. Current buildrunning; not accepted before completedreceipt.'
a['runtime32_boundary']='New owned_prefix_evaluator/owned_initial_provider/owned_same_information_search source draft. Only graph serialization/mutablegraph walks/destructive completed probes removed by inverseAST, fixed source/private serial state ownership; retained point alias/popped-event/terminal guards, originalfutureAPI/_cut/65inventories,16freshinitialcontexts/32wholegraphclones/all32denominator. New ownership schema no fabricateddiagnosticflags. Explicit v2 finalcurrent guard innewsearch. Source/fakepure underway; actual full96/offline independent comparison andtiming stillpending.'
actions=[
 'Complete typed-C build001 once owned120 and review binary/dependencies/full externalreceipt before independent functional120. Then159tests/126directbytes/10fallback with exactmodule/DLL identity; no blindtimeout retries.',
 'Only after typed-C correctness, implement and test actual originaldelivered_peer fixed27212/27215 ABBA with full returns/errors andbytes. Retain bothfixtures absentreturn limitation. Only validatedactualcostgain justifies new all-day600.',
 'Finish source/fakepure of runtime32 ownership separation and independent legal/root review. Preserve16freshcontexts32wholegraphcopies65inventories/all32unknowns. Full96 exact savedcomparison before anyonline/performance promotion.',
 'Initialactual6v2passed. New full32provider mustbindv2freshrevalidation, oldv1provider remainsfrozen. Allmethods mustpay equal32 andactualstrict5job outcomes; projectiontargetneverinput.',
 'Ownedinitialbundlecopy removal remainscandidate only:24exact butmixedweakgain. Do notrepeat benchmark to cherry-pick or installasdefault. Complete actual18still434–976ms/0under100/2unknown; plan coherentintegrated change before rerun.',
 'All-day originalall28506/fullrequest100ms/fairjointmethodvalidity stillopen. Continue withoutloweredrequirements, preservefailures/history. No externalGPTProsend/push/commit.'
]
state['next_actions']=actions;a['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone041\n\n真实六域修正通过；复制优化仅弱混合改善，暂不推广。三个总目标仍未完成。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone041：真实六域闭合，复制优化弱混合，C 准备超时修复

新v2保持同三场景六owner，180sources/81pure后真实whole25.967149/120，6known0unknown，原44+21验收entry/exit闭合、source[]。A只使用已验证自己送达capture的load完成时间、公开node0服务时长，以及当前真实loaded身份/job/gen/traversal/ACK一致性推导最早service结束；严格now+.01<bound，没有读取不存在的observe字段或增加epsilon。仍须native权限验证；0预测/物理提交，不能视作在线联合有效性或100ms。旧3known3unknown不改。

私有bundle复制移除保留原revalidate deepcopy、协议复制和所有guards。26组件测试和25成本门通过；首轮成本pure8pass17fail系未使用SCHEMA私有global/测试clone漏keyworddefaults，原件保留。显式闭合bare helper。181sources固定ABBA24均全输出exact、0unknown，whole7.2145636/120。A中位154.09455ms、总1865.6961、max206.7047；B中位142.6357、总1845.9013、max218.7902。5/6配对中位改善，但insufficient_advance/vector_17从189.8785到206.7796ms恶化。总仅约1.06%改善且尾部变差，暂不默认推广，也不重复跑来挑好结果。

C typed-v2 metadata001达到120秒，未build/load；无阶段journal，不能把推测热点说成实测。v2只以同选择谓词剪去原本排除的stdlib目录，完整依赖核验保留，22测试通过，metadata00277.797秒闭合，13源码/7779工具链/3082运行时。journal保留独立阶段，不能累加嵌套耗时。根审后只授权build001一次120秒，无load；functional要另审真实build外层时钟及二进制，再做159测试、126直接C全字节和10回退分别统计。新runtime32源仅拆诊断遍历，仍保留16上下文/32整图deepcopy/全部动态guards及重复sourceinventory；尚未实际模型验证。

全天原28506、完整请求100ms、强公平联合有效性三个标准不变。父目录用户PIBT未改；无GPTPro外发、commit或push。\n'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 71. 真实字段修复闭合与复制优化负例保留\n\n新真实6域全部通过，但只证明初始信息与局部时间界可执行。24次复制优化全输出一致，弱总改善及单场景回退不足以推广。C元数据同集合枚举修正完成，构建/功能/实际validator加速尚需逐门证据；完整32执行与诊断分离仍在源码阶段。三个总目标未达标。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,
 'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'root_sessions_active_at_checkpoint':[],
 'agent_work_at_checkpoint':['control_timers: build001 owned120','r1_research: runtime32 source/fakepure','legal_context: independent runtime32 source review'],
 'new_native_branches_since040':3,'native_owner_domains_known':6,'native_owner_domains_unknown':0,'external_messages_sent':0}
with (HERE/'milestone_041.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_041.json')}))
