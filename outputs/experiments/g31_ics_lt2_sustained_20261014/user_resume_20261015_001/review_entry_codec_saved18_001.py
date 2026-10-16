"""Root source review and outer wall binding for the new successful saved18."""
from pathlib import Path
from datetime import datetime, timezone
import json
from scripts.experiments.g31_ics_circulation import review_initial_owner_route_entry_codec_saved as reader

c = reader.c
here = Path(__file__).resolve().parent
out = c.OUT/'initial_entry_codec_saved_review_001'
expected = 'c97bb3be43164f0c4b6253cf4e6976e2777b12123a4c67e42b710d89c8386e9c'
assert c.sha(reader.__file__) == '994e168fda169588d9f7db82805ae7429aff709c52d196ccfd4bf4a6ddbe77f3'
plan = reader.verify_prepared(out, expected)
producer, evidence, outer, receipt, ledger = reader.producer_state(Path(plan['source_directory']))
loaded = reader.actual_loaded(producer, plan, receipt)
assert len(plan['source_sha256']) == 144
assert len(producer['source_sha256']) == 169
assert len(producer['compiled_source_archive_sha256']) == 67
assert len(ledger) == 18 and len(receipt['loaded_project_sources_entry']) == 103
assert receipt['loaded_project_sources_entry'] == receipt['loaded_project_sources_exit']
assert not (out/'execution_claim.json').exists()
original = here/'invoke_saved_entry_recovery_001_measured.ps1'
assert c.sha(original) == 'd3d60f4b76d6a13d9079f360eaaf502500068158ffbd82a62378dd412788f143'
body = original.read_text(encoding='utf8')
replacements = {
    'initial_owner_route_entry_independent_actual_review_001': 'initial_entry_codec_saved_review_001',
    '5363525a3a3203f2d1783ad4b93c856384852b4366faf29c4b1fca698b845a3e': expected,
    'review_initial_owner_route_entry_saved_v2': 'review_initial_owner_route_entry_codec_saved',
    'g31.initial_entry.separate_saved_recovery.external_wall.v1': 'g31.initial_entry_codec.saved18.external_wall.v1',
    "original_producer_failed=$true;producer_exit_import_proof='unknown_not_recreated'": "original_producer_failed=$false;producer_exit_import_proof='recorded_103_equal_entry_exit'",
    'Independent full saved endpoint/physical/RPC/gate/outbox audit after repaired verifier globals. Full launch/import/pin/read/decode/check/export/cleanup/exit cost is included. No native rerun. Original producer exit1 and missing receipt remain.': 'Independent full saved endpoint/physical/RPC/entry/gate/outbox/codec audit of successful new producer. Full launch/import/pin/read/decode/check/export/cleanup/exit cost is included. No native rerun; older failed producer is unchanged.',
}
for before, after in replacements.items():
    assert body.count(before) == 1, before
    body = body.replace(before, after)
wrapper = here/'invoke_entry_codec_saved18_001_measured.ps1'
with wrapper.open('x', encoding='utf8', newline='\n') as stream:
    stream.write(body)
report = {
    'schema': 'g31.initial_entry_codec.saved18.root_review.v1',
    'recorded_utc': datetime.now(timezone.utc).isoformat(),
    'status': 'ready_for_one_separate_saved_audit',
    'plan': c.reference(out/'plan.json'), 'preparation': c.reference(out/'preparation.json'),
    'audit_sources': 144, 'producer_sources': 169, 'compiled_sources': 67,
    'producer_recorded_imports': 103, 'loaded_checked': len(loaded),
    'full_saved_branches': 18, 'owned_seconds': 180, 'new_native_or_predictor_calls': 0,
    'reviewed_rules': [
        'Read the complete new reader. Same complete saved verifier bytecode/closure executes once; passive same-decoded-row callback retains original branch result.',
        'Successful producer receipt, verification, both recorded103 import maps, launch/outer identities and all169 source/67 compiled archive are bound. Older failed producer remains distinct.',
        'All18 raw inputs and144 audit sources are checked before/after. Same strict verification result is compared to producer result.',
        'Full endpoint, physical, RPC, entry marker, gate, outbox and codec checks retained. All six normal pairs retain five-job deltas and unknown/regression accounting.',
        'Gate002 and failed-entry-recovery comparisons are descriptive separate rounds; selection or root-time differences do not establish codec causation.',
        'Fixed180 includes imports/checks/decode/report/cleanup. Cost reference prior saved18 was53.422411s, not a guarantee. Full100ms/full32/all-day claims remain open.',
    ],
    'producer': c.reference(__file__), 'wrapper': c.reference(wrapper),
}
review = out/'root_source_review_001.json'
with review.open('x', encoding='utf8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
ready = out/'root_ready_001.json'
with ready.open('x', encoding='utf8') as stream:
    json.dump({'status': 'ready_for_one_separate_saved_audit', 'plan_sha256': expected,
        'root_review': c.reference(review), 'wrapper_sha256': c.sha(wrapper),
        'owned_seconds': 180, 'full_audit_dispatched': False}, stream, indent=2)
print(json.dumps({'review_sha256': c.sha(review), 'ready_sha256': c.sha(ready),
    'wrapper_sha256': c.sha(wrapper)}))
