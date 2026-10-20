"""Train-only gate and fixed-weight callback replay; never fits or reads test."""
import copy
import cProfile
import gzip
import hashlib
import io
import json
from pathlib import Path
import pstats
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_ranker as ranker
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_training_campaign as campaign

OUT = Path(__file__).resolve().parent
RUN = OUT.parent
STEMS = ("H_701_calendar", "H_702_calendar", "C_701_extra", "C_702_extra")


def main():
    mode = sys.argv[1]
    assert mode in ("before", "after")
    inputs = [{
        "dataset": campaign.file_ref(RUN/(stem+"_dataset_001.json.gz")),
        "reference_plan": campaign.file_ref(RUN/(stem+"_a_ref_001")/"plan.json"),
        "patched_plan": campaign.file_ref(RUN/(stem+"_a_patch_001")/"plan.json"),
    } for stem in STEMS]
    datasets, provenance = campaign.load_datasets(inputs, split="train", training_domain="primary_22")
    gates = {variant: ranker.sufficiency(datasets, information_variant=variant) for variant in ranker.VARIANTS}
    result = {"schema": "g31.pair_ranker_train_only_profile.v1", "mode": mode,
        "datasets": inputs, "provenance": provenance, "sufficiency": gates,
        "source_pins": ranker.source_pins(), "fit_calls": 0, "test_opened": False,
        "claim": "saved_callback_replay_with_manual_fixed_weights_no_native_runtime_claim",
        "profiles": [], "clocks": []}
    for data in datasets:
        pair = data["pair"]
        row = data["rows"][0]
        evidence = row["forecast_evidence"]
        result["clocks"].append({"pair_id": pair["pair_id"], "parent": pair["parent"],
            "observed_at": row["observation"]["now"],
            "observed_at_epoch_seconds": ranker._absolute_now(row),
            "label_closed_at_epoch_seconds": pair["parent"]["calendar_start_epoch_seconds"]
                + pair["reference_cost"]["label_end"],
            "B1_model_available_at_epoch_seconds": evidence["model_available_at_epoch_seconds"],
            "actual_plan_received_at_epoch_seconds": evidence["plan_received_at_epoch_seconds"],
            "advantage_bag_seconds": pair["advantage_bag_seconds"],
            "known_job_counts": pair["per_job_comparison_counts"]})
    for stem, data in zip(STEMS[:2], datasets[:2], strict=True):
        for variant in ranker.VARIANTS:
            rows = data["rows"]
            vectors = [ranker.action_features(row, information_variant=variant) for row in rows]
            names = sorted(vectors[0])
            weights = [(i+1)/len(names) for i in range(len(names))]
            model = {"schema": ranker.SCHEMA, "feature_schema": ranker.FEATURE_SCHEMA,
                "information_variant": variant, "seed": 17,
                "model_available_at_epoch_seconds": 1., "feature_names": names,
                "forecast_contract": ranker._forecast_contract(rows[0]) if variant == "C11" else None,
                "parameters": {"center": [0.]*len(names), "scale": [1.]*len(names),
                    "target_scale": 1., "layers": [{"weight": [weights], "bias": [0.]}]},
                "fixture_not_fitted": True}
            model["model_id"] = ranker.digest(model)
            predict = ranker.prepare_predictor(model)
            timings, feature_timings = [], []
            for _ in range(3):
                start = time.perf_counter()
                score = predict(*rows)
                timings.append(time.perf_counter()-start)
                start = time.perf_counter()
                [ranker.action_features(row, information_variant=variant) for row in rows]
                feature_timings.append(time.perf_counter()-start)
            profiler = cProfile.Profile()
            profiler.runcall(predict, *rows)
            output = io.StringIO()
            pstats.Stats(profiler, stream=output).strip_dirs().sort_stats("cumtime").print_stats(18)
            row = {"stem": stem, "variant": variant, "features": vectors,
                "fixed_weight_score": score, "predict_seconds": timings,
                "predict_median_seconds": statistics.median(timings),
                "external_features_median_seconds": statistics.median(feature_timings),
                "profile": output.getvalue()}
            result["profiles"].append(row)
    if mode == "after":
        previous = json.loads((OUT/"pair_ranker_profile_before.json").read_bytes())
        result["exact_feature_and_score_parity"] = all(
            before["features"] == after["features"]
            and before["fixed_weight_score"] == after["fixed_weight_score"]
            for before, after in zip(previous["profiles"], result["profiles"], strict=True))
        assert result["exact_feature_and_score_parity"]
    target = OUT/f"pair_ranker_profile_{mode}.json"
    with target.open("x", encoding="utf8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    if mode == "before":
        source = Path(ranker.__file__).read_bytes()
        (OUT/"pair_ranker_source_before_shared_current.py").write_bytes(source)
    print(json.dumps({"path": str(target), "gates": gates,
        "profiles": [{key: row[key] for key in ("stem", "variant", "predict_median_seconds",
            "external_features_median_seconds")} for row in result["profiles"]],
        "fit_calls": 0, "test_opened": False}, indent=2))


if __name__ == "__main__":
    main()
