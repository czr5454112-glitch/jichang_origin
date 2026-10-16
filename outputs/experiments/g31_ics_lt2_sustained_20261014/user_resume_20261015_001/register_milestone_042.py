from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT,OUT=HERE.parents[3],HERE.parent;DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'planning_v2_C_encoder_build_001/failure_readback_001.json':'a25945b56d586bac3bee114f935a4facb016d7f9545b83198e362dffc4b56779',
 'planning_v2_C_encoder_build_001/receipt.json':'7024bc068d52648deb36236647942cf360dc3a3329db05bcdd4cd9304b703363',
 'planning_v2_C_encoder_build_001/external_application_wall.json':'8a92b3bda91b677f220c96740bc751a6c61a8c6c3bde9111a0f5dbef9bbf1777',
 'live_owned_initial_runtime_source_prepare_001/plan.json':'7333bc27f2905e0d5077c6f300639885478753ae91e97532bdde8f31c9be1ecd',
 'live_owned_initial_runtime_pure_001/receipt.json':'adcb2f7739df8204d9f3d21c9c8a14f335076962fcd3f03148075b7949314816',
 'live_owned_initial_runtime_pure_001/tests.xml':'a55a424bdc8f05eb11082c23da1818796e658a0cad0a665a73207b194fb0deca',
 'user_resume_20261015_001/owned_runtime_archive_failure_root_001.json':'e562fb2425a687a8de4a48933e3cddcf10d8235963d3c83f2f116355fd6e549c',
 'owned_initial_runtime_source_review_legal_001.json':'466010fb949e5da1f8322e4ce497ea3ed0ea8a0b8973be530e6f9439a11c66b5'}
for p,d in pins.items():assert sha(OUT/p)==d,p
failure=json.loads((HERE/'owned_runtime_archive_failure_root_001.json').read_bytes())
assert failure['declared_source_keys']==336 and failure['absolute_source_keys']==180 and failure['unique_canonical_sources']==186
assert len(failure['invalid_declared_archives'])==180 and failure['current_source_changed']==[]
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_042';backup.mkdir(exist_ok=False)
for name in names:(backup/name).write_bytes((DOC/name).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());a=state['active_experiment']
state['current_stage']='All3goals open. Actual6v2 andABBA24 findings unchanged. Cbuild001 failed before targetcompile due parent/worker build.stdout.log collision, whole109.857/120; v3 newparentlogs+composition tests inprogress. Ownedruntime47tests passed54.347/120 but sourcearchive REJECTED:336keys=180absolute+relative duplicates,186unique,180invalid archives; currenthashes unchanged. New canonical containment version required before full96. VerifiedC/ownedpublisher livebinding source+45synthetic preparation ongoing,0actual18.'
a['typed_C_build001_failure']='Closedexit1 in109.8570487s/120. CMake configureexit0/4.353031s maycompile compiler-identification probes; targetbuild subprocess notstarted because parent mode build.stdout.log alreadyexists where worker run(name=build) opensxb. Source entry/exit verified unchanged,0extensionload/functional. Alllogs/builddir preserved. Repeated prior delivered_peer stage-log lesson; newv3 must change onlyparent logs with inverseAST and fullparent-open/fakeworker-original-run composition tests for3modes, freshbuilddir002/prepare003. No blindretry or120extension.'
a['runtime32_source_archive_failure']='47synthetic passed54.3471295/120 including80_cut/65source/32wholegraphclone and16context counters. Narrow legal review466010fb...c66b5 covers3source only. Root archive review rejected sourceprepare001:336declaredkeys are180absolute inherited plusrelative closure,186unique. output/source/absolutename discardedarchive root and wrotecurrent samebytes; declaredsource/+absolute references180invalid. Rootrehashed allcurrent unchanged; timestamps maychange so no neverwrittenclaim. Rootfailuree562fb24...e549c preserved; actualmodel/native0, no sourcearchive acceptance. Newv2 mustcanonicalize ROOT-relative keys beforemerge, equalcontent duplicatesonly, rootcontainment andarchive!=live, newpure/prepare002 withfullpath tests;3runtimecore immutable.'
a['single_capture_owned_C_publisher_binding']='Newsource-only explicit binder composes verifiedexisting C+owneddecoderB into current singlecapture complete publisher. Newrequest subclass changes evidence only; same actualadvancechain/constructor/classcell/collect/observe/drain/currentguards; scheduler andbranch direct failure publish both privately rebound. B records remain in A completeevidence, collectionnormalization andmodel untouched. Rootreadsource+40synthetic tests;5canonical path tests added before first execution,45pureowned120 authorized.0Cload/native/model/actual18; campaign+failureaware savedverifier+binary acceptance stillfuture.'
actions=[
 'Cgatev3: preservebuild001; testparent andworker logs together forprepare/build/functional, same120 andfreshbuilddir002. Pure+metadata003 first, rootreviewbeforebuild002, then separatefunctional159/126direct/10fallback onlyafteracceptedbuild/externalclock.',
 'Repair ownedruntime sourcearchive innewv2. Never concatenate absolute keys intoarchive. Canonical ROOT-relative normalizedkeys,duplicateequalbytes,outputcontainment andno currentwrites; fullsyntheticprepare regression andfreshpure/prepare002. Old001 archived-closure claim rejected even though47tests passed.',
 'After validruntimearchive, finishfull96driver fixed48groups/96fulloutputs andallretainedsemanticpoints. Keep originalsourcediagnostics onlyhistoricalreference; no fakegraphflags.16contexts32clones65inventories remain beforeseparateoptimization.',
 'Run45synthetic liveCpublisher binding/path checks, prepare fullsource forrootreview. Futureactual18 mustload acceptedC, pinmodule/DLL, preservefull100ms/60mscutoff/current/ACK/drain/strictsavedunknowns. Current evidence remains actual18 0under100,2unknown.',
 'Typed-C correctness then actualdelivered_peer fixed2ABBA/fullbytes/fullreturn/exception beforeanotherall-day600. Originalall28506 andstrictnormalprotection remain; bothfixedfixtures absentreturn limitation retained.',
 'Threeoverallgoals remainopen, weakownedbundlecandidate notdefault. Record failures and fixes, continue; no GPTProsend/push/commit.'
]
state['next_actions']=actions;a['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone042\n\n实际六域已通过。当前修复构建日志冲突和源码归档路径错误，原失败保留；三个总目标仍开放。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone042：阻止把测试通过误当作构建或归档完成

C build001在109.8570487/120秒内失败。CMake配置成功4.353031秒，但父进程已经打开build.stdout.log，worker编译run以xb打开同名日志时报FileExistsError，目标编译未启动。CMake自身可能编译识别probe，不能写成全部compiler调用0。入口出口来源核验通过，0扩展加载/functional。该日志域问题此前delivered_peer已出现，属于复犯；必须增加父日志打开与真实worker日志打开组合测试，不能只检查命名字符串。新v3只改父日志、使用新目录、保持120及所有核验，旧失败不覆盖。

owned runtime47合成测试通过，whole54.3471295/120；源窄审未见限定域内动态guard阻断。但根全归档核验拒绝了prepare001：336个key实际包含180旧绝对路径及相对路径重复，仅186唯一文件。output/source/绝对路径丢弃目标根，重写了当前源码同样字节，180个声明档案路径无效。根重新核对全部当前源码哈希未变；可能变更mtime，不能声称从未写原文件。47通过只属当时当前源码测试，不能升级为336完整归档闭合。失败脚本及根诊断e562fb24...e549c保留，0实际模型/native。新v2统一规范ROOT-relative键、相同内容去重、拒绝逃逸并保证目标在output/source且非live，增加完整prepare路径回归，使用新pure与prepare002。

另一完整请求线已编写显式C+owneddecoder publisher接线，原singlecapture采集、exact native chain、构造器classcell、时钟、ACK/firsthop/drain与scheduler均保留，仅证据publisher替换。root完成源码及40接线测试阅读；首次执行前追加5路径用例，45pure授权，仍0真实18/C加载/模型。旧100ms未达标结果继续有效，三目标不降标准。\n'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 72. 接线测试必须覆盖父子日志与归档路径组合\n\n构建配置成功不等于目标编译执行；纯测试通过不等于归档闭合。两项实际准备错误均保留原件，禁止进入下一门。源码字节未漂移，仍需修正路径与日志组合并用新证据证明。算法、物理和100ms标准均未改变。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,
 'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'root_sessions_active_at_checkpoint':[],
 'new_native_branches_since041':0,'external_messages_sent':0}
with (HERE/'milestone_042.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_042.json')}))
