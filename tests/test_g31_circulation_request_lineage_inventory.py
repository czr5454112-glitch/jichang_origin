from pathlib import Path

from scripts.experiments.g31_ics_circulation.request_lineage_inventory import audit_sources, current_inventory


def sources():
    root = Path("scripts/experiments/g31_ics_circulation")
    return {name: (root/name).read_text(encoding="utf-8")
        for name in ("protocol_control.py", "event_protocol_control.py")}


def test_all_frozen_submit_paths_have_inventory_but_no_runtime_claim():
    result = current_inventory()
    assert result["status"] == "known_syntactic_sites_only", result
    assert len(result["calls"]) == 12
    assert result["business_request_runtime_roots_available"] is False
    assert result["branch_contracts_implemented"] is False
    assert result["complete_lineage_certified"] is False


def test_new_replacement_path_is_unknown_even_with_known_command_kind():
    data = sources()
    data["event_protocol_control.py"] += '\ndef replacement(client):\n    client.submit("A", "route", {})\n'
    result = audit_sources(data)
    assert result["status"] == "unknown_unclassified_sites"
    assert result["mismatches"][0]["site"] == ["event_protocol_control.py", "replacement", "route"]


def test_removed_path_cannot_pass_complete_inventory():
    data = sources()
    data["protocol_control.py"] = data["protocol_control.py"].replace('client.submit(owner, "route", payload)', 'client.unknown_submit(owner, "route", payload)', 1)
    result = audit_sources(data)
    assert result["status"] == "unknown_unclassified_sites"
    assert any(row["actual_count"] == 0 for row in result["mismatches"])


def test_dynamic_kind_or_retry_flag_requires_explicit_new_classification():
    data = sources()
    data["protocol_control.py"] = data["protocol_control.py"].replace('self._send(row, retry=True)', 'self._send(row, retry=retry)', 1)
    result = audit_sources(data)
    assert result["status"] == "unknown_unclassified_sites"
    assert any(row["site"][-1] == "unknown_retry_flag" for row in result["mismatches"])


def test_second_submit_in_same_function_is_not_silently_coalesced():
    data = sources()
    data["event_protocol_control.py"] = data["event_protocol_control.py"].replace(
        'channels[recipient] = request_id', 'client.submit(owner, "demand", {})\n        channels[recipient] = request_id', 1)
    result = audit_sources(data)
    assert result["status"] == "unknown_unclassified_sites"
    assert any(row["actual_count"] == 2 for row in result["mismatches"])
