from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'full32_future_suffix_prepare_001/plan.json':'c48367f67be44aea409369d72f632228d28839fe1580fcda6bdacdabbdf7d811',
 'full32_future_suffix_prepare_001/external_application_wall.json':'ad421e8307868a62c4eb8de4db3c242eb2ab83c17ab824d1a1d0072191e76846',
 'full32_future_suffix_prepare_001/rows.json':'1aa499bf1ed23ac7b85949416f79004c445f506f3a7980079256f38973bcac33',
 'full32_future_suffix_prepare_001/groups.json':'fad65a75d98a4869abe992b348f6c50c9aae95756a57916669ca86cd60f5ee7f',
 'scoped_public_inputs_v2_six_cost_prepare_001/report.json':'05a338830db5d8b0b8e5ab54c2542a9ad4a4d9201d19538019dda672148d0063',
 'scoped_public_inputs_v2_six_cost_prepare_001/external_application_wall.json':'e3be0eb41682508c624a9e6a34aa5355fa3ecccc07d6bca22ebe06dda237799f',
 'complete_C_publisher_profile_prepare_001/receipt.json':'23441df00fe81c8844d44fc44f82dbd25bf30599e8af0e8c54d8d8f2e4957708',
 'complete_C_publisher_profile_prepare_001/external_application_wall.json':'d1fa9358b248a88c6b141a27069f7b043ab14e583c4fb30232b9a696355df126',
 'user_resume_20261015_001/C_publisher_profile18_small_readback_001.json':'e795e72ff4ed9ecdd79a7edb35d86984a98b269c45e92407a92e74dde62c003a',
 'bridge_policy_digest_source_attribution_001.json':'459621cf1be2032debfd6017c95f173794f0ab4350d2d52be63682efa0897069',
 'owned_decoder_tree_elision_source_review_001.json':'527767325862772c257355f1e88228fd2620fbe38deff926767b80d1a2192864',
 'complete_root_owned_decode_v2_pure_001/receipt.json':'a17963015caed50ee916f6803a492b57f2ec5b23b9ab3ce4c4a1e11fe357be25',
 'full32_delivered_online_integration_plan_001.json':'825d29c0d7e391fde49e7096fe4decb80feefdc84c85f1b781513a20bcd0525c',
 'live_communication_scoped_inputs_v2_prepare_001/plan.json':'d64ab44189e5c7cb3d79b109072a6f29d22c9004cd8da872ceffc65dbc8a9fe9'}
for p,d in pins.items():assert sha(OUT/p)==d,p
r=json.loads((OUT/'full32_future_suffix_prepare_001/receipt.json').read_bytes())
assert r['status']=='exact_full96_future_suffixes' and r['exact_rows']==96 and r['unknown_rows']==0
assert r['exact_groups']==r['context_constructions']==48 and r['unknown_groups']==0 and r['source_changed']==[]
assert r['counts']=={'initial_engines':48,'initial_advances':48,'prefix_same_resumes':65,'future_forks':96,'future_resumes':96}
for key in ('rows','groups','entry_pins','exit_pins','loaded_entry','loaded_exit'):assert sha(r[key]['path'])==r[key]['sha256']
pins['full32_future_suffix_prepare_001/receipt.json']=sha(OUT/'full32_future_suffix_prepare_001/receipt.json')
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_038';backup.mkdir(exist_ok=False)
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());active=state['active_experiment']
state['current_stage']='All3 goals open. Full32 future fork complete original96 exact0unknown passed216.9747081/360. Scoped v2 ABBA24 exact and lower median but model102ms median still not complete100ms. C publisher profile18 isolates repeated owned decoded-tree walk. Owned decoder87pure passed; C binding not tested. V2full96 active root session86384. Initial online full32 adapter/provider/search source work continues.'
active['future_full32']='60pure; original3x32 partition exact16prefixes each. 48fresh paired contexts/48engines48advance65same-prefixresume96fork96futureresume;96exact0unknown48exactgroups/sourceunchanged. Whole216.9747081/360. Both children from same unconsumed firstknownB, earlier3coordinates fixed including return_delay; all output saves before target reads, fullbytes/types/order/floathex/chronology and alias guards. Actiondomain coverage only; no hiddenstate/actual current-state/online protection/100ms certificate.'
active['scoped_v2_ABBA24']='36functionalpure plus32harnesspure002 after31/32 AST-docstring test failure001 retained. Fixed6xABBA24 exact0unknown,12eacharm,whole7.8307793/120. Amedian134.3762ms Bmedian102.1483ms,all6paired medians improve; Bmax135.2676. Newfresh scope/setup and allguards inside each model; initial context caller unchanged. Extra fullv1 check after originalworker_seconds, only externalwhole covers all. No actual-native/full32/100msclaim. Full96 adapter25pure passed and164sources frozen; actual active session86384.'
active['C_publisher_profile18']='8syntheticpure and source review; fixed18 complete publisher cProfile with18originalCpreflights,whole65.0284289/120,18exact/sourceunchanged/defaultGC. Historical16closed2unknown semantics preserved. _tree has2primitivecalls perroot, decoder dominates while ledger tiny; median63.7204percent instrumentedtotal cumulative. Instrumented self/cumulative overlap, not latency gain. Separate smallreadback verifies36 profile refs only, not independent raw18 audit.'
active['owned_decoder_v2']='Closed owned pipeline source87pure passed whole7.5206301/120. Only freshly normalized and encoded internal full evidence removes redundant decoded_tree; original UTF8/bytebound/duplicate/nonfinite JSON hooks and canonical reencode equal remain. No new bytes-input API; publicdecoder and ledger_tree unchanged; source/AST/globals/no-prior-alias proofs. Canonical foreign bytes alone cannot prove origin. Resource failures remain unknown, not asserted exception identical. Pythonnormalizer only; fair C/C+owned binding source pending,0performance gain claim.'
active['all_day_attribution']='11source pins/read small saved reports only. ReplayTape/refresh no digest; actualdelivered_peer0or1; latestown scans allhistory but onlynewestdigest; Bridgeactivation atmost4 with consume, final3relayplaces*2ownersatmost6postpolicy. Actualfrequency unknown, cannot multiplyAPIrows. 19712marker beforeouterpolicy consumption. Batcheddigest negative retained. Next bounded120 fixed2 actualoriginaldelivered_peer nested originaldigest timer, exactowner/peer/now/nodes inputs; no blind600 or late fabricated policy state.'
actions=[
 'Finish active scopedv2 full96 root86384, require original96 exact/0unknown226checks192known/full outputs andwhole360; no alteredtargets or initialcontext optimization.',
 'Implement source-only actualdelivered initial adapter, shared32 provider and strongsameinfo selector; conditional forecast estimates cannot certify strict actualprotection. Ownerviews independent, originalcurrent/nativeguards retained. 21prospective arms need separate source/pure/cost registration.',
 'Review owneddecoder separateC binding and synthetictests, then fixed18 fairABBA currentC vs sameC+owneddecoder if gatespass. Publicdecoder/ledgerdepth/node/resourcechecks remain, no externalbytes shortcut.',
 'Optimize originalinitialcontext+v2prediction together with freshscope, compare totalA/B and fulloutputs; source-onlywhileactiveperformance. Do not compareBcombinedspan toAbarepredict.',
 'All-day next actual deliveredvalidator bounded attribution; preserve existing600/2400 failures and all28506 denominator. No batchedwriter installation or sourcecount-only speed inference.',
 'All3 goals remainopen; actual16closedroots still434–976ms/0under100,2unknown retained. No GPTPro send/push/commit.'
]
state['next_actions']=actions;active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone038\n\n全面恢复继续有效，三项目标均未达标。完整32域未来分叉的96结果全部一致；v2公共输入模型提速，但未达完整请求100ms。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone038：完整候选域未来分叉通过，模型与发布热点继续收敛

完整32域16前缀共享（return_delay属于已执行坐标）在原3场景验证：48对新建初始上下文、48engine/advance、65同前缀resume、96fork/future-resume，96exact、0unknown、48exactgroups，whole216.9747081/360。严格第一个knownB未消费切点，兄弟均先clone再执行、父与兄弟隔离；完整输出先保存后读取目标，完整bytes/JSON类型/顺序/floathex/chronology一致，162source未变。仅证明声明动作域的条件模型一致，隐状态覆盖、实际后续状态重建与在线有效性未证明。

公共输入v2实际6输入ABBA24通过，whole7.8307793/120，24exact0unknown。A12模型中位134.3762ms，B12为102.1483ms，六组配对均改善，B最大135.2676ms，尚不满足完整100ms。原initialcontext调用未变；model span含freshscope和所有guard，额外v1全比较计入external whole而不在旧worker_seconds。新全96 adapter25pure通过并164sources封存，当前root86384执行中。先前costpure失败由AST docstring假设导致，仅修测试、失败保留。

C发布18固定真实fixture的完整publisher诊断通过，whole65.0284289/120、18exact、历史16closed2unknown未升级。每root两次_tree，重的是内部完整结果decode，ledger_tree极小；_tree累计占插桩whole中位63.7204%，不能把插桩累计当未插桩收益。下一候选只对刚normalise/encode且未逃逸的私有证据省重复tree walk，公开decoder、ledger_tree、UTF8/size/duplicate/nonfinite parse与完整canonical reencode不变；来源proof是必要前提，合法canonical外来bytes本身不足。87pure首轮通过、whole7.5206301；暂无C绑定或性能收益。

全天源码归因确认ReplayTape/refresh无摘要，delivered_peer至多1次，latestown只摘要最新但扫描整历史，桥owner激活含consume最多4次，三处末尾relay合计最多6次。实际频次仍未知，不能用37270行乘常数。19712进度在outerpolicy消费之前，不能当完成激活。批量编码实测负结果保留；下一步固定2实际delivered_peer诊断，禁止伪造晚时刻policy状态或盲重跑600。所有3目标继续开放，父目录用户C++哈希不变，无外发/提交推送。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 68. 完整动作域分叉一致，尚无联合方法优势证据\n\n3场景x32未来后缀全一致，作用是复用条件模型前缀。v2公共输入模型中位仍102ms，C发布诊断仅定位重复内部解码遍历；87pure不是速度或原生保护证书。下一步实际送达数据接入共同32provider与强公平方法。全天原流、完整100ms、联合有效性仍未完成。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'root_sessions_active_at_checkpoint':[86384],
 'new_native_branches_since037':0,'external_messages_sent':0}
with (HERE/'milestone_038.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_038.json'),'full32_receipt_sha256':pins['full32_future_suffix_prepare_001/receipt.json']}))
