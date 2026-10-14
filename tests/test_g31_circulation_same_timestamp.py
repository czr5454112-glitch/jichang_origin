"""Due-now source work retains the returned tray before discretionary export."""
from copy import deepcopy
import os
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.native_host import audit_result, load_native, tiny_cycle


@pytest.fixture(scope='module')
def native():
    configured = os.environ.get('G31_CIRCULATION_BINARY')
    if configured:
        return load_native(configured)
    folder = Path(__file__).resolve().parents[1] / 'build_g31_circulation' / 'python'
    binaries = [*folder.glob('czr005_circulation*.pyd'), *folder.glob('czr005_circulation*.so')]
    assert len(binaries) == 1, 'Build czr005_circulation or set G31_CIRCULATION_BINARY'
    return load_native(binaries[0])


def test_receive_completion_at_arrival_timestamp_preserves_normal_source_service(native):
    case = tiny_cycle()
    case['trays'][0]['node'] = 4
    case['jobs'] = []
    case['transfers'][0]['issued_at'] = 0.0
    case['transfers'].append(dict(request_id='second-export', tray_id='T0', source=0,
        destination=4, issued_at=0.1, message_delay=0.0, earliest_departure=0.0, expiry=20.0))
    calibration = native.run(case)
    arrival = calibration['transfers'][0]['received_at']
    assert arrival > 0
    job = dict(tiny_cycle()['jobs'][0])
    job.update(business_bag_id='due-now-normal', arrival=arrival, storage_node=-1)
    case['jobs'] = [job]
    observed = native.run(case)
    control = deepcopy(case)
    control['transfers'] = control['transfers'][:1]
    without_export = native.run(control)
    for data, result in ((case, observed), (control, without_export)):
        audit_result(data, result)
        assert result['jobs'][0]['status'] == 'completed'
        assert result['jobs'][0]['loaded_at'] == pytest.approx(arrival + job['load_seconds'])
    assert observed['jobs'][0]['completed_at'] == without_export['jobs'][0]['completed_at']
    simultaneous = [e['event'] for e in observed['receipts'] if abs(e['time']-arrival) < 1e-9]
    assert simultaneous.index('BAG_ARRIVAL') < simultaneous.index('LOAD_START')
    assert 'EXPORT_GRANTED' not in simultaneous
