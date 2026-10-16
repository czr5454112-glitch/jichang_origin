"""Checkpoint new bounded evidence and open gates without declaring completion."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT, OUT = HERE.parents[3], HERE.parent
DOC = ROOT/'docs/g31_ics_circulation'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_bytes())
pins = {
    'bridge_actor_reparse_prepare_001/result.json': 'e23bc20c9e66fd7e6933149c3c8a214043c2bbe41dfa83e3f81f9d0d494e7b50',
    'bridge_actor_reparse_prepare_001/external_application_wall.json': '9c02fa3b5b1216365c714542604df687c3ebd542b99a4f5d9a7186dc4da7257f',
    'bridge_actor_reparse_readback_001/report.json': '9bca7b1da48ca8c2520df312e5e6589f560cc1ec38cd8e881de017350d83237f',
    'bridge_saved_text_actor_prepare_001/plan.json': '6a56cee53dc46444a96815210076863e37738f449f73b50e845c48d39e887f4a',
    'bridge_saved_text_actor_prepare_001/root_source_review_001.json': '678503a539f7c61bee21dc00e9c2a2732c95693b4acf65ba1e87afe89af41848',
    'bridge_saved_text_actor_prepare_001/independent_narrow_review_legal_001.json': 'b7b3dc1e48a7bf4a901bdf395fd4459110a6f5c234165370a33429b922948fc0',
    'c_tree_normalizer_acceptance_summary_001.json': '202786fdc89de41341d00a7996b746b3010fbd103f5a869307dee5a96d7d3a9f',
    'initial_single_failure_pure_001/plan.json': 'a3598e38238cfb1999313833d50b7148a335b8013dfe001de3a0543b8b5354d9',
    'initial_single_failure_pure_001/tests.xml': 'a9af7fc5fc9482f6b768cbeeeef64b4136eed462a2d13572127c1eada9e9f2fa',
    'initial_single_failure_independent_source_review_r1_001.json': 'a311d6e3503b0a5c41afd0fe6dcc70ac5700c5f396d2b878d47e1dc3434b7fad',
    'live_phase_b_pause_source_prepare_001/receipt.json': 'fa185fc26cc1263d1ebb8ad2f2fe5a194c7e1158d9818f83ced197cce2d51411',
    'live_phase_b_pause_prepare_001/plan.json': 'be90c0042ac1073e7c880275c2fc412a0d11242bc06189bfc93a52eb309a8fbb',
}
for path, digest in pins.items():
    assert sha(OUT/path) == digest, path
summary = read(OUT/'c_tree_normalizer_acceptance_summary_001.json')
assert summary['functional_tests'] == 61 and summary['saved18_reads'] == 0
assert sha(summary['binary']['path']) == summary['binary']['sha256']
parent = ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent) == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert (OUT/'bridge_saved_text_actor_prepare_001/execution_claim.json').exists()
backup = HERE/'before_milestone_033'
receipt = HERE/'milestone_033.json'
assert not backup.exists() and not receipt.exists()
backup.mkdir()
names = ('RESEARCH_STATE.json', 'NEXT_ACTION.md', 'RESUMPTION_20261015.md', 'NOVELTY_LEDGER.md')
for name in names:
    (backup/name).write_bytes((DOC/name).read_bytes())
state = read(DOC/'RESEARCH_STATE.json')
active = state['active_experiment']
state['current_stage'] = 'Fully resumed; all3 overall goals remain unmet. Full bridge saved audit new same-text actor/C comparison candidate running once under600 after measured local improvement; no acceptance yet. C normalizer isolated build and61functional passed, saved18 pending. Singlecapture failedprefix36pure and narrow independent review passed, full branch integration pending. Passive model snapshot16pure plus sixinput driver10pure prepared, no real snapshots executed.'
active['bridge_saved_audit_status'] = 'Fixed16 original-text secondloads copy diagnostic64ABBA passed whole67.806501s/120. Deepcopy batch median424.06245ms vs same-text secondparse137.0207ms,67.68855625percent lower localcopy. Whole firstread/decode/domain cost and all64 equality/type/order/floathex/container isolation/hash/journal/cleanup retained. Author saved-only readback30.3738049s independently recalculated16text/64records/80sources+50XML; not author-independent and saved records cannot redo livealias proof. New96source/34pure combined binder restores originalCcomparison and secondloadsactor from one original private text, observer originaldecodedrow unchanged, allguards/37270new/27218old/28506jobs/22trays retained. Root full source/pin review and legal narrow review passed. One shared600 running, no result claimed. Additional secondparse allocation failures may differ; unknown retained. Percentages not additive; no whole600 guarantee. Old2400/600/92/progress failures preserved.'
active['normalization_c_helper'] = 'Separate CPython3.11.9 nonlimitedABI C helper built in freshbuild004; pyd e95b1de151c7628b32707bde17c4342f528b3de47af430d18be8d57b2ecb6786,16KiB. Build54.5266534s/180, functional61passed42.3156373s/120, saved18 excluded. Agent checked6124toolchain/header/library entries beforeafter, old169/135 originalnormalizer/image/codec exact, full10testsource closure7actualloaded, pyd/runtime imports unchanged, GCtrue. Root read summary/source design; not an independent rerun of6124entries. Import dependencies Python311/VCruntime/CRTAPIset/KERNEL32. Failures001002 MSVC command environment and003 DebugPDBmanager C1902 preserved. /u hypothesis refuted; nativecmd path spelling fixed currentenvironment launch, explicit Release trycompile fixed probe without skipping checks. Stable-input/privateCPythonfield limits remain. Saved18 completeparity must pass before wholeevidence timing or actualintegration.'
active['single_capture_failure_review'] = 'Original singlecapture24pure successful path6to3query source only, nativegetters have timing/cache side effects; no no-side-effects claim. New standalonefailedprefix checker131source archive includingold128,36purepassed in4.8454316s internalharness wall/owned120, no native/model. Typed bounded inverse retains order/tuple/intkeys/floathex/nonfinitefailuredata, exactcompletedprefix/active/startclock/owner/request and optionalactualbranch envelope. Validfailedrecords alwaysunknown; prefix_export_error remains payloadunverified. R1 independent narrow4source+XML review a311d6e... no specificblockingbug, no rerun. Malformedview/command checkerexception must be caught in future versionedbranch and retain failedroot/attempt/denominator. Successful oldendpointreplay unchanged; fullbranch/campaign integration NOT ready.'
active['rolling_passive_snapshot'] = 'New passive hook immediately after originaldecide collect beforeaction/record; inverseAST restoresoriginal. Wholeengine/pending/info/screen/view deepcopy preserves heap/client/world aliases, recorder memoedNone.16fakepure passed, explicitlyresumableFalse/nativeauthorityFalse/coverageFalse. Sixfixedcasevector plan105sources/10driverpure prepared, max6model/14points/42graphcopies/shared120, noexecutionyet. Original6modelcost2.3896373s,max.5241252; newcopy cost unmeasured so boundedfailureunknown. Independentactualsupportinventories notrelated tomodelpoints and cannotfilter; missinghiddenstate/opaqueID mapping/historycoverage remainshardgate.'
actions = [
    'Wait for root-owned full bridge600 session18350; inspect final receipt and exact denominator, or retain timeout/fatal and diagnose the measured stage. No blind rerun or budget extension.',
    'Review C helper saved18 plan and execute one180 full parity after bridge heavy window; preserve16closed2unknown and completeoriginalcodec/strictdecode before any ABBA speed test.',
    'Execute reviewed sixinput passive snapshot diagnostic after bridge; compare complete predictionbytes and14alias/copy points. This is no restart/beliefcoverage/nativeonlineefficacy proof.',
    'Design versioned singlecapture branch integration with old successfulchecks and newfailedprefixunknown paths, exact ActualAdvanceChain sourcebinding and unchanged freshfinalguards. No failedrecord dropping.',
    'Keep full32/complete100ms and sameinformation strongmethod efficacy goals. Full39 bridge acceptance is still prerequisite to legal completion-baton trial; Storage53 and all28506 requirements unchanged.',
    'Retain all failures and solutions for later user-commanded GPTPro review. No commit/push/externalsend here.',
]
state['next_actions'] = actions
active['pending'] = actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone033\n\n全面恢复持续有效，全天原流、完整请求100ms/full32、联合方法有效性三项目标均未达标。新全量保存审计正在原600秒预算内运行；C helper已建并通过61功能门，尚未通过saved18。\n\n'+'\n'.join(f'{i+1}. {x}' for i,x in enumerate(actions))+'\n', encoding='utf8')
note = '''

## milestone033：复制局部改善转入完整审计；C helper 构建通过

同原文本第二次标准 JSON 解码的 fixed16/64ABBA 全通过，whole67.806501秒/120；批次中位424.06245→137.0207ms，局部复制下降67.68856%。第一解压/解析及完整类型、顺序、浮点、隔离、hash、导出均计入whole。作者另做30.3738秒saved-only读回，核80源/50XML/16原text/64记录；不是作者独立复现，保存记录也不能重建运行时alias证明。结合此前原C比较局部40.65%，准备96源/34pure新版完整审计，保留所有37270新API、27218旧前缀、28506原流、22盘和原保护门。两项百分比不可相加，不能保证全600通过。root源审/全sourcepins及legal窄审通过，当前仅单次600正在运行。额外第二次parse的内存失败可与deepcopy不同，必须保unknown。

C normalizer新build004成功54.5266534秒；61功能测试42.3156373秒通过且saved18显式未执行。pyd e95b1de151c7628b32707bde17c4342f528b3de47af430d18be8d57b2ecb6786。执行者核6124工具/头/库和旧169/135 baseline、10功能源与7实际loaded，GC开启。最初两次cmd环境失败及第三次Debug PDB C1902失败全部留存：/u假设被反证，当前环境cmd原生反斜杠拼写和Release trycompile修正成功；未跳编译探测。CPython3.11.9私有ABI与稳定输入限制不变，不称saved18、性能或100ms通过。

单次采集失败prefix新增独立checker，131source包含旧128，36纯测试通过，R1对4源+XML窄审无具体阻断。保留已完成前缀/active/精确整数起始clock/owner/request/typed原值；prefix导出失败明确payload未验证。没有endpoint结束clock，不能虚构duration。malformed返回值的checker异常仍须由新版branch捕获为unknown且保留root、attempt与分母。原成功endpoint verifier未变，整个actual集成仍未ready。

被动模型点16fakepure通过，六真实输入/14点driver10pure已准备；尚未执行真实模型快照。保持resumable=False，复制heap不等于恢复Python栈。独立actual支持清单与模型点没有建立opaqueID关系，不能筛状态；隐藏队列/资源历史/peer私有payload覆盖未证明。总目标不降级。

另保留一次root预审包装失败：与agent同时exclusive创建同名wrapper触发FileExistsError，未启动完整审计；新root独有命名重新源审成功。之后执行模板由各自路径持有，防止并发写同名产物。未修改冻结源码或覆盖失败记录，未推送或发送GPTPro。
'''
with (DOC/'RESUMPTION_20261015.md').open('a', encoding='utf8') as stream:
    stream.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a', encoding='utf8') as stream:
    stream.write('\n\n## 63. 原文本复制与完整树 C helper 的工程前置门\n\n固定输入第二次解码局部复制约67.69%改善，现转一次同600全量审计，尚未认证全天业务。C helper61功能门只证明已测语义，完整18与性能仍待核；失败prefix36纯门补足证据保留但尚未接branch。被动点不等于可恢复或完整隐藏状态。所有三目标继续开放。\n')
record = {'schema': 'g31.resume_milestone.v1', 'recorded_utc': datetime.now(timezone.utc).isoformat(),
    'immutable_evidence': pins, 'before_sha256': {n: sha(backup/n) for n in names},
    'after_sha256': {n: sha(DOC/n) for n in names}, 'parent_user_file_sha256': sha(parent),
    'overall_goal_achieved': False, 'root_sessions_active_at_checkpoint': [18350],
    'native_dispatched_here': 0, 'external_messages_sent': 0}
with receipt.open('x', encoding='utf8') as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
print(json.dumps({'state_updated': True, 'milestone_sha256': sha(receipt)}))
