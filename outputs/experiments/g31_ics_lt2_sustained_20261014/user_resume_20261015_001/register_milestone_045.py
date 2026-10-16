from pathlib import Path
from datetime import datetime, timezone
import hashlib, json

HERE=Path(__file__).resolve().parent; ROOT,OUT=HERE.parents[3],HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'single_owned_C18_prepare_002/campaign.json':'4ac4569ad5145ccf62e83a39d29ad238077bf00fa0657c130fb12916cfb91bdc',
 'single_owned_C18_prepare_002/root_review_001.json':'de24dfe036794e4e9a83378ccbd99e6ff421a7456d0dabbb8ffda3cf50d0b278',
 'single_owned_C18_prepare_002/actual_external_application_wall.json':'1a80c1e0e9cf82cd2bb1704ea917b51d0c7dc77c12aff9d8a30764dc3703c3e2',
 'single_owned_C18_prepare_002/receipt.json':'fe658c332d88175a84fc9aeaa3fcd0e8bd161966ebd2707c7d4e40927840a733',
 'single_owned_C18_prepare_002/verification.json':'f01b6e3f743ce5fb73f561d71774d1e9960c2cea36969dffef099bb290510480',
 'single_owned_C18_prepare_002/root_saved_review_001.json':'e2a661c6295e030ad1dff3171d9b4225bc1410b35981055ddefd655e185023b3',
 'single_owned_C18_prepare_002/actual_compact_summary_001.json':'f0f7661f8b848c6033dd78e2702c62d2159727559fa5220c608c9b7877242802',
 'dpc_pure_001/receipt.json':'ddb078e7b08dcae837921b6f579b7fe9656a3cdd5c0639a7daebbf60f242be6e',
 'dpc_pure_001/tests.xml':'d726b849cff82faf021f069ab1f63e7d312fbd3a9edb44e2a6a09cff009609da',
 'dpc_pure_001/external_application_wall.json':'8a4856cdfd0b53e88caee7e1d6eea737f69b9567bb5532a8a081489627822820'}
for name,digest in pins.items(): assert sha(OUT/name)==digest,name
for name in ('user_resume_20261015_001/owned_C18_saved_readback_001_correction.json',
             'user_resume_20261015_001/static_proof_literature_root_001.json'):
    pins[name]=sha(OUT/name)
other={str(ROOT/'outputs/si65p1/receipt.json'):'9f4616c5cb6fc3bcb83bb109302b9c4e60d0f2ceb61c8040e3d464784918e533',
       str(ROOT/'outputs/si65p1/tests.xml'):'87dc709d47788df65ddd40414a4bce2ba77e0c1ec781f164367f46191d2eaeed'}
for path,digest in other.items():assert sha(path)==digest,path
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_045';backup.mkdir(exist_ok=False)
for name in names:(backup/name).write_bytes((DOC/name).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes()); a=state['active_experiment']
state['current_stage']='三个总目标仍未达标。新C publisher actual18一次运行关闭：222.5240049/600秒，16闭合/2初始ACK缺失未知/0invalid/0under100；闭合414.5762–885.403ms，中位579.4566ms。normal6全部5任务严格不回退，1改善5相等。root独立核全部18完整证据bytes/ledger/clock及正常配对。fixed2 C编码器83纯测试和source_proof诊断71纯测试通过，metadata准备中，实际ABBA32/65诊断尚未放行。'
a['single_capture_owned_C_publisher_binding'].update(status='actual18_closed_saved_root_integrity_reviewed',metadata_seconds=38.3158153,metadata_sources=218,compiled_archive_files=67,full_toolchain_files=6124,actual_whole_seconds=222.5240049,closed_roots=16,unknown_roots=2,invalid_roots=0,under100=0,closed_median_ms=579.4566,closed_min_ms=414.5762,closed_max_ms=885.403,normal_pairs_strict_all5_nonregression=6,normal_improved=1,normal_equal=5,actual_direct_C_supported=None,actual_fallback_count=None)
a['single_capture_owned_C_actual18_limits']=[
 '三遍6124核验均保留。C setup4691.7507ms/close4210.2906ms，RPC startup876.9131ms/close318.9342ms，全在600内，无摊销扣除。RPC8次，baseline8完整8、额外candidate8。',
 '基线normal2改善4相等，此次1改善5相等。block0_load2预算分支初始边2变1，612.4918变885.403ms。17条仅initialedge+laterchoices匹配，不证明全执行相同。不同轮次不是ABBA，不将中位下降当作因果收益。',
 'root saved-only独立核18完整normalized canonical bytes/ledger/时钟，全部raw outcome与saved审计一致，重算正常五项差值；未重演native/model/C。完整物理/endpoint/RPC仍属已通过producer审计，不冒称第二套独立物理检查。',
 'root reader001在初始ACK未知行误要求audit_status=passed而失败，未写报告。保留001，002精确检查两ACK行为passed_with_retained_unknown且closed=false，其余passed且closed=true。生产证据未改，未知不升级。']
a['typed_C_delivered_peer']={'status':'pure83_passed_metadata_pending','pure_seconds':8.706633,'source_count':95,'expected_actual_calls':32,'fixed_inputs':[27212,27215],'actual_performance_dispatched':False,'scope':'同原validator，仅B digest global替换；完整typed异常args、原拒绝/expiry次序、fallback原一次、返回身份保持。全source/archive预检，整数tick预算守门。历史两query都absent，不代表成功路径/全天频率。'}
a['source_inventory_cost_design'].update(status='pure71_passed_metadata_pending',pure_seconds=23.1898688,pure_tests=71,actual_diagnostic_dispatched=False,source_proof_cache_modified=False)
a['literature_static_proof']={'record':'user_resume_20261015_001/static_proof_literature_root_001.json','scope':'Jones1996 partial evaluation的static/dynamic区分与语义等价；Necula/Lee1996 consumer proof checker。仅设计启发，本项目AST/hash/finite测试不是形式证明或PCC。动态cut/current/ACK/wire/deadline不可缓存，coldsetup仍计入。'}
actions=[
 '审查 fixed2 C validator 的新准备plan，通过后独占一次原32 ABBA/120，保留完整bytes/异常/direct/fallback与所有入口出口成本；另一65诊断等该窗口关闭。',
 '审查source_inventory诊断准备，另独占一次固定65原source_proof/cProfile/120，无缓存改动、无model/native；完整proofbytes与未知分母不能省。',
 '基于actual18已保存分阶段时钟分析完整请求剩余成本，精确区分不重叠/嵌套/未知，确定下一项高影响修改。保持原100ms与full32最终目标。',
 '只有实际digest收益支持后再设计全天复跑；原28506 offered、严格正常保护、全天独立证据、完整full32 100ms、同信息强在线方法联合有效性仍开放。',
 '按成本证据设计静态proof复用，cold成本、依赖变更失效、动态状态保护与全部32分支保持；实施前源码和行为验证，不凭文献宣称正确或加速。',
 '持续记录失败/修复/限定结论，无新指令不发GPTPro、不push/commit。']
state['next_actions']=actions;a['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone045\n\n新完整请求publisher实际18与保存完整证据回读已关闭，仍0/18在100ms内。两项下一诊断的纯测试通过，正在准备独立测量；三个总目标仍未达标。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone045：实际18闭合，100ms和联合目标仍未完成\n\n短路径metadata002在38.3158153/120秒通过，218源码/67native归档/6124工具链，归档最长243字符。一次actual18完整Python222.5240049/600秒，16闭合、2 initial_ack_drop3未知、0invalid、0/18在100ms内。闭合延迟414.5762–885.403ms，中位579.4566ms。normal6全部5任务严格不退化：1改善5相等。RPC8请求，8 baseline/8完整baseline/8额外candidate。C setup4691.7507ms、close4210.2906ms；RPC startup876.9131ms、close318.9342ms，全部原样计入。C实际module/spec/loader/DLL入口出口通过，direct/fallback次数未知。\n\nroot逐18压缩原件重构完整canonical证据bytes/hash/ledger和完整时钟，重算所有正常5任务差值，核218当前/独立归档及67native归档；结果e2a661c6…023b3。完整物理/endpoint/RPC仍采用producer原审计，不冒称新物理验证器。首个root reader错误要求未知行也标passed；失败无报告，保留源码和修正记录，新002精确检查原passed_with_retained_unknown标签及closed=false，无生产源/证据改变。\n\n基线normal为2改善4相等，此次1改善5相等；block0_load2预算分支旧选边2变默认1，完整612.4918→885.403ms。其余17仅保存选择字段一致，不能证明完整时序一致，不把跨轮中位下降认作因果加速。\n\n下一C digest原validator固定2 ABBA源码83纯测试通过，8.706633/120秒，95来源；固定65原source_proof诊断71纯测试通过，23.1898688/120秒。两者准备中，实际执行须分开独占，尚无收益结论。Jones部分求值和Necula/Lee proof checking文献只指导静态/动态边界与依赖失效设计，本项目目前不是形式PCC。\n'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 75. 新发布器实际根仍远超100ms，保留决策退回与未知\n\n18原分支完整运行后16闭合2未知，六正常配对均严格不回退，但仅1改善，较旧轮2改善少一组。60ms截止会改变选择，不能拿跨轮延迟变化认作优化收益。所有完整证据保存并独立核canonical bytes/ledger/clock。下一步依据阶段成本及隔离ABBA优化，100ms/full32/全天/强在线联合标准不变。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,'other_evidence':other,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'actual18_closed':True,'new_native_branches_since044':18,'external_messages_sent':0}
with (HERE/'milestone_045.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_045.json')}))
