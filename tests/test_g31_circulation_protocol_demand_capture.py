"""The receiver must recover from an execution-time transient queue snapshot."""
import os

from scripts.experiments.g31_ics_circulation import protocol_control
from scripts.experiments.g31_ics_circulation.native_host import load_native
from scripts.experiments.g31_ics_circulation.probe_protocol_demand_capture import execute


def test_native_delayed_demand_capture_is_corrected_after_real_loading(tmp_path):
    receipt = execute(protocol_control, load_native(os.environ["G31_CIRCULATION_BINARY"]), tmp_path)
    assert receipt["fixture_valid"], receipt
    assert receipt["fixed"], receipt
