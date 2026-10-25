"""Full-population first-planning THT and explicit timing components.

User THT sums each business bag's legs from first planning attempt to goal,
including failed planning retries and excluding inter-leg EBS storage. Legacy
paper_tht fields remain as network-duration components, never fallback user THT.
No generated_release, release_time, or admission substitutes for a missing
first_planning_attempt_time.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math


def _stats(values):
    values = sorted(values)
    n = len(values)

    def quantile(p):
        if not n:
            return None
        position = (n - 1) * p
        lo = int(position)
        hi = min(lo + 1, n - 1)
        return values[lo] + (position - lo) * (values[hi] - values[lo])

    return {"count": n, "sum": math.fsum(values) if n else None,
            "mean": math.fsum(values) / n if n else None,
            "min": values[0] if n else None, "p50": quantile(.5),
            "p95": quantile(.95), "p99": quantile(.99),
            "max": values[-1] if n else None}


def _metric(values, restricted, definition):
    """None is censored/unavailable, never a reason to change the denominator."""
    known = [v for v in values if v is not None]
    full = _stats(known) if len(known) == len(values) else {
        **{k: None for k in ("sum", "mean", "min", "p50", "p95", "p99", "max")},
        "count": len(values)}
    return {"definition": definition, "denominator": len(values),
            "observed_count": len(known), "censored_count": len(values) - len(known),
            "full_population": full,
            "completed_subset_diagnostic": _stats(known),
            "restricted_full_population": _stats(restricted)}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _audit_tht_existing(rows, bags, horizon=98259.0):
    """Audit continuous metrics using all canonical legs and original businesses.

    ``completed`` must be explicitly true, with finite admission and finish no
    later than the executed horizon. A planned finish of an incomplete bag is
    not an observation. Restricted values are exposure through the horizon,
    not an estimate of eventual THT. Missing bag telemetry keeps the canonical
    denominator but makes its restricted source/network split unavailable.
    """
    rows, bags = list(rows), list(bags)
    if not _finite(horizon) or horizon < 0:
        raise ValueError("horizon must be a finite nonnegative executed time")
    canonical = {str(r["segment_id"]): r for r in rows}
    actual = {str(b["segment_id"]): b for b in bags}
    if len(canonical) != len(rows) or len(actual) != len(bags):
        raise ValueError("duplicate canonical or actual segment_id")
    if actual.keys() - canonical.keys():
        raise ValueError("actual population contains unknown segment_id")
    violations = []
    segments = []
    grouped = defaultdict(list)
    missing = 0

    for sid, row in canonical.items():
        release = row["pass_time"]
        if not _finite(release):
            raise ValueError(f"nonfinite canonical pass_time: {sid}")
        leg = row["leg"]
        if leg not in ("direct", "storage_in", "storage_out"):
            raise ValueError(f"unknown canonical leg: {sid}")
        bag = actual.get(sid)
        valid = True
        if bag is None:
            missing += 1
            violations.append([sid, "missing_actual_segment"])
            bag = {}
        for key in ("task_id", "leg", "start", "goal"):
            if key in bag and key in row and bag[key] != row[key]:
                violations.append([sid, "identity_mismatch", key])
                valid = False
        admission, finish = bag.get("admission"), bag.get("finish")
        attempt = bag.get("first_planning_attempt_time")
        activation = bag.get("activation_time")
        anchor_declared = "first_planning_attempt_time" in bag
        for field, value in (("admission", admission), ("finish", finish),
                             ("first_planning_attempt_time", attempt), ("activation_time", activation)):
            if value is not None and not _finite(value):
                violations.append([sid, "invalid_time", field])
                valid = False
        admitted = _finite(admission) and admission <= horizon
        if _finite(admission) and (admission < release or admission > horizon):
            violations.append([sid, "admission_outside_observed_release_window"])
            valid = False
        if _finite(finish) and _finite(admission) and finish < admission:
            violations.append([sid, "finish_before_admission"])
            valid = False
        if _finite(attempt) and (attempt < release or attempt > horizon or
                                (_finite(admission) and attempt > admission)):
            violations.append([sid, "first_attempt_outside_release_admission_window"])
            valid = False
        if anchor_declared and attempt is None and _finite(admission):
            violations.append([sid, "missing_first_attempt_for_admitted_record"])
            valid = False
        if _finite(activation) and (activation < release or activation > horizon or
                                   (_finite(attempt) and activation > attempt)):
            violations.append([sid, "activation_outside_release_attempt_window"])
            valid = False
        claimed_done = bag.get("completed") is True
        done = claimed_done and admitted and _finite(finish) and finish <= horizon and valid
        if claimed_done and not done:
            violations.append([sid, "invalid_completed_record"])
        elapsed_restricted = max(0.0, (finish if done else horizon) - release)
        restricted_known = sid in actual and valid
        attempt_known = anchor_declared and restricted_known
        attempted = _finite(attempt) and attempt <= horizon and valid
        source_restricted = (admission - release if admitted else max(0.0, horizon - release))
        network_restricted = max(0.0, (finish if done else horizon) - admission) if admitted else 0.0
        item = {"sid": sid, "leg": leg, "row": row, "done": done,
                "unreleased": release > horizon, "missing": sid not in actual,
                "admission": admission if admitted and valid else None,
                "telemetry_valid": restricted_known,
                "anchor_declared": anchor_declared,
                "user_tht": finish - attempt if done and attempted else None,
                "planning_wait": admission - attempt if admitted and attempted else None,
                "canonical_preplanning": attempt - release if attempted else None,
                "activation_to_first_planning": attempt - activation if attempted and _finite(activation) else None,
                "canonical_to_activation": activation - release if _finite(activation) and valid else None,
                "user_tht_restricted": (max(0.0, (finish if done else horizon) - attempt) if attempted else 0.0)
                if attempt_known else None,
                "planning_wait_restricted": (max(0.0, (admission if admitted else horizon) - attempt) if attempted else 0.0)
                if attempt_known else None,
                "canonical_preplanning_restricted": (attempt - release if attempted else max(0.0, horizon - release))
                if attempt_known else None,
                "activation_to_first_planning_restricted": (max(0.0, (attempt if attempted else horizon) - activation)
                if _finite(activation) else 0.0) if "activation_time" in bag and attempt_known else None,
                "canonical_to_activation_restricted": (activation - release if _finite(activation) else max(0.0, horizon - release))
                if "activation_time" in bag and restricted_known else None,
                "observed_user_tht": math.ceil(finish) - attempt if done and attempted else None,
                "network": finish - admission if done else None,
                "elapsed": finish - release if done else None,
                "source": admission - release if admitted and valid else None,
                "network_restricted": network_restricted if restricted_known else None,
                "source_restricted": source_restricted if restricted_known else None,
                "elapsed_restricted": elapsed_restricted,
                "observed_network": math.ceil(finish) - admission if done else None,
                "observed_elapsed": math.ceil(finish) - release if done else None,
                "finish": finish if done else None}
        segments.append(item)
        grouped[str(row["task_id"])].append(item)

    def segment_metric(items, field, restriction, definition):
        restricted = [x[restriction] for x in items]
        result = _metric([x[field] for x in items], [], definition)
        # Incomplete telemetry cannot justify a source/network decomposition.
        result["restricted_full_population"] = (_stats(restricted) if all(
            v is not None for v in restricted) else {
                **{k: None for k in ("sum", "mean", "min", "p50", "p95", "p99", "max")},
                "count": len(items)})
        return result

    businesses = []
    for task_id, items in grouped.items():
        legs = [x["leg"] for x in items]
        if sorted(legs) not in (["direct"], ["storage_in", "storage_out"]):
            raise ValueError(f"business must be direct or exactly both EBS legs: {task_id}")
        original = [x["row"].get("original_entry_time") for x in items]
        entry_known = all(_finite(v) for v in original) and len(set(original)) == 1
        if not entry_known:
            violations.append([task_id, "missing_or_inconsistent_original_entry_time"])
        done = all(x["done"] for x in items)
        final = next(x for x in items if x["leg"] in ("direct", "storage_out"))
        first = next(x for x in items if x["leg"] in ("direct", "storage_in"))
        if entry_known and done and final["finish"] < original[0]:
            violations.append([task_id, "business_finish_before_original_entry"])
            entry_known = False
        business = {"done": done,
                    "end_to_end": final["finish"] - original[0] if done and entry_known else None,
                    "end_to_end_restricted": max(0.0, (final["finish"] if done else horizon) - original[0])
                    if entry_known else None,
                    "observed_end_to_end": math.ceil(final["finish"]) - original[0]
                    if done and entry_known else None,
                    "first_admission_to_final_goal": final["finish"] - first["admission"]
                    if done else None,
                    "first_admission_to_final_goal_restricted": (
                        max(0.0, (final["finish"] if done else horizon) - first["admission"])
                        if first["admission"] is not None else 0.0)
                    if first["telemetry_valid"] else None,
                    "observed_first_admission_to_final_goal": math.ceil(final["finish"]) - first["admission"]
                    if done else None}
        for field in ("network", "elapsed", "source", "network_restricted", "elapsed_restricted",
                      "source_restricted", "observed_network", "observed_elapsed", "user_tht",
                      "planning_wait", "canonical_preplanning", "activation_to_first_planning", "canonical_to_activation",
                      "user_tht_restricted", "planning_wait_restricted", "canonical_preplanning_restricted",
                      "activation_to_first_planning_restricted", "canonical_to_activation_restricted", "observed_user_tht"):
            values = [x[field] for x in items]
            business[field] = math.fsum(values) if all(v is not None for v in values) else None
        businesses.append(business)

    network_definition = "Network-elapsed component: per business sum of each leg continuous finish minus successful actual admission. Includes device passage and internal wait, excludes planning retries and EBS dwell. Legacy paper_tht field is not the user THT objective."
    user_definition = "Primary user THT: per original business sum of each leg continuous finish minus first_planning_attempt_time. Includes every planning retry, device passage and internal wait; excludes EBS inter-leg storage and preplanning hold. No fallback for missing first-attempt telemetry."
    elapsed_definition = "Continuous finish minus canonical pass_time for each independent transport leg; includes every hold before actual admission."
    source_definition = "Canonical-to-admission component: actual admission minus canonical pass_time. Includes preplanning hold and planning retries; not wholly outside-system waiting. Canonical pass_time is not actual source-generation time."
    business_elapsed_definition = "Sum of leg canonical elapsed per original business bag; excludes the interval between inbound finish and nominal outbound release."
    end_to_end_definition = "Final leg continuous finish minus original_entry_time; includes EBS dwell and all external holds. Requires all legs complete."
    first_admission_definition = "Final leg continuous finish minus actual admission of the first leg (storage_in or direct); includes EBS dwell, excludes initial external hold. Requires all legs complete."
    metric = segment_metric
    network = metric(businesses, "network", "network_restricted", network_definition)
    primary = metric(businesses, "user_tht", "user_tht_restricted", user_definition)
    secondary = {
        "segment_canonical_elapsed": metric(segments, "elapsed", "elapsed_restricted", elapsed_definition),
        "business_sum_canonical_elapsed": metric(businesses, "elapsed", "elapsed_restricted", business_elapsed_definition),
        "segment_network_duration": metric(segments, "network", "network_restricted", "Continuous finish minus actual admission per independent leg."),
        "segment_source_hold": metric(segments, "source", "source_restricted", source_definition),
        "business_sum_source_hold": metric(businesses, "source", "source_restricted", "Sum of leg canonical source hold per original business bag."),
        "business_end_to_end": metric(businesses, "end_to_end", "end_to_end_restricted", end_to_end_definition),
        "business_first_admission_to_final_goal": metric(businesses, "first_admission_to_final_goal", "first_admission_to_final_goal_restricted", first_admission_definition),
        "segment_user_tht": metric(segments, "user_tht", "user_tht_restricted", user_definition),
        "segment_planning_wait": metric(segments, "planning_wait", "planning_wait_restricted", "Successful admission minus first planning attempt; all failed-retry delay."),
        "business_sum_planning_wait": metric(businesses, "planning_wait", "planning_wait_restricted", "Sum of leg planning retry wait per business."),
        "segment_canonical_preplanning": metric(segments, "canonical_preplanning", "canonical_preplanning_restricted", "First planning attempt minus canonical release; includes generation, causal gate and pre-head FIFO delay where present."),
        "business_sum_canonical_preplanning": metric(businesses, "canonical_preplanning", "canonical_preplanning_restricted", "Sum of leg canonical-release-to-first-planning hold per business; mandatory companion to user THT."),
        "business_sum_activation_to_first_planning": metric(businesses, "activation_to_first_planning", "activation_to_first_planning_restricted", "Sum first attempt minus actual source-queue activation; unavailable where activation telemetry is absent."),
        "business_sum_canonical_to_activation": metric(businesses, "canonical_to_activation", "canonical_to_activation_restricted", "Sum actual source-queue activation minus canonical release; activation is not the primary THT anchor."),
        "by_leg": {leg: {
            "user_tht": metric([x for x in segments if x["leg"] == leg], "user_tht", "user_tht_restricted", user_definition),
            "planning_wait": metric([x for x in segments if x["leg"] == leg], "planning_wait", "planning_wait_restricted", "Successful admission minus first planning attempt."),
            "canonical_preplanning": metric([x for x in segments if x["leg"] == leg], "canonical_preplanning", "canonical_preplanning_restricted", "First planning attempt minus canonical release."),
            "canonical_elapsed": metric([x for x in segments if x["leg"] == leg], "elapsed", "elapsed_restricted", elapsed_definition),
            "network_duration": metric([x for x in segments if x["leg"] == leg], "network", "network_restricted", "Continuous finish minus actual admission per leg."),
            "source_hold": metric([x for x in segments if x["leg"] == leg], "source", "source_restricted", source_definition)}
            for leg in ("direct", "storage_in", "storage_out")}}
    # The same ceil transformation is applied to either algorithm. Source times
    # remain the actual continuous admissions; no supplied observed field is used.
    observed = {
        "definition": "Auxiliary only: replace each completed continuous finish with ceil(finish), for both algorithms; admissions/releases unchanged.",
        "user_tht": _metric([x["observed_user_tht"] for x in businesses], [], user_definition),
        "paper_tht": _metric([x["observed_network"] for x in businesses], [], network_definition),
        "segment_canonical_elapsed": _metric([x["observed_elapsed"] for x in segments], [], elapsed_definition),
        "business_sum_canonical_elapsed": _metric([x["observed_elapsed"] for x in businesses], [], business_elapsed_definition),
        "business_end_to_end": _metric([x["observed_end_to_end"] for x in businesses], [], end_to_end_definition),
        "business_first_admission_to_final_goal": _metric([x["observed_first_admission_to_final_goal"] for x in businesses], [], first_admission_definition)}
    for value in observed.values():
        if isinstance(value, dict):
            value.pop("restricted_full_population", None)
    return {
        "schema": "g31.nowait.tht_metrics.v2", "passed": not violations,
        "horizon": horizon, "units": "seconds", "primary": "user_tht",
        "segment_denominator": len(segments), "business_denominator": len(businesses),
        "completed_segments": sum(x["done"] for x in segments),
        "completed_businesses": sum(x["done"] for x in businesses),
        "censored_segments": sum(not x["done"] for x in segments),
        "censored_businesses": sum(not x["done"] for x in businesses),
        "unreleased_segments": sum(x["unreleased"] for x in segments),
        "missing_segments": missing, "violation_counts": dict(Counter(v[1] for v in violations)),
        "violations": violations, "user_tht": primary,
        "user_tht_total_seconds": primary["full_population"]["sum"],
        "user_tht_mean_per_business_seconds": primary["full_population"]["mean"],
        "missing_first_planning_attempt_segments": sum(not x["anchor_declared"] for x in segments),
        "user_tht_full_population_available": primary["full_population"]["sum"] is not None,
        "paper_tht": network, "network_elapsed": network,
        "paper_tht_total_seconds": network["full_population"]["sum"],
        "paper_tht_mean_per_business_seconds": network["full_population"]["mean"],
        "secondary": secondary, "observed_ceil_finish": observed,
        "interpretation": [
            "Full-population duration statistics are null whenever any member lacks the required completed observation; completed-subset values are diagnostic only.",
            "Canonical-to-admission observations become known at actual admission even if transport is incomplete; they include both preplanning hold and retries.",
            "User THT requires explicit first_planning_attempt_time. A source activation, generated_release, successful admission or canonical release never fills a missing anchor.",
            "Restricted elapsed is finish-release for completed legs, otherwise max(0,horizon-release). Restricted network is finish-admission or observed in-network exposure; unadmitted legs contribute zero exposure, not zero eventual THT.",
            "Missing telemetry preserves denominators and invalidates source/network exposure split. Restricted canonical elapsed conservatively treats missing records as uncompleted through horizon.",
            "Observed ceil finish is an auxiliary common transformation; continuous physical finish defines the primary result.",
            "Metric validity does not establish physical safety, EBS causality, optimality, or a performance advantage. These require independent audits."]}


def audit_tht(rows, bags, horizon=98259.0):
    from .future_metadata import audit_future_metadata, merge_future_result
    rows, bags = list(rows), list(bags)
    future = audit_future_metadata(rows, bags, horizon=horizon)
    result = _audit_tht_existing(rows, bags, horizon)
    result["interpretation"].append("Unlaunched reserved certificates remain unadmitted and censored. First-attempt-to-horizon exposure includes the future-reservation hold; planned clocks never substitute for actual clocks.")
    return merge_future_result(result, future)
