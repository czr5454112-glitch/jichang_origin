from pathlib import Path
from datetime import datetime, timezone
import hashlib, json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];DOC=ROOT/'docs/g31_ics_circulation'
OUT='outputs/experiments/g31_ics_lt2_sustained_20261014/'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
pins={
 'outputs/bdb2/root_prelaunch_review_001.json':'3cb7407cebd9f9c0b28e4b7eba2ac860394696917ad3fc77ca1bde8d50845a64',
 'outputs/bdb2/root_failure_readback_001.json':'85db4de8fbfb8d75f20853c4eb1b00837117ec012d222d5e2ed11fd274a01b60',
 'outputs/sicc1/saved_readback_001.json':'8caeb6f09021db270b0d0f53901a45f9c0c3acd5a81061f881c591bed9b0afff',
 OUT+'bcdm1/root_execution_review_001.json':'e73ddb7f3071a56ebdc9a22f572d04d0fafb366a7f530042b3413966d49ac440',
 OUT+'control_timers_bcdm1_terminal_readback_001.json':'6b8b01f7e4682a8a3aae4bf6f8fa9c4e5410eba69d70a350f3d4b7762680bb64',
 OUT+'lorp1/root_saved_review_001.json':'d118b80721d805d88e963c0894dfef80b95bfd06ee51e8eb395b89b17c1753d9',
 OUT+'oimp1/root_saved_review_001.json':'b282b481d50742210207e339b42c852d1bb3c54ceba92a921fdbdff46708194a',
 'outputs/online_initial_methods_source_review_legal_001.json':'b25caa5d847015615a9092b4b2878bcf8208cb161d038efca96579de7d930da3',
}
for name,digest in pins.items():assert sha(ROOT/name)==digest,name
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_051';backup.mkdir(exist_ok=False)
for name in names:(backup/name).write_bytes((DOC/name).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());active=state['active_experiment'];work=active['new_static_and_bridge_work']
state['current_stage']='三项目标仍未达标，持续恢复中。sicm1保存成本18整数分区核验通过，16闭合总5197.8033ms，其中未分类前段2626.4559ms/收尾1380.0546ms；完整100ms仍0/18。bdb2真实绑定在__future__._Feature静态对象失败，0proof；独立v3精确对象支持源码审过、42门待执行。bcdm1 saved600在51.430112秒因C固定启动环境与PYTHONPATH设置不一致失败，未进完整回放；新bcdm2按原环境要求准备，不放宽门。retained22和online接线21均已通过并根审；actual online21未执行。'
work['saved_request_cost']={'directory':'outputs/sicc1','status':'saved18_integer_partitions_readback_passed',
 'closed':16,'unknown':2,'under100':0,'closed_total_ms':5197.8033,
 'exclusive_closed_ms':{'native_envelope':40.9577,'refresh_including_query':709.7056,'RPC':280.3935,
 'constructor':160.236,'unclassified_prefinal':2626.4559,'finalization':1380.0546},
 'next':'Versioned passive constructor prelude diagnostic; no residual function attribution or old constructor savings inference.'}
work['model_v2']['status']='actual_bdb2_failed_before_original_proof_at_canonical_future_feature'
work['model_v2']['actual']={'directory':'outputs/bdb2','whole_seconds':9.8205753,'cold_bind_ms':835.4619,
 'cold_requests':1,'warm_uses':0,'original_proof_calls':0,'source_count':209,'evidence_count':461,
 'failure':'unsupported_static_object at root:original_proof:_source_inventory:core.build_parts:lazy.check_sources:previous.check_sources:original.annotations',
 'v3_next':'Only exact canonical annotations object with pinned whole stdlib class/method/instance/live bindings, preserve all v2/original checks. 42 synthetic source reviewed; not yet executed.'}
work['all_day_driver']['status']='bcdm1_saved600_failed_C_startup_environment_before_large_replay'
work['all_day_driver']['actual']={'directory':OUT+'bcdm1','whole_seconds':51.430112,'owned_exitcode':1,
 'C_loaded':False,'full_saved_replay_entered':False,'reason':'Cgate expected PYTHONPATH absent; wrapper explicitly set src;.;tests.',
 'unobserved_environment':'Other three C-controlled inherited values were not captured; do not infer their actual values retrospectively.',
 'next':'Freshbcdm2 same full denominators600; ProcessStartInfo exact C-startup4 keys, null Remove not empty. Add cross-check to preflight; unchanged gates/driver.'}
work['online_retained_and_branch']={'status':'synthetic22_and21_passed_root_saved_review',
 'retained':{'directory':OUT+'lorp1','tests':22,'sources':128,'whole_seconds':25.7562985},
 'branch':{'directory':OUT+'oimp1','tests':21,'sources':153,'whole_seconds':28.6975458},
 'scope':'Own actual initial estimate retained; no later re-estimation or peer consensus gate. Retrospective A-initial/return+B-empty/later combination enters assessment only.',
 'actual_online21_executed':False,'strict_protection_or_100ms_or_joint_effectiveness':False}
actions=[
 '新bcdm2修正启动环境后，审唯一metadata120和新600 wrapper，保持所有37270/27218/28506/22/完整C entry-exit检查。bcdm1环境失败和原2400/600失败保留。',
 '源码审过的v3精确__future__.annotations支持先42纯门，再新actual1cold1warm依赖门；通过后才原full96同输出和未来全32接入。',
 'sicm1完整100ms仍0/18。最小新增prelude时钟只定位boundary.check和root metadata/append，保留原constructor clock/异常/收费，先源审和focused pure。',
 'retained22+online branch21/root通过；准备actual21的注册/完整保存验证，所有方法同信息同full32预算，独立owner proposal，强历史incumbent，实际五任务全保护。不要把synthetic接线当联合有效性。',
 '继续三项目标，不降低要求；记录所有失败和修复。无用户后续命令不GPTPro/外发、不push/commit。']
state['next_actions']=active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone051\n\n三项目标未达标，持续推进。\n\n'+'\n'.join(f'{i+1}. {a}' for i,a in enumerate(actions))+'\n',encoding='utf8')
note='''

## milestone051：成本分区闭合、真实依赖与环境失败保留、online接线完成

sicm1保存分析3.7905482/120秒，根读核18行全部整数区间和原输出绑定。16closed总5197.8033ms分为native envelope40.9577、refresh含嵌套query709.7056、RPC280.3935、constructor排他160.236、未分类prefinal2626.4559、完整finalization1380.0546ms。中位/嵌套不可相加，两个ACK未知仍保留；不把剩余间隙归因单个函数。新prelude最小诊断仅源码设计，未再跑18。

bdb2 metadata23.2445216/120、209源/461证据根审；唯一真实1cold1warm门9.8205753/120退出1。cold835.4619ms在canonical __future__.annotations对象依赖处被拒；原proof/privateproof/inventory均0，warm0，监视器有效。v1非有限float与v2_Feature两次失败都不覆盖。v3只补精确标准库对象的完整code/class/instance/live bindings，不删依赖；42门源码完成，尚未执行。

bcdm1 metadata22.8099833/120并经根预检后，唯一saved600在51.430112秒退出1。原C verify_plan拒绝PYTHONPATH：固定C gate为null，wrapper显式src;.;tests；C begin尚未走到load_candidate，完整raw/policy回放未开始。另三键当时仅继承，未捕获，不倒推。预检遗漏启动环境交叉核对，已记录；新bcdm2按原C四键精确Remove/Set，不改验收门、不增加600预算、不复用失败输出目录。

新retained-policy22/22通过25.7562985/120（128源）；online branch21/21通过28.6975458/120（153源），两者源码/owned/outer/XML/完整档案/加载域/有序成对journal根审。两owner只使用自身实际dispatch；缺owner不造policy、不同proposal不构造全局一致门；事后动作只用于原physical assessor。源审发现原拷贝cursor只含存在policy，违反native027 requested A/B与cursor keys完全相等契约；已在执行前保存错误草案，增加可逆cursor域修改和四种owner域真实约束测试。没有实际online21、rolling重估、100ms或联合方法收益证明。

根保存reader第一次误沿用另一harness的parent20行假设，两份新测试证据的reader在journal_count处拒绝，未写成功记录；源码/实际journal均为source2+archive2+check4+child2+check4=14。001失败helper保留，002仅修正期望14，原worker10/全绑定/有序平衡检查保留，保存复读通过，没有重跑测试。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 81. 在线initial接线可测，不等于已证联合优化\n\n同owner origin、强incumbent、原通知/执行门、事后组合和21synthetic闭合；尚无actual21或rolling/联合必要性结论。标准库静态绑定与C环境修复均工程工作。成本区间守恒不提供未测函数归因。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'external_messages_sent':0}
target=HERE/'milestone_051.json'
with target.open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(target)}))
