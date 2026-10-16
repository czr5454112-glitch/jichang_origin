from copy import deepcopy
from functools import lru_cache
import pytest

from scripts.experiments.g31_ics_circulation import review_original_low_wip_third_saved as v


@lru_cache(maxsize=1)
def saved():
    directory = v.m.OUT / "original_low_wip_third_prepare_001"
    return (v.m.base.gzread(directory / "input.json.gz"), v.m.base.gzread(directory / "raw_final.json.gz"),
        v.m.base.read(directory / "assessment.json"))


def test_actual_third_chain_has_owned_source_and_new_destination_owner():
    data, raw, assessment = saved()
    source, facts = v.validate_third(data, raw, assessment)
    assert facts["source_owner"] == "owner:system_domestic"
    assert facts["final_resource_owner"] == "owner:system_international" and facts["final_node"] == 46
    assert facts["all_actual_peer_fifo_heads"] == [
        {"origin": 0, "head": "projected:1x:0", "mandatory_paths_reachable": False},
        {"origin": 24, "head": "projected:1x:1", "mandatory_paths_reachable": False},
        {"origin": 26, "head": "projected:1x:14", "mandatory_paths_reachable": False},
        {"origin": 49, "head": "projected:1x:8", "mandatory_paths_reachable": True}]


@pytest.mark.parametrize("change", ["first_completion", "departed_ack", "future_ack", "not_empty", "wrong_source",
    "wrong_peer", "older_peer", "wrong_job", "missing_blocked_head", "wrong_final_node", "holding_final", "early_hold"])
def test_actual_chain_tampering_fails_closed(change):
    data, original, assessment = saved(); raw = deepcopy(original)
    source = next(o for o in raw["owners"] if o.get("third_supply")); third = source["third_supply"]
    proof = third["return_proof"]; peer = third["choice"]["delivered_message"]
    if change == "first_completion": proof["terminal_receipt"]["business_bag_id"] = "projected:1x:2"
    elif change == "departed_ack": proof["first_received_ack"]["status"] = "departed"
    elif change == "future_ack": proof["first_received_ack"]["delivered_at"] = 50000.
    elif change == "not_empty": proof["current_token"]["mode"] = "holding"
    elif change == "wrong_source": third["request"]["source"] = 49
    elif change == "wrong_peer": peer["capture"]["local_capture"]["source_owner"] = source["owner"]
    elif change == "older_peer": peer["capture"]["local_capture"]["captured_at"] -= 10.
    elif change == "wrong_job": third["choice"]["job"]["business_bag_id"] = "projected:1x:18"
    elif change == "missing_blocked_head":
        peer["capture"]["local_capture"]["jobs"] = [j for j in peer["capture"]["local_capture"]["jobs"] if j["business_bag_id"] != "projected:1x:14"]
    else:
        tray = next(t for t in raw["result"]["trays"] if t["tray_id"] == third["request"]["tray_id"])
        if change == "wrong_final_node": tray["node"] = 116
        elif change == "holding_final": tray["mode"] = "hold"
        else: tray["available_at"] = 0.
    peer["payload_sha256"] = v.m.base.capture_digest_v2(peer["capture"])
    with pytest.raises(ValueError): v.validate_third(data, raw, assessment)
