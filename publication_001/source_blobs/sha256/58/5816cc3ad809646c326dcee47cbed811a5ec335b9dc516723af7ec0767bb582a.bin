"""Execute the twelve already registered finite chains and freeze all models."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from . import foundation_airport_action_campaign as common
from . import foundation_airport_pair_training_campaign as training


def run():
    grid = common.read(common.CYCLE/"prospective_evaluation_grid_001.json")
    for row in grid["rows"]:
        if row["batch"] == "E" and not (common.CYCLE/row["name"]/"receipt.json").exists():
            raise ValueError("training_execution:all_E_development_attempts_must_close_first")
    registration = common.read(common.CYCLE/"pair_training_registration_receipt_001.json")
    references = []
    for domain in ("primary_22", "mixed_18_22_26"):
        registered = registration["campaigns"][domain]
        reference = registered["manifest"]
        campaign = training.read_bound(reference)
        if campaign["status"] != "registered_not_run":
            raise ValueError("training_execution:preregistered_sufficiency_failed")
        references.append(reference)
        for chain in campaign["chain_plans"]:
            plan = training.read_bound(chain)
            receipt_path = Path(plan["output"])/"receipt.json"
            if receipt_path.exists():
                receipt = common.read(receipt_path)
            else:
                events = [json.loads(line) for line in (common.CYCLE/"ledger.jsonl").read_text().splitlines()]
                manifest = common.read(common.CYCLE/"manifest.json")
                age = datetime.now(timezone.utc)-datetime.fromisoformat(manifest["created_at"])
                if sum(row["event"] == "training_chain_launch" for row in events) >= 12 or age.total_seconds() >= 16*3600:
                    raise ValueError("training_execution:finite_campaign_budget_exhausted")
                common.event(common.CYCLE, "training_chain_launch", chain_id=plan["chain_id"],
                    registration=chain, fit_calls_planned=2)
                receipt_ref = training.run_registered_chain(chain)
                receipt = training.read_bound(receipt_ref)
                common.event(common.CYCLE, "training_chain_closed", chain_id=plan["chain_id"],
                    status=receipt["status"], fit_calls_started=receipt["fit_calls_started"],
                    fit_calls_completed=receipt["fit_calls_completed"], receipt=receipt_ref)
            print(json.dumps(dict(chain=plan["chain_id"], status=receipt["status"],
                fits=receipt["fit_calls_completed"])), flush=True)
        if not (Path(campaign["output"])/"controls_receipt.json").exists():
            control = training.run_registered_controls(reference)
            common.event(common.CYCLE, "training_diagnostic_control", domain=domain, receipt=control)
    output = common.CYCLE/"all_models_frozen_001.json"
    reference = training.file_ref(output) if output.exists() else training.freeze_all(references, output=output)
    frozen = training.validate_frozen_manifest(reference, required_domains=training.DOMAINS)
    common.event(common.CYCLE, "all_models_frozen", manifest=reference, models=len(frozen["models"]),
        actual_primary_fit_calls=frozen["primary_fit_calls_completed"],
        diagnostic_control_fit_calls=frozen["control_fit_calls_completed"], test_opened=False)
    print(json.dumps(dict(status=frozen["status"], models=len(frozen["models"]), path=str(output))), flush=True)


if __name__ == "__main__":
    run()
