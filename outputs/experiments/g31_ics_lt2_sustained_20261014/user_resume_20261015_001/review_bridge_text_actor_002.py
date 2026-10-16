"""Root review of full saved audit candidate; no large evidence reads."""
from pathlib import Path
from datetime import datetime, timezone
import json
import xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import audit_bridge_saved_text_actor as a

out = a.OUT/'bridge_saved_text_actor_prepare_001'
here = Path(__file__).resolve().parent
expected = '6a56cee53dc46444a96815210076863e37738f449f73b50e845c48d39e887f4a'
sha = a.base.sha
assert sha(out/'plan.json') == expected
assert sha(out/'preparation.json') == '7bff2a78d8b60cf3f1ce808d6f0df337618ff86817f2e13f58634176953a65ea'
plan = a.base.read(out/'plan.json')
assert len(plan['source_before']) == 96 and plan['linear_contract'] == a.contract()
assert {str(p): sha(p) for p in a.closure()} == plan['source_before']
for name, digest in plan['source_before'].items():
    assert sha(name) == sha(out/'source'/Path(name).relative_to(a.ROOT)) == digest
prior = a.base.read(a.FAILED/'plan.json')
assert len(prior['source_before']) == 92
assert all(plan['source_before'][name] == digest for name, digest in prior['source_before'].items())
assert all(plan[k] == prior[k] for k in (
    'original_campaign_sha256', 'original_external_sha256', 'original_refs',
    'old_prefix_manifest_sha256', 'expected_new_rows', 'expected_old_prefix_rows',
    'hard_timeout_seconds', 'native_calls', 'predictions', 'write_scope', 'runtime_scope', 'budget_scope'))
loaded = a.prior.check_runtime(plan)
pure = plan['pure']
assert sha(pure['path']) == pure['sha256'] == '53d85fb35a5efc5a5d779de1b1635b392c0516b66af11d2437569bee1af16ecd'
assert sha(pure['XML_path']) == pure['XML_sha256'] == '8dd9f0a1f46124f68197886b1ba438a19a58fdb54c1fe76fc9fbef0120ce06d5'
counts = {k: sum(int(s.get(k, 0)) for s in ET.parse(pure['XML_path']).getroot().iter('testsuite'))
          for k in ('tests', 'failures', 'errors', 'skipped')}
assert counts == dict(tests=34, failures=0, errors=0, skipped=0)
assert sha(a.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp') == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert not (out/'execution_claim.json').exists()
original = here/'invoke_bridge_linear_v3_001_measured.ps1'
body = original.read_text(encoding='utf8')
changes = {
    'bridge_saved_linear_v3_prepare_001': 'bridge_saved_text_actor_prepare_001',
    '4bbf6f364ac097db7fbf2bd1ff35f9ea74500566f367933e552bf6da6f0bd87e': expected,
    'audit_bridge_saved_linear_v3 --execute': 'audit_bridge_saved_text_actor --execute',
    'g31.bridge.linear_saved_audit.external_application_wall.v3': 'g31.bridge.same_text_actor.external_wall.v1',
    'actor-copy retention, observer-copy removal, strict ordered comparison':
        'actor second standard parse of the identical private text, observer-copy removal, original C semantic comparison',
}
for before, after in changes.items():
    assert body.count(before) == 1, before
    body = body.replace(before, after)
body += "\nif ($taskWall -gt 600) {throw 'Whole Python audit budget exceeded'}\n"
wrapper = here/'invoke_bridge_text_actor_root_002_measured.ps1'
with wrapper.open('x', encoding='utf8', newline='\n') as stream:
    stream.write(body)
review = out/'root_source_review_001.json'
report = {
    'schema': 'g31.bridge.same_text_actor.root_review.v1',
    'status': 'ready_for_separate_saved_audit',
    'recorded_utc': datetime.now(timezone.utc).isoformat(),
    'plan_sha256': expected, 'source_count': 96, 'prior92_source_unchanged': True,
    'pure_counts': counts, 'loaded_sources': loaded, 'source_proof': a.core.source_proof(),
    'reviewed': [
        'Read entire combined module, driver, tests and original private binder/observer/progress driver.',
        'Private binder retains full defining globals; only SharedReads, semantic_equal and replay_type differ. Replay two-expression inverse AST leaves original guards exact.',
        'Current manifest-selected file is read once. Its first decoded row stays with observer; second standard loads of same immutable text supplies the actor, preserving container isolation without reencoding or new input.',
        'All original hash/ordinal/endpoint/arguments/clock/error checks precede actor return. Pending observer cannot be overwritten. One text sidecar is cleared on every return/error; lifetime is bounded by current row size, not a byte cap.',
        'Default JSON decoding domain and original guard failures remain. Extra second-parse allocation failures may differ from deepcopy and remain unknown; no arbitrary resource-failure equivalence asserted.',
        'Original C semantic_api comparison restored, not a relaxed comparator. Full37270 new,27218 old prefix,28506 offered and22trays plus source/binary/input/physical/FIFO/Storage/ACK protections remain.',
        'Tail comparison and copy diagnostics justify one new600 attempt; percentages cannot be added or extrapolated to a whole-audit deadline guarantee.',
        'No large evidence read in this source review; all large hashes/decode/replay/export remain in the owned600 execution. Prior failures remain unchanged.',
    ],
    'native_calls': 0, 'predictions': 0, 'large_evidence_reads': 0,
    'full_saved_audit_accepted': False, 'alloffered_success': False,
    'complete_request_100ms_certified': False,
    'source': {'path': str(Path(__file__).resolve()), 'sha256': sha(__file__)},
    'wrapper_sha256': sha(wrapper),
}
with review.open('x', encoding='utf8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
with (out/'root_ready_001.json').open('x', encoding='utf8') as stream:
    json.dump({'status': report['status'], 'plan_sha256': expected,
        'root_review': {'path': str(review), 'sha256': sha(review)},
        'wrapper_sha256': sha(wrapper), 'owned_seconds': 600, 'dispatched': False}, stream, indent=2)
print(json.dumps({'review_sha256': sha(review), 'ready_sha256': sha(out/'root_ready_001.json'),
                  'wrapper_sha256': sha(wrapper)}))
