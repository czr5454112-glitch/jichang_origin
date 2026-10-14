"""Independent test and published full-file audit, without calling the importer."""
from pathlib import Path
import contextlib
from collections import Counter, defaultdict
from fractions import Fraction
import gzip
from hashlib import sha256
import json
import sys
import time
import traceback

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
AUTHOR = BASE.parent / "phase4_round9_business_inputs_20261011"
AUTHOR_RUN = sys.argv[1] if len(sys.argv) > 1 else "003"
TEST = ROOT / "tests/test_ics_v3_business_input_audit.py"
SOURCE = ROOT / "scripts/experiments/ics_circulation_v3/business_inputs.py"
index = 1
while (BASE / f"run_{index:03d}").exists():
    index += 1
out = BASE / f"run_{index:03d}"
out.mkdir()

def digest(path):
    return sha256(path.read_bytes()).hexdigest()

def ceil(value):
    return -(-value.numerator // value.denominator)

def floor(value):
    return value.numerator // value.denominator

before = {str(path): digest(path) for path in (SOURCE, TEST, Path(__file__).resolve())}
(out / "before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
for path in (SOURCE, TEST):
    (out / path.name).write_bytes(path.read_bytes())
cpu, wall = time.process_time(), time.perf_counter()
result = {"status": "running", "physics_calls": 0, "full_input_checks": 0, "scales": []}

def check(condition, message):
    result["full_input_checks"] += 1
    if not condition:
        raise AssertionError(message)

try:
    with (out / "stdout.txt").open("w", encoding="utf-8") as stdout, (out / "stderr.txt").open("w", encoding="utf-8") as stderr:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            import pytest
            result["pytest_exit_code"] = int(pytest.main(["-q", str(TEST), "--basetemp", str(out / "pytest_tmp"),
                                                         "--junitxml", str(out / "junit.xml")]))
    check(result["pytest_exit_code"] == 0, "independent counterexamples failed")
    author = json.loads((AUTHOR / f"audit_{AUTHOR_RUN}.json").read_bytes())
    contract = json.loads((AUTHOR / f"proxy_contract_{AUTHOR_RUN}.json").read_bytes())
    check(author["status"] == "passed", "author full input audit not passed")
    check(author["source_sha256_before"] == author["source_sha256_after"] == digest(SOURCE), "input source changed")
    check(contract["protection"] == {"policy": "all", "business_ids": []}, "unknown protection rule")
    check(contract["deadline"]["policy"] == "std_minus_lead", "unknown deadline")
    tick, lead = Fraction(str(contract["tick_seconds"])), Fraction(str(contract["deadline"]["lead_seconds"]))
    parent_path = ROOT / "legacy/jichang_origin_readonly/inputdata.txt"
    parent = {int(fields[0]): fields for fields in (
        line.split() for line in parent_path.read_text(encoding="utf-8-sig").splitlines()[1:] if line.strip())}
    parent_order, inserted_offset = tuple(parent), max(parent) + 1
    profile = json.loads((ROOT / "scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json").read_bytes())
    adjacency = defaultdict(set)
    for edge in profile["edges"]:
        if edge["capacity"] > 0:
            adjacency[str(edge["start"])].add(str(edge["end"]))
    reach = {}
    for start in {str(n["location"]) for n in profile["nodes"]}:
        queue, visited = [start], {start}
        while queue:
            for node in adjacency[queue.pop()] - visited:
                visited.add(node)
                queue.append(node)
        reach[start] = visited
    for summary in author["scales"]:
        scale = summary["scale"]
        for filename, expected in summary["input_sha256"].items():
            check(digest(Path(filename)) == expected, "published source binding changed: " + filename)
        raw_path = ROOT / f".g4irsf24_worktree/artifacts/tasks/g4irsf31_nanning/nanning_{scale}x_raw.txt"
        raw_expected_sha = digest(raw_path)
        raw = {}
        for line in raw_path.read_text(encoding="utf-8-sig").splitlines()[1:]:
            if line.strip():
                fields = line.split()
                check(int(fields[0]) not in raw, "duplicate raw ID")
                raw[int(fields[0])] = fields
        binding_path = AUTHOR / summary["output_clock_binding"]
        check(digest(binding_path) == summary["output_clock_binding_sha256"], "clock artifact changed")
        rows = [json.loads(line) for line in gzip.decompress(binding_path.read_bytes()).splitlines()]
        check(len(rows) == len(raw) == summary["raw_business_count"], "full raw denominator differs")
        seen, counts, unreachable, stage_unreachable, max_error = set(), Counter(), 0, 0, Fraction(0)
        original_parents, derived_parents, flight_shifts = set(), set(), {}
        for row in rows:
            raw_sha, ident = row["raw_identity"]
            check(ident in raw and ident not in seen, "binding ID missing or duplicate")
            seen.add(ident)
            fields = raw[ident]
            arrival, std = Fraction(fields[1]), Fraction(fields[2])
            derived = ident not in parent
            expected_parent = parent_order[ident - inserted_offset] if derived else ident
            check(row["parent_id"] == expected_parent, "parent identity changed")
            check(expected_parent not in (derived_parents if derived else original_parents), "parent occurrence duplicated")
            (derived_parents if derived else original_parents).add(expected_parent)
            parent_fields = parent[expected_parent]
            shift = std - Fraction(parent_fields[2])
            check(arrival == Fraction(parent_fields[1]) + shift, "parent/source times differ")
            check(shift > 0 if derived else shift == 0, "parent shift class differs")
            if derived:
                flight = (parent_fields[2], parent_fields[4], parent_fields[5])
                check(flight_shifts.setdefault(flight, shift) == shift, "derived parent flight split")
            early = std - arrival >= 4800
            release = ceil((std - 2700) / tick) if early else None
            check(raw_sha == raw_expected_sha, "raw digest mismatch")
            check(row["business_bag_id"] == f"projected:{scale}x:{ident}", "namespace mismatch")
            check(Fraction(row["source_seconds"]) == arrival, "source seconds changed")
            check(row["arrival"] == ceil(arrival / tick), "arrival rounding differs")
            check(row["deadline"] == floor((std - lead) / tick), "deadline softened")
            check(row["protected"] is True, "protection removed")
            check(row["release_at"] == release, "release differs")
            check(row["published_at"] == (row["arrival"] if early else None), "publication differs")
            check((row["origin"], row["destination"]) == (fields[3], fields[4]), "OD changed")
            counts["early_storage" if early else "direct"] += 1
            unreachable += fields[4] not in reach[fields[3]]
            stage_unreachable += (("53" not in reach[fields[3]] or fields[4] not in reach["53"])
                                  if early else fields[4] not in reach[fields[3]])
            max_error = max(max_error, row["arrival"] * tick - arrival)
        check(seen == set(raw), "omitted raw IDs")
        check(original_parents == set(parent), "original parent manifest incomplete")
        check(derived_parents == (set(parent) if scale == 2 else set()), "derived parent manifest incomplete")
        check(summary["original_count"] == len(original_parents) and summary["derived_count"] == len(derived_parents), "parent counters differ")
        check(dict(counts) == summary["lifecycle_counts"], "lifecycle totals differ")
        check(unreachable == summary["static_positive_capacity_outbound_unreachable_kept"], "unreachable total differs")
        check(stage_unreachable == summary["static_positive_capacity_stage_unreachable_kept"], "stage unreachable differs")
        check(max_error == Fraction(summary["max_arrival_rounding_seconds"]), "rounding maximum differs")
        check(summary["independent_observed_operating_days"] == 0 and summary["source_timetable_count"] == 1, "source-day claim differs")
        result["scales"].append({"scale": scale, "rows": len(rows), "unreachable_kept": unreachable,
                                  "stage_unreachable_kept": stage_unreachable, "lifecycle": dict(counts)})
    after = {filename: digest(Path(filename)) for filename in before}
    check(after == before, "audit/source changed during independent read")
    result.update(status="passed", after=after)
except BaseException:
    result.update(status="failed", failure=traceback.format_exc())
finally:
    result.update(cpu_seconds=time.process_time() - cpu, wall_seconds=time.perf_counter() - wall,
                  resource_scope="in-process pytest import/tests plus independent raw artifact read; excludes startup/snapshot/final write",
                  unmetered_auxiliary=["source review", "audit design", "tool orchestration"])
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
sys.exit(0 if result["status"] == "passed" else 1)
