"""Adjacent floating horizons must not run a future tick or mutate past time."""
import os

from scripts.experiments.g31_ics_circulation import protocol_control
from scripts.experiments.g31_ics_circulation.native_host import load_native
from scripts.experiments.g31_ics_circulation.probe_protocol_tick_boundary import execute


def test_native_nextafter_horizon_and_json_continuation(tmp_path):
    receipt = execute(protocol_control, load_native(os.environ["G31_CIRCULATION_BINARY"]), tmp_path)
    assert receipt["fixed"], receipt
