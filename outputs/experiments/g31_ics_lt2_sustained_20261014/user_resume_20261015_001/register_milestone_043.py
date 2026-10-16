from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT,OUT=HERE.parents[3],HERE.parent;DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'planning_v2_C_encoder_gate_prepare_003/plan.json':'d6912d695e36707dbba6bd7a0359e5ec6c6ed1a964323e99c4aae4fecf28579b',
 'planning_v2_C_encoder_build_002/receipt.json':'fb2c4ddfabfc0277da6f40d397ecba86e50c4a9cb9f67820ebd11f4346d56979',
 'planning_v2_C_encoder_build_002/external_application_wall.json':'c9ae7c89205f72c87734fc60d16a4e9b9c9d59a78031e047e20dbae2422aeaa4',
 'planning_v2_C_encoder_functional_002/root_saved_review_001.json':'395d5f14dbbcb2b8d2b0d842fdaacd25075f86b42e2849a70125329a2c821521',
 'planning_v2_C_encoder_functional_002/receipt.json':'3116ddf66830d8f3f70cb6dc6651a29ecf539bf328db4ae1e28906edc49212cd',
 'planning_v2_C_encoder_functional_002/external_application_wall.json':'50709239e57767b579b79f03235a0aa6d082b30487798b4f69eddf8002bedb32',
 'live_owned_initial_runtime_source_prepare_002/root_source_review_001.json':'2c98cccfb5f0a982cdfe2797588cb3284d69e72e19ac4d38022d2d80eae7f40d',
 'single_capture_owned_codec_source_prepare_001/root_source_review_001.json':'23e161691b1727c963ffd8386b77161ed3a976f08f43b9e945b13f5789626eda',
 'owned_full32_runtime_prepare_001/root_review_001.json':'05a8502fabb9ce7436571e4f6675b957e8f0074fd30125d0f179a727264cd312'}
for p,d in pins.items():assert sha(OUT/p)==d,p
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_043';backup.mkdir(exist_ok=False)
for name in names:(backup/name).write_bytes((DOC/name).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());a=state['active_experiment']
state['current_stage']='三个总目标仍未达标。typed-C 新build002成功115.9467724/120秒；functional002成功88.1473211/120秒，159测试、126直接C完整字节+10原回退独立核对通过。归档修复v2通过71测试及188源码独立审查，完整96候选实际验证已启动，结果待关闭回读。完整请求C发布器接线45测试及156源码审查通过，新actual18 campaign正在38纯测试阶段，尚未实际运行。'
a['typed_C_build002_and_functional002']={'build_seconds':115.9467724,'functional_seconds':88.1473211,'tests':159,'direct_full_byte_pairs':126,'fallback_full_byte_pairs':10,'root_saved_review':'planning_v2_C_encoder_functional_002/root_saved_review_001.json','status':'accepted_synthetic_only','binary_sha256':'a690ba550c49cd437afbeb2286e6a2082213ce44d3f1f64840e1b9d41f68a809','limits':'未读原始fixture、未测速度、未运行全天。原build001日志冲突失败保留。v3仅改父日志，两层真实打开组合测试39通过；16项目/7779工具链/3082运行库门保持，实际加载模块与DLL来源已记录。'}
a['runtime32_source_archive_fixed_v2']={'status':'accepted_source_only','tests':71,'pure_seconds':58.7451486,'canonical_sources':188,'root_review':'live_owned_initial_runtime_source_prepare_002/root_source_review_001.json','limits':'旧001归档仍被拒绝，旧同字节重写行为保留记录。新v2先规范ROOT相对路径、相同字节去重、全目标containment和非live预检，独立归档通过；三个runtime核心没有改变。'}
a['owned_runtime_full96']={'status':'one_actual_run_in_progress','plan_sha256':'6f4434bcf87d8e35d709eabfed5561b6461adde71389b92c8042072a9e6c4bc5','driver_tests':20,'source_count':191,'root_evidence_rehashed':447,'seconds_limit':360,'scope':'原48组/96后缀。逐项比较完整输出及保留的语义点、terminal、动作、计数；历史图诊断只作参考。动态检查、每full32的16context/32clone/65inventory/80cut不变。无native/C、无缓存、无100ms声明。'}
a['single_capture_owned_C_publisher_binding']={'status':'accepted_source_only_campaign_pure_in_progress','binding_tests':45,'binding_pure_seconds':17.823796,'binding_sources':156,'new_campaign_focused_tests':38,'actual18_runs':0,'scope':'verified Candidate及原fallback，实际直接C数量unknown；不重复preflight。完整18输入/600秒、60ms决策截止、100ms完整请求、所有ACK/current/drain/物理和未知分母保持。实际campaign先保留三遍6124工具链核验并全收费，独立性能窗口前不得运行。'}
actions=[
 '关闭并审核正在运行的owned完整96：原48组/96输出、所有语义点及计数、来源入口出口、外层360秒；失败和unknown全部保留。此轮不作配对速度或100ms结论。',
 '基于已接受typed-C功能门编写原delivered_peer固定2输入的ABBA32。先审源码和合成门，再独占性能窗口运行；比较完整字节、全返回和拒绝/异常，资源失败不回退。两fixture历史均absent，不能推广全天频率或成功覆盖。',
 '新完整请求发布器campaign通过38纯测试和规范源码准备后，审查一次原18/600实际执行。冷setup/close、工具链、原始完整请求均计时，保留原16closed/2unknown/0under100基线。',
 '完整96通过后，先测静态source inventory/AST重建成本，再设计单次有界proof复用；动态cut/current/ACK/wire/deadline不可混入静态缓存，来源变化仍必须拒绝。',
 '全天仍要求原28506 offered与严格正常保护；只有实际校验器收益证据才支持再跑600秒桥接，不能用两个样本或合成C结果替代。',
 '继续优化完整full32请求及同信息强基线联合有效性。三目标均未完成；保留问题与修复记录，未经用户指令不发GPTPro、不push/commit。']
state['next_actions']=actions;a['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone043\n\nC编码器功能验证通过；归档修复已独立核验。完整96候选实际验证和完整请求新发布器准备正在推进，三项目标仍未达标。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone043：C功能门与两个源码修复门通过\n\n新build002在115.9467724/120秒内完成，目标二进制a690ba55…a809封存；functional002在88.1473211/120秒内完成159测试。126直接C与10原fallback分别保存完整bytes。根独立读取136对完整字节、159 XML用例及外部启动到退出时钟、命令/plan/runner/wrapper/output绑定，确认通过；不重加载C、不重复全部工具链。实际加载路径、spec、ExtensionFileLoader及DLL路径/哈希由原功能运行核验，根核对记录并重新哈希实际文件。原build001失败不改，v3父日志修复39合成测试覆盖真实父子日志打开组合。此轮没有原始fixture/实际速度/全天成功证据。\n\nowned runtime归档v2通过71测试（58.7451486秒）和188规范唯一源码当前/独立归档核验。旧001的336声明、180错误归档及同字节当前文件重写仍保留为失败。新full96 driver20合成测试通过，191源码及447证据根重核后启动一次实际96/48验证，共享360，尚待结果。只移除诊断图编码，所有动态检查和完整复制保持；历史图指标绝不冒充本次测量。\n\n完整请求的C+owned decoder发布器接线45测试（17.823796秒）、156源码根复核通过。新actual18 campaign/runtime/saved verifier/launcher及38合成测试已源审，正在一次120秒纯门；尚无实际18执行。保留verified Candidate原Python fallback，实际直接C数量unknown，不加请求内重复preflight，不作扩展卸载或逐样本循环清理声明。第一轮保留三遍6124工具链核验并全计600，避免同时改变出版路径和来源门。全部100ms/60ms、ACK/current/drain、物理及unknown标准不变。\n'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 73. 功能正确、运行等价与任务达标分开验收\n\nC编码器159测试和136完整字节对通过，只建立限定输入下的编码等价；原回退10不算直接C支持。归档v2及完整publisher接线分别通过，下一轮实际96和实际18仍须保留全分母、完整计时和原动态门。任何一项不能单独证明全天、100ms或联合方法有效性。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,
 'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'root_sessions_active_at_checkpoint':[],
 'agent_actual_full96_in_progress':True,'new_native_branches_since042':0,'external_messages_sent':0}
with (HERE/'milestone_043.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_043.json')}))
