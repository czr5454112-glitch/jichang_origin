from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent;ROOT,OUT=HERE.parents[3],HERE.parent;DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'owned_full32_runtime_prepare_001/root_saved_review_001.json':'1a0927f87248183ed4535e2e74cbe747e2a7f7e1e45424d84708545c8deb1054',
 'owned_full32_runtime_prepare_001/receipt.json':'a6cebda0a1321415bc5ccdf4ebd1d8889a96adf73e62e3f5af973b2b350e94ed',
 'owned_full32_runtime_prepare_001/external_application_wall.json':'60129533dd298c95b451c8421d46823ba29933073461e8c8f4f6e12c37fc0d2e',
 'source_inventory_cost_investigation_design_001.json':'f35eccbc2d18da823e52d0cea3511627e14856a21cb7da09732d354b37392e64',
 'single_capture_owned_codec_campaign_pure_001/fixture_correction_before_002.json':'fcd1fbdb66277630d8636c6629910dae0e850feea47cae0fedafeb03c0ae140c',
 'single_capture_owned_codec_campaign_pure_002/receipt.json':'165f0bd2bcc148b5b34230de56e2fae033338a80a51cb0ae5d1e45f3d07b9958',
 'single_capture_owned_codec_campaign_pure_002/tests.xml':'80e491b982331e49b7c4db91c62627429ea9acecf77a493fc5562c9e69af99ce'}
for p,d in pins.items():assert sha(OUT/p)==d,p
failed='initial_owner_route_single_capture_owned_codec_campaign_prepare_001'
for p in (failed+'/preparation_failure.json',failed+'.metadata_worker.stderr.log',failed+'.metadata_parent.json'):
    pins[p]=sha(OUT/p)
oldcases=ET.parse(OUT/'single_capture_owned_codec_campaign_pure_001/tests.xml').findall('.//testcase')
newcases=ET.parse(OUT/'single_capture_owned_codec_campaign_pure_002/tests.xml').findall('.//testcase')
assert len(oldcases)==38 and sum(any(n.tag=='failure' for n in row) for row in oldcases)==1
assert len(newcases)==38 and not any(n.tag in ('failure','error','skipped') for row in newcases for n in row)
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_044';backup.mkdir(exist_ok=False)
for name in names:(backup/name).write_bytes((DOC/name).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());a=state['active_experiment']
state['current_stage']='三个总目标仍未达标。C编码器159功能测试通过。owned runtime完整96实际验证已关闭通过：96等价/0unknown、48组，170.4947017/360秒；根另核96完整bytes和113语义点。新完整请求发布器campaign38合成测试修复夹具后通过；metadata001遇265字符归档路径FileNotFound，保留失败，获准只改短输出目录执行metadata002，不改源码或门。实际18尚未运行。'
a['owned_runtime_full96'].update(status='closed_and_independently_saved_reviewed',exact_rows=96,unknown_rows=0,exact_groups=48,unknown_groups=0,external_seconds=170.4947017,worker_seconds=166.94014920000336,execution_counts={'initial_engines':48,'initial_advances':48,'prefix_same_resumes':65,'future_forks':96,'future_resumes':96},root_saved_review='owned_full32_runtime_prepare_001/root_saved_review_001.json',independent_full_byte_pairs=96,independent_retained_points=113,independent_current_archive_evidence_rehashes=829)
a['single_capture_owned_C_publisher_binding'].update(status='campaign_pure002_passed_metadata001_failed_short_path002_authorized',campaign_pure_seconds=17.8191388,campaign_pure_sources=161)
a['single_capture_owned_C_campaign_failures']={
 'pure001':'37passed/1failed,19.7672193/120秒。fixture缺native_contract_reference.path，在原worker读path处进入unknown_setup，未抵达fakepredictor/positivebranch；相关negative通过不证明期望路径。仅修test fixture和加强无setupfailure/raw_saved/constructor_refused断言，四业务文件不改。pure002全38通过，旧001全保留。',
 'metadata001':'14.0959769/120秒退出1，源码归档xb目标265字符FileNotFound，父目录实际存在；未生成campaign.json，未到工具链核验，0C/native/model。路径长度是待短路径验证的原因假设；保持全部源和门，仅新输出single_owned_C18_prepare_002，先校验整个归档最大长度，原120不变。'}
a['source_inventory_cost_design']={'status':'source_and_synthetic_draft_only','design_sha256':pins['source_inventory_cost_investigation_design_001.json'],'fixed_source_proof_calls':65,'proposed_seconds':120,'method':'未改的source_proof，外层timer+cProfile，逐调用完整proofbytes；不monkeypatch身份门、不改缓存。65为完整provider固定路径，不是完整driver全部proof次数。','not_speed_comparison':True}
actions=[
 '关闭新短目录metadata002并审核完整请求C发布器campaign。保持三遍6124工具链检查、原18/600、60ms决策和100ms完整请求及所有失败分母；通过后优先一次独占实际18性能窗口。',
 '完成typed-C原delivered_peer固定2输入ABBA32源码及focused synthetic门。新执行closure明确合并原16/旧依赖/新harness，完整字节、返回、拒绝/异常与direct/fallback分列；root审后另独占实际窗口。',
 'owned完整96已独立保存回读通过，不重复实际模型。实现并审查固定65次原source_proof的成本诊断，保留完整proof、未执行/失败行、默认GC及全120外时钟；不得与实际18/ABBA并跑。',
 '根据测得归因再设计静态proof复用，源码/MRO/code/default/closure/globals等依赖必须有边界核验，动态cut/current/ACK/wire/deadline及32完整分支不随意删减。',
 '实际校验器收益证据成立后才安排全天600。原28506 offered、严格正常保护、完整full32的100ms、与同信息强在线基线比较联合有效性仍全部开放。',
 '持续记录问题、修复与限定结论；无用户新指令不发GPTPro、不push/commit。']
state['next_actions']=actions;a['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone044\n\n完整96候选实际验证及独立保存回读均通过。下一步是新完整请求发布器实际18、原始查询C编码ABBA和静态源码检查成本归因；三项目标仍未达标。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone044：完整96等价通过，保留两项准备失败\n\nowned full96一次实际运行完整关闭：96等价/0未知、48组/0未知，48context、48engine、48advance、65prefix resume、96fork与96future resume。整Python170.4947017/360秒。根另作仅保存数据的独立审查：96对完整解压预测字节、48组113保留语义点、terminal、动作、计数及829当前/归档/证据哈希均一致。历史图诊断仍仅参考，没有重复测量或虚构隔离指标。此结果不是与旧216秒的受控速度对照，亦不是实际native隐藏态、在线保护/效用或完整100ms达标。\n\n新publisher campaign首次38合成测试37过1失败；缺少fixture的native_contract_reference.path，使原worker在fakepredictor前进入失败路径。根阅读原worker和失败日志确认，修复只涉及fixture与更强路径断言，原四业务文件冻结。pure002全部38通过，17.8191388秒；首轮相关negative未到预期路径的限制明确记录，不能把旧37过升级。随后metadata001在14.0959769秒退出1：265字符归档目标xb写入FileNotFound，父目录存在，未生成campaign.json/未到工具链/C/native/模型。获准保持源码与所有门，只换短目录single_owned_C18_prepare_002并先核最大路径；原120预算不变，旧原件保留，原因暂标路径长度假说。\n\n下一source inventory诊断设计已冻结，固定65次原source_proof（provider1+fork32+resume32），timer/cProfile仅测原调用，完整proof字节比较、全分母与120外时钟保留。源码读取/AST/compile重建可作为未来静态proof候选；当前cut和任何模型/ACK/current/时效约束不得被当作静态数据缓存。尚未执行诊断或修改缓存。\n'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 74. 完整输出等价成立，性能归因仍需单独测量\n\n96候选完整保存字节和全部保留语义点独立匹配，支持在限定私有状态所有权下移除诊断遍历的实现等价。170.49秒是整轮成本，不是100ms请求，也不能与旧不同时间运行直接推导收益。测试夹具错误和归档长路径失败分别保留，用新证据关闭；不降低业务验收条件。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,
 'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'root_sessions_active_at_checkpoint':[],
 'actual_full96_closed':True,'new_native_branches_since043':0,'external_messages_sent':0}
with (HERE/'milestone_044.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_044.json')}))
