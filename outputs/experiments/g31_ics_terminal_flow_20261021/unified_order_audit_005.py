"""Independent offline unified-order audit of all 28 closed runtime005 DEV runs.

Default check mode never reads ACK exports. Execute reads only the explicitly
contracted compact transfer-ACK subset after source, closure and size guards.
No native construction, TEST execution, registration or ledger mutation.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

CONTRACT = 'deferred_complete_intermediate_results_and_transfer_ack_subset_v1'
ACK_BYTES_LIMIT = 30_000_000
ACK_JSON_BYTES_LIMIT = 300_000_000
REASONS = ('REAL_DEMAND_SUPPLY', 'NECESSARY_CLEARING', 'ORDINARY_RETURN', 'FORECAST_REPOSITION')
ACK_FIELDS = ('schema', 'now', 'owner_id', 'scope', 'delivered_transfer_acks', 'client_transfer_ledger')
ACK_ROW_FIELDS = {'request_id','sequence','attempt','observed_at','delivered_at','status','reason','received_at','delivered_copies'}
LEDGER_ROW_FIELDS = {'request_id','tray_id','source','destination','issued_at','earliest_departure','expiry',
    'message_delay','transfer_scope','status','received_at','reason','status_scope'}
SOFT_FIELDS = {'target_by', 'useful_until', 'plan_valid_until', 'latest_issue_estimate'}
EVIDENCE = ('plan.json', 'receipt.json', 'worker_report.json', 'trajectory.json.gz',
    'terminal_evidence.json.gz', 'calls.json.gz', 'controller_checkpoint_scope.json', 'delivered_ack_evidence.json.gz')
SCHEMA = 'g31.terminal_flow.unified_order_audit005.v1'


def need(ok, reason):
    if not ok:
        raise ValueError('unified_order_audit:'+reason)


def dependency():
    path = Path(__file__).with_name('final_science_audit_004.py')
    entry_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location('_unified_science_registration_guards', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    need(module.bind(path)['sha256'] == entry_sha, 'dependency_changed_during_import')
    module._unified_entry_binding = dict(path=str(path.resolve()), sha256=entry_sha)
    return module


def verify_source_contract(source_ref, science):
    need(Path(source_ref['path']).resolve().parent.name == 'terminal_flow_runtime_005', 'runtime005_only')
    manifest = science.bound_read(source_ref)
    need(manifest.get('worker_evidence_contract') == CONTRACT, 'compact_ack_source_contract_required')
    return manifest


def preflight(rows, status, source_ref, science):
    """Only metadata/stat reads here; never inspect an unclosed ACK file."""
    verify_source_contract(source_ref, science)
    for row in rows.values():
        need(row['plan'].get('source_bundle') == source_ref, 'plan_source005_binding')
        need(row['plan'].get('worker_evidence_contract') == CONTRACT, 'plan_compact_ack_contract_required')
    if status['status'] != 'ready':
        return dict(status='pending', compact_transfer_ack_subset_read=False, full_owner_history_opened=False)
    need(len(rows) == 28, 'all_28_closed_dev_runs_required')
    for row in rows.values():
        path = row['directory']/'delivered_ack_evidence.json.gz'
        need(path.is_file() and path.stat().st_size < ACK_BYTES_LIMIT, 'ack_file_must_be_below_30MB:'+str(path))
        worker = science.read(row['directory']/'worker_report.json')
        need(worker.get('delivered_ack_evidence_scope') ==
            'complete transfer ACK history and transfer ledger; owner protocol subset', 'worker_compact_ack_scope_required')
        need(worker.get('delivered_ack_evidence', {}).get('gzip_bytes') == path.stat().st_size,
             'worker_ack_export_size_binding')
    return dict(status='ready', compact_transfer_ack_subset_read=False, full_owner_history_opened=False)


def finite_time(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def read_subset(path, *, owners, horizon):
    need(path.stat().st_size < ACK_BYTES_LIMIT, 'ack_file_must_be_below_30MB')
    with gzip.open(path, 'rb') as stream:
        raw = stream.read(ACK_JSON_BYTES_LIMIT+1)
    need(len(raw) <= ACK_JSON_BYTES_LIMIT, 'ack_inflated_json_limit')
    def unique_object(pairs):
        result = {}
        for key,value in pairs:
            need(key not in result, 'duplicate_ack_json_key:'+key)
            result[key] = value
        return result
    views = json.loads(raw, object_pairs_hook=unique_object)
    need(isinstance(views, dict) and set(views) == set(owners), 'complete_ack_owner_roster')
    for owner, view in views.items():
        need(set(view) == set(ACK_FIELDS)|{'evidence_scope'}, 'compact_ack_exact_field_roster')
        scope = view['evidence_scope']
        need(view['schema'] == 'g31.owner_protocol_observation.v1'
            and view['owner_id'] == owner and view['now'] == horizon, 'ack_owner_final_time_binding')
        need(scope.get('schema') == 'g31.airport_joint_campaign.v1.transfer_ack_subset.v1'
            and scope.get('complete_owner_protocol_view') is False
            and scope.get('full_transfer_ack_history_preserved') is True
            and scope.get('full_client_transfer_ledger_preserved') is True
            and scope.get('owner_protocol_fields_retained') == list(ACK_FIELDS)
            and scope.get('original_owner_protocol_scope') == view['scope']
            and scope.get('online_actor_input') is False, 'compact_ack_scope_flags')
        need(isinstance(scope.get('owner_protocol_fields_omitted'), list)
            and not set(ACK_FIELDS).intersection(scope['owner_protocol_fields_omitted']), 'compact_ack_omitted_fields')
        need(isinstance(view['delivered_transfer_acks'], list) and isinstance(view['client_transfer_ledger'], list),
            'compact_ack_complete_lists')
        need(all(set(row) == ACK_ROW_FIELDS for row in view['delivered_transfer_acks'])
            and all(set(row) == LEDGER_ROW_FIELDS for row in view['client_transfer_ledger']), 'compact_ack_nested_field_roster')
        need(all(not isinstance(value,(dict,list)) for field in ('delivered_transfer_acks','client_transfer_ledger')
                 for row in view[field] for value in row.values()), 'compact_ack_scalar_row_fields')
    return views


def payload_category(payload):
    return {'observed_source_queue':'REAL_DEMAND_SUPPLY',
        'terminal_receiving_pressure':'NECESSARY_CLEARING',
        'ordinary_return_to_loader':'ORDINARY_RETURN',
        'joint_optional_reposition':'baseline_optional_inventory_reposition',
        'optional_zero_stock_replenishment':'baseline_optional_inventory_reposition'}.get(
            payload.get('control_reason'), 'unclassified')


def audit_rows(*, plan, checkpoint, call_rows, terminal, ack_views, frozen_audit):
    """Add raw-record checks before frozen helper dict joins can hide duplicates."""
    instrumented = plan['method'].startswith('TF-')
    orders = ((checkpoint.get('policy_state') or {}).get('empty_transport_orders') or {}).get('orders', {})
    first, native, ledgers, ack_index, violations = {}, {}, {}, defaultdict(list), []
    transfer_calls, retries, seen_orders, bound_requests = 0, 0, set(), set()
    ack_deliveries = defaultdict(list)
    for receipt in terminal.get('receipts', []):
        if receipt.get('event') == 'PROTOCOL_ACK_DELIVERED':
            ack_deliveries[receipt.get('reason')].append(receipt['time'])
    def issue(reason, **fields):
        violations.append(dict(reason=reason, **fields))
    for key, order in orders.items():
        oid = order.get('order_id')
        if oid != key or oid in seen_orders:
            issue('order_book_key_or_identity_mismatch', order_id=oid, book_key=key)
        seen_orders.add(oid)
        if order.get('reason') not in REASONS:
            issue('unknown_order_reason', order_id=oid, actual_reason=order.get('reason'))
        if order.get('request_id') is not None:
            if order['request_id'] in bound_requests:
                issue('duplicate_order_request_identity', request_id=order['request_id'])
            bound_requests.add(order['request_id'])
    for call in call_rows:
        if call.get('kind') != 'transfer':
            continue
        transfer_calls += 1
        payload = call['request']; rid = payload['request_id']
        leaked = sorted(SOFT_FIELDS.intersection(payload))
        if leaked:
            issue('soft_order_times_in_any_transfer_payload', request_id=rid, fields=leaked, retry=bool(call.get('retry')))
        if not finite_time(payload.get('expiry')) or not finite_time(payload.get('issued_at')):
            issue('invalid_native_lease_time', request_id=rid)
        if call.get('retry'):
            retries += 1
            if rid not in first or first[rid]['request'] != payload:
                issue('retry_changed_or_missing_first_payload', request_id=rid)
        elif rid in first:
            issue('duplicate_nonretry_submission', request_id=rid)
        else:
            first[rid] = call
    for row in terminal['transfers']:
        rid = row['request_id']
        if rid in native:
            issue('duplicate_native_request_identity', request_id=rid)
        native[rid] = row
    for owner, view in ack_views.items():
        for row in view['client_transfer_ledger']:
            rid = row['request_id']
            if rid in ledgers:
                issue('duplicate_client_ledger_request_identity', request_id=rid)
            ledgers[rid] = (owner, row)
        sequences = set()
        for ack in view['delivered_transfer_acks']:
            rid = ack['request_id']; call = first.get(rid)
            if call is None or call['request'].get('owner_id') != owner:
                issue('ack_without_same_owner_submission', request_id=rid)
            times = [ack.get(k) for k in ('observed_at','delivered_at')]
            issued = call['request'].get('issued_at') if call else None
            if (not all(finite_time(t) for t in times) or not finite_time(issued)
                    or not issued <= times[0] <= times[1] <= plan['horizon']):
                issue('ack_delivery_time_invalid', request_id=rid)
            if type(ack.get('delivered_copies')) is not int or ack['delivered_copies'] <= 0:
                issue('ack_not_actually_delivered', request_id=rid)
            sequence = (rid, ack.get('sequence'))
            if type(ack.get('sequence')) is not int or ack['sequence'] <= 0 or sequence in sequences:
                issue('ack_sequence_duplicate_or_invalid', request_id=rid)
            if type(ack.get('attempt')) is not int or ack['attempt'] <= 0:
                issue('ack_attempt_invalid', request_id=rid)
            delivery = ack_deliveries.get(rid+':'+str(ack.get('sequence')), [])
            if not delivery or len(delivery) != ack.get('delivered_copies') or min(delivery) != ack.get('delivered_at'):
                issue('ack_physical_delivery_receipts_mismatch', request_id=rid, sequence=ack.get('sequence'))
            sequences.add(sequence); ack_index[rid].append(ack)
    for name, values in [('native', native), ('client_ledger', ledgers)]:
        if set(first) != set(values):
            issue('actual_request_set_mismatch', compared=name,
                submit_only=sorted(set(first)-set(values)), other_only=sorted(set(values)-set(first)))
    for rid, call in first.items():
        payload = call['request']
        for name, actual in [('native',native.get(rid)), ('client_ledger',ledgers.get(rid,(None,None))[1])]:
            if actual is None:
                continue
            for field in ('tray_id','source','destination','issued_at','expiry'):
                if (name == 'client_ledger' or field in actual) and actual.get(field) != payload.get(field):
                    issue('request_payload_evidence_mismatch', request_id=rid, evidence=name, field=field)
        if rid in ledgers and (ledgers[rid][0] != payload['owner_id'] or
                ledgers[rid][1].get('status_scope') != 'own_payload_and_last_delivered_ack_only'):
            issue('client_ledger_owner_scope_mismatch', request_id=rid)
    if instrumented:
        violations.extend(frozen_audit['violations'])
        if not frozen_audit['request_sets_equal']:
            issue('instrumented_order_submit_native_sets_differ')
        for order in orders.values():
            rid = order.get('request_id')
            if rid not in first:
                continue
            category = payload_category(first[rid]['request'])
            expected = 'FORECAST_REPOSITION' if category == 'baseline_optional_inventory_reposition' else category
            if expected != order['reason']:
                issue('order_reason_payload_category_mismatch', request_id=rid, payload_category=category)
    elif orders:
        issue('unexpected_baseline_upper_order_instrumentation')
    categories = {reason: Counter(orders=0, submitted=0, accepted=0, received=0, failed_at_export=0) for reason in REASONS}
    if instrumented:
        for reason, counts in frozen_audit['by_reason'].items():
            categories.setdefault(reason,Counter()).update(counts)
        classification = 'serialized_upper_order_reason; optional category does not itself prove forecast guidance or service gain'
    else:
        for rid, call in first.items():
            counts = categories.setdefault(payload_category(call['request']),Counter(orders=0,submitted=0,accepted=0,received=0,failed_at_export=0))
            counts['submitted'] += 1
            counts['accepted'] += any(a.get('status') in {'accepted','granted','dispatching','departed','in_transit','received'} for a in ack_index[rid])
            counts['received'] += native.get(rid,{}).get('received_at',-1) >= 0
            counts['failed_at_export'] += native.get(rid,{}).get('status') in {'failed','rejected','expired'}
        classification = 'actual_payload_control_reason_only; optional inventory reposition kept separate; no order IDs synthesized'
    for reason,counts in categories.items():
        category_orders = [order for order in orders.values() if order.get('reason') == reason]
        counts['all_order_records'] = len(category_orders)
        counts['unsubmitted_order_records'] = sum(order.get('request_id') is None for order in category_orders)
        counts['submitted_order_records'] = len(category_orders)-counts['unsubmitted_order_records']
    by_reason = {reason: dict(counts, accepted_per_submitted=(counts['accepted']/counts['submitted'] if counts['submitted'] else None),
        received_per_submitted=(counts['received']/counts['submitted'] if counts['submitted'] else None)) for reason,counts in categories.items()}
    request_chains = [dict(request_id=rid, actual_submission=call['request'],
        payload_category=payload_category(call['request']), native_transfer=native.get(rid),
        client_transfer_ledger=ledgers.get(rid,(None,None))[1], delivered_acks=ack_index[rid])
        for rid,call in first.items()]
    return dict(instrumentation='serialized_unified_order_book' if instrumented else 'upper_order_book_not_instrumented',
        classification_basis=classification, actual_nonretry_requests=len(first), actual_transfer_call_records=transfer_calls,
        retry_call_records=retries, native_request_records=len(terminal['transfers']), unique_native_requests=len(native),
        unique_client_ledger_requests=len(ledgers), all_order_records=len(orders), unsubmitted_order_records=sum(o.get('request_id') is None for o in orders.values()),
        submitted_order_records=sum(o.get('request_id') is not None for o in orders.values()),
        payload_classification_counts=dict(Counter(payload_category(row['request']) for row in first.values())),
        by_reason=by_reason, violations=violations, passed=not violations, request_chains=request_chains)


def frozen_book_audit(flow, directory, views):
    """Give the frozen join the exact validated complete subset, without rereading."""
    previous = flow.read
    ack_path = (directory/'delivered_ack_evidence.json.gz').resolve()
    def validated_read(path):
        return views if Path(path).resolve() == ack_path else previous(path)
    try:
        flow.read = validated_read
        return flow.audit_unified_order_book(directory)
    finally:
        flow.read = previous


def run_audit(row, h, science):
    plan, directory = row['plan'], row['directory']
    refs = {name:science.bind(directory/name) for name in EVIDENCE}
    data = science.bound_read(plan['input'])
    owners = sorted({r['resource_owner'] for r in data['node_contracts']})
    del data
    views = read_subset(directory/'delivered_ack_evidence.json.gz', owners=owners, horizon=plan['horizon'])
    checkpoint = science.read(directory/'controller_checkpoint_scope.json')
    terminal = science.read(directory/'terminal_evidence.json.gz')
    frozen = frozen_book_audit(h['flow'], directory, views)
    extra = audit_rows(plan=plan, checkpoint=checkpoint, terminal=terminal, ack_views=views, frozen_audit=frozen,
        call_rows=h['stream'].iter_json_array_gz(directory/'calls.json.gz'))
    science.verify_bindings(list(refs.values()), 'unified_run_evidence_changed')
    return dict(schema=SCHEMA+'.run', task_id=plan['task_id'], method=plan['method'], parent=plan['parent'],
        source_bundle=plan['source_bundle'], worker_evidence_contract=plan['worker_evidence_contract'],
        evidence=refs, frozen_unified_order_book=frozen, full_request_audit=extra,
        compact_transfer_ack_subset_read=True, full_owner_history_opened=False,
        frozen_join_receives_same_validated_complete_ack_subset=True,
        native_starts=0, scientific_service_improvement_claimed=False)


def dependency_refs(rows):
    found = {}
    def walk(value):
        if isinstance(value,dict):
            if {'path','sha256'} <= set(value):
                need(value['path'] not in found or found[value['path']]['sha256'] == value['sha256'], 'conflicting_dependency_bindings')
                found[value['path']] = dict(path=value['path'],sha256=value['sha256'])
            else:
                for child in value.values(): walk(child)
        elif isinstance(value,list):
            for child in value: walk(child)
    for row in rows.values(): walk(row['plan'])
    return list(found.values())


def aggregate_denominators(reports):
    groups = {}
    for report in reports:
        group = groups.setdefault(report['instrumentation'],dict(runs=0,by_reason={}))
        group['runs'] += 1
        for reason,values in report['by_reason'].items():
            target = group['by_reason'].setdefault(reason,Counter())
            for name,value in values.items():
                if type(value) is int:
                    target[name] += value
    for group in groups.values():
        for reason,values in group['by_reason'].items():
            group['by_reason'][reason] = dict(values,
                accepted_per_submitted=values['accepted']/values['submitted'] if values['submitted'] else None,
                received_per_submitted=values['received']/values['submitted'] if values['submitted'] else None)
    return groups


def execute(rows, status, source_ref, workflow_ref, h, science, output, producers):
    need(status['status'] == 'ready', 'all_28_closed_dev_runs_required')
    preflight(rows,status,source_ref,science)
    output = Path(output)
    need(not output.exists(), 'fresh_output_required')
    refs = dependency_refs(rows)
    science.verify_bindings(producers+refs, 'producer_or_dependency_changed_before_audit')
    science.verify_sources(source_ref); science.bound_read(workflow_ref)
    output.mkdir(parents=True)
    science.fresh(output/'pending.json',dict(schema=SCHEMA, status='in_progress', producer_bindings=producers,
        no_complete_report_without_COMPLETE=True, source_bundle=source_ref, workflow=workflow_ref))
    reports, artifacts = [], []
    for key,row in sorted(rows.items()):
        print(json.dumps(dict(stage='unified_order_audit', parent=key[0],method=key[1])),flush=True)
        report = run_audit(row,h,science)
        reference = science.fresh(output/f'P{key[0]}_{key[1]}_unified_orders.json.gz',report)
        artifacts.append(reference)
        reports.append(dict(task_id=report['task_id'], parent=key[0], method=key[1], artifact=reference,
            **{k:v for k,v in report['full_request_audit'].items() if k != 'request_chains'}))
    science.verify_sources(source_ref); science.bound_read(workflow_ref)
    end_rows,end_status = science.inspect_blocks([r['path'] for r in status['blocks']],source_ref,h)
    need(end_status == status and set(end_rows) == set(rows), 'closure_changed_during_audit')
    science.verify_bindings(producers+refs+artifacts, 'producer_dependency_or_artifact_changed_during_audit')
    for artifact in artifacts:
        saved = science.bound_read(artifact)
        science.verify_bindings(list(saved['evidence'].values()), 'run_evidence_changed_during_audit')
    summary = dict(schema=SCHEMA, status='complete', source_bundle=source_ref, workflow=workflow_ref,
        producer_bindings=producers, dependency_bindings=refs, run_reports=reports, registered_runs=28,
        instrumented_transport_runs=sum(r['instrumentation']=='serialized_unified_order_book' for r in reports),
        baseline_upper_book_uninstrumented_runs=sum(r['instrumentation']=='upper_order_book_not_instrumented' for r in reports),
        violations_total=sum(len(r['violations']) for r in reports), all_request_audits_passed=all(r['passed'] for r in reports),
        aggregate_by_instrumentation=aggregate_denominators(reports),
        compact_transfer_ack_subset_read=True, full_owner_history_opened=False,
        ack_file_limit_bytes_exclusive=ACK_BYTES_LIMIT, ack_inflated_json_limit_bytes=ACK_JSON_BYTES_LIMIT,
        native_starts=0, TEST_unlocked=False, scientific_service_improvement_claimed=False,
        scope='independent unified ledger artifact; does not change the separate final_science no-ACK declaration',
        baseline_order_identity_not_certified=True, all_four_categories_retained_even_when_zero=True)
    report_ref = science.fresh(output/'unified_order_summary.json',summary)
    science.verify_bindings(producers+refs, 'producer_or_dependency_changed_before_complete')
    science.fresh(output/'COMPLETE.json',dict(schema=SCHEMA, status='complete', summary=report_ref,
        compact_transfer_ack_subset_read=True, full_owner_history_opened=False,
        producer_dependency_source_and_evidence_checked_at_entry_and_end=True,
        violations_total=summary['violations_total'], all_request_audits_passed=summary['all_request_audits_passed']))


def main():
    sys.dont_write_bytecode = True
    self_entry = dict(path=str(Path(__file__).resolve()),sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    science = dependency()
    producers = [self_entry,science._unified_entry_binding]
    science.verify_bindings(producers, 'producer_changed_at_entry')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest',type=Path,required=True)
    parser.add_argument('--workflow',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--output-dir',type=Path)
    args = parser.parse_args()
    source_ref = science.bind(args.source_manifest)
    verify_source_contract(source_ref,science)
    source_root = science.verify_sources(source_ref)
    blocks,workflow_ref = science.workflow_blocks(args.workflow,source_ref)
    need(args.workflow.resolve().parent.name == 'workflow_005', 'workflow005_only')
    h = science.load_helpers(source_root)
    rows,status = science.inspect_blocks(blocks,source_ref,h)
    check = preflight(rows,status,source_ref,science)
    if not args.execute:
        science.verify_bindings(producers, 'audit_producer_changed_during_check')
        print(json.dumps(dict(**check, registered_runs=len(rows), expected_runs=28,
            pending=status['pending'], source_bundle=source_ref, producer_bindings=producers,
            native_starts=0, audit_executed=False),indent=2)); return
    need(args.output_dir is not None, 'execute_requires_output_directory')
    execute(rows,status,source_ref,workflow_ref,h,science,args.output_dir,producers)


if __name__ == '__main__':
    main()
