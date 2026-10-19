"""Relocatable standard-library evidence checks; never runs project code or native."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics
import sys
import xml.etree.ElementTree as ElementTree
import zipfile


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def known_prediction(prediction):
    completion = prediction.get('completion')
    return prediction.get('status') == 'conditional_prediction' and type(completion) is dict \
        and set(completion) == {'loaded', 'receiver', 'reuse1', 'reuse2', 'blocker'} \
        and all(type(value) in (int, float) and math.isfinite(value) and value >= 0
                for value in completion.values())


def references_in(value):
    def path(value):
        return type(value) is str and (re.match(r'^[A-Za-z]:[/\\]', value) is not None
                                       or value.startswith('/'))

    def hash_value(value):
        return type(value) is str and re.fullmatch(r'[0-9a-fA-F]{64}', value) is not None

    if type(value) is dict:
        if path(value.get('path')) and hash_value(value.get('sha256')):
            yield value['path'].replace('\\', '/'), value['sha256'].lower()
        for key, item in value.items():
            if path(key) and hash_value(item):
                yield key.replace('\\', '/'), item.lower()
            elif type(item) in (dict, list):
                yield from references_in(item)
    elif type(value) is list:
        for item in value:
            yield from references_in(item)


def safe_name(name):
    parts = PurePosixPath(name).parts
    require(name and '\\' not in name and not name.startswith('/')
            and ':' not in name and all(part not in ('', '.', '..') for part in parts)
            and '/'.join(parts) == name, 'unsafe_member:' + name)
    return name


class Archive:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.archive = zipfile.ZipFile(self.path) if self.path.is_file() else None
        if self.archive:
            names = [item.filename for item in self.archive.infolist()]
            require(len(names) == len(set(names)), 'duplicate_zip_members')
            require(not any(item.is_dir() for item in self.archive.infolist()), 'unexpected_directory_member')
            require(self.archive.testzip() is None, 'zip_crc_failure')
        else:
            names = [item.relative_to(self.path).as_posix()
                     for item in self.path.rglob('*') if item.is_file()]
        self.names = set(safe_name(name) for name in names)

    def read(self, name):
        safe_name(name)
        require(name in self.names, 'missing_member:' + name)
        if self.archive:
            return self.archive.read(name)
        target = (self.path / name).resolve()
        require(target.is_relative_to(self.path), 'symlink_escape:' + name)
        return target.read_bytes()

    def json(self, name):
        payload = self.read(name)
        return json.loads(gzip.decompress(payload) if name.endswith('.gz') else payload)

    def close(self):
        if self.archive:
            self.archive.close()


def nonpublication_receipts(raw):
    result = []
    for row in raw['result']['receipts']:
        identity = row.get('reason', '').rsplit(':', 1)[0]
        request = raw['outbox'].get(identity)
        publication_ack = row['event'] in ('PROTOCOL_ACK_DELIVERED', 'PROTOCOL_COMMAND_ACK_DELIVERED') \
            and request is not None and request['kind'] in ('planning_snapshot', 'demand')
        if not publication_ack:
            result.append(row)
    return result


def check_successful_pair(archive, mapped, member):
    receipt = archive.json(member)
    require(receipt['status'] == 'completed_successful_refresh_probe'
            and receipt['process']['status'] == 'exited' and receipt['process']['exitcode'] == 0,
            'fresh_pair_process_not_closed')
    report = archive.json(mapped(receipt['worker_report']))
    plan = archive.json(mapped(receipt['plan']))
    require(report['status'] == 'completed_successful_refresh_probe'
            and report['source_and_reference_exit_pins_passed'] is True
            and plan['automatic_retries'] == 0 and plan['native_branches'] == 1
            and plan['extra_successful_pairs'] == 1 and plan['probe_owner'] == 'B', 'fresh_pair_protocol')
    raw = archive.json(mapped(report['native_raw']))
    native_receipt = archive.json(mapped(report['native_receipt']))
    require(native_receipt['status'] == 'assessed'
            and native_receipt['run_acceptance_status'] == 'closed_run_acceptance_passed'
            and canonical(native_receipt['raw_artifact']) == canonical(report['native_raw']), 'fresh_pair_raw_binding')
    observations = archive.json(mapped(report['probe_observations']))['B']['successful_refresh_probe']
    audit = archive.json(mapped(report['refresh_audit']))
    binding = audit['episode_binding']
    require(binding['plan_episode_id'] == plan['episode_id'] == observations['episode_id']
            and canonical(binding['plan']) == canonical(receipt['plan'])
            and canonical(binding['native_raw']) == canonical(report['native_raw'])
            and canonical(binding['native_receipt']) == canonical(report['native_receipt']), 'fresh_pair_episode_binding')
    pair = observations['successful_observations']
    require(len(pair) == len(audit['records']) == 2, 'fresh_pair_exactly_two_successes')
    before, after = pair
    for row, record in zip(pair, audit['records'], strict=True):
        evidence = row['evidence']
        now = evidence['at']
        endpoints = evidence['information']['raw_endpoints']
        require(type(now) in (int, float) and math.isfinite(now)
                and evidence['owner'] == row['observation']['owner'] == endpoints['view']['owner_id'] == 'B'
                and now == row['observation']['at'] == endpoints['view']['now'], 'fresh_pair_current_owner_epoch')
        require(row['observation_only'] is True and row['action_or_transition_created'] is False,
                'fresh_pair_observation_not_action')
        require(row['model_report']['status'] == row['model_report']['seed']['status'] == 'conditional_current_seed'
                and canonical(row['model_report']['seed']['evidence']) == canonical(evidence)
                and len(row['model_report']['candidate_results']) == 2
                and all(known_prediction(value) for value in row['model_report']['candidate_results'].values()),
                'fresh_pair_complete_current_prediction')
        require(evidence['information']['native_delivery_verified'] is True
                and evidence['information']['online_information_delivered'] is True, 'fresh_pair_delivery_scope')
        require(sha(canonical(row['initial_reference'])) == row['initial_reference_sha256'], 'fresh_pair_original_reference_hash')
        require(row['initial_reference']['candidate_index'] == 4
                and row['initial_reference']['reference_refresh_allowed'] is False, 'fresh_pair_unchanged_reference_policy')
        require(canonical(record['evidence']) == canonical(evidence)
                and record['episode_id'] == report['native_raw']['sha256'], 'fresh_pair_saved_audit_record_binding')
        own = endpoints['command']['last_delivered_ack']['planning_snapshot_v3']
        peer = [value for value in endpoints['received']
                if value['capture']['capture_v2']['local_capture']['message_id'] == evidence['collection']['peer_message']]
        require(len(peer) == 1, 'fresh_pair_exact_peer_message')
        for side, envelope in (('own', own), ('peer', peer[0])):
            capture = envelope['capture']['capture_v2']['local_capture']
            identity = {key: capture[key] for key in ('message_id', 'publication_sequence', 'captured_at')}
            require(canonical(identity) == canonical(row['publication_identities'][side])
                    and capture['captured_at'] <= now, 'fresh_pair_native_publication_identity')
            delivered = [entry['ack']['planning_snapshot_v3'] for entry in raw['outbox'].values()
                         if type(entry.get('ack')) is dict and 'planning_snapshot_v3' in entry['ack']
                         and entry['ack']['planning_snapshot_v3']['capture']['capture_v2']['local_capture']['message_id']
                         == capture['message_id']]
            require(len(delivered) == 1 and canonical(delivered[0]) == canonical(envelope),
                    'fresh_pair_publication_not_in_actual_outbox')
        enabled_default = [value for value in row['candidate_mask'] if value['action_id'] == 'native_default']
        require(len(enabled_default) == 1 and enabled_default[0]['enabled'] is True
                and enabled_default[0]['guard_status'] == 'passed', 'fresh_pair_default_guard')
    require(after['evidence']['at'] > before['evidence']['at'], 'fresh_pair_not_later')
    require(canonical(before['initial_reference']) == canonical(after['initial_reference']), 'fresh_pair_reference_drift')
    for side in ('own', 'peer'):
        first, second = before['publication_identities'][side], after['publication_identities'][side]
        require(first['message_id'] != second['message_id']
                and second['publication_sequence'] > first['publication_sequence']
                and second['captured_at'] > first['captured_at'], 'fresh_pair_not_new_' + side)
    followup = observations['followup_request']
    require(followup['prior_request_id'] == before['evidence']['collection']['request_id']
            and followup['request_id'] == after['evidence']['collection']['request_id']
            and followup['native_physics_paused'] is False
            and followup['additional_physical_commands'] == 0, 'fresh_pair_followup_identity')
    transitions = raw['later_transitions']
    require(len(transitions) == 2 and [row['owner'] for row in transitions] == ['A', 'B']
            and [row['executed_action_id'] for row in transitions] == ['return_now', 'native_default'],
            'fresh_pair_extra_or_changed_business_action')
    require(canonical(transitions[1]['observation']) == canonical(after['observation'])
            and canonical(transitions[0]['next_observation']) == canonical(after['observation'])
            and transitions[1]['command_id'] is None and transitions[1]['command_ids'] == []
            and transitions[1]['ACK'] is None and transitions[1]['ACK_status'] == 'not_applicable_no_command',
            'fresh_pair_actual_action_binding')
    require(all(row['conditional_protection_status'] == 'passed' and row['actor_state_unchanged'] is True
                and row['actual_physical_effect']['next_edge_enter'] is not None for row in transitions),
            'fresh_pair_guard_or_effect')
    require(audit['audit']['status'] == 'full_refresh_required'
            and audit['audit']['cache_execution_authorized'] is False
            and audit['audit']['native_computation_reduced'] is False, 'fresh_pair_no_cache_claim')
    baseline = archive.json(mapped(plan['baseline']['raw.json.gz']))
    for key in ('input',):
        require(canonical(raw[key]) == canonical(baseline[key]), 'fresh_pair_input_difference')
    for key in ('jobs', 'trays'):
        require(canonical(raw['result'][key]) == canonical(baseline['result'][key]), 'fresh_pair_physical_' + key)
    left, right = nonpublication_receipts(raw), nonpublication_receipts(baseline)
    require(canonical(left) == canonical(right), 'fresh_pair_nonpublication_receipt_difference')
    require(canonical(raw['summary']['completion']) == canonical(baseline['summary']['completion']),
            'fresh_pair_per_job_regression')
    return {'kind': 'successful_refresh_pair', 'member': member, 'actual_successful_observations': 2,
            'additional_business_actions': 0, 'nonpublication_receipts_compared': len(left),
            'times': [row['evidence']['at'] for row in pair],
            'scope': 'Strict recorded current/publication/action/physical bindings; no recreated native authority or cross-event cache permission.'}


def verify(source):
    archive = Archive(source)
    try:
        manifest = archive.json('MANIFEST.sha256.json')
        require(manifest['schema'] == 'g31.refresh.review_bundle.v1', 'manifest_schema')
        records = manifest['files']
        listed = {row['path'] for row in records}
        require(len(records) == len(listed), 'duplicate_manifest_records')
        require(archive.names == listed | {'MANIFEST.sha256.json'}, 'manifest_member_set_mismatch')
        for row in records:
            payload = archive.read(row['path'])
            require(len(payload) == row['bytes'] and sha(payload) == row['sha256'],
                    'byte_hash_mismatch:' + row['path'])
        mapping = archive.json('PATH_MAP.json')
        indexed = {}
        for row in mapping['references']:
            key = (row['original_path'].replace('\\', '/'), row['sha256'])
            require(key not in indexed or indexed[key] == row['member'], 'ambiguous_path_mapping')
            indexed[key] = row['member']
            require(sha(archive.read(row['member'])) == row['sha256'], 'mapped_reference_hash_mismatch')
        omissions = archive.json('NATIVE_DEPENDENCIES_NOT_BUNDLED.json')['dependencies']
        omitted = {(row['original_path'].replace('\\', '/'), row['sha256']) for row in omissions}
        require(all(type(row.get('reason')) is str and row['reason'] for row in omissions), 'unexplained_omission')
        reference_occurrences = 0
        for member in sorted(archive.names):
            if member.startswith(('repo/', 'attachments/')) and member.endswith(('.json', '.json.gz', '.jsonl')):
                payload = archive.read(member)
                plain = gzip.decompress(payload) if member.endswith('.gz') else payload
                values = [json.loads(line) for line in plain.splitlines() if line.strip()] \
                    if member.endswith('.jsonl') else [json.loads(plain)]
                for document in values:
                    for key in references_in(document):
                        require(key in indexed or key in omitted, 'unresolved_saved_reference:' + member + ':' + key[0])
                        reference_occurrences += 1

        def mapped(reference):
            key = (reference['path'].replace('\\', '/'), reference['sha256'])
            require(key in indexed, 'unmapped_reference:' + key[0])
            return indexed[key]

        checks = []
        for specification in archive.json('AUDIT_SPEC.json')['checks']:
            kind = specification['kind']
            member = specification['member']
            if kind == 'pytest':
                receipt = archive.json(member)
                tree = ElementTree.fromstring(archive.read(mapped(receipt['xml'])))
                suites = [tree] if tree.tag == 'testsuite' else list(tree.iter('testsuite'))
                counts = {key: sum(int(suite.attrib.get(key, 0)) for suite in suites)
                          for key in ('tests', 'failures', 'errors', 'skipped')}
                require(counts == receipt['counts'], 'pytest_counts:' + member)
                if receipt.get('status') == 'passed':
                    require(receipt['process']['status'] == 'exited'
                            and receipt['process']['exitcode'] == 0
                            and counts['failures'] == counts['errors'] == 0,
                            'pytest_false_success:' + member)
                checks.append({'kind': kind, 'member': member, 'counts': counts})
            elif kind == 'native_receipt':
                receipt = archive.json(member)
                raw = archive.json(mapped(receipt['raw_artifact']))
                if receipt.get('status') == 'assessed':
                    require(receipt.get('run_acceptance_status') == 'closed_run_acceptance_passed',
                            'native_unclosed:' + member)
                    require(raw['summary']['status'] == 'assessed', 'raw_unassessed:' + member)
                    require(canonical(receipt['summary']) == canonical(raw['summary']), 'native_summary_mismatch')
                    acceptance = archive.json(str(PurePosixPath(member).parent / 'acceptance.json'))
                    require(acceptance['status'] == 'closed_run_acceptance_passed'
                            and acceptance['active'] is False and acceptance['invalid'] == [], 'native_acceptance_not_closed')
                    require(mapped(acceptance['run_reference']) == mapped(receipt['plan']), 'native_plan_binding')
                checks.append({'kind': kind, 'member': member,
                               'recorded_status': receipt.get('status'),
                               'raw_status': raw.get('summary', {}).get('status')})
            elif kind == 'service_abba':
                report = archive.json(member)
                plan = archive.json(specification['plan_member'])
                references = {}
                for item in plan['inputs']:
                    raw = archive.json(mapped(item['raw']))
                    for transition in raw['later_transitions']:
                        if transition['owner'] in item['owners']:
                            references[item['name'] + '_' + transition['owner']] = transition['model_report']
                grouped = {}
                for row in report['rows']:
                    result = archive.json(mapped(row['artifact']))
                    subset = {key: result[key] for key in ('status', 'seed', 'candidate_results')}
                    reference = {key: references[row['context']][key] for key in subset}
                    require(subset['status'] == subset['seed']['status'] == 'conditional_current_seed'
                            and all(known_prediction(prediction) for prediction in subset['candidate_results'].values())
                            and len(subset['candidate_results']) == 2, 'abba_unknown_predictions')
                    require(canonical(subset) == canonical(reference), 'abba_strict_prediction_parity')
                    require(sha(canonical(subset)) == row['result_sha256'] == row['reference_sha256'],
                            'abba_semantic_hash')
                    if 'baseline_archive' in plan:
                        require(result['evaluation']['source_exit_pins_passed'] is True,
                                'incremental_abba_request_source_exit_pins')
                        if row['method'] == 'request_shared_previous':
                            for item in plan['baseline_archive']['modules'].values():
                                require(result['evaluation']['source_sha256'].get(item['path']) == item['sha256'],
                                        'incremental_abba_previous_source_binding')
                    require(type(row['wall_ms']) in (int, float) and math.isfinite(row['wall_ms'])
                            and row['wall_ms'] >= 0, 'abba_invalid_time')
                    grouped.setdefault(row['context'], []).append(row)
                for context in report['contexts']:
                    rows = sorted(grouped[context['context']], key=lambda row: row['order_index'])
                    require([row['method'] for row in rows] == plan['order'], 'abba_order')
                    for method, count in Counter(plan['order']).items():
                        values = [row['wall_ms'] for row in rows if row['method'] == method]
                        expected = {'min_ms': min(values), 'median_ms': statistics.median(values),
                                    'max_ms': max(values), 'samples': count}
                        require(canonical(expected) == canonical(context['timings'][method]), 'abba_statistics')
                    ratio = statistics.median([row['wall_ms'] for row in rows if row['method'] == plan['order'][0]]) \
                        / statistics.median([row['wall_ms'] for row in rows if row['method'] == plan['order'][1]])
                    for name, value in context['timings'].items():
                        if 'ratio' in name:
                            require(canonical(value) == canonical(ratio), 'abba_ratio')
                    if 'median_ratio_previous_over_current' in context:
                        require(canonical(context['median_ratio_previous_over_current']) == canonical(ratio),
                                'incremental_abba_ratio')
                checks.append({'kind': kind, 'member': member, 'reports': len(report['rows']),
                               'strict_complete_seed_prediction_parity': True})
            elif kind == 'successful_refresh_pair':
                checks.append(check_successful_pair(archive, mapped, member))
            elif kind == 'strict_json_fields':
                left = archive.json(member)
                right = archive.json(specification['other_member'])
                for chain in specification['fields']:
                    left_value, right_value = left, right
                    for key in chain:
                        left_value, right_value = left_value[key], right_value[key]
                    require(canonical(left_value) == canonical(right_value), 'strict_json_fields:' + repr(chain))
                checks.append({'kind': kind, 'member': member, 'fields': specification['fields']})
            else:
                raise ValueError('unknown_audit_kind:' + kind)
        publication = archive.json('SNAPSHOT_IDENTITY.json')
        require(publication['fresh_native_execution_portable'] is False
                and publication['commit_or_push_performed_by_packager'] is False,
                'unsupported_publication_or_native_claim')
        return {'status': 'passed', 'verified_member_count': len(records),
                'verified_reference_count': len(indexed), 'checks': checks,
                'saved_reference_occurrences_checked': reference_occurrences,
                'explicitly_omitted_native_or_historical_reference_count': len(omitted),
                'native_executions': 0, 'model_inference_executions': 0, 'training_executions': 0,
                'scope': 'Exact bytes, explicit original-path/hash mappings and configured saved-data checks only; not fresh native, timing, safety, learning-generalization or 100ms certification.'}
    finally:
        archive.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path, help='ZIP or extracted bundle directory')
    arguments = parser.parse_args()
    try:
        result = verify(arguments.bundle)
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'error': str(error)}))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
