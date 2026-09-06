import json
from types import SimpleNamespace

import pytest

from scripts.eval import run_hca_segment_identity_campaign as campaign


def test_remaining_requires_successful_bound_preflight(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, 'check_freeze', lambda args: {'cells': []})
    (tmp_path / 'preflight_gate.json').write_text(json.dumps({'status': 'FAILED'}), encoding='utf-8')
    with pytest.raises(ValueError, match='preflight'):
        campaign.run(SimpleNamespace(result_root=tmp_path, phase='remaining', workers=1))


def test_failed_case_stops_admitting_further_cases(tmp_path, monkeypatch):
    cells = [{'map': m, 'load_factor': l, 'seed': s} for m, l, s in campaign.PREFLIGHT]
    monkeypatch.setattr(campaign, 'check_freeze', lambda args: {'cells': cells})
    (tmp_path / 'campaign_freeze.json').write_text('{}', encoding='utf-8')
    admitted = []

    def fail(cell):
        admitted.append(cell)
        raise ValueError('intentional native accounting failure')

    monkeypatch.setattr(campaign, 'run_cell', fail)
    result = campaign.run(SimpleNamespace(result_root=tmp_path, phase='preflight', workers=1))
    assert result['status'] == 'FAILED'
    assert len(admitted) == len(result['failures']) == 1
    assert not (tmp_path / 'preflight_gate.json').exists()


@pytest.mark.parametrize('field,value', [('method', 'FENG_NATIVE_HCA'), ('seed', 42),
                                       ('workload_identity_sha256', 'wrong-input')])
def test_completed_record_rejects_foreign_identity(tmp_path, monkeypatch, field, value):
    monkeypatch.setattr(campaign, 'ROOT', tmp_path)
    native = tmp_path / 'cell'
    native.mkdir()
    record = {'status': 'COMPLETE', 'method': campaign.METHOD, 'map': 'map2', 'load_factor': 1.0,
              'seed': 104729, 'population_audit': {'status': 'PASS'},
              'workload_identity_sha256': 'expected-input', 'fixed_horizon_seconds': 98259.0}
    record[field] = value
    (native / 'normalized_result.json').write_text(json.dumps(record), encoding='utf-8')
    cell = {'output': 'cell', 'map': 'map2', 'load_factor': 1.0, 'seed': 104729,
            'identity': {'sha256': 'expected-input'}}
    with pytest.raises(ValueError):
        campaign.load_completed(cell)
