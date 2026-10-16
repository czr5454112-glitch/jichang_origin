from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];DOC=ROOT/'docs/g31_ics_circulation'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'outputs/bsvp1/root_saved_review_001.json':'e9ac599fe2a9cc90ab48e1a5a2debbbf18c5bc8995fece408a895ead041cc1c1',
 'outputs/bdbv2p1/root_saved_review_001.json':'e8a65188f8c104d317b5b5f631b4e7f0b083479768c5d714d087753356045941',
 'outputs/odp1/root_saved_review_001.json':'14ce8458c5763018af7f50ef9dfb0325efccd7dcf32db2d85ff7a4a08529678c',
 'outputs/experiments/g31_ics_lt2_sustained_20261014/bcdp2/root_saved_review_001.json':'b61f2bf610fc67d349c418fda042967daa6f137979af51b11b710d29b5bbed46',
 'outputs/sicm1/root_prelaunch_review_001.json':'cd7bbb44f7929a5df82874c298f95f8964f9e293688e49ef2dd1946acccb0fed',
 'outputs/sicm1/root_saved_review_001.json':'2998f1def4ecb95de857cf7ebc3d0267e5223abd4d1ca2a649879b5dd0f295e5',
 'outputs/sicm1/actual_external_application_wall.json':'f33d1debdde90b47c59f6db13b1c432bb571546a37d499aca2fe46895333298a',
 'outputs/sicm1/actual_scalar_summary_001.json':'c79fa1fc427b92a0e4b42d955f7c414b3cca59f97abbd6d5c4d8bb6abb9b0984'}
for p,d in pins.items():assert sha(ROOT/p)==d,p
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_050';backup.mkdir(exist_ok=False)
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());active=state['active_experiment'];work=active['new_static_and_bridge_work']
state['current_stage']='三项目标未达标。static inventory实际18闭合16/未知2/0在100ms内，闭合中位308.20205ms，normal6全五job严格保护、2改善4相等；完整保存根审通过。全天共享源码遍历27门通过，新600 metadata准备中。模型静态float v2的25+接线8门通过，真实1cold1warm待新metadata。在线initial dispatch24通过，后续保留初始suffix仅源码工作，非rolling证明。'
work['actual_request_integration']={'directory':'outputs/sicm1','status':'actual18_closed_and_root_saved_review_verified',
 'whole_seconds':210.3875392,'closed':16,'unknown':2,'under100':0,'closed_ms':{'min':174.4935,'median':308.20205,'max':601.8734},
 'normal_pairs':6,'strictly_improved':2,'equal':4,'constructor_nested_wall_ms':{'min':8.2544,'median':9.6768,'max':11.8709,'sum':179.8264},
 'cold_static_bind_ms':275.8036,'sources':232,'native_archive':67,'root_review':pins['outputs/sicm1/root_saved_review_001.json'],
 'limits':'No ABBA causal speed attribution; constructor wall is nested, not CPU/inventory-only. Finite2, not full32 or complete100ms. All ACK unknowns retained.'}
work['model_v2']={'status':'synthetic25_and_required_driver8_passed_real_dependency_unexecuted',
 'static_float_bits':'exact IEEE64 inf/NaN/sign/zero; finiteJSON and model unchanged',
 'pure25':'outputs/bsvp1','pure8':'outputs/bdbv2p1','v1_failure':'outputs/bdb1',
 'next':'Newbdb2 metadata with required8 gate pinned at prepare/actual checks, then1cold1warm120 actual gate before full96.'}
work['all_day_driver']={'status':'new_shared_source_union27_passed_bcdm1_metadata_authorized',
 'directory':'outputs/experiments/g31_ics_lt2_sustained_20261014/bcdp2','tests':27,'sources':138,
 'old_domain':134,'added_files':4,'whole_seconds':53.3848021,'completed_source_collections':5,
 'root_review':pins['outputs/experiments/g31_ics_lt2_sustained_20261014/bcdp2/root_saved_review_001.json'],
 'next':'Separate source-reviewed metadata120 then full saved audit600; original37270/27218/28506/22/C checks unchanged.'}
work['online_initial_dispatch_draft']={'status':'synthetic24_passed_root_saved_review_verified_initial_only',
 'directory':'outputs/odp1','source':'scripts/experiments/g31_ics_circulation/live_obligation_online_initial_dispatch.py',
 'sha256':sha(ROOT/'scripts/experiments/g31_ics_circulation/live_obligation_online_initial_dispatch.py'),
 'tests':24,'sources':154,'whole_seconds':26.6706411,'root_review':pins['outputs/odp1/root_saved_review_001.json'],
 'failure_evidence':'Actual Transport code with fake sessions verifies own row survives getter/native/reply-copy failures; clock/export secondary failure preserves original exception. No retry.',
 'limits':'No actual native/model; no later re-estimation, complete100ms, robust protection or joint usefulness claim.'}
actions=[
 'sicm1实际18/root完整保存核验通过但100ms仍0/18。审新的saved-only成本分析，把constructor仅作为嵌套区间，找其余174–602ms成本，保留所有原始失败和未知。',
 '全天bcdp2新27门/root通过；bcdm1 metadata已授权唯一120。审其plan/完整138档案与实际600 wrapper，再独占一次全37270+27218审计，不扩时不删记录。',
 '模型v2 static25+mandatory wiring8/root通过；封新metadata固定证据并审核，后执行原1cold1warm真实依赖120门，不能跳过实际域直接声称全96等价或收益。',
 '在线initial dispatcher24/root通过。新retained-suffix policy仅改真实标签并保留全部历史/current/wire/union guards；准备7方法×3场景公平前瞻runner，不读peer私有提案，不用全局一致控制。后续rolling重估仍独立缺口。',
 '三项目标和强标准不变：全天原流1x/2x严格正常保护、full32完整100ms、实际联合方法有效性；任何证据门不替代目标。无用户命令不发GPTPro、不push/commit。']
state['next_actions']=active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone050\n\n实际18进一步降低观察延迟，100ms仍未达标；全天和模型绑定继续推进。\n\n'+'\n'.join(f'{i+1}. {a}' for i,a in enumerate(actions))+'\n',encoding='utf8')
note='''

## milestone050：静态清点复用实际18完成；0/18达到100ms

sicm1 metadata40.2612564/120秒，232源码/67native档案/原18输入一致。一次actual完整Python210.3875392/600秒，16闭合、2 ACK丢失未知、0 invalid，0/18在100ms内。闭合174.4935–601.8734ms，中位308.20205ms；normal6全部五任务严格不退化，2改善4相等。root独立读取全部18压缩原件并重建canonical证据bytes、hash、完整时钟和normal差值，另把全部18构造区间对应到真实root区间，根审2998f1de…295e5。旧579.4566ms到新308.20205ms只是跨轮观察，不宣称全差值为因果加速。block0_load2预算分支实际初始路径从默认1变2，其余17选择字段相同不等于全过程相同。

构造完整墙钟8.2544–11.8709ms，中位9.6768，总179.8264ms；冷静态绑定275.8036ms含在C setup3998.4101ms内，C close3552.3811ms。以上都保留计费，构造是嵌套wall而非CPU或独立库存开销。RPC8 baseline+8 candidate，两个unknown保留。继续分析剩余开销，不能以局部10ms代替完整100ms。

全天新bcdp2共享visited按原resolver语义保留134旧域+4新源，27/27通过，53.3848021/120秒；五次source_union完成，完整current/archive/loaded/journal根审b61f2bf6…bed46。旧bcdp1的120超时仍失败，原12未知现在新门实际执行；未重跑已通过37。新bcdm1仅metadata授权，完整600尚未执行。

模型v2 exactIEEE float25门通过26.9156757/120，206源；新接线8门通过20.9954308/120，209源，并成为未来prepare/actual强制证据。真实v2 cold/warm依赖尚未运行，旧非有限float失败不可覆盖。在线initial dispatch新24测试通过26.6706411/120，154源；真实Transport/LocalTransport代码仅接fake session，证实失败时保存新own row、无reply不推断未提交、次生clock/export错误不覆盖原异常。仍无实际online21/rolling证书。

根wrapper生成中一次过宽字符串25→24替换误伤SHA256字段/哈希，源码检查在执行前发现；错误草案保存odp1_preexecution_wrapper_broad_replace_error.ps1，改成仅明确计数字段替换后才运行一次odp1。没有失败执行被重标为成功。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 80. 静态清点实际接入有观察改善，完整100ms仍0/18\n\n正常六组保持五任务严格保护、两组改善。源码收集共享visited27和模型float边界25/接线8为工程正确性门；online dispatch24仅功能。没有新rolling联合方法有效性、全日完成或方法新颖性结论。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'completed_actual18':True,
 'bcdm1_metadata_authorized_unreviewed_result':True,'external_messages_sent':0}
target=HERE/'milestone_050.json'
with target.open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(target)}))
