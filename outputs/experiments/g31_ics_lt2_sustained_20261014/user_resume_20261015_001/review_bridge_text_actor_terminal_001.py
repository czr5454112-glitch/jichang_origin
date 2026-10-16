"""Terminal metadata and small journal only, no policy/native or big raw reads."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT, OUT = HERE.parents[3], HERE.parent
source = OUT/'bridge_saved_text_actor_prepare_001'
destination = OUT/'bridge_text_actor_terminal_review_001'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_bytes())
assert sha(source/'plan.json') == '6a56cee53dc46444a96815210076863e37738f449f73b50e845c48d39e887f4a'
assert sha(source/'external_application_wall.json') == '8215f25b11efe738bece294b5c9fc98d05a66d28095f5ba2eed44770979940b1'
plan, outer, bounded = (read(source/name) for name in ('plan.json', 'external_application_wall.json', 'bounded_execution.json'))
assert bounded['process']['status'] == 'hard_timeout' and outer['exit_code'] == 1
assert not (source/'report.json').exists()
for name, digest in plan['source_before'].items():
    assert sha(name) == sha(source/'source'/Path(name).relative_to(ROOT)) == digest
rows = [json.loads(line) for line in (source/'progress.jsonl').read_text(encoding='utf8').splitlines()]
assert len(rows) == 275 and [r['record'] for r in rows] == list(range(275))
assert all(type(r['at_ns']) is int and r['at_ns'] >= 0 for r in rows)
assert all(a['at_ns'] <= b['at_ns'] for a, b in zip(rows, rows[1:]))
last = rows[-1]
assert last['event'] == 'api_replay_progress' and last['completed'] == last['old_prefix_completed'] == 19712
api = [r for r in rows if r['event'] == 'api_replay_progress']
assert all(r['completed'] == r['ordinal']+1 and r['completed'] % 256 == 0 for r in api)
blocks = [{'through_before': a['completed'], 'through_after': b['completed'],
           'seconds': (b['at_ns']-a['at_ns'])/1e9} for a, b in zip(api, api[1:])]
stages = [{'stage': r['stage'], 'seconds': r['elapsed_ns']/1e9}
          for r in rows if r['event'] == 'stage_end']
report = {
    'schema': 'g31.bridge.same_text_actor.terminal_review.v1',
    'status': 'unknown_full_saved_audit_timeout_preserved',
    'recorded_utc': datetime.now(timezone.utc).isoformat(),
    'references': {name: {'path': str(source/name), 'sha256': sha(source/name)} for name in
        ('plan.json', 'external_application_wall.json', 'bounded_execution.json', 'progress.jsonl', 'stdout.log', 'stderr.log')},
    'live_archive_source_count': len(plan['source_before']),
    'whole_python_application_seconds': outer['whole_python_application_seconds'],
    'owned_process_status': bounded['process']['status'], 'budget_seconds': 600,
    'journal_count': 275, 'journal_limit': 1024, 'journal_limit_exhausted': False,
    'last_logged_tape_progress': last,
    'tape_checked_and_actor_constructed_through_lower_bound': 19712,
    'required_new_rows': 37270, 'required_old_prefix_rows': 27218,
    'completed_stages': stages,
    'slowest_logged256_intervals': sorted(blocks, key=lambda r: r['seconds'], reverse=True)[:8],
    'progress_semantics_correction': 'The marker is emitted in actor retain before returning to the outer ObservedTape and policy. It proves tape guards, old-prefix comparison and actor construction through N only; it does NOT establish completion of the Nth observer/policy consumption, full replay, or the exact final in-flight call. This qualification also applies to earlier linear progress reports.',
    'missing_terminal_files': [name for name in ('report.json', 'failure.json', 'instrumentation_failure.json', 'all_job_states.json.gz') if not (source/name).exists()],
    'interpretation': 'Measured local C comparison and same-text copy improvement did not close full audit under600. The aggregate replay interval contains decode/hash/comparison/copy plus observer/policy guards/history work and cannot attribute the residual to one function.',
    'next_gate': 'Source review identifies call-site discarded refresh result copies and transient latest-own capture copies as hypotheses, plus repeated history scans/digests. Isolate costs and prove private alias/guard semantics on representative saved data before any new full audit. No automatic retry or budget extension.',
    'big_raw_or_API_reads': 0, 'native_calls': 0, 'model_calls': 0,
    'full_saved_audit_certified': False, 'all28506_business_goal_achieved': False,
    'producer39_claim_upgraded': False, 'old_failures_rewritten': False,
    'prelaunch_packaging_failure': 'Root prelaunch001 reached wrapper creation after pin checks but collided with agent-created same filename; FileExistsError, no fullaudit dispatch. Retained original source/template, new root wrapper002 used after fresh source review.',
    'producer_script': {'path': str(Path(__file__).resolve()), 'sha256': sha(__file__)},
}
destination.mkdir(exist_ok=False)
with (destination/'report.json').open('x', encoding='utf8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
print(json.dumps({'report_sha256': sha(destination/'report.json'), 'through': 19712,
                  'whole_seconds': outer['whole_python_application_seconds'], 'stages': stages}))
