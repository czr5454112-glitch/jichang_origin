from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,statistics
HERE=Path(__file__).resolve().parent;ROOT,OUT=HERE.parents[3],HERE.parent;DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'dpc_prepare_001/root_review_001.json':'84e64c2410fccb6e7bfbb830a7b7375d8a40edaa6b8e9f9349864d73efc2f295',
 'dpc_prepare_001/result.json':'729c3a240538c8ef8aa8d0714402840d133ee36ad50b0a52e64c0b36d33632d1',
 'dpc_prepare_001/actual_external_application_wall.json':'93bb690984a194d8a89770791515ad9e5263fed1f602bfbb928ba8d6a627ec59',
 'dpc_prepare_001/root_saved_review_001.json':'93690fcb1bb4fdf48463f5451d4d435225c0f4e28b3990797ac988ab1abe38f1',
 'bridge_C_digest_private_design_001.json':'dbfac906040135acdbaedbb67aac9ccc86ea61b6b46ff167e416896aca5bede5',
 'bridge_C_digest_private_design_pins_001.json':'546c5e19d35d3b17a315bda651c9d32224a066f7c1fb5c92ef4d8cb53baf4b78',
 'single_owned_C18_cost_analysis_002/report.json':'a5ac730be202fd8b3452bfd5935965d967d1d034f9ad15b400896bcf83a0c7ad',
 'single_owned_C18_cost_analysis_002/external.json':'c6f1e0aa65e9f5b583282206fe1dc89b0052936b0a3282080274e9f1751ba5f9'}
for name,digest in pins.items():assert sha(OUT/name)==digest,name
for name in ('single_owned_C18_cost_analysis_001/execution.json','single_owned_C18_cost_analysis_001/failure_diagnosis.json',
             'single_owned_C18_cost_analysis_002/source_conclusion_001.json'):
    pins[name]=sha(OUT/name)
other={str(ROOT/'outputs/si65d1/plan.json'):'cc6432f563f1b447ebac5c8058f93cc6e721f6711ba33e2c1dbe6baa60bec0c6',
 str(ROOT/'outputs/si65d1/root_review_001.json'):'ccc559c819c2bd88db2bdc4d8a5a16e11a18a61e408e18448df0cfc112d8011e',
 str(ROOT/'outputs/si65d1/receipt.json'):'6f921d8be061073e95b410c21557308a36e49ff40245dd419da2a55edc38cb1c',
 str(ROOT/'outputs/si65d1/report.json'):'7f919ed5e699c90dad78c78d0fc6859a83a2f90457d260c3a9f85e812e9c406f',
 str(ROOT/'outputs/si65d1/external_application_wall.json'):'79d98ac99373a88d60f4b3ccc132eba2aff0749ee192b44004e3e18a8eb3d519',
 str(ROOT/'outputs/si65d1/root_saved_review_001.json'):'e5e6252e5727e9df2c36adc13f08b22bbd392f2adfb8df264855840ba269c8ae'}
for path,digest in other.items():assert sha(path)==digest,path
cost=json.loads((OUT/'single_owned_C18_cost_analysis_002/report.json').read_bytes())
assert len(cost['rows'])==18
closed=[r for r in cost['rows'].values() if r['root']['closed']];assert len(closed)==16
for row in cost['rows'].values():
    assert sum(row['warm_partition_ns'].values())==row['outside_return_ns']-row['root_started_ns']
    assert abs(sum(row['exclusive_known_and_residual_ms'].values())-row['root']['warm_ms'])<1e-9
sums={name:sum(r['exclusive_known_and_residual_ms'][name] for r in closed) for name in closed[0]['exclusive_known_and_residual_ms']}
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp';assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_046';backup.mkdir(exist_ok=False)
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());a=state['active_experiment']
state['current_stage']='三个总目标仍未达标。C digest固定2原validator ABBA32实际通过：33.2986→8.40715ms、56.4458→12.7397ms，32结果全absent，16B全directC，2完整字节oracle，whole111.8239422/120秒；root独立保存复核通过。65原source_proof诊断65exact/0unknown，whole105.4363922/120秒；profile99.7秒集中在重复静态AST构造。两项静态证明复用及全天C digest私有绑定新源码草案正在实现，尚无新测试/性能/全天运行。'
a['typed_C_delivered_peer'].update(status='actual32_passed_root_saved_reviewed',metadata_seconds=12.461307,whole_seconds=111.8239422,actual_performance_dispatched=True,actual_calls=32,batches=8,absent=32,direct_C_measurements=16,fallback_measurements=0,complete_byte_oracles=2,median_ms={'27212':{'A':33.2986,'B':8.40715},'27215':{'A':56.4458,'B':12.7397}},C_load_dependency_entry_seconds=46.2123891,dependency_exit_seconds=50.0233258,full_stream_benefit_unknown=True,root_saved_review='dpc_prepare_001/root_saved_review_001.json')
a['source_inventory_cost_design'].update(status='actual65_closed_root_saved_reviewed',actual_diagnostic_dispatched=True,metadata_seconds=13.2114817,sources=196,evidence_references=12,whole_seconds=105.4363922,actual_calls=65,exact_proofs=65,unknown_rows=0,profiled_call_total_seconds=99.8138111,profiled_call_median_seconds=1.5297592,profiled_inventory_cumulative_seconds=99.7226485,source_proof_cache_modified=False,root_saved_review=str(ROOT/'outputs/si65d1/root_saved_review_001.json'),interpretation='cProfile开销在内，嵌套累计不可相加，不能据此推无profile的实际收益或full96占比。read_bytes455次累计0.2411573秒；源码静态解析/AST编译可尝试复用，来源失效检查继续。')
a['actual18_saved_phase_cost']={'status':'saved18_integer_partition_verified_root_aggregate_checked','whole_saved_analysis_seconds':3.7579922,'closed16_exclusive_ms':sums,'unclassified_prefinal_fraction':0.7374170187046813,'finalization_fraction':0.1471599739025097,'query_nested_ms_not_additive':102.8097,'even_zero_finalization_prefinal_median_ms':495.30505000000005,'limits':'不可把73.74%残差全部归因于constructor。query在refresh内部不重复加。零final只是诊断算术，不允许删除证据。报告17条同选择不能当同执行。','failure001':'分析器遗漏原artifact编码末尾LF，首条字节断言失败，旧源/日志保留；v2仅补LF+新目录，18全部通过，首条跨两次实际被读2次。'}
a['new_static_and_bridge_work']={'status':'new_source_drafts_only_not_tested','actual_request':'initial_owner_route_static_inventory.py候选：冷原inventory/collection_inventory，原constructor code逐root完整动态门+轻量依赖失效，新私有drain/class关系；不混入模型或typed encoder。','model_source':'live_obligation_bound_source_proof.py和bound_future_fork候选：冷原source_proof一次，仅私有_source_inventory返回器改变，逐call保留原loadedchecks、完整fresh deepcopy、原_cut及所有动态门；保留有限原源码读取域SHA。','all_day':'bridge_C_digest_private_design_001：base/reuse/PossessionGate/BridgeOwner/caprelay/inner+outer assess全部私有绑定，__class__/super和definingglobals/kwdefaults保持；不夹带borrow/discard。原37270/27218/28506/22/600全保留。'}
actions=[
 '审查两项独立静态proof复用源码和focused synthetic：实际ActualAdvanceChain constructor与模型future source_proof分开变更。冷绑定成本完整计入、依赖变更失效、fresh证明返回及全部动态门保持。',
 '审查全天C digest私有bundle真实MRO及两层runner/checker/assessment调用接线，再focused synthetic、新source/archive准备与root审核。通过后才一次新600原全天保存审计；不能以局部74–77%直接预言完成。',
 '模型缓存候选通过源码/纯测试后，先完整96输出/点/动作/未知分母等价，再单独预算与受控性能测量，继续接入同信息同32预算7臂×3场景在线方法。原设计尚未实现actual21，不把固定向量最优当在线结果。',
 '实际constructor候选通过后保留原18/600、60ms选择、100ms完整请求和正常5任务严格不回退，新增明确constructor计时，单独新运行，保留所有选择变化/未知/失败。',
 '原流1x/2x、严格正常保护、完整full32 100ms及双机必要档、同信息强在线方法的联合有效性仍开放；不改变拓扑/FIFO/盘数或弱化基线。',
 '持续保存问题与解决方案。无新指令不发GPTPro、不push/commit。']
state['next_actions']=actions;a['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone046\n\nC摘要原validator实测有局部收益，65次源码成本诊断也已完成并独立回读。下一步实施静态证明复用与全天私有C绑定；三个总目标仍未达标。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone046：原validator局部加速成立，重复静态分析成为下一验证方向\n\nC摘要固定两条query的ABBA32一次实际运行通过，111.8239422/120秒，95源码无漂移。27212中位33.2986→8.40715ms；27215为56.4458→12.7397ms。32结果全部absent，B16次全部实际directC、0fallback；两对完整字节oracle一致。7779工具链/3082运行时完整入口出口核验保留，入口46.2123891秒、出口50.0233258秒，不能从全程扣掉。root独立核32条结果/类型时钟/8批/26stage/两完整字节/入口出口身份与95来源，保存review93690fcb…be38f1。不将两absent输入推广为成功guard路径、全流频率、全天完成或100ms达标。\n\n固定65原source_proof带cProfile诊断完整结束，105.4363922/120秒，65exact/0unknown、原function/GC/来源不变，未修改缓存。调用wall总99.8138111秒，中位1.5297592秒；_source_inventory累计99.7226485秒，getsource11375次累计31.4889秒，build_parts65次26.4835秒，action_uses7865次25.6737秒。均带profiler，累计互相嵌套不可相加，不能推无profile收益或full96占比。有限来源read_bytes455次仅累计0.2411573秒；下一版本保留文件SHA失效检查，尝试复用静态AST结果。root逐65完整2604字节证明与pstats/时钟/196当前归档和12证据核对通过，reviewe5e6252e…269c8ae。\n\n实际18保存成本分析也关闭：16closed根总9459.3004ms，不重叠advance含copy41.7151、refresh含query773.2795、RPC276.8263、未归因prefinal6975.4491、final1392.0304。query102.8097嵌在refresh，不能再次加。即使final为0，prefinal中位仍495.30505ms。源码发现每root重新构造ActualAdvanceChain库存证明，尚无独立constructorclock，不能把全部73.74%残差归给它。分析001漏末尾LF导致首条失败，保留；v2仅修LF与新输出3.7579922秒通过，首条确读2次。\n\n新工作三线仅源码草案：实际constructor静态证明复用、模型future静态证明复用、全天C digest完整私有调用链。原accepted源/测试/证据冻结，动态session/current/ACK/ledger/_cut/截止和全部分母保持。还没有新全流实际运行、完整100ms或强在线联合有效性结果。\n'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 76. 局部编码收益与静态分析复用候选，均不替代方法证据\n\n两原始absent-query ABBA验证器中位缩短约75%/77%，完整bytes与32结果一致；范围有限，全天实际频率未知。65原静态证明诊断显示重复AST成本，但带profile不能冒称已加速。下阶段以独立冷绑定和依赖失效保持证明与动态权限的边界。工程优化为完整32候选与同信息强在线比较创造预算条件，仍不等于联合方法创新。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,'other_evidence':other,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'active_processes':[],'new_native_branches_since045':0,'external_messages_sent':0}
with (HERE/'milestone_046.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_046.json')}))
