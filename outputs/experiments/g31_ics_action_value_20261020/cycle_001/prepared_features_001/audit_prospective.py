"""Read-only actor audit and real train-evidence execution-binding recheck."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_prospective_campaign as campaign
from scripts.experiments.g31_ics_circulation import foundation_airport_prospective_control as control
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_ranker as ranker
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_training_campaign as training
from scripts.experiments.g31_ics_circulation import foundation_airport_batch_patch as patch
from scripts.experiments.g31_ics_circulation import foundation_airport_opportunities as opportunities
from scripts.experiments.g31_ics_circulation import foundation_airport_protocol_v2 as protocol

OUT = Path(__file__).resolve().parent
RUN = OUT.parent


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def main():
    source = RUN/"H_701_calendar_a_patch_001"
    evidence, result, calls, views = [read(source/name) for name in (
        "branch_evidence.json.gz", "final_result.json.gz", "client_calls.json.gz", "ack_views.json.gz")]
    selected = evidence["selected"]
    target = selected["chosen_action"]["tray_id"]
    intended = next(row for row in selected["chosen_decision"]["intents"] if row["tray_id"] == target)
    index = [{"owner_id": selected["observation"]["owner_id"], "observed_at": selected["observation"]["now"],
        "tray_id": target, "decision_differs": True, "chosen_intent": intended}]
    actual = campaign.indexed_execution(index, result, calls, views)
    assert actual["different_decision_with_complete_G1_chain"] == 1
    cases = {"actual_H701_patch": actual["different_decision_with_complete_G1_chain"]}
    for label in ("wrong_selected_destination", "selected_hold_but_actual_submit", "future_ACK", "wrong_native_tray"):
        idx, native, acks = copy.deepcopy(index), result, views
        if label == "wrong_selected_destination":
            idx[0]["chosen_intent"]["destination"] += 1
        elif label == "selected_hold_but_actual_submit":
            idx[0]["chosen_intent"] = None
        elif label == "future_ACK":
            acks = copy.deepcopy(views)
            request_id = actual["rows"][0]["attempts"][0]["actual_request"]["request_id"]
            for view in acks.values():
                for ack in view.get("delivered_transfer_acks", []):
                    if ack["request_id"] == request_id:
                        ack["delivered_at"] = result["physical_clock"]+1
        else:
            native = copy.deepcopy(result)
            identity = actual["rows"][0]["attempts"][0]["native_leg"]["transport_leg_id"]
            for leg in native["leg_identities"]:
                if leg["transport_leg_id"] == identity:
                    leg["tray"] = -1
        recomputed = campaign.indexed_execution(idx, native, calls, acks)
        cases[label] = recomputed["different_decision_with_complete_G1_chain"]
        assert cases[label] == 0
    registered_sources_still_exact = []
    for name in ("training_primary_001", "training_resource_001"):
        manifest = json.loads((RUN/name/"manifest.json").read_bytes())
        for ref in manifest["chain_plans"]:
            training._validate_chain(training.read_bound(ref))
        registered_sources_still_exact.append(name)
    receipt = {
        "schema": "g31.airport.prospective_actor_independent_code_audit.v1",
        "status": "passed_after_two_audit_findings_corrected",
        "sources": [training.file_ref(module.__file__) for module in
            (campaign, control, ranker, training, patch, opportunities, protocol)],
        "real_train_evidence": [training.file_ref(source/name) for name in
            ("branch_evidence.json.gz", "final_result.json.gz", "client_calls.json.gz", "ack_views.json.gz")],
        "execution_binding_counterexamples": cases,
        "actual_H701_execution": actual,
        "findings": [
            {"id": "chosen_action_native_entity_binding",
             "original_gap": "same owner/time/tray plus request ID alone did not prove selected destination/scope/leg endpoints",
             "resolution": "intent effective-departure match; native tray/scope/LEG_START endpoints; owner and time bound positive ACK; EDGE_ENTER required",
             "verified": True},
            {"id": "test_inputs_before_freeze_gate",
             "original_gap": "prepare constructed parent input before validating all-domain frozen model manifest",
             "resolution": "registered seed split and complete freeze validated before parent_input",
             "regression_test": "test_test_model_freeze_precedes_any_test_input_read",
             "verified": True}],
        "read_only_checks": {
            "no_evaluator_future_jobs_or_outcome_targets_in_actor_rows": True,
            "C00_C01_do_not_call_or_forward_forecast_provider": True,
            "C10_C11_require_actual_owner_plan_receipt_and_absolute_calendar": True,
            "common_catalog_does_not_use_plan": True,
            "single_tray_patch_preserves_all_other_initial_batch_intents": True,
            "residual_recomputes_current_without_repeated_selector": True,
            "held_optional_exclusion_only_same_owner_timestamp": True,
            "prepared_predictor_detaches_static_model_and_validates_each_current": True,
            "selector_full_current_feature_forward_timing_separate_from_audit": True},
        "registration_sources_still_exact": registered_sources_still_exact,
        "fit_calls": 0, "native_jobs": 0, "test_data_opened": False,
        "strict_nonharm_certified": False,
        "limitations": [
            "Static code audit plus rejoin of saved train native evidence; prospective native execution remains separate.",
            "Preserved initial batch bytes and native residual admission do not certify completion of every mandatory business obligation.",
            "Shared-resource per-job nonharm and out-of-parent generalization remain unproven."]}
    target = OUT/"prospective_actor_audit_001.json"
    with target.open("x", encoding="utf8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({"path": str(target), "status": receipt["status"],
        "counterexamples": cases, "test_data_opened": False, "fit_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
