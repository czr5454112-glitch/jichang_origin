"""Pure replay of native-shaped endpoints; none of these tests loads a pyd."""
import copy
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import native_preexisting_v3_adapter as adapter
from test_g31_circulation_preexisting_v3_data_adapter import pair


def collected(owner="A"):
    view, ack, inbox, kwargs = pair(owner)
    own = ack["planning_snapshot_v3"]["capture"]["capture_v2"]["local_capture"]
    peer = inbox[0]["capture"]["capture_v2"]["local_capture"]
    kwargs.pop("collection_contract")
    kwargs.update(own_request_id=own["message_id"], peer_message_id=peer["message_id"],
        collection_started_at=min(own["captured_at"], peer["captured_at"])-.01,
        policy_quiet_since=min(own["captured_at"], peer["captured_at"])-.02)
    return view, {"last_delivered_ack": ack}, inbox, kwargs


@pytest.mark.parametrize("owner", ["A", "B"])
def test_exact_owner_endpoint_replay_keeps_actual_epochs_and_never_authenticates(owner):
    view, command, inbox, kwargs = collected(owner)
    result = adapter.validate_collected_endpoints(view, command, inbox, **kwargs)
    assert result["status"] == "conditional_validated_later_v3_data", result
    assert not result["native_delivery_verified"] and not result["online_information_delivered"]
    assert result["raw_endpoints"] == {"view": view, "command": command, "received": inbox}
    assert len({r["captured_at"] for r in result["bundle"]["source_records"]}) == 2


@pytest.mark.parametrize("defect", ["wrong_self_id", "wrong_peer_id", "missing_self_ack", "missing_peer",
    "duplicate_selected_peer", "collection_after_capture", "quiet_after_collection", "quiet_bool",
    "collection_bool", "unknown_unselected_peer", "superseded_selected_peer"])
def test_selection_and_collection_bindings_reject_without_claiming_delivery(defect):
    view, command, inbox, kwargs = collected()
    if defect == "wrong_self_id": kwargs["own_request_id"] = "another-command"
    elif defect == "wrong_peer_id": kwargs["peer_message_id"] = "another-message"
    elif defect == "missing_self_ack": command = {}
    elif defect == "missing_peer": inbox = []
    elif defect == "duplicate_selected_peer": inbox.append(copy.deepcopy(inbox[0]))
    elif defect == "collection_after_capture": kwargs["collection_started_at"] = view["now"]
    elif defect == "quiet_after_collection": kwargs["policy_quiet_since"] = kwargs["collection_started_at"]+.001
    elif defect == "quiet_bool": kwargs["policy_quiet_since"] = True
    elif defect == "collection_bool": kwargs["collection_started_at"] = True
    elif defect == "unknown_unselected_peer": kwargs["peer_message_id"] = None
    else: inbox[0]["capture"]["capture_v2"]["local_capture"]["message_id"] = "newer-revision"
    result = adapter.validate_collected_endpoints(view, command, inbox, **kwargs)
    assert result["status"] == "unknown" and not result["native_delivery_verified"]
    assert result["raw_endpoints"]["received"] == inbox


def test_unselected_endpoint_history_is_retained_but_cannot_replace_selected_revision():
    view, command, inbox, kwargs = collected()
    unrelated = copy.deepcopy(inbox[0]); unrelated["capture"]["capture_v2"]["local_capture"]["message_id"] = "old-message"
    inbox.insert(0, unrelated)
    result = adapter.validate_collected_endpoints(view, command, inbox, **kwargs)
    assert result["status"] == "conditional_validated_later_v3_data"
    assert len(result["raw_endpoints"]["received"]) == 2 and len(result["envelopes"]) == 2


def test_python_fake_and_dictionary_handle_are_rejected_before_any_endpoint_read():
    class NoReads:
        def __getattr__(self, name): raise AssertionError("No fake native endpoint may be called: " + name)
    fake = SimpleNamespace()
    result, handle = adapter.bind_native027(fake, NoReads(), {"runtime_accepted": True})
    assert handle is None and result["status"] == "unknown"
    result = adapter.collect_native(fake, NoReads(), "A", "mine", accepted={"runtime_accepted": True},
        ledger={}, owned_client_rows={}, phase="first_return", peer_message_id="peer",
        collection_started_at=1., policy_quiet_since=1.)
    assert result["status"] == "unknown" and not result["native_delivery_verified"]


def test_acceptance_constructor_cannot_accept_external_truth_flag():
    with pytest.raises(ValueError, match="closed_native_runtime_gate"):
        adapter.Native027Acceptance(True, None, None, {}, {})


def test_supplied_or_json_reloaded_dict_cannot_mint_collection_authority():
    value = {"status": "conditional_native_delivered_later_v3_model_input", "native_delivery_verified": True,
        "online_information_delivered": True}
    assert not adapter.is_native_collected(value)
    with pytest.raises(ValueError, match="actual_native_reads"):
        adapter.NativeCollectedV3(True, value, None)
