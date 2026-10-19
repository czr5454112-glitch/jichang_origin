"""One shared600s owned Windows Job for the candidate and its saved verifier."""
import time
BOOT = time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
from . import bounded_windows_job

LIMIT = 600.
MODULE = "scripts.experiments.g31_ics_circulation.probe_original_route_update_pending_ack"
CASES = {"baseline", "drop_first_ack", "ack_withheld_in_window"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path); parser.add_argument("--campaign-sha256", required=True)
    args = parser.parse_args(); output = args.output.resolve()
    digest = hashlib.sha256((output / "campaign.json").read_bytes()).hexdigest()
    if digest != args.campaign_sha256: raise ValueError("pending_launch:campaign_changed")
    if (output / "receipt.json").exists() or (output / "external_launch_receipt.json").exists():
        raise ValueError("pending_launch:already_attempted")
    with (output / "external_launch_claim.json").open("x", encoding="utf8") as stream:
        json.dump({"campaign_sha256": digest, "shared_seconds": LIMIT}, stream)
    command = [sys.executable, "-m", MODULE, "--output", str(output), "--campaign", "--admission", digest]
    remaining = LIMIT - (time.monotonic() - BOOT)
    receipt = {"status": "unknown_before_dispatch", "command": command, "campaign_sha256": digest,
        "shared_seconds": LIMIT, "pre_job_wall_seconds": LIMIT - remaining,
        "outer_python_startup_before_BOOT_unmeasured": True, "complete_100ms_certified": False}
    try:
        if remaining <= 0: raise TimeoutError("pending_launch:budget_before_job")
        with (output / "campaign.stdout.log").open("x", encoding="utf8") as stdout, \
                (output / "campaign.stderr.log").open("x", encoding="utf8") as stderr:
            result = bounded_windows_job.run(command, timeout=remaining, stdout=stdout, stderr=stderr,
                admission=digest, cwd=Path(__file__).resolve().parents[3])
        receipt["process"] = result
        receipt["status"] = "campaign_process_exited" if result["status"] == "exited" and result["exitcode"] == 0 else "unknown_campaign_process"
        if receipt["status"] == "campaign_process_exited":
            internal = json.loads((output / "receipt.json").read_bytes())
            if internal.get("status") != "completed_finite_pending_ack_cohort" or internal.get("campaign_sha256") != digest or \
                    set(internal.get("cases", {})) != CASES or internal.get("source_changed") != []:
                raise ValueError("pending_launch:unconfirmed_internal_receipt")
    except BaseException as error:
        receipt.update(status="unknown_launcher_error", error=repr(error)); raise
    finally:
        receipt["whole_dispatch_before_final_evidence_seconds"] = time.monotonic() - BOOT
        if receipt["whole_dispatch_before_final_evidence_seconds"] > LIMIT:
            receipt["status"] = "unknown_shared_budget_overrun"
        receipt["timing_scope"] = "Owned child startup/import/campaign/native/verification bounded. This clock precedes final hashes/receipt export; external launch-to-exit receipt required for complete Python application wall."
        for name in ("receipt.json", "branch_ledger.json", "campaign.stdout.log", "campaign.stderr.log"):
            path = output / name
            if path.is_file(): receipt.setdefault("artifact_sha256", {})[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        with (output / "external_launch_receipt.json").open("x", encoding="utf8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
    return 0 if receipt["status"] == "campaign_process_exited" else 1


if __name__ == "__main__": raise SystemExit(main())
