"""New campaign preparation and bounded launch plumbing; native is mocked."""
import copy
import gzip
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_feasible_campaign as campaign
from scripts.experiments.g31_ics_circulation import foundation_airport_feasible_domain as domain
from scripts.experiments.g31_ics_circulation import foundation_airport_campaign as legacy


@pytest.fixture
def prepared(tmp_path):
    return campaign.prepare(tmp_path / 'prepared')


def test_prepare_new_contract_input_lineage_mapping_and_strict_budget(prepared):
    plan = prepared
    assert plan['schema'] == campaign.SCHEMA and plan['branch'] == 'C00'
    assert (plan['hard_process_seconds'], plan['soft_stop_seconds']) == (300, 240)
    assert (legacy.HARD_SECONDS, legacy.SOFT_SECONDS) == (150, 120)
    assert plan['business_contract_version'] == domain.VERSION
    assert plan['protocol_input_semantic_sha256'] == domain.PROTOCOL_INPUT_SHA
    assert plan['forecast_references'] == [] and plan['calibration_reference'] is None
    assert plan['window_boundaries'] == list(legacy.BOUNDARIES)
    assert plan['physical_start'] == 0. and plan['reset_at_window_boundary'] is False
    campaign.check_pins(plan)
    graph = legacy.source_dependency_closure(roots=campaign.SOURCE_ROOTS)
    for module, path in graph.items():
        for imported in legacy._import_names(module, path):
            assert legacy._local_module(imported, legacy.ROOT) is None or imported in graph
    assert campaign.MODULE in graph
    assert 'scripts.experiments.g31_ics_circulation.foundation_action_value' not in graph


def test_C10_cannot_be_prepared_without_new_C00_calibration(tmp_path):
    with pytest.raises(ValueError, match='explicit_C10_calibration_reference'):
        campaign.prepare(tmp_path / 'no_calibration', branch='C10')
    assert not (tmp_path / 'no_calibration').exists()


def test_old_C00_reference_cannot_be_used_as_new_domain_calibration():
    old = campaign.ROOT / 'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/C00_calibration_001/receipt.json'
    with pytest.raises(ValueError, match='new_domain_C00_reference'):
        campaign.calibration_reference(old)


def test_exact_lineage_audit_cannot_be_forged_even_if_local_hash_is_updated(prepared):
    plan = copy.deepcopy(prepared)
    path = campaign.Path(plan['business_audit']['path'])
    audit = json.loads(gzip.decompress(path.read_bytes()))
    audit['exact_changed_jobs'][0]['business_bag_id'] = 'invented'
    path.write_bytes(gzip.compress(json.dumps(audit).encode(), mtime=0))
    plan['business_audit'] = campaign.reference(path)
    with pytest.raises(ValueError, match='business_audit_binding'):
        campaign.check_pins(plan)


def test_launch_uses_new_module_and_300s_job_limit_without_retry(prepared, monkeypatch):
    seen = []
    def run(command, **kwargs):
        seen.append((command, kwargs['timeout'], kwargs['admission']))
        return {'status': 'timeout', 'exitcode': None}
    monkeypatch.setattr(legacy.bounded_windows_job, 'run', run)
    receipt = campaign.launch(prepared['output'])
    assert len(seen) == 1 and seen[0][0][2] == campaign.MODULE and seen[0][1] == 300
    assert receipt['schema'] == campaign.SCHEMA and receipt['status'] == 'unknown_hard_timeout_or_incomplete'
    assert receipt['automatic_retries'] == 0 and receipt['native_branch_count'] == 1
    assert not receipt['full_1x_completion_established']
