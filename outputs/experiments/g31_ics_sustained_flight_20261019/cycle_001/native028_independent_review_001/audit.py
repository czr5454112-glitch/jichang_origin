"""Read-only standard-library audit of the saved native028 gate and C00 plan.

Never imports the runtime, controller, gate, model, or training modules.
No native construction, process launch, or simulation is performed.
"""
from pathlib import Path
import copy
import gzip
import hashlib
import json

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
GATE = BASE / 'native028_receiver_gate_002'
CHECKS = 0


def require(value, reason):
    global CHECKS
    CHECKS += 1
    if not value:
        raise ValueError(reason)


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def stable(value, path='$', removed=None):
    # Deliberately narrower than production: only the actual observed timing
    # fields are ignored. No event/ACK/simulation timestamp is excluded.
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            child_path = path + '.' + key
            if child_path in {'$.outputs[].returned.wall_seconds', '$.outputs[].returned.advance.wall_seconds'}:
                if removed is not None:
                    removed[child_path] = removed.get(child_path, 0) + 1
            else:
                result[key] = stable(child, child_path, removed)
        return result
    if isinstance(value, list):
        return [stable(child, path + '[]', removed) for child in value]
    return value


def main():
    plan = read(GATE / 'plan.json')
    receipt = read(GATE / 'receipt.json')
    contract_path = BASE / 'native028_accepted_contract_001.json'
    contract = read(contract_path)
    require(receipt['plan_sha256'] == sha(GATE / 'plan.json'), 'gate plan binding')
    require(contract['semantic_gate'] == reference(GATE / 'receipt.json'), 'accepted gate binding')
    require(contract['binary_sha256'] == sha(contract['binary']) == plan['binary']['sha256'], 'accepted binary')
    require(contract['complete_request_100ms_certified'] is False and contract['global_deadlock_freedom_established'] is False,
            'bounded acceptance claims')
    for path, expected in receipt['evidence_sha256'].items():
        require(sha(path) == expected, 'evidence bytes: ' + path)
    require(plan['maximum_native_constructor_attempts'] == 9 and plan['native_session_fork_count'] == 0,
            'finite constructor/fork budget')
    require(plan['maximum_parallel_workers'] == 1 and plan['automatic_retries'] == 0, 'serial no retry')
    rows, summaries = {}, {}
    attempts = 0
    for arm, names in (('native027', ('default',)), ('native028', ('default', 'explicit_zero', 'reserve1', 'reserve2'))):
        process = read(GATE / (arm + '.process.json'))
        completion = read(GATE / arm / 'completion.json')
        require(process['status'] == 'exited' and process['exitcode'] == 0
                and process['windows_job_kill_on_close'] and process['child_released_only_after_job_assignment'], 'bounded arm')
        require(completion['status'] == 'all_declared_fixtures_executed' and set(completion['raw']) == set(names), 'complete arm')
        require(completion['constructor_attempts'] == (1 if arm == 'native027' else 8), 'actual declared constructor count')
        attempts += completion['constructor_attempts']
        rows[arm] = {}
        for name in names:
            raw_ref = completion['raw'][name]
            require(reference(raw_ref['path']) == raw_ref, 'raw file binding')
            row = read(raw_ref['path']); rows[arm][name] = row
            require(row['initial_seal'] == row['checkpoint_initial_seal']
                    and row['final_seal'] == row['checkpoint_final_seal'], 'checkpoint seals')
            result = row['outputs'][-1]['returned']
            require(result['physical_clock'] == 20. and len(result['jobs']) == 1 and len(result['trays']) == 5, 'physical fixture domain')
            transfers = {item['request_id']: item for item in result['transfers']}
            require(len(transfers) == 2, 'immutable retry has one reservation')
            grants = [item for item in result['receipts'] if item['event'] == 'EXPORT_GRANTED']
            statuses = [transfers['live:1:A:return:' + tray]['status'] for tray in ('E1', 'E2')]
            cancel = row['outputs'][-2]['returned']['last_delivered_ack']
            if name in ('default', 'explicit_zero'):
                require(statuses == ['received', 'received'] and len(grants) == 2
                        and result['jobs'][0]['status'] != 'completed', 'default two reservations block loaded')
            elif name == 'reserve1':
                require(statuses == ['received', 'rejected'] and len(grants) == 1
                        and transfers['live:1:A:return:E2']['reason'] == 'receiver_transit_reserve', 'atomic reserve1 admission')
                require(result['jobs'][0]['status'] == 'completed', 'loaded progress')
                require({item['tray_id'] for item in result['trays'] if item['node'] == 1} == {'L', 'E1', 'P0', 'P1'}, 'four physical slots usable')
                require(cancel['status'] == 'rejected', 'departed lease not cancelled')
                require(sum(item['event'] == 'EMPTY_RECEIVED' and item['tray_id'] == 'E1' for item in result['receipts']) == 1,
                        'existing own reservation permits exactly one receipt')
                require(row['restore'] == {'initial': row['initial_seal'], 'restored': row['initial_seal'], 'clock': 0.}, 'same session initial checkpoint restore')
            else:
                require(statuses == ['rejected', 'rejected'] and not grants
                        and all(item['reason'] == 'receiver_transit_reserve' for item in transfers.values())
                        and result['jobs'][0]['status'] == 'completed', 'reserve2 negative fixture')
            static_digest = row['outputs'][10]['returned'][0]['capture']['capture_v2']['local_capture']['static_contract_sha256']
            summaries[arm + '/' + name] = {'transfers': statuses, 'empty_grants': len(grants), 'job_status': result['jobs'][0]['status'],
                'initial_seal': row['initial_seal'], 'static_contract_sha256': static_digest, 'checkpoint_restore': row['restore']}
        if arm == 'native028':
            expected = {'negative': -1, 'capacity': 4, 'fraction': 1.5, 'boolean': True}
            require(set(completion['invalid']) == set(expected), 'all invalid constructors')
            for name, value in expected.items():
                actual = completion['invalid'][name]
                require(type(actual['value']) is type(value) and actual['value'] == value
                        and actual['exception']['type'] == 'ValueError'
                        and actual['exception']['message'] == 'circulation:invalid_receiver_transit_reserve', 'invalid type/value rejected')
    require(attempts == 9, 'total actual constructors')
    removed = {}
    require(stable(rows['native027']['default'], removed=removed) == stable(rows['native028']['default'], removed=removed), 'old/new default exact parity')
    zero = copy.deepcopy(rows['native028']['explicit_zero']); zero['input'] = rows['native028']['default']['input']
    require(stable(zero, removed=removed) == stable(rows['native028']['default']), 'explicit zero exact parity')
    for field in ('initial_seal', 'static_contract_sha256'):
        require(len({summaries['native028/' + name][field] for name in ('default', 'reserve1', 'reserve2')}) == 3, 'policy version sealed: ' + field)
    campaign_path = BASE / 'C00_receiver_admission_001' / 'plan.json'
    campaign = read(campaign_path)
    old_plan = read(BASE / 'C00_cyclic_od_001' / 'plan.json')
    current_input = read(campaign['input']['path']); restored_input = copy.deepcopy(current_input)
    changes = [(node['node'], node.pop('empty_receive_transit_reserve')) for node in restored_input['node_contracts'] if 'empty_receive_transit_reserve' in node]
    require(changes == [(49, 1)] and restored_input == read(old_plan['input']['path']), 'only node49 policy overlay')
    require(len(current_input['jobs']) == 28506 and len(current_input['trays']) == 22, 'whole business inventory')
    require(campaign['controller'] == old_plan['controller'] and campaign['physical_start'] == 0.
            and campaign['warmup_end'] == 57600. and campaign['window_boundaries'] == [57600., 58200., 58800., 59400.], 'unchanged continuous calibration')
    require(campaign['native_branch_budget'] == 1 and campaign['forecast_references'] == [] and campaign['observed_counts'] is None, 'C00 bounded no forecast scope')
    for source, expected in campaign['source_sha256'].items():
        require(sha(source) == sha(campaign_path.parent / campaign['source_archive'][source]) == expected, 'campaign archived source')
    report = {'schema': 'g31.native028.independent_readonly_review.v1', 'status': 'passed_finite_gate_and_C00_preparation',
        'auditor': reference(__file__), 'gate_plan': reference(GATE / 'plan.json'), 'gate_receipt': reference(GATE / 'receipt.json'),
        'accepted_contract': reference(contract_path), 'C00_plan': reference(campaign_path), 'checks': CHECKS,
        'verified_gate_evidence_files': len(receipt['evidence_sha256']), 'verified_campaign_sources': len(campaign['source_sha256']),
        'actual_saved_constructor_attempts': attempts, 'native_constructors_invoked_by_audit': 0, 'training_or_fit_calls': 0,
        'ignored_diagnostics_exact_paths': removed, 'fixtures': summaries,
        'C00_input_overlay_only': {'node': 49, 'empty_receive_transit_reserve': 1},
        'C00_execution_or_global_deadlock_freedom_established': False, 'legacy_44_plus_21_reexecuted': False,
        'complete_request_100ms_certified': False,
        'review_conclusion': 'No substantive source or saved-fixture blocker found for the registered one-branch finite C00 calibration.'}
    with (HERE / 'report.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'status': report['status'], 'checks': CHECKS, 'report_sha256': sha(HERE / 'report.json')}))


if __name__ == '__main__':
    main()
