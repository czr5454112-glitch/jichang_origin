"""Offline terminal-flow publication inventory; never stages Git or runs native.

Inventory is safe while experiments run. Finalize requires a terminal dispatch,
idle accounting, a reviewed disposition, and stable evidence; it emits a manifest
and literal NUL-delimited pathspec. Large raw owner histories stay local.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CYCLE_REL = Path('outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001')
REPORTS_REL = Path('outputs/experiments/g31_ics_terminal_flow_20261021')
MAX_FILE_BYTES = 95_000_000  # Stay below both decimal 100 MB and GitHub's 100 MiB ceiling.
SCHEMA = 'g31.terminal_flow.release.v1'
RESEARCH_RECORDS = ('docs/g31_ics_circulation/RESULT_INDEX.jsonl', 'docs/g31_ics_circulation/NOVELTY_LEDGER.md')
TRACKED = ('docs/g31_ics_circulation/README.md', 'docs/g31_ics_circulation/RESEARCH_STATE.json',
    'scripts/experiments/g31_ics_circulation/foundation_airport_inventory_projection.py',
    'scripts/experiments/g31_ics_circulation/foundation_airport_joint_calendar_prepared.py',
    'scripts/experiments/g31_ics_circulation/foundation_airport_joint_campaign.py',
    'scripts/experiments/g31_ics_circulation/foundation_airport_joint_control.py',
    'scripts/experiments/g31_ics_circulation/foundation_airport_protocol_v2.py',
    'scripts/experiments/g31_ics_circulation/protocol_control.py') + RESEARCH_RECORDS
RAW_LOCAL_ONLY = {'observations.json.gz', 'delivered_ack_evidence.json.gz', 'control_trace.json.gz'}
COMPACT_ACK_MAX_BYTES = 30_000_000  # Strict decimal-byte limit; equality is rejected.
COMPACT_ACK_CONTRACT = 'deferred_complete_intermediate_results_and_transfer_ack_subset_v1'
ACK_VIEW_FIELDS = ('schema', 'now', 'owner_id', 'scope', 'delivered_transfer_acks', 'client_transfer_ledger')
ACK_ROW_FIELDS = {'request_id', 'sequence', 'attempt', 'observed_at', 'delivered_at', 'status', 'reason',
                  'received_at', 'delivered_copies'}
ACK_LEDGER_FIELDS = {'request_id', 'tray_id', 'source', 'destination', 'issued_at', 'earliest_departure',
    'expiry', 'message_delay', 'transfer_scope', 'status', 'received_at', 'reason', 'status_scope'}
ACK_SCOPE_FIELDS = {'schema', 'complete_owner_protocol_view', 'full_transfer_ack_history_preserved',
    'full_client_transfer_ledger_preserved', 'owner_protocol_fields_retained', 'owner_protocol_fields_omitted',
    'original_owner_protocol_scope', 'online_actor_input'}
LEGACY_HANDOFF_TASKS = ('JOINT_bridge_R0_legacy_P2201_001', 'JOINT_bridge_R0_joint_bridge_P2201_001')
LEGACY_HANDOFF_FILES = ('plan.json', 'receipt.json', 'worker_report.json', 'progress.jsonl',
    'stdout.log', 'stderr.log', 'terminal_evidence.json.gz', 'trajectory.json.gz', 'cost_events.json',
    'controller_checkpoint_scope.json', 'calls.json.gz', 'decisions.json.gz', 'offline_diagnostics.json.gz',
    'wait_graph.json.gz', 'calendar_binding.json', 'arrival_support_contract.json', 'arrival_support_receipts.json',
    'offline_origin_support_audit.json', 'plan_preload_receipts.json')
LEGACY_HANDOFF_STAGE_FILES = ('registration.json', 'advance_001.dispatch.json', 'advance_001.stdout.log',
                              'advance_001.stderr.log', 'advance_002.dispatch.json')


def require(value, reason):
    if not value:
        raise ValueError('terminal_flow_release:'+reason)


def read(path):
    path = Path(path)
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf8') as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding='utf8'))


def relative(path, root):
    path = Path(path).resolve()
    require(path.is_relative_to(root.resolve()), 'path_outside_repository:'+str(path))
    return path.relative_to(root.resolve()).as_posix()


def fingerprint(path, root):
    path = Path(path)
    before = path.stat()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), 'file_changed_while_hashing:'+str(path))
    return dict(path=relative(path, root), sha256=sha, bytes=after.st_size)


def bound_read(reference):
    path = Path(reference['path'])
    with path.open('rb') as stream:
        require(hashlib.file_digest(stream, 'sha256').hexdigest() == reference['sha256'], 'changed_bound_file:'+str(path))
    return read(path)


def compact_transfer_ack_guard(path, root):
    """Publication eligibility only; not ACK delivery or scientific certification.

    Reject large/legacy/unknown evidence before opening its gzip. Invalid compact
    evidence stays local, with its complete file hash recorded by finalization.
    """
    path = Path(path)
    if path.stat().st_size >= COMPACT_ACK_MAX_BYTES:
        return dict(publish=False, reason='ack_at_or_above_compact_decimal_byte_limit')
    try:
        require(path.name == 'delivered_ack_evidence.json.gz', 'compact_ack_filename')
        plan_path = path.parent/'plan.json'
        plan = read(plan_path)
        require(plan.get('worker_evidence_contract') == COMPACT_ACK_CONTRACT, 'compact_ack_plan_contract')
        source_ref = plan['source_bundle']
        relative(Path(source_ref['path']), root)
        source = bound_read(source_ref)
        require(source.get('worker_evidence_contract') == COMPACT_ACK_CONTRACT, 'compact_ack_source_contract')
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, 'compact_ack_duplicate_json_key')
                result[key] = value
            return result
        with gzip.open(path, 'rt', encoding='utf8') as stream:
            views = json.load(stream, object_pairs_hook=unique_object)
        require(isinstance(views, dict) and views, 'compact_ack_owner_views')
        ack_count = ledger_count = 0
        for owner, view in views.items():
            require(isinstance(owner, str) and owner and isinstance(view, dict)
                and set(view) == set(ACK_VIEW_FIELDS) | {'evidence_scope'}, 'compact_ack_view_fields')
            require(view['schema'] == 'g31.owner_protocol_observation.v1' and view['owner_id'] == owner
                and isinstance(view['scope'], str) and view['scope'].strip(), 'compact_ack_owner_scope')
            require(type(view['now']) in (int, float) and math.isfinite(view['now']) and view['now'] >= 0,
                    'compact_ack_view_clock')
            scope = view['evidence_scope']
            require(isinstance(scope, dict) and set(scope) == ACK_SCOPE_FIELDS
                and scope['schema'] == 'g31.airport_joint_campaign.v1.transfer_ack_subset.v1'
                and scope['complete_owner_protocol_view'] is False
                and scope['full_transfer_ack_history_preserved'] is True
                and scope['full_client_transfer_ledger_preserved'] is True
                and scope['online_actor_input'] is False
                and scope['owner_protocol_fields_retained'] == list(ACK_VIEW_FIELDS)
                and scope['original_owner_protocol_scope'] == view['scope'], 'compact_ack_subset_flags')
            omitted = scope['owner_protocol_fields_omitted']
            require(isinstance(omitted, list) and all(isinstance(name, str) for name in omitted)
                and len(omitted) == len(set(omitted)) and not set(omitted).intersection(ACK_VIEW_FIELDS),
                'compact_ack_omitted_field_roster')
            for field, allowed in (('delivered_transfer_acks', ACK_ROW_FIELDS), ('client_transfer_ledger', ACK_LEDGER_FIELDS)):
                rows = view[field]
                require(isinstance(rows, list) and all(isinstance(row, dict) and set(row) == allowed
                    and all(not isinstance(value, (dict, list)) for value in row.values()) for row in rows),
                    'compact_ack_row_fields:'+field)
            ack_count += len(view['delivered_transfer_acks'])
            ledger_count += len(view['client_transfer_ledger'])
        return dict(publish=True, reason='verified_compact_transfer_ack_subset', contract=COMPACT_ACK_CONTRACT,
            decimal_byte_limit_exclusive=COMPACT_ACK_MAX_BYTES, plan=fingerprint(plan_path, root), source_manifest=source_ref,
            owner_views=len(views), delivered_ack_rows=ack_count, client_transfer_ledger_rows=ledger_count,
            complete_owner_protocol_view=False, delivery_truth_certified=False)
    except (OSError, EOFError, ValueError, KeyError, TypeError) as error:
        return dict(publish=False, reason='compact_ack_contract_or_structure_unverified', detail=str(error))


def git_inventory(root):
    def lines(*args):
        result = subprocess.run(['git', '-c', 'core.quotepath=false', *args], cwd=root,
                                capture_output=True, check=True)
        return [name.decode('utf8') for name in result.stdout.split(b'\0') if name]
    modified = sorted(set(lines('diff', '--name-only', '-z', 'HEAD')))
    new_source = lines('ls-files', '--others', '--exclude-standard', '-z', '--', 'scripts', 'tests', 'src')
    def ours(name):
        return (name.startswith('scripts/experiments/g31_ics_circulation/foundation_airport_terminal_')
            or name.startswith('scripts/experiments/g31_ics_circulation/foundation_airport_transport_')
            or name.startswith('tests/test_g31_terminal_')
            or name in ('tests/test_g31_airport_deferred_result.py', 'tests/test_g31_airport_transport_allocation.py',
                        'tests/test_g31_foundation_airport_transport_evidence.py'))
    return dict(modified_tracked=modified, unexpected_tracked=sorted(set(modified)-set(TRACKED)),
                new_source=sorted(new_source), unrelated_new_source=sorted(name for name in new_source if not ours(name)))


def candidate_paths(root):
    """Select only this task's bounded namespaces, plus exact parent input refs."""
    root, cycle = Path(root), Path(root)/CYCLE_REL
    selected = {root/name for name in TRACKED}
    patterns = ('scripts/experiments/g31_ics_circulation/foundation_airport_terminal_*.py',
        'scripts/experiments/g31_ics_circulation/foundation_airport_transport_*.py',
        'tests/test_g31_terminal_*.py', 'tests/test_g31_airport_deferred_result.py',
        'tests/test_g31_airport_transport_allocation.py', 'tests/test_g31_foundation_airport_transport_evidence.py',
        'docs/g31_ics_circulation/TERMINAL*.md', 'docs/g31_ics_circulation/STARTUP_DELTA_TERMINAL_FLOW.md',
        'docs/g31_ics_circulation/G31_CODEX_TERMINAL_FLOW_MULTIRATE_PLAN_20261021.md',
        'outputs/terminal*.py', 'outputs/TERMINAL_FLOW_RELEASE*.md', 'outputs/terminal*.xml',
        'outputs/terminal*.log', 'outputs/terminal*.json', 'outputs/forecast_*tests_*.xml')
    for pattern in patterns:
        selected.update(root.glob(pattern))
    selected.update((cycle/'terminal_flow').rglob('*'))
    selected.update((root/REPORTS_REL).rglob('*'))
    # Exactly the two charged tasks present at handoff, never the entire old JOINT chain.
    # Their legacy owner histories are not enumerated or read, even for hashing.
    for task_id in LEGACY_HANDOFF_TASKS:
        directory = cycle/'runs'/task_id
        selected.update(directory/name for name in LEGACY_HANDOFF_FILES)
        plan_path = directory/'plan.json'
        if plan_path.exists():
            plan = read(plan_path)
            require(plan['task_id'] == task_id, 'legacy_handoff_task_identity')
            for key in ('input', 'source_bundle', 'mapping', 'calibration'):
                if plan.get(key):
                    path = Path(plan[key]['path']).resolve()
                    require(path.is_relative_to(cycle.resolve()), 'legacy_handoff_reference_outside_cycle')
                    selected.add(path)
    selected.update(cycle/'stage'/name for name in LEGACY_HANDOFF_STAGE_FILES)
    for directory in (cycle/'runs').glob('TF_*'):
        selected.update(directory.rglob('*'))
        plan_path = directory/'plan.json'
        if plan_path.exists():
            plan = read(plan_path)
            for key in ('input', 'mapping', 'calibration'):
                if plan.get(key):
                    path = Path(plan[key]['path'])
                    relative(path, root)
                    selected.add(path)
            parent_directory = Path(plan['input']['path']).parent
            require(parent_directory.is_relative_to(cycle/'parents'), 'unexpected_parent_input_location')
            selected.update(parent_directory.glob('*'))
    selected.update(cycle/name for name in ('campaign_budget.json', 'runtime_calibration_001.json', 'ledger.jsonl'))
    archives = cycle/'publication/terminal_flow_001'
    selected.update(archives.glob('*.json'))
    selected.update(archives.glob('terminal_flow_runtime_*_sources.zip'))
    selected.update((cycle/'sources').glob('terminal_flow_runtime_*/source_manifest.json'))
    return sorted({path.resolve() for path in selected if path.is_file()
                   and '__pycache__' not in path.parts and path.suffix != '.pyc'}, key=str)


def jsonl(path):
    data = path.read_bytes()
    require(not data or data.endswith(b'\n'), 'partial_jsonl_tail:'+str(path))
    return data, [json.loads(line) for line in data.splitlines() if line]


def idle_ledger(path):
    data, rows = jsonl(path)
    runners, attempts, ever_started = set(), set(), set()
    for row in rows:
        if row['event'] == 'runner_open':
            require(not runners, 'overlapping_ledger_runners')
            runners.add(row['runner_id'])
        elif row['event'] == 'runner_close':
            require(row['runner_id'] in runners, 'unmatched_runner_close')
            runners.remove(row['runner_id'])
        elif row['event'] == 'native_start':
            require(row['task_id'] not in ever_started, 'duplicate_native_start')
            attempts.add(row['task_id'])
            ever_started.add(row['task_id'])
        elif row['event'] == 'native_finish':
            require(row['task_id'] in attempts, 'unmatched_native_finish')
            attempts.remove(row['task_id'])
    require(not runners and not attempts, 'active_or_unresolved_native_work')
    return data


def task_state(reference, *, attempted=False):
    plan = bound_read(reference)
    for key in ('source_bundle', 'input', 'mapping', 'calibration', 'forecast_binding', 'arrival_support_contract'):
        if plan.get(key):
            bound_read(plan[key])
    directory = Path(reference['path']).parent
    receipt_path = directory/'receipt.json'
    status = 'missing_receipt_after_native_start' if attempted else 'not_started'
    if receipt_path.exists():
        receipt = read(receipt_path)
        status = receipt['worker']['scientific_status']
        if status == 'closed':
            try:
                worker, trajectory = read(directory/'worker_report.json'), read(directory/'trajectory.json.gz')
            except (FileNotFoundError, json.JSONDecodeError, EOFError, gzip.BadGzipFile):
                return dict(task_id=plan['task_id'], status='invalid_closed', plan=reference)
            good = (receipt.get('plan_sha256') == reference['sha256'] and receipt.get('process', {}).get('exitcode') == 0
                and receipt['worker'] == worker and worker.get('process_status') == 'completed'
                and worker.get('final_physical_time') == plan['horizon']
                and trajectory.get('scientific_status') == 'closed_finite_horizon'
                and trajectory.get('process_status') == 'completed' and trajectory.get('logs_complete') is True
                and trajectory.get('physical_clock') == plan['horizon'])
            status = 'closed' if good else 'invalid_closed'
    return dict(task_id=plan['task_id'], status=status, plan=reference)


def head_bytes(root, name):
    return subprocess.run(['git', 'show', 'HEAD:'+name], cwd=root, capture_output=True, check=True).stdout


def research_record_appends(root, disposition):
    """Keep HEAD byte-for-byte; require explicit review of only this turn's appendices."""
    reviewed = disposition.get('research_record_appends', {})
    result = {}
    for name in RESEARCH_RECORDS:
        original, current = head_bytes(root, name), (root/name).read_bytes()
        require(current.startswith(original), 'research_record_history_changed:'+name)
        appended = current[len(original):]
        if not appended:
            continue
        require(not original or original.endswith(b'\n'), 'research_record_missing_baseline_newline:'+name)
        require(appended.endswith(b'\n'), 'research_record_partial_append:'+name)
        approval = reviewed.get(name, {})
        digest = hashlib.sha256(appended).hexdigest()
        require(approval.get('sha256') == digest and approval.get('reason', '').strip(),
                'research_record_append_requires_review:'+name)
        if name.endswith('.jsonl'):
            old_rows = [json.loads(line) for line in original.splitlines() if line.strip()]
            new_rows = [json.loads(line) for line in appended.splitlines() if line.strip()]
            old_ids = {row['id'] for row in old_rows}
            new_ids = [row['id'] for row in new_rows]
            require(new_ids and len(new_ids) == len(set(new_ids)) and not old_ids.intersection(new_ids),
                    'research_record_duplicate_or_empty_append')
        result[name] = dict(head_sha256=hashlib.sha256(original).hexdigest(), head_bytes=len(original),
            append_sha256=digest, append_bytes=len(appended), review_reason=approval['reason'])
    require(set(reviewed) == set(result), 'research_record_review_roster')
    return result


def source_pairs(root):
    cycle = root/CYCLE_REL
    manifests, archives = {}, {}
    for directory in (cycle/'sources').glob('terminal_flow_runtime_*'):
        match = re.fullmatch(r'terminal_flow_runtime_(\d{3})', directory.name)
        require(match and directory.is_dir(), 'unexpected_runtime_source_name:'+directory.name)
        path = directory/'source_manifest.json'
        require(path.is_file(), 'runtime_source_manifest_missing:'+directory.name)
        manifests[int(match[1])] = path
    for path in (cycle/'publication/terminal_flow_001').glob('terminal_flow_runtime_*_sources.zip'):
        match = re.fullmatch(r'terminal_flow_runtime_(\d{3})_sources.zip', path.name)
        require(match and path.is_file(), 'unexpected_runtime_archive_name:'+path.name)
        archives[int(match[1])] = path
    require(manifests and set(manifests) == set(archives), 'runtime_source_archive_pair_roster')
    require(set(manifests) == set(range(1, max(manifests)+1)), 'runtime_source_sequence_gap')
    return [(manifests[number], archives[number]) for number in sorted(manifests)]


def superseded_workflows(root, active_registration, ledger_rows):
    terminal = root/CYCLE_REL/'terminal_flow'
    registrations = sorted(terminal.glob('workflow_*/registration.json'))
    # Runtime005 must preserve the known, never-dispatched workflow004 history.
    active_source = Path(read(active_registration)['source_bundle']['path']).parent.name
    if int(active_source.rsplit('_', 1)[1]) >= 5:
        require(terminal/'workflow_004/registration.json' in registrations, 'superseded_workflow004_required')
    result, snapshots = [], {}
    for path in registrations:
        if path.resolve() == active_registration.resolve():
            continue
        registration = read(path)
        reference = dict(path=str(path.resolve()), sha256=fingerprint(path, root)['sha256'])
        source = registration['source_bundle']
        bound_read(source)
        dispatch_path = path.parent/'dispatch_001.jsonl'
        data, rows = jsonl(dispatch_path)
        require(len(rows) == 2 and rows[0]['event'] == 'waiting_for_frozen_predecessor'
            and rows[-1]['event'] == 'dispatch_failed', 'historical_workflow_not_superseded_before_dispatch')
        last = rows[-1]
        require(last.get('exception_type') == 'SupervisorSupersededBeforeDispatch'
            and type(last.get('native_starts_in_workflow')) is int and last['native_starts_in_workflow'] == 0
            and last.get('predecessor_native_untouched') is True and last.get('frozen_runtime004_unchanged') is True
            and last.get('reason', '').strip() and last.get('supervisor_action', '').strip(),
            'historical_supersession_attestation')
        require(all(row.get('registration') == reference for row in rows), 'historical_registration_binding')
        recorder = last['recorder']
        require(fingerprint(Path(recorder['path']), root)['sha256'] == recorder['sha256'], 'supersession_recorder_changed')
        stages = registration['stages']
        require(len(stages) == 6 and len({stage['name'] for stage in stages}) == 6
            and {stage['phase'] for stage in stages} == {'export_gate', 'train_demand', 'bridge', 'bins', 'period', 'predictor'},
            'historical_six_stage_registration')
        names = [stage['name'] for stage in stages]
        require(all(re.fullmatch(r'[A-Za-z0-9_]+', name) for name in names), 'unsafe_stage_name')
        require(all(not (terminal/name).exists() for name in names), 'superseded_stage_was_prepared')
        def belongs(row):
            return (row.get('source_manifest_sha256') == source['sha256']
                or row.get('source_bundle', {}).get('sha256') == source['sha256']
                or any(row.get('task_id', '').startswith('TF_'+name+'_') for name in names))
        require(not any(row['event'] == 'native_start' and belongs(row) for row in ledger_rows),
                'superseded_workflow_native_start')
        for plan_path in (root/CYCLE_REL/'runs').glob('TF_*/plan.json'):
            plan = read(plan_path)
            require(not belongs(plan) and plan.get('source_bundle') != source, 'superseded_workflow_plan_prepared')
        matching = [row for row in ledger_rows if row['event'] == 'terminal_flow_unstarted_workflow_superseded'
                    and row.get('registration') == reference]
        require(len(matching) == 1 and matching[0].get('dispatch') == dict(path=str(dispatch_path.resolve()),
            sha256=hashlib.sha256(data).hexdigest()) and type(matching[0].get('native_starts')) is int
            and matching[0]['native_starts'] == 0 and matching[0].get('predecessor_native_untouched') is True
            and matching[0].get('reason') == last['reason'], 'supersession_ledger_binding')
        snapshots[dispatch_path] = data
        result.append(dict(registration=reference, status='superseded_before_dispatch', scientifically_closed=False,
            native_starts_verified=0, unprepared_stages=sorted(names), reason=last['reason'], recorder=recorder,
            predecessor_native_untouched_recorded=True, predecessor_attestation_source='supervisor_record_and_ledger'))
    return result, snapshots


def final_gate(root, disposition_path, registration_path):
    cycle = root/CYCLE_REL
    registration_path = registration_path.resolve()
    workflow = registration_path.parent
    require(workflow.parent == cycle/'terminal_flow' and re.fullmatch(r'workflow_\d{3}', workflow.name)
        and registration_path.name == 'registration.json', 'workflow_registration_location')
    registration = read(registration_path)
    pairs = source_pairs(root)
    require(Path(registration['source_bundle']['path']).resolve() == pairs[-1][0].resolve(), 'active_workflow_not_latest_runtime')
    bound_read(registration['source_bundle'])
    disposition = read(disposition_path)
    require(disposition.get('schema') == SCHEMA+'.disposition' and disposition.get('reason', '').strip(), 'reviewed_disposition_required')
    require(disposition['registration_sha256'] == fingerprint(registration_path, root)['sha256'], 'disposition_registration_binding')
    require(disposition['outcome'] in ('complete', 'stopped_after_failure'), 'disposition_outcome')
    snapshots = {cycle/'ledger.jsonl': idle_ledger(cycle/'ledger.jsonl')}
    ledger_rows = [json.loads(line) for line in snapshots[cycle/'ledger.jsonl'].splitlines() if line]
    attempted = {row['task_id'] for row in ledger_rows if row['event'] == 'native_start'}
    historical, historical_snapshots = superseded_workflows(root, registration_path, ledger_rows)
    snapshots.update(historical_snapshots)
    appends = research_record_appends(root, disposition)
    dispatch_path = workflow/'dispatch_001.jsonl'
    dispatch, rows = jsonl(dispatch_path)
    require(rows and rows[-1]['event'] in ('successor_process_finished', 'dispatch_failed'), 'dispatch_not_terminal')
    snapshots[dispatch_path] = dispatch
    tasks = {}
    for block_path in sorted((cycle/'terminal_flow').glob('*/block.json')):
        for reference in read(block_path)['task_plans']:
            state = task_state(reference, attempted=bound_read(reference)['task_id'] in attempted)
            require(state['task_id'] not in tasks, 'duplicate_registered_task')
            tasks[state['task_id']] = state
    for plan_path in sorted((cycle/'runs').glob('TF_*/plan.json')):
        plan = read(plan_path)
        if plan['task_id'] not in tasks:
            reference = dict(path=str(plan_path.resolve()), sha256=fingerprint(plan_path, root)['sha256'])
            state = task_state(reference, attempted=plan['task_id'] in attempted)
            state['registration_scope'] = 'orphan_plan_without_complete_block'
            tasks[state['task_id']] = state
    unclosed = {identity: row['status'] for identity, row in tasks.items() if row['status'] != 'closed'}
    acknowledged = disposition.get('nonclosed_tasks', {})
    require(set(acknowledged) == set(unclosed) and all(acknowledged[key].get('status') == status
        and acknowledged[key].get('reason', '').strip() for key, status in unclosed.items()), 'every_nonclosed_task_requires_reason')
    missing = {entry['name'] for entry in registration['stages']
               if not (cycle/'terminal_flow'/entry['name']/'block.json').exists()}
    omitted = disposition.get('unprepared_stages', {})
    require(set(omitted) == missing and all(str(reason).strip() for reason in omitted.values()), 'every_unprepared_stage_requires_reason')
    if disposition['outcome'] == 'complete':
        require(not missing and rows[-1]['event'] == 'successor_process_finished' and rows[-1]['exitcode'] == 0,
                'complete_workflow_requires_successful_dispatch')
        completion = read(workflow/'completion.json')
        require(completion['registration']['sha256'] == disposition['registration_sha256']
            and completion.get('all_registered_development_tasks_closed') is True
            and completion.get('TEST_unlocked') is False, 'workflow_completion_binding')
        for stage in registration['stages']:
            block = read(cycle/'terminal_flow'/stage['name']/'block.json')
            require(all(tasks[bound_read(ref)['task_id']]['status'] == 'closed' for ref in block['task_plans']),
                    'current_workflow_has_nonclosed_task')
    return dict(outcome=disposition['outcome'], registration=dict(path=str(registration_path),
        sha256=disposition['registration_sha256']), tasks=list(tasks.values()), unprepared_stages=sorted(missing),
        historical_workflows=historical, research_record_appends=appends), snapshots


def verify_archive(archive, manifest_path):
    manifest = read(manifest_path)
    expected = dict(manifest['files'])
    expected['source_manifest.json'] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as stream:
        members = stream.namelist()
        require(len(members) == len(set(members)) and set(members) == set(expected), 'source_archive_member_roster')
        for name, sha in expected.items():
            require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'unsafe_archive_member')
            with stream.open(name) as entry:
                require(hashlib.file_digest(entry, 'sha256').hexdigest() == sha, 'source_archive_bytes:'+name)
    return dict(archive=archive.name, verified_members=len(expected))


def snapshot_required(path, cycle):
    return (path == cycle/'ledger.jsonl' or path.suffix == '.log'
            or path.name.startswith('dispatch_') and path.suffix == '.jsonl'
            or path.name == 'progress.jsonl')


def write_json(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def finalize(root, output, disposition_path, registration_path):
    root, output, disposition_path = root.resolve(), output.resolve(), disposition_path.resolve()
    require(output.is_relative_to(root/'outputs') and not output.exists(), 'fresh_output_directory_within_outputs_required')
    inventory = git_inventory(root)
    require(not inventory['unexpected_tracked'] and not inventory['unrelated_new_source'], 'unrelated_source_changes_require_isolation')
    gate, journal_snapshots = final_gate(root, disposition_path, registration_path)
    candidates = candidate_paths(root)
    require(not any(path.is_relative_to(output) for path in candidates), 'output_cannot_contain_input')
    candidates.append(disposition_path)
    cycle = root/CYCLE_REL
    archive_checks = [dict(**verify_archive(archive, manifest), source_manifest=fingerprint(manifest, root))
                      for manifest, archive in source_pairs(root)]
    # No output exists until all closure and archive gates have passed.
    entries, snapshot_bytes, included = [], {}, []
    initial_stats = {}
    for path in sorted(set(candidates), key=str):
        record = fingerprint(path, root)
        initial_stats[path] = (path.stat().st_size, path.stat().st_mtime_ns)
        ack_guard = compact_transfer_ack_guard(path, root) if path.name == 'delivered_ack_evidence.json.gz' else None
        if ack_guard is not None:
            record['ack_publication'] = ack_guard
        if path.name in RAW_LOCAL_ONLY and not (ack_guard and ack_guard['publish']):
            record.update(bundled=False, reason='owner_observation_ack_control_history_retained_locally')
        elif record['bytes'] > MAX_FILE_BYTES:
            record.update(bundled=False, reason='above_publication_single_file_limit')
        else:
            publish_path = path
            if snapshot_required(path, cycle):
                data = path.read_bytes()
                require(hashlib.sha256(data).hexdigest() == record['sha256'], 'snapshot_source_changed')
                # Flat names avoid exceeding Windows MAX_PATH with duplicated repository paths.
                token = hashlib.sha256(record['path'].encode('utf8')).hexdigest()[:16]
                publish_path = output/'snapshots'/(token+'_'+path.name)
                require(publish_path not in snapshot_bytes, 'snapshot_name_collision')
                snapshot_bytes[publish_path] = data
            record.update(bundled=True, publish_path=relative(publish_path, root))
            included.append(publish_path)
        entries.append(record)
    second_gate, second_journals = final_gate(root, disposition_path, registration_path)
    require(second_gate == gate and second_journals == journal_snapshots, 'execution_changed_during_publication_review')
    for path, expected in initial_stats.items():
        stat = path.stat()
        require((stat.st_size, stat.st_mtime_ns) == expected, 'evidence_changed_during_publication_review:'+str(path))
    output.mkdir(parents=True)
    for path, data in snapshot_bytes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    manifest_path = output/'manifest.json'
    write_json(manifest_path, dict(schema=SCHEMA, generated_at_utc=datetime.now(timezone.utc).isoformat(),
        repository_root=str(root), gate=gate, inventory=inventory, source_archives=archive_checks,
        max_file_bytes=MAX_FILE_BYTES, included_files=sum(row['bundled'] for row in entries),
        compact_transfer_ack_byte_limit_exclusive=COMPACT_ACK_MAX_BYTES,
        compact_transfer_ack_files=sum(row['bundled'] and row.get('ack_publication', {}).get('publish', False) for row in entries),
        included_bytes=sum(row['bytes'] for row in entries if row['bundled']), entries=entries,
        reproduction_scope='Published terminal/call/trajectory/receipt evidence supports finite outcome and protocol audits; '
            'Only compact transfer ACK subsets explicitly marked bundled are published for the separate unified-order ACK audit. '
            'Full public-observation replay and full owner ACK/command/control-history replay require the hashed local-only files. '
            'Native binary and older external dependencies remain governed by their existing repository/publication references.',
        native_started=False, git_index_modified=False, publication_does_not_certify_scientific_improvement=True))
    require(manifest_path.stat().st_size <= MAX_FILE_BYTES, 'manifest_exceeds_publication_size_limit')
    included.append(manifest_path)
    pathspec_path = output/'stage_paths.nul'
    pathspec_path.write_bytes(b''.join((':(literal)'+relative(path, root)).encode('utf8')+b'\0'
                                     for path in sorted(set(included), key=str)))
    # The pathspec itself is helper metadata; no self-referential entry is needed.
    return dict(manifest=str(manifest_path), pathspec=str(pathspec_path), included_files=len(included))


def verify_manifest(root, manifest_path):
    manifest = read(manifest_path)
    require(manifest['schema'] == SCHEMA, 'manifest_schema')
    checked = 0
    for record in manifest['entries']:
        if not record['bundled']:
            continue
        current = fingerprint(root/record['publish_path'], root)
        require(current['bytes'] == record['bytes'] and current['sha256'] == record['sha256'], 'published_file_changed')
        require(current['bytes'] <= MAX_FILE_BYTES, 'publication_size_limit')
        checked += 1
    expected = {root/row['publish_path'] for row in manifest['entries'] if row['bundled']}
    expected.add(manifest_path.resolve())
    pathspec = b''.join((':(literal)'+relative(path, root)).encode('utf8')+b'\0' for path in sorted(expected, key=str))
    require((manifest_path.parent/'stage_paths.nul').read_bytes() == pathspec, 'pathspec_does_not_exactly_match_reviewed_files')
    require(manifest_path.stat().st_size <= MAX_FILE_BYTES, 'manifest_exceeds_publication_size_limit')
    return dict(verified_included_files=checked, native_started=False, git_index_modified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('inventory', 'finalize', 'verify'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--disposition', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--workflow', type=Path, help='Explicit active workflow registration.json path (required for finalize).')
    args = parser.parse_args()
    if args.mode == 'inventory':
        paths = candidate_paths(ROOT)
        result = dict(git=git_inventory(ROOT), candidate_files=len(paths), candidate_bytes=sum(p.stat().st_size for p in paths),
                      finalization_attempted=False, native_started=False, git_index_modified=False)
    elif args.mode == 'finalize':
        require(args.output and args.disposition and args.workflow, 'output_disposition_and_workflow_required')
        result = finalize(ROOT, args.output, args.disposition, args.workflow)
    else:
        require(args.manifest, 'manifest_required')
        result = verify_manifest(ROOT, args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
