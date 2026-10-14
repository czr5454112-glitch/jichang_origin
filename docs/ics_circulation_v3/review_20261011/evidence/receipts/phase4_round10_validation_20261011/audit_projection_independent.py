"""Independent artifact audit: no projection/business/runtime implementation imports."""
from collections import Counter
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import process_time, perf_counter
import traceback

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
PARENT = BASE.parent
out = BASE / sys.argv[1]
out.mkdir()
source = PARENT / "phase4_round10_business_projection_20261011" / sys.argv[2]
cpu, wall = process_time(), perf_counter()
bindings, checks = {}, 0


def check(value, reason):
    global checks
    checks += 1
    if not value:
        raise AssertionError(reason)


def data(path, *, lines=False):
    raw = path.read_bytes()
    bindings[path.relative_to(ROOT).as_posix()] = sha256(raw).hexdigest()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    if lines:
        return [json.loads(row, parse_float=str) for row in raw.splitlines()]
    return json.loads(raw, parse_float=str)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                             allow_nan=False).encode()).hexdigest()


rows = []
try:
    report = data(source / "resource.json")
    check(report["status"] == "passed" and not report["changed_inputs"], "author full audit finished on frozen inputs")
    manifest = data(source / "manifest.json")
    for relative, expected in manifest.items():
        check(sha256((source / relative).read_bytes()).hexdigest() == expected, "projection artifact seal " + relative)
    previous = data(PARENT / "phase4_round9_resource_ledger_20261011/static_domains_001/analysis.json")
    static = {(str(Fraction(str(row["flight_surrogate"][0]))), str(row["flight_surrogate"][1]), str(row["flight_surrogate"][2])): row
              for row in previous["flight_rows"]}
    assignments = {}
    for scale in (1, 2):
        records = data(source / f"projected_tasks_{scale}x.jsonl.gz", lines=True)
        groups = data(source / f"flight_projection_{scale}x.json")
        metadata = data(source / f"projection_metadata_{scale}x.json")
        contract = data(source / f"projection_contract_{scale}x.json")
        normalized = data(PARENT / f"phase4_w3_round8_business_input_research_repaired_20261010/business_tasks_{scale}x.jsonl.gz", lines=True)
        clocks = data(PARENT / f"phase4_round9_business_inputs_20261011/full_business_clock_binding_{scale}x_004.jsonl.gz", lines=True)
        source_rows = {r["business_bag_id"]: r for r in normalized}
        source_clocks = {r["business_bag_id"]: r for r in clocks}
        by_id = {r["original"]["business_bag_id"]: r for r in records}
        check(len(records) == len(by_id) == len(source_rows) == len(source_clocks) == 28506 * scale, "full source denominator")
        check(by_id.keys() == source_rows.keys() == source_clocks.keys(), "exact source identities")
        payload = dict(metadata, records=records, groups=groups)
        expected_seal = payload.pop("content_sha256")
        check(digest(payload) == expected_seal, "independent full projection content seal")
        check(metadata["runtime_adaptation_required"] is True, "explicit separate input type")
        check(metadata["source_business_count"] == len(records), "metadata denominator")
        check(metadata["independent_observed_operating_days"] == 0, "no invented independent day")
        check(len(groups) == 360 and sum(g["flight_instance_count"] for g in groups) == 360 * scale, "parent families and derived instances")
        member_ids = []
        for group in groups:
            key = group["parent_flight_key"]
            check(group["group_id"] == "parent-flight:" + digest(key), "canonical parent family identity")
            old_domain = static[tuple(key[1:])]
            check(group["structural_domain"] == old_domain["static_reachability_and_return_domain"], "independently audited structural domain")
            check(group["necessary_domain"] == old_domain["static_deadline_necessary_domain"], "independently audited time necessary domain")
            check(len(group["necessary_domain"]) == 36, "full source necessary domain size")
            if group["original_destination"] in group["necessary_domain"]:
                selected, selected_hash = group["original_destination"], None
            else:
                selected_hash, selected = min((digest([contract["schema"], contract["salt"], key, node]), node)
                    for node in group["necessary_domain"])
            check(group["projected_destination"] == selected and group["selection_sha256"] == selected_hash, "independent declared deterministic selection")
            if scale == 1:
                assignments[group["group_id"]] = selected
            else:
                check(assignments[group["group_id"]] == selected, "same parent assignment across densification")
            for bag_id in group["business_bag_ids"]:
                member_ids.append(bag_id)
                record = by_id[bag_id]
                check(record["group_id"] == group["group_id"] and record["projected_destination"] == selected, "whole-family membership and destination")
        check(len(member_ids) == len(set(member_ids)) == len(records) and set(member_ids) == set(by_id), "partition with no dropped or duplicated bag")
        changed = 0
        for bag_id, row in by_id.items():
            original, prior, clock = row["original"], source_rows[bag_id], source_clocks[bag_id]
            for key in ("business_bag_id", "origin", "final_destination", "lifecycle", "old_segment_ids"):
                check(original[key] == prior[key], "preserve normalized " + key)
            for key in ("arrival_seconds", "std_seconds", "scheduled_release_seconds"):
                if original[key] is None or prior[key] is None:
                    check(original[key] is prior[key], "preserve optional " + key)
                else:
                    check(Fraction(str(original[key])) == Fraction(str(prior[key])), "preserve exact " + key)
            check(original["storage_node"] == prior["storage_node_proxy"], "preserve storage role")
            osource, psource = original["source"], prior["source"]
            for key in osource:
                if key == "flight_surrogate":
                    check(Fraction(osource[key][0]) == Fraction(str(psource[key][0])) and osource[key][1:] == psource[key][1:], "preserve original flight surrogate")
                elif key == "time_shift_seconds":
                    check(Fraction(osource[key]) == Fraction(str(psource[key])), "preserve derived time shift")
                else:
                    check(osource[key] == psource[key], "preserve raw provenance " + key)
            for key in ("arrival", "deadline", "protected", "published_at", "release_at", "origin"):
                check(original[key] == clock[key], "preserve audited source contract " + key)
            check(original["final_destination"] == clock["destination"] == row["original_destination"], "retain original final explicitly")
            check([osource["raw_sha256"], osource["raw_task_id"]] == clock["raw_identity"], "exact raw identity")
            changed += row["original_destination"] != row["projected_destination"]
        check(changed == 4001 * scale, "all and only out-of-domain source assignments changed")
        rows.append({"scale": scale, "records": len(records), "changed": changed, "groups": len(groups),
                     "flight_instances": sum(g["flight_instance_count"] for g in groups)})
    result = {"status": "passed", "rows": rows}
except Exception:
    result = {"status": "failed", "rows": rows, "exception": traceback.format_exc()}
result.update(checks=checks, physical_runs=0, cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
              input_sha256=bindings, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
              scope="independent read-only artifact review, no author implementation imports or physics; final writes excluded",
              qualification="Domain values reuse separately Floyd-audited Round9 domains; this is not a new independent scenario")
(out / "results.json").write_text(json.dumps(result, indent=2))
print(json.dumps({k: v for k, v in result.items() if k != "input_sha256"}, indent=2))
raise SystemExit(0 if result["status"] == "passed" else 1)
