"""Reproducible G4IRSF12-K demand calibration and generation audit.

This module does not generate a scaled workload and does not run the runtime.
It validates the immutable historical input, reconstructs the audited Java
task-splitting rules, describes the observed one-day demand, and publishes
fail-closed candidate manifests for later gated work.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import io
import json
import math
import sys
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_IMPORT_ROOT = Path(__file__).resolve().parents[2]
if str(_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMPORT_ROOT))

from scripts.eval.g4irsf12_reproducible_harness import (
    CANDIDATE_BUNDLE_SCHEMA,
    ExecutionProvenance,
    candidate_bundle as rebuild_phase_j_candidate_bundle,
    load_result_ledger,
)

ROOT = Path(__file__).resolve().parents[2]
PHASE_DATE = "2026-07-23"

MAP_PATH = Path("data/processed/maps/map2.json")
PROCESSED_INPUT_PATH = Path("data/processed/tasks/inputdata.jsonl")
RAW_INPUT_PATH = Path("legacy/jichang_origin_readonly/inputdata.txt")
JAVA_MAIN_PATH = Path("legacy/jichang_origin_readonly/src/RUN/Main.java")
JAVA_TASKS_PATH = Path("legacy/jichang_origin_readonly/src/App/Tasks.java")

MAP_RAW_SHA256 = "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
PROCESSED_INPUT_RAW_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
PROCESSED_INPUT_SEMANTIC_SHA256 = PROCESSED_INPUT_RAW_SHA256
RAW_INPUT_SHA256 = "0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87"
JAVA_MAIN_SHA256 = "af7ba8f8224a480f61e4d4b010d0c6fcf5e8798cccfdf6f298d786ac053bf5af"
JAVA_TASKS_SHA256 = "dd4505e495fd3c0fa737923dca83c9d404fc3b1e3a7ce979e7dd384a57d0948b"

EXPECTED_BAGS = 28_506
EXPECTED_SEGMENTS = 43_603
EXPECTED_EARLY_BAGS = 15_097
EXPECTED_DIRECT_BAGS = 13_409
EXPECTED_MAP_NODES = 54
EXPECTED_MAP_EDGES = 69
EARLY_THRESHOLD_SECONDS = 4_800.0
EBS_RELEASE_LEAD_SECONDS = 2_700.0
SIMULATION_WINDOW_SECONDS = 86_400
RESAMPLE_SEED = 20_260_723

CONFIG_PATH = Path("artifacts/configs/g4irsf12_demand_calibration_protocol.json")
MANIFEST_DIR = Path("artifacts/tasks/g4irsf12")
AIRPORT_REPORT_PATH = Path(
    "outputs/reports/g4irsf12_airport_scope_and_demand_calibration.md"
)
CALIBRATION_INPUTS_PATH = Path(
    "outputs/tables/g4irsf12_demand_calibration_inputs.csv"
)
SCALE_ENVELOPE_PATH = Path(
    "outputs/tables/g4irsf12_scale_uncertainty_envelope.csv"
)
GENERATION_AUDIT_PATH = Path(
    "outputs/reports/g4irsf12_original_task_generation_audit.md"
)
PHASE_J_BUNDLE_PATH = Path(
    "artifacts/policies/g4irsf12_original_scale_candidate_bundle.json"
)
PHASE_J_LEDGER_PATH = Path("outputs/tables/g4irsf12_original_scale_full_ab.csv")

SCALE_CANDIDATES: tuple[tuple[str, Decimal, str], ...] = (
    ("1p0", Decimal("1.0"), "historical_observed_day_reference"),
    ("1p1", Decimal("1.1"), "mild_growth_sensitivity"),
    ("1p2", Decimal("1.2"), "busy_day_candidate_not_calibrated"),
    ("1p3", Decimal("1.3"), "provisional_peak_envelope_not_calibrated"),
    ("1p5", Decimal("1.5"), "engineering_reserve_sensitivity"),
    ("2p0", Decimal("2.0"), "extreme_stress_sensitivity"),
)

EXTERNAL_SOURCES: tuple[dict[str, str], ...] = (
    {
        "source_id": "caac_2019_airport_statistics",
        "authority": "Civil Aviation Administration of China",
        "url": (
            "https://www.caac.gov.cn/XXGK/XXGK/TJSJ/202003/"
            "t20200309_201358.html"
        ),
        "claim": (
            "Official 2019 whole-airport passenger-throughput context; it does "
            "not identify the thesis airport or represented BHS share."
        ),
    },
    {
        "source_id": "acrp_report_163",
        "authority": "National Academies / Airport Cooperative Research Program",
        "url": "https://nap.nationalacademies.org/read/23692/chapter/9",
        "claim": (
            "Design-day demand should use flight-by-flight schedules and "
            "airport-specific time-of-day/facility profiles; generic annual "
            "averages do not establish a baggage subsystem peak."
        ),
    },
    {
        "source_id": "iata_adrm",
        "authority": "International Air Transport Association",
        "url": (
            "https://www.iata.org/en/publications/manuals/"
            "airport-development-reference-manual/"
        ),
        "claim": (
            "Official airport-planning guidance covers peak forecasting, "
            "design-day schedules, demand-capacity calculations, and BHS."
        ),
    },
    {
        "source_id": "iata_demand_triggers",
        "authority": "International Air Transport Association",
        "url": (
            "https://www.iata.org/contentassets/"
            "d1d4d535bf1c4ba695f43e9beff8294f/"
            "demand-triggers-for-airport-investments.pdf"
        ),
        "claim": (
            "Capacity assessment should be subsystem-specific and driven by "
            "peak/design demand and the constraining process."
        ),
    },
    {
        "source_id": "mapd_aamas_2017",
        "authority": "International Foundation for Autonomous Agents and Multiagent Systems",
        "url": "https://www.ifaamas.org/Proceedings/aamas2017/pdfs/p837.pdf",
        "claim": (
            "MAPD models online exogenous task arrival; one-shot agent count "
            "is not a substitute for an arrival-process calibration."
        ),
    },
    {
        "source_id": "lifelong_mapf_aaai_2021",
        "authority": "Association for the Advancement of Artificial Intelligence",
        "url": "https://ojs.aaai.org/index.php/AAAI/article/view/17344",
        "claim": (
            "Lifelong MAPF throughput is a time-based completed-goal measure; "
            "map-specific agent-density examples are auxiliary diagnostics."
        ),
    },
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalised_text_sha256(payload: bytes) -> str:
    return _sha256(payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(payload)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _close(left: float, right: float, tolerance: float = 1.0e-8) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _csv_scalar(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.9f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _csv_text(rows: Iterable[Mapping[str, Any]], fieldnames: Sequence[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(fieldnames),
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_scalar(row.get(key)) for key in fieldnames})
    return buffer.getvalue()


def _quantile(values: Sequence[float], probability: float) -> float:
    """Return the deterministic R-7/NumPy-linear sample quantile."""

    _require(bool(values), "quantile requires at least one value")
    _require(0.0 <= probability <= 1.0, "quantile probability out of range")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _distribution(values: Sequence[float]) -> dict[str, float | int]:
    _require(bool(values), "distribution requires at least one value")
    return {
        "count": len(values),
        "min": min(values),
        "mean": sum(values) / len(values),
        "p50": _quantile(values, 0.50),
        "p95": _quantile(values, 0.95),
        "p99": _quantile(values, 0.99),
        "max": max(values),
    }


def _counter_dict(counter: Counter[Any]) -> dict[str, int]:
    return {str(key): int(counter[key]) for key in sorted(counter, key=str)}


def _rolling_peak(entry_times: Sequence[float], window_seconds: int) -> dict[str, Any]:
    """Maximum bag count in a half-open interval [observed start, start+window)."""

    ordered = sorted(float(value) for value in entry_times)
    right = 0
    best_count = -1
    best_start = 0.0
    for left, start in enumerate(ordered):
        if right < left:
            right = left
        while right < len(ordered) and ordered[right] < start + window_seconds:
            right += 1
        count = right - left
        if count > best_count:
            best_count = count
            best_start = start
    return {
        "window_seconds": window_seconds,
        "interval_definition": "[observed_entry_time, observed_entry_time + window)",
        "start_time_seconds": best_start,
        "end_time_seconds_exclusive": best_start + window_seconds,
        "bag_count": best_count,
        "equivalent_bags_per_hour": best_count * 3600.0 / window_seconds,
        "bags_per_second": best_count / window_seconds,
    }


def _parse_raw_input(path: Path) -> tuple[str, list[dict[str, Any]]]:
    lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
    _require(bool(lines), f"raw input is empty: {path}")
    header = lines[0].strip()
    _require(
        header == "ID EntryTime(s) STD(s) star end Unloader Loader",
        f"unexpected raw input header: {header!r}",
    )
    rows: list[dict[str, Any]] = []
    for source_line, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        fields = line.split()
        _require(len(fields) == 7, f"raw source line {source_line}: expected 7 fields")
        rows.append(
            {
                "task_id": int(fields[0]),
                "entry_time": float(fields[1]),
                "std": float(fields[2]),
                "start": int(fields[3]),
                "goal": int(fields[4]),
                "unloader": fields[5],
                "loader": fields[6],
                "source_line": source_line,
            }
        )
    return header, rows


def _parse_processed_input(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_line, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        _require(isinstance(value, dict), f"processed line {source_line} is not object")
        rows.append(value)
    return rows


def _shortest_tables(
    map_data: Mapping[str, Any],
) -> tuple[
    dict[tuple[int, int], float],
    dict[tuple[int, int], float],
    dict[tuple[int, int], float],
]:
    adjacency: dict[int, list[tuple[int, float, float]]] = defaultdict(list)
    nodes = [int(node["location"]) for node in map_data["nodes"]]
    for edge in map_data["edges"]:
        adjacency[int(edge["start"])].append(
            (
                int(edge["end"]),
                float(edge["length"]),
                float(edge["travel_time"]),
            )
        )

    def run(source: int, weight_index: int) -> dict[int, float]:
        distances = {source: 0.0}
        queue: list[tuple[float, int]] = [(0.0, source)]
        while queue:
            distance, node = heapq.heappop(queue)
            if distance != distances[node]:
                continue
            for target, length, travel_time in adjacency.get(node, []):
                weights = (length, travel_time, 1.0)
                candidate = distance + weights[weight_index]
                if candidate < distances.get(target, math.inf):
                    distances[target] = candidate
                    heapq.heappush(queue, (candidate, target))
        return distances

    tables: list[dict[tuple[int, int], float]] = []
    for weight_index in range(3):
        table: dict[tuple[int, int], float] = {}
        for source in nodes:
            for target, distance in run(source, weight_index).items():
                table[(source, target)] = distance
        tables.append(table)
    return tables[0], tables[1], tables[2]


def _validate_java_rules(
    root: Path,
    raw_rows: Sequence[Mapping[str, Any]],
    processed_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_task: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in processed_rows:
        by_task[int(row["task_id"])].append(row)

    _require(len(raw_rows) == EXPECTED_BAGS, "unexpected raw bag count")
    _require(len(processed_rows) == EXPECTED_SEGMENTS, "unexpected segment count")
    _require(len(by_task) == EXPECTED_BAGS, "processed task-id count differs")
    _require(
        [int(row["task_id"]) for row in raw_rows] == list(range(EXPECTED_BAGS)),
        "raw task IDs must be contiguous 0..28505",
    )
    _require(set(by_task) == set(range(EXPECTED_BAGS)), "processed task IDs differ")

    early_count = 0
    direct_count = 0
    for raw in raw_rows:
        task_id = int(raw["task_id"])
        rows = by_task[task_id]
        lead = float(raw["std"]) - float(raw["entry_time"])
        expected_early = lead >= EARLY_THRESHOLD_SECONDS
        common_checks = [
            int(row["pallet_id"]) == task_id
            and int(row["task_id"]) == task_id
            and int(row["source_line"]) == int(raw["source_line"])
            and int(row["original_start"]) == int(raw["start"])
            and int(row["original_goal"]) == int(raw["goal"])
            and _close(float(row["original_entry_time"]), float(raw["entry_time"]))
            and _close(float(row["std"]), float(raw["std"]))
            and bool(row["early_bag_split"]) == expected_early
            for row in rows
        ]
        _require(all(common_checks), f"common conversion mismatch for task {task_id}")

        if expected_early:
            early_count += 1
            _require(len(rows) == 2, f"early task {task_id} must have two segments")
            by_leg = {str(row["leg"]): row for row in rows}
            _require(
                set(by_leg) == {"storage_in", "storage_out"},
                f"early task {task_id} has wrong legs",
            )
            storage_in = by_leg["storage_in"]
            storage_out = by_leg["storage_out"]
            _require(
                int(storage_in["start"]) == int(raw["start"])
                and int(storage_in["goal"]) == 47
                and _close(float(storage_in["pass_time"]), float(raw["entry_time"]))
                and str(storage_in["segment_id"]) == f"{task_id}:storage_in",
                f"storage-in rule mismatch for task {task_id}",
            )
            _require(
                int(storage_out["start"]) == 52
                and int(storage_out["goal"]) == int(raw["goal"])
                and _close(
                    float(storage_out["pass_time"]),
                    float(raw["std"]) - EBS_RELEASE_LEAD_SECONDS,
                )
                and str(storage_out["segment_id"]) == f"{task_id}:storage_out",
                f"storage-out rule mismatch for task {task_id}",
            )
        else:
            direct_count += 1
            _require(len(rows) == 1, f"direct task {task_id} must have one segment")
            direct = rows[0]
            _require(
                str(direct["leg"]) == "direct"
                and int(direct["start"]) == int(raw["start"])
                and int(direct["goal"]) == int(raw["goal"])
                and _close(float(direct["pass_time"]), float(raw["entry_time"]))
                and str(direct["segment_id"]) == f"{task_id}:direct",
                f"direct rule mismatch for task {task_id}",
            )

    _require(early_count == EXPECTED_EARLY_BAGS, "unexpected early-bag count")
    _require(direct_count == EXPECTED_DIRECT_BAGS, "unexpected direct-bag count")

    main_text = (root / JAVA_MAIN_PATH).read_text(encoding="utf-8")
    tasks_text = (root / JAVA_TASKS_PATH).read_text(encoding="utf-8")
    required_main_fragments = (
        'String path = "inputdata.txt"',
        "double time = 4800",
        "newtask.setGoal(47)",
        "double passtime = newtask1.getSTD()-2700",
        "newtask1.setStar(52)",
    )
    required_tasks_fragments = (
        "public void generate_tasks",
        "temptask.getPass_time() - epoch >= 1",
        "task_List.get(ics_pf.getMap().star.get(i).getLocation()).remove(0)",
        "//\t\t\t\t\tRandom random = new Random();",
        "//\t\t\t\t\tint end_index = random.nextInt",
    )
    for fragment in required_main_fragments:
        _require(fragment in main_text, f"Main.java rule missing: {fragment}")
    for fragment in required_tasks_fragments:
        _require(fragment in tasks_text, f"Tasks.java rule missing: {fragment}")

    return {
        "raw_bag_count": len(raw_rows),
        "processed_segment_count": len(processed_rows),
        "early_split_bag_count": early_count,
        "direct_bag_count": direct_count,
        "segments_per_bag": len(processed_rows) / len(raw_rows),
        "early_split_share": early_count / len(raw_rows),
        "validation": "PASS_EXACT_JAVA_RULE_RECONSTRUCTION",
    }


def _valid_sha256(value: Any) -> bool:
    text = str(value or "").lower()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _phase_j_evidence(root: Path) -> dict[str, Any]:
    """Verify that Phase-K's J conclusion is backed by the v4 ledger.

    Phase K deliberately does not trust a hand-written promotion bit.  It
    re-admits the formal v4 ledger, reconstructs the candidate bundle from
    those rows under the bundle's recorded execution provenance, and then
    records whether a complete finalist actually met both original-entry
    performance targets.  The result is evidence only: it never opens G4J or
    authorises a scaled workload.
    """

    bundle_path = root / PHASE_J_BUNDLE_PATH
    ledger_path = root / PHASE_J_LEDGER_PATH
    result: dict[str, Any] = {
        "schema": "czr005.g4irsf12.phase_j_v4_ledger_binding.v1",
        "bundle_path": PHASE_J_BUNDLE_PATH.as_posix(),
        "ledger_path": PHASE_J_LEDGER_PATH.as_posix(),
        "bundle_file_sha256": _sha256(bundle_path.read_bytes()) if bundle_path.is_file() else "",
        "ledger_file_sha256": _sha256(ledger_path.read_bytes()) if ledger_path.is_file() else "",
        "verification_status": "UNVERIFIED",
        "bundle_reconstructed_from_ledger": False,
        "full_repeat_completed": False,
        "original_1x_full_formal_pass": False,
        "original_entry_performance_pass": False,
        "g4j_status": "CLOSED",
        "g4j_enabled": False,
        "finalists": [],
        "blockers": [],
    }
    blockers: list[str] = []
    if not bundle_path.is_file():
        blockers.append("Phase-J v4 candidate bundle is missing")
    if not ledger_path.is_file():
        blockers.append("Phase-J v4 original-scale ledger is missing")
    if blockers:
        result["blockers"] = blockers
        return result

    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        result["blockers"] = [f"Phase-J candidate bundle is not valid JSON: {exc}"]
        return result
    if not isinstance(bundle, dict):
        result["blockers"] = ["Phase-J candidate bundle must be a JSON object"]
        return result
    if bundle.get("schema") != CANDIDATE_BUNDLE_SCHEMA:
        blockers.append("Phase-J candidate bundle is not the required v4 schema")
    recorded_sha = str(bundle.get("bundle_sha256") or "")
    canonical_bundle = dict(bundle)
    canonical_bundle.pop("bundle_sha256", None)
    if not _valid_sha256(recorded_sha) or _canonical_sha256(canonical_bundle) != recorded_sha:
        blockers.append("Phase-J candidate bundle self-hash is missing or stale")
    if bundle.get("current_provenance_status") != "VERIFIED":
        blockers.append("Phase-J bundle lacks verified current execution provenance")
    if bundle.get("primary_denominator") != "original_entry_time_tth":
        blockers.append("Phase-J bundle is not bound to original_entry_time_tth")
    if bundle.get("g4j_enabled") is not False or bundle.get("g4j_status") != "CLOSED":
        blockers.append("Phase-J evidence must not open G4J")

    provenance_raw = bundle.get("current_provenance")
    provenance: ExecutionProvenance | None = None
    if isinstance(provenance_raw, Mapping):
        try:
            provenance = ExecutionProvenance(**dict(provenance_raw))
        except (TypeError, ValueError):
            blockers.append("Phase-J bundle current provenance has an invalid shape")
    else:
        blockers.append("Phase-J bundle current provenance is missing")

    rows: list[dict[str, Any]] = []
    try:
        rows = load_result_ledger(ledger_path, root=root)
    except Exception as exc:  # Formal ledger validation is intentionally fail-closed.
        blockers.append(f"Phase-J v4 ledger failed formal admission: {exc}")

    if provenance is not None and rows:
        try:
            rebuilt = rebuild_phase_j_candidate_bundle(
                rows, current_provenance=provenance
            )
        except Exception as exc:  # A reconstruction failure cannot be promoted.
            blockers.append(f"Phase-J bundle reconstruction failed: {exc}")
        else:
            if rebuilt != bundle:
                blockers.append(
                    "Phase-J candidate bundle does not exactly reconstruct from its v4 ledger"
                )
            else:
                result["bundle_reconstructed_from_ledger"] = True

    finalists = bundle.get("finalists")
    if not isinstance(finalists, list) or not finalists:
        blockers.append("Phase-J candidate bundle has no finalists")
        finalists = []
    normalized_finalists: list[dict[str, Any]] = []
    for finalist in finalists:
        if not isinstance(finalist, Mapping):
            blockers.append("Phase-J finalist is not an object")
            continue
        completed = int(finalist.get("executed_full_repeat_count") or 0) == 5
        repeat_pass = finalist.get("repeat_gate") == "PASS"
        performance_pass = (
            finalist.get("v2_safe_original_entry_gate") == "PASS"
            and finalist.get("corrected_hca_original_entry_gate") == "PASS"
            and finalist.get("validated_full_gate") == "PASS"
        )
        normalized_finalists.append(
            {
                "candidate_id": str(finalist.get("candidate_id") or ""),
                "completed_five_full_repeats": completed and repeat_pass,
                "original_entry_performance_pass": performance_pass,
                "promotion_status": str(finalist.get("promotion_status") or ""),
            }
        )
    result["finalists"] = normalized_finalists
    result["full_repeat_completed"] = any(
        item["completed_five_full_repeats"] for item in normalized_finalists
    )
    result["original_entry_performance_pass"] = any(
        item["completed_five_full_repeats"]
        and item["original_entry_performance_pass"]
        for item in normalized_finalists
    )
    result["original_1x_full_formal_pass"] = any(
        item["completed_five_full_repeats"]
        and item["original_entry_performance_pass"]
        and item["promotion_status"] == "PROMOTED"
        for item in normalized_finalists
    )
    result["g4j_status"] = str(bundle.get("g4j_status") or "CLOSED")
    result["g4j_enabled"] = bool(bundle.get("g4j_enabled"))
    if not blockers and not result["original_1x_full_formal_pass"]:
        if result["full_repeat_completed"]:
            blockers.append(
                "Phase-J full repeats are verified, but no candidate passes both matched original-entry performance gates"
            )
            result["verification_status"] = "VERIFIED_COMPLETE_PERFORMANCE_FAIL"
        else:
            blockers.append("Phase-J has no verified complete five-repeat original-1x finalist")
            result["verification_status"] = "VERIFIED_INCOMPLETE"
    elif not blockers:
        result["verification_status"] = "VERIFIED_PROMOTED"
    if blockers:
        # Candidate fields are merely claims until the bundle is proven to be
        # the exact projection of the admitted ledger.
        result["original_entry_performance_pass"] = False
        result["original_1x_full_formal_pass"] = False
    result["blockers"] = sorted(set(blockers))
    return result


def collect_demand_evidence(root: Path = ROOT) -> dict[str, Any]:
    """Validate immutable inputs and collect the Phase-K baseline evidence."""

    payloads = {
        "map": (root / MAP_PATH).read_bytes(),
        "processed_input": (root / PROCESSED_INPUT_PATH).read_bytes(),
        "raw_input": (root / RAW_INPUT_PATH).read_bytes(),
        "java_main": (root / JAVA_MAIN_PATH).read_bytes(),
        "java_tasks": (root / JAVA_TASKS_PATH).read_bytes(),
        "implementation": Path(__file__).read_bytes(),
    }
    actual_hashes = {
        "map_raw_sha256": _sha256(payloads["map"]),
        "map_semantic_sha256": _normalised_text_sha256(payloads["map"]),
        "processed_input_raw_sha256": _sha256(payloads["processed_input"]),
        "processed_input_semantic_sha256": _normalised_text_sha256(
            payloads["processed_input"]
        ),
        "raw_input_sha256": _sha256(payloads["raw_input"]),
        "java_main_sha256": _sha256(payloads["java_main"]),
        "java_tasks_sha256": _sha256(payloads["java_tasks"]),
        "implementation_sha256": _sha256(payloads["implementation"]),
    }
    expected_hashes = {
        "map_raw_sha256": MAP_RAW_SHA256,
        "map_semantic_sha256": MAP_SEMANTIC_SHA256,
        "processed_input_raw_sha256": PROCESSED_INPUT_RAW_SHA256,
        "processed_input_semantic_sha256": PROCESSED_INPUT_SEMANTIC_SHA256,
        "raw_input_sha256": RAW_INPUT_SHA256,
        "java_main_sha256": JAVA_MAIN_SHA256,
        "java_tasks_sha256": JAVA_TASKS_SHA256,
    }
    for key, expected in expected_hashes.items():
        _require(actual_hashes[key] == expected, f"{key} identity mismatch")

    source_bundle_members = {
        "implementation": actual_hashes["implementation_sha256"],
        "java_main": actual_hashes["java_main_sha256"],
        "java_tasks": actual_hashes["java_tasks_sha256"],
        "map_raw": actual_hashes["map_raw_sha256"],
        "processed_input_raw": actual_hashes["processed_input_raw_sha256"],
        "raw_input": actual_hashes["raw_input_sha256"],
    }
    actual_hashes["source_bundle_sha256"] = _canonical_sha256(source_bundle_members)

    map_data = json.loads(payloads["map"].decode("utf-8"))
    _require(len(map_data["nodes"]) == EXPECTED_MAP_NODES, "unexpected map node count")
    _require(len(map_data["edges"]) == EXPECTED_MAP_EDGES, "unexpected map edge count")
    raw_header, raw_rows = _parse_raw_input(root / RAW_INPUT_PATH)
    processed_rows = _parse_processed_input(root / PROCESSED_INPUT_PATH)
    conversion = _validate_java_rules(root, raw_rows, processed_rows)

    entry_times = [float(row["entry_time"]) for row in raw_rows]
    deadline_leads = [
        float(row["std"]) - float(row["entry_time"]) for row in raw_rows
    ]
    early_dwell = [
        float(row["std"])
        - EBS_RELEASE_LEAD_SECONDS
        - float(row["entry_time"])
        for row in raw_rows
        if float(row["std"]) - float(row["entry_time"]) >= EARLY_THRESHOLD_SECONDS
    ]

    hourly_counts = Counter(int(entry // 3600) for entry in entry_times)
    _require(
        all(0 <= hour < 24 for hour in hourly_counts),
        "entry time falls outside the historical 24-hour clock day",
    )
    hourly_profile = [
        {
            "clock_hour": hour,
            "start_seconds": hour * 3600,
            "end_seconds_exclusive": (hour + 1) * 3600,
            "bag_count": int(hourly_counts.get(hour, 0)),
            "share": hourly_counts.get(hour, 0) / EXPECTED_BAGS,
        }
        for hour in range(24)
    ]
    _require(sum(row["bag_count"] for row in hourly_profile) == EXPECTED_BAGS, "")

    loader_counts = Counter(str(row["loader"]) for row in raw_rows)
    unloader_counts = Counter(str(row["unloader"]) for row in raw_rows)
    source_node_counts = Counter(int(row["start"]) for row in raw_rows)
    goal_node_counts = Counter(int(row["goal"]) for row in raw_rows)
    loader_unloader_counts = Counter(
        f"{row['loader']}->{row['unloader']}" for row in raw_rows
    )
    node_od_counts = Counter(
        f"{row['start']}->{row['goal']}" for row in raw_rows
    )
    expected_loader_counts = {
        "A1": 1176,
        "B1": 2872,
        "B2": 5544,
        "C1": 4533,
        "C2": 7542,
        "D1": 2585,
        "T": 4254,
    }
    _require(
        _counter_dict(loader_counts) == expected_loader_counts,
        "raw loader totals do not reproduce the paper-extracted station totals",
    )

    shortest_length, shortest_time, shortest_hops = _shortest_tables(map_data)
    segment_lengths: list[float] = []
    segment_times: list[float] = []
    segment_hops: list[float] = []
    bag_lengths: dict[int, float] = defaultdict(float)
    bag_times: dict[int, float] = defaultdict(float)
    bag_hops: dict[int, float] = defaultdict(float)
    unreachable_segments: list[str] = []
    for row in processed_rows:
        pair = (int(row["start"]), int(row["goal"]))
        segment_id = str(row["segment_id"])
        if (
            pair not in shortest_length
            or pair not in shortest_time
            or pair not in shortest_hops
        ):
            unreachable_segments.append(segment_id)
            continue
        length = shortest_length[pair]
        travel_time = shortest_time[pair]
        hops = shortest_hops[pair]
        segment_lengths.append(length)
        segment_times.append(travel_time)
        segment_hops.append(hops)
        task_id = int(row["task_id"])
        bag_lengths[task_id] += length
        bag_times[task_id] += travel_time
        bag_hops[task_id] += hops
    _require(not unreachable_segments, "processed segment has no directed map path")
    _require(len(bag_lengths) == EXPECTED_BAGS, "bag route lower bounds incomplete")

    observed = {
        "window_seconds": SIMULATION_WINDOW_SECONDS,
        "first_entry_time_seconds": min(entry_times),
        "last_entry_time_seconds": max(entry_times),
        "active_entry_span_seconds": max(entry_times) - min(entry_times),
        "average_bags_per_hour_over_24h": EXPECTED_BAGS / 24.0,
        "average_bags_per_second_over_24h": (
            EXPECTED_BAGS / SIMULATION_WINDOW_SECONDS
        ),
        "rolling_peaks": {
            "5_minutes": _rolling_peak(entry_times, 300),
            "15_minutes": _rolling_peak(entry_times, 900),
            "60_minutes": _rolling_peak(entry_times, 3600),
        },
        "hourly_profile": hourly_profile,
        "loader_station_counts": _counter_dict(loader_counts),
        "unloader_label_counts": _counter_dict(unloader_counts),
        "physical_source_node_counts": _counter_dict(source_node_counts),
        "physical_goal_node_counts": _counter_dict(goal_node_counts),
        "loader_to_unloader_mix": _counter_dict(loader_unloader_counts),
        "physical_node_od_mix": _counter_dict(node_od_counts),
        "deadline_lead_seconds": _distribution(deadline_leads),
        "planned_early_bag_ebs_dwell_seconds": _distribution(early_dwell),
        "static_directed_shortest_path_lower_bounds": {
            "scope": (
                "edge-only static lower bound; not a realized route, queueing "
                "time, conflict-free schedule, or runtime THT"
            ),
            "segment_length_map_units": _distribution(segment_lengths),
            "segment_travel_time_seconds": _distribution(segment_times),
            "segment_hops": _distribution(segment_hops),
            "bag_length_map_units": _distribution(list(bag_lengths.values())),
            "bag_travel_time_seconds": _distribution(list(bag_times.values())),
            "bag_hops": _distribution(list(bag_hops.values())),
            "unreachable_segment_count": len(unreachable_segments),
        },
    }

    official_2019_airports = {
        "Chengdu_Shuangliu": 55_858_552,
        "Chongqing_Jiangbei": 44_786_722,
    }
    conditional_examples = {
        airport: {
            "official_2019_whole_airport_passenger_movements": annual,
            "unsupported_example_assumptions": (
                "50% departures; all checked bags use the represented system; "
                "no terminal, transfer, subsystem, or parallel-system adjustment"
            ),
            "implied_bags_per_departing_passenger": (
                EXPECTED_BAGS / (annual / 365.0 * 0.5)
            ),
            "calibration_role": "NONE_CONTEXT_ONLY",
        }
        for airport, annual in official_2019_airports.items()
    }
    phase_j_evidence = _phase_j_evidence(root)

    return {
        "phase": "G4IRSF12-K",
        "published_date": PHASE_DATE,
        "hashes": actual_hashes,
        "source_bundle_members": source_bundle_members,
        "map": {
            "node_count": len(map_data["nodes"]),
            "directed_edge_count": len(map_data["edges"]),
            "edge_speed_meters_per_second": float(map_data["constants"]["edge_speed"]),
        },
        "raw_header": raw_header,
        "conversion": conversion,
        "observed": observed,
        "scope": {
            "paper_reported_region": (
                "an international-airport terminal case in southwest China"
            ),
            "airport_identity": "UNKNOWN_NOT_ESTABLISHED",
            "airport_candidates_investigated": ["Chengdu", "Chongqing"],
            "terminal_identity": "UNKNOWN_NOT_ESTABLISHED",
            "represented_bhs_subsystem": "UNKNOWN_NOT_ESTABLISHED",
            "departure_local_transfer_scope": "UNKNOWN_NOT_ESTABLISHED",
            "parallel_bhs_share": "UNKNOWN_NOT_ESTABLISHED",
            "day_type": "UNKNOWN_ORDINARY_DESIGN_OR_PEAK",
            "input_flight_coverage": "UNKNOWN_NOT_ESTABLISHED",
            "paper_reported_day_basis": "one day of flight schedule",
            "paper_reported_duration_hours": 24,
            "paper_reported_loading_stations": 7,
            "paper_reported_ebs_count": 1,
            "identity_conclusion": (
                "No primary evidence located ties the fixed case to Chengdu "
                "or Chongqing, a terminal, or a represented subsystem share."
            ),
            "conditional_passenger_examples": conditional_examples,
        },
        "calibration": {
            "final_multiplier_formula": (
                "represented_system_design_day_checked_bags / 28506"
            ),
            "represented_bags_component_formula": (
                "(annual_passenger_movements / 365) * design_day_factor * "
                "departing_passenger_share * terminal_allocation_share * "
                "(local_departure_share * local_checked_bags_per_departing_passenger "
                "+ transfer_departure_share * "
                "transfer_checked_bags_per_transfer_passenger) * "
                "represented_subsystem_share * (1 - parallel_diversion_share)"
            ),
            "composition_constraints": (
                "EBS/early-bag share and flight-bank profile calibrate demand "
                "composition and time shape; they are not arbitrary scalar factors."
            ),
            "required_unknown_inputs": {
                "annual_passenger_movements_for_case_period": None,
                "design_day_factor": None,
                "departing_passenger_share": None,
                "terminal_allocation_share": None,
                "local_departure_share": None,
                "transfer_departure_share": None,
                "local_checked_bags_per_departing_passenger": None,
                "transfer_checked_bags_per_transfer_passenger": None,
                "represented_subsystem_share": None,
                "parallel_diversion_share": None,
                "design_day_flight_bank_profile": None,
                "design_day_ebs_share": None,
            },
            "calibrated_multiplier": None,
            "calibrated_multiplier_status": "UNKNOWN_NOT_COMPUTABLE",
            "finite_uncertainty_interval": None,
            "uncertainty_status": "UNBOUNDED_MISSING_SCOPE_AND_DESIGN_DAY_INPUTS",
            "phase_k_status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
        },
        "capacity_measurement_contract": {
            "mapf_agent_density_role": (
                "AUXILIARY_ONLY; active agents per node/edge may diagnose a "
                "specific closed-loop run but cannot calibrate airport demand."
            ),
            "baseline_active_agent_density": None,
            "required_injection_metrics": [
                "bag injections per second and per 5/15/60-minute window",
                "injections per physical source and business loading station",
                "flight-bank/hour shares and deadline-lead composition",
            ],
            "required_capacity_metrics": [
                "critical directed-edge/corridor/merge busy-time utilization",
                "original-entry total-system-time p50/p95/p99/max",
                "Java-release network-time p50/p95/p99/max",
                "source wait and deadline-miss rate",
                "source backlog and in-network backlog reported separately",
                "post-peak backlog drain-to-zero time",
                "completed bags per hour and unresolved-deadlock count",
            ],
            "current_runtime_values": {
                "critical_utilization": None,
                "tail_latency": None,
                "deadline_miss_rate": None,
                "post_peak_backlog_clearance": None,
                "service_level": None,
            },
        },
        "phase_j_evidence": phase_j_evidence,
        "external_sources": list(EXTERNAL_SOURCES),
    }


def _candidate_rows(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scale_id, multiplier, classification in SCALE_CANDIDATES:
        target_bags = _round_half_up(Decimal(EXPECTED_BAGS) * multiplier)
        estimated_segments = _round_half_up(Decimal(EXPECTED_SEGMENTS) * multiplier)
        is_baseline = multiplier == Decimal("1.0")
        rows.append(
            {
                "scale_id": scale_id,
                "nominal_multiplier": str(multiplier),
                "classification": classification,
                "target_bag_count_arithmetic_only": target_bags,
                "estimated_segment_count_if_baseline_mix_preserved": estimated_segments,
                "calibration_status": (
                    "HISTORICAL_OBSERVED_DAY_REFERENCE"
                    if is_baseline
                    else "UNCALIBRATED_SENSITIVITY_ONLY"
                ),
                "calibrated_real_demand_claim": False,
                "historical_day_claim": is_baseline,
                "candidate_workload_materialized": False,
                "references_existing_immutable_input": is_baseline,
                "runtime_executed": False,
                "execution_authorized": False,
                "phase_l_status": "BLOCKED_NOT_RUN",
                "critical_utilization": None,
                "original_entry_tth_p95_seconds": None,
                "original_entry_tth_p99_seconds": None,
                "deadline_miss_rate": None,
                "peak_backlog": None,
                "post_peak_backlog_clearance_seconds": None,
                "unresolved_deadlock_count": None,
                "claim_boundary": (
                    "Count is deterministic arithmetic for a descriptor, not "
                    "a generated task file, airport forecast, or capacity result."
                ),
            }
        )
    return rows


def _phase_l_gates(evidence: Mapping[str, Any]) -> dict[str, Any]:
    phase_j = evidence["phase_j_evidence"]
    j_blockers = list(phase_j["blockers"])
    if not j_blockers and not phase_j["original_1x_full_formal_pass"]:
        j_blockers.append("Phase-J original-1x formal PASS is not established")
    return {
        "gate_rule": "all gates must be true simultaneously before any scale run",
        "original_1x_full_formal_pass": bool(
            phase_j["original_1x_full_formal_pass"]
        ),
        "original_entry_mean_meets_historical_hca_target": bool(
            phase_j["original_entry_performance_pass"]
        ),
        "numeric_real_demand_calibration_complete": False,
        "original_task_generation_audit_pass": True,
        "traceable_1p1_workload_artifact_exists": False,
        "protected_map_identity_matches": (
            evidence["hashes"]["map_raw_sha256"] == MAP_RAW_SHA256
            and evidence["hashes"]["map_semantic_sha256"] == MAP_SEMANTIC_SHA256
        ),
        "all_gates_pass": False,
        "status": "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "blockers": [
            *j_blockers,
            "Airport/terminal/subsystem and design-day demand inputs are unknown.",
            "The 1.1 descriptor is not a materialized, traceable workload.",
        ],
    }


def build_protocol_config(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "czr005.g4irsf12.demand_calibration_protocol.v1",
        "phase": "G4IRSF12-K",
        "published_date": PHASE_DATE,
        "purpose": (
            "Reproduce historical-day demand evidence and fail closed on "
            "real-demand scaling until scope/design-day inputs are established."
        ),
        "protected_identity": {
            "map_path": MAP_PATH.as_posix(),
            "map_raw_sha256": MAP_RAW_SHA256,
            "map_semantic_sha256": MAP_SEMANTIC_SHA256,
            "processed_input_path": PROCESSED_INPUT_PATH.as_posix(),
            "processed_input_raw_sha256": PROCESSED_INPUT_RAW_SHA256,
            "processed_input_semantic_sha256": PROCESSED_INPUT_SEMANTIC_SHA256,
            "raw_input_path": RAW_INPUT_PATH.as_posix(),
            "raw_input_sha256": RAW_INPUT_SHA256,
            "java_main_path": JAVA_MAIN_PATH.as_posix(),
            "java_main_sha256": JAVA_MAIN_SHA256,
            "java_tasks_path": JAVA_TASKS_PATH.as_posix(),
            "java_tasks_sha256": JAVA_TASKS_SHA256,
            "source_bundle_sha256": evidence["hashes"]["source_bundle_sha256"],
        },
        "baseline": {
            "bag_count": EXPECTED_BAGS,
            "segment_count": EXPECTED_SEGMENTS,
            "duration_seconds": SIMULATION_WINDOW_SECONDS,
            "early_threshold_seconds": EARLY_THRESHOLD_SECONDS,
            "ebs_release_lead_seconds": EBS_RELEASE_LEAD_SECONDS,
            "quantile_method": (
                "R-7 linear interpolation at (n-1)*p after ascending sort"
            ),
            "rolling_window_definition": (
                "[observed_entry_time, observed_entry_time + window)"
            ),
        },
        "calibration": evidence["calibration"],
        "candidate_scales": [
            {
                "scale_id": scale_id,
                "nominal_multiplier": str(multiplier),
                "classification": classification,
            }
            for scale_id, multiplier, classification in SCALE_CANDIDATES
        ],
        "future_generation_protocol": {
            "current_state": "DESCRIPTOR_ONLY_NOT_EXECUTED",
            "fixed_seed": RESAMPLE_SEED,
            "time_compression": False,
            "preserve_original_24h_clock_profile": True,
            "retain_each_baseline_bag_once": True,
            "additional_bag_selection": (
                "deterministic stratified resampling with largest-remainder "
                "integer allocation and SHA-256 ordering within strata"
            ),
            "stratification_fields": [
                "clock_hour",
                "loader_label",
                "unloader_label",
                "original_start",
                "original_goal",
                "early_split",
                "deadline_lead_bin",
            ],
            "new_ids_required": True,
            "java_split_rules_reapplied": True,
            "allowed_label_if_materialized_and_audited": (
                "original_rule_replay_scaled_input"
            ),
            "forbidden_label": "original_project_generated",
            "required_drift_audits": [
                "hourly/5-minute/15-minute/60-minute arrival shape",
                "loading-station, unloader, source-node, goal-node, and OD shares",
                "early-split share and EBS planned-dwell distribution",
                "deadline-lead distribution",
                "static directed route-lower-bound distribution",
            ],
            "drift_threshold_policy": (
                "Thresholds must be declared before materialization and remain "
                "engineering tolerances, not evidence of real-world demand."
            ),
        },
        "capacity_measurement_contract": evidence["capacity_measurement_contract"],
        "phase_j_evidence": evidence["phase_j_evidence"],
        "phase_l_gates": _phase_l_gates(evidence),
        "execution_policy": "DESCRIPTORS_ONLY_NO_SCALING_RUN",
        "external_sources": evidence["external_sources"],
    }


def build_candidate_manifest(
    evidence: Mapping[str, Any],
    row: Mapping[str, Any],
) -> dict[str, Any]:
    is_baseline = bool(row["historical_day_claim"])
    return {
        "schema": "czr005.g4irsf12.demand_candidate_manifest.v1",
        "phase": "G4IRSF12-K",
        "published_date": PHASE_DATE,
        "descriptor_kind": (
            "historical_baseline_reference"
            if is_baseline
            else "unmaterialized_scale_candidate"
        ),
        "scale_id": row["scale_id"],
        "nominal_multiplier": row["nominal_multiplier"],
        "classification": row["classification"],
        "calibration_status": row["calibration_status"],
        "calibrated_real_demand_claim": False,
        "historical_observed_day_claim": is_baseline,
        "planning_counts": {
            "target_bag_count_arithmetic_only": row[
                "target_bag_count_arithmetic_only"
            ],
            "estimated_segment_count_if_baseline_mix_preserved": row[
                "estimated_segment_count_if_baseline_mix_preserved"
            ],
            "segment_estimate_is_artifact_truth": False,
        },
        "artifact_state": {
            "candidate_workload_materialized": False,
            "references_existing_immutable_input": is_baseline,
            "referenced_input_path": (
                PROCESSED_INPUT_PATH.as_posix() if is_baseline else None
            ),
            "task_output_path": None,
            "result_output_path": None,
            "runtime_executed": False,
            "execution_authorized": False,
            "workload_generation_level": "descriptor_only_not_generated",
        },
        "identity": {
            "map_raw_sha256": evidence["hashes"]["map_raw_sha256"],
            "map_semantic_sha256": evidence["hashes"]["map_semantic_sha256"],
            "processed_input_raw_sha256": evidence["hashes"][
                "processed_input_raw_sha256"
            ],
            "processed_input_semantic_sha256": evidence["hashes"][
                "processed_input_semantic_sha256"
            ],
            "raw_input_sha256": evidence["hashes"]["raw_input_sha256"],
            "implementation_sha256": evidence["hashes"]["implementation_sha256"],
            "source_bundle_sha256": evidence["hashes"]["source_bundle_sha256"],
            "resource_semantics_id": None,
            "scorer_id": None,
            "pibt_mode": None,
            "pressure_mode": None,
            "admission_mode": None,
            "tht_denominator": "original_entry_time_required_for_future_main_comparison",
        },
        "baseline_demand_descriptor": {
            "bags": EXPECTED_BAGS,
            "segments": EXPECTED_SEGMENTS,
            "hourly_profile": evidence["observed"]["hourly_profile"],
            "rolling_peaks": evidence["observed"]["rolling_peaks"],
            "loader_station_counts": evidence["observed"]["loader_station_counts"],
            "physical_source_node_counts": evidence["observed"][
                "physical_source_node_counts"
            ],
            "loader_to_unloader_mix": evidence["observed"][
                "loader_to_unloader_mix"
            ],
            "physical_node_od_mix": evidence["observed"]["physical_node_od_mix"],
            "deadline_lead_seconds": evidence["observed"]["deadline_lead_seconds"],
            "planned_early_bag_ebs_dwell_seconds": evidence["observed"][
                "planned_early_bag_ebs_dwell_seconds"
            ],
            "static_route_lower_bounds": evidence["observed"][
                "static_directed_shortest_path_lower_bounds"
            ],
        },
        "future_generation_protocol_ref": CONFIG_PATH.as_posix(),
        "allowed_label_if_later_materialized_and_audited": (
            "original_rule_replay_scaled_input"
        ),
        "forbidden_label": "original_project_generated",
        "runtime_metrics": {
            "critical_utilization": None,
            "original_entry_tth_p95_seconds": None,
            "original_entry_tth_p99_seconds": None,
            "deadline_miss_rate": None,
            "peak_source_backlog": None,
            "peak_network_backlog": None,
            "post_peak_backlog_clearance_seconds": None,
            "unresolved_deadlock_count": None,
        },
        "phase_l_gate_snapshot": _phase_l_gates(evidence),
        "claim_boundary": (
            "This is a non-executable descriptor. Its count is arithmetic only; "
            "it is not a generated task file, airport forecast, runtime result, "
            "or demonstrated capacity."
        ),
    }


def _calibration_input_rows(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    observed = evidence["observed"]
    conversion = evidence["conversion"]
    route = observed["static_directed_shortest_path_lower_bounds"]
    rows: list[dict[str, Any]] = []

    def add(
        section: str,
        field: str,
        status: str,
        value: Any,
        unit: str,
        source: str,
        evidence_or_formula: str,
        claim_boundary: str,
    ) -> None:
        rows.append(
            {
                "section": section,
                "field": field,
                "status": status,
                "value": value,
                "unit": unit,
                "source": source,
                "evidence_or_formula": evidence_or_formula,
                "claim_boundary": claim_boundary,
            }
        )

    add(
        "identity",
        "airport_identity",
        "UNKNOWN_NOT_ESTABLISHED",
        None,
        "",
        "paper protocol + official airport context search",
        "No source ties the map to Chengdu or Chongqing.",
        "Do not infer identity from southwest-China geography.",
    )
    add(
        "identity",
        "terminal_identity",
        "UNKNOWN_NOT_ESTABLISHED",
        None,
        "",
        "paper protocol",
        "No terminal identifier was extracted.",
        "Terminal allocation cannot be computed.",
    )
    add(
        "identity",
        "represented_bhs_subsystem_share",
        "UNKNOWN_NOT_ESTABLISHED",
        None,
        "share",
        "paper protocol",
        "No represented-system fraction or parallel-diversion rule was found.",
        "Whole-airport passenger totals cannot be mapped directly.",
    )
    add(
        "identity",
        "departure_transfer_scope",
        "UNKNOWN_NOT_ESTABLISHED",
        None,
        "",
        "paper protocol + raw input",
        "Loader/unloader labels do not establish local/transfer scope.",
        "No transfer-share assumption is inserted.",
    )
    add(
        "baseline",
        "historical_bag_count",
        "VALIDATED",
        conversion["raw_bag_count"],
        "bags/day",
        RAW_INPUT_PATH.as_posix(),
        "Raw data rows after header.",
        "Historical observed input only; not a design day.",
    )
    add(
        "baseline",
        "processed_segment_count",
        "VALIDATED",
        conversion["processed_segment_count"],
        "segments/day",
        PROCESSED_INPUT_PATH.as_posix(),
        "JSONL rows.",
        "Segments are not independent bags.",
    )
    add(
        "baseline",
        "segments_per_bag",
        "DERIVED",
        conversion["segments_per_bag"],
        "segments/bag",
        "raw + processed input",
        "43603 / 28506",
        "Composition descriptor, not capacity.",
    )
    add(
        "baseline",
        "early_split_share",
        "DERIVED_FROM_AUDITED_RULE",
        conversion["early_split_share"],
        "share",
        "Main.java + raw input",
        "count(STD-entry >= 4800) / 28506",
        "Historical EBS composition only.",
    )
    add(
        "arrival_rate",
        "average_bag_rate",
        "DERIVED",
        observed["average_bags_per_hour_over_24h"],
        "bags/hour",
        RAW_INPUT_PATH.as_posix(),
        "28506 / 24",
        "24-hour mean hides flight-bank peaks.",
    )
    for name, peak in observed["rolling_peaks"].items():
        add(
            "arrival_rate",
            f"rolling_peak_{name}",
            "DERIVED",
            peak["equivalent_bags_per_hour"],
            "equivalent bags/hour",
            RAW_INPUT_PATH.as_posix(),
            (
                f"{peak['bag_count']} bags in {peak['window_seconds']} seconds; "
                "[observed start, start+window)"
            ),
            "Injection demand, not completed throughput or capacity.",
        )
    add(
        "mix",
        "loader_station_counts",
        "VALIDATED",
        observed["loader_station_counts"],
        "bags/day by loader label",
        RAW_INPUT_PATH.as_posix(),
        "Raw Loader column; sums to 28506.",
        "Business station label differs from physical start node.",
    )
    add(
        "mix",
        "physical_source_node_counts",
        "VALIDATED",
        observed["physical_source_node_counts"],
        "bags/day by map node",
        RAW_INPUT_PATH.as_posix(),
        "Raw star column.",
        "Do not substitute for the seven paper loading-station totals.",
    )
    add(
        "mix",
        "loader_to_unloader_mix",
        "VALIDATED",
        observed["loader_to_unloader_mix"],
        "bags/day by OD label",
        RAW_INPUT_PATH.as_posix(),
        "Raw Loader and Unloader columns.",
        "Labels do not establish passenger transfer status.",
    )
    add(
        "deadline",
        "std_minus_original_entry",
        "DERIVED",
        observed["deadline_lead_seconds"],
        "seconds",
        RAW_INPUT_PATH.as_posix(),
        "STD - EntryTime(s), R-7 quantiles.",
        "Schedule lead, not realized slack at completion.",
    )
    add(
        "dwell",
        "planned_early_bag_ebs_dwell",
        "DERIVED_FROM_AUDITED_RULE",
        observed["planned_early_bag_ebs_dwell_seconds"],
        "seconds",
        "Main.java + raw input",
        "STD - 2700 - EntryTime(s) for early-split bags.",
        "Planned release interval, not measured physical EBS residence time.",
    )
    for metric in (
        "bag_length_map_units",
        "bag_travel_time_seconds",
        "bag_hops",
    ):
        add(
            "route_lower_bound",
            metric,
            "DERIVED_STATIC_DIRECTED",
            route[metric],
            (
                "map units"
                if "length" in metric
                else "seconds"
                if "time" in metric
                else "directed edges"
            ),
            MAP_PATH.as_posix(),
            "Sum of per-segment directed shortest paths, R-7 quantiles.",
            "Lower bound only; not realized route or runtime THT.",
        )

    unknown_fields = evidence["calibration"]["required_unknown_inputs"]
    for field in unknown_fields:
        add(
            "real_demand_formula_input",
            field,
            "UNKNOWN_REQUIRED",
            None,
            "share/rate/profile as applicable",
            "not established",
            evidence["calibration"]["represented_bags_component_formula"],
            "Unknown remains null; no midpoint or convenient default is used.",
        )
    add(
        "result",
        "calibrated_multiplier",
        "UNKNOWN_NOT_COMPUTABLE",
        None,
        "x",
        "fail-closed formula",
        evidence["calibration"]["final_multiplier_formula"],
        "Candidate multipliers are sensitivities, not calibrated demand.",
    )
    add(
        "capacity",
        "mapf_active_agent_density",
        "UNKNOWN_AUXILIARY_ONLY",
        None,
        "active agents per node/edge",
        "future closed-loop runtime",
        "Requires time-varying active-agent state.",
        "Not an airport-demand or capacity calibration.",
    )
    for field in (
        "critical_utilization",
        "tail_latency",
        "deadline_miss_rate",
        "post_peak_backlog_clearance",
        "service_level",
    ):
        add(
            "capacity",
            field,
            "UNKNOWN_NOT_RUN",
            None,
            "",
            "future gated runtime",
            "Must be measured with explicit injection and backlog accounting.",
            "No value is inferred from a descriptor.",
        )
    return rows


def _markdown_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    rendered = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    rendered.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(rendered)


def _format_distribution(value: Mapping[str, Any]) -> str:
    return (
        f"mean={value['mean']:.3f}, p50={value['p50']:.3f}, "
        f"p95={value['p95']:.3f}, p99={value['p99']:.3f}, "
        f"min={value['min']:.3f}, max={value['max']:.3f}"
    )


def build_airport_report(
    evidence: Mapping[str, Any], candidate_rows: Sequence[Mapping[str, Any]]
) -> str:
    observed = evidence["observed"]
    conversion = evidence["conversion"]
    route = observed["static_directed_shortest_path_lower_bounds"]
    phase_j = evidence["phase_j_evidence"]
    hourly_rows = [
        (row["clock_hour"], row["bag_count"], f"{100 * row['share']:.3f}%")
        for row in observed["hourly_profile"]
        if row["bag_count"]
    ]
    peak_rows = [
        (
            name,
            peak["bag_count"],
            f"{peak['equivalent_bags_per_hour']:.3f}",
            f"{peak['start_time_seconds']:.6f}",
        )
        for name, peak in observed["rolling_peaks"].items()
    ]
    scale_rows = [
        (
            row["nominal_multiplier"],
            row["classification"],
            row["target_bag_count_arithmetic_only"],
            row["calibration_status"],
            row["phase_l_status"],
        )
        for row in candidate_rows
    ]
    loader_rows = [
        (loader, count)
        for loader, count in observed["loader_station_counts"].items()
    ]
    source_rows = [
        (node, count)
        for node, count in observed["physical_source_node_counts"].items()
    ]
    source_links = {item["source_id"]: item["url"] for item in EXTERNAL_SOURCES}

    lines = [
        "# G4IRSF12-K Airport Scope and Demand Calibration",
        "",
        f"Date: {PHASE_DATE}",
        "",
        "status: `PARTIAL_WITH_EXPLICIT_BLOCKER`",
        "calibrated_multiplier: `UNKNOWN_NOT_COMPUTABLE`",
        "finite_uncertainty_interval: `UNBOUNDED_MISSING_SCOPE_AND_DESIGN_DAY_INPUTS`",
        "phase_l_status: `BLOCKED_NOT_RUN`",
        f"phase_j_v4_ledger_status: `{phase_j['verification_status']}`",
        "",
        "## Decision",
        "",
        (
            "The immutable input is a validated 28,506-bag historical clock-day "
            "with a strong banked arrival profile. It is not proven to be an "
            "ordinary day, design day, or peak day. No primary evidence located "
            "identifies Chengdu versus Chongqing, the terminal, the local/transfer "
            "scope, the represented BHS fraction, or parallel-system diversion. "
            "The only defensible numeric multiplier is therefore **not yet "
            "computable**."
        ),
        "",
        (
            "The 1.1/1.2/1.3/1.5/2.0 entries published here are non-executable "
            "sensitivity descriptors. They are not airport forecasts, task "
            "artifacts, runtime results, or demonstrated capacity."
        ),
        "",
        "## What the historical input establishes",
        "",
        _markdown_table(
            ["Measure", "Validated value", "Boundary"],
            [
                ("Raw bags", f"{conversion['raw_bag_count']:,}", "bag denominator"),
                (
                    "Processed segments",
                    f"{conversion['processed_segment_count']:,}",
                    "split legs; not bags",
                ),
                (
                    "Segments per bag",
                    f"{conversion['segments_per_bag']:.6f}",
                    "composition only",
                ),
                (
                    "Early/EBS-split bags",
                    f"{conversion['early_split_bag_count']:,} "
                    f"({100 * conversion['early_split_share']:.3f}%)",
                    "Java rule: STD-entry >= 4,800 s",
                ),
                (
                    "Direct bags",
                    f"{conversion['direct_bag_count']:,}",
                    "Java rule: STD-entry < 4,800 s",
                ),
                (
                    "24-hour mean injection",
                    f"{observed['average_bags_per_hour_over_24h']:.3f} bags/h",
                    "not system throughput",
                ),
                (
                    "First / last entry",
                    f"{observed['first_entry_time_seconds']:.6f} / "
                    f"{observed['last_entry_time_seconds']:.6f} s",
                    "clock-day input",
                ),
            ],
        ),
        "",
        "The seven business loading-station labels exactly reproduce the paper-extracted totals:",
        "",
        _markdown_table(["Loader label", "Bags"], loader_rows),
        "",
        (
            "The physical source-node totals differ because several business "
            "stations are distributed over multiple map entry nodes:"
        ),
        "",
        _markdown_table(["Physical source node", "Bags"], source_rows),
        "",
        "This distinction is retained in every future drift audit.",
        "",
        "## Time-of-day intensity",
        "",
        _markdown_table(
            ["Window", "Maximum bags", "Equivalent bags/hour", "Window start (s)"],
            peak_rows,
        ),
        "",
        (
            "Rolling windows are half-open `[observed entry, observed entry + "
            "window)`. They measure offered injection demand, not departures or "
            "completed throughput."
        ),
        "",
        _markdown_table(["Clock hour", "Bags", "Daily share"], hourly_rows),
        "",
        "## Deadline, EBS, and route-length composition",
        "",
        (
            "- `STD - original_entry_time`: "
            + _format_distribution(observed["deadline_lead_seconds"])
            + " seconds."
        ),
        (
            "- Planned early-bag interval before Java storage-out release "
            "(`STD - 2700 - entry`): "
            + _format_distribution(observed["planned_early_bag_ebs_dwell_seconds"])
            + " seconds."
        ),
        (
            "- Bag-level directed shortest-path length lower bound: "
            + _format_distribution(route["bag_length_map_units"])
            + " map units."
        ),
        (
            "- Bag-level directed edge-travel-time lower bound: "
            + _format_distribution(route["bag_travel_time_seconds"])
            + " seconds."
        ),
        (
            "- Bag-level directed hop lower bound: "
            + _format_distribution(route["bag_hops"])
            + " edges."
        ),
        "",
        (
            "Route values are edge-only static lower bounds summed across a bag's "
            "one or two segments. They are not realized routes, conflict-free "
            "schedules, queueing times, or THT."
        ),
        "",
        "## Airport-scope investigation and claim boundary",
        "",
        (
            "The local thesis evidence reports a real international-airport "
            "terminal case in southwest China, 24 hours, seven loading stations, "
            "one EBS, and 28,506 bags. It does not name the airport or terminal. "
            "The fixed topology and demand fields do not distinguish Chengdu from "
            "Chongqing."
        ),
        "",
        (
            "CAAC's official 2019 table reports whole-airport passenger movements "
            "of 55,858,552 for Chengdu Shuangliu and 44,786,722 for Chongqing "
            f"Jiangbei ([CAAC source]({source_links['caac_2019_airport_statistics']})). "
            "Those totals are context only: passenger movements include arrivals "
            "and departures and say nothing about terminal allocation, checked-bag "
            "propensity, transfer flows, the represented subsystem, or parallel "
            "BHS diversion."
        ),
        "",
        _markdown_table(
            ["Candidate context", "Unsupported illustration", "Calibration role"],
            [
                (
                    "Chengdu Shuangliu 2019",
                    "0.37254 bags/departing passenger if 50% departures and "
                    "100% system share",
                    "NONE",
                ),
                (
                    "Chongqing Jiangbei 2019",
                    "0.46463 bags/departing passenger under the same unsupported "
                    "assumptions",
                    "NONE",
                ),
            ],
        ),
        "",
        (
            "These two ratios are counterexamples to direct annual-throughput "
            "mapping, not estimates. Neither assumption set is admitted into the "
            "calibration."
        ),
        "",
        "## Fail-closed multiplier",
        "",
        "`multiplier = represented-system design-day checked bags / 28,506`",
        "",
        (
            "The represented-system numerator requires case-period annual "
            "passengers, design-day factor, departure share, terminal allocation, "
            "local/transfer shares and checked-bag rates, represented-subsystem "
            "share, and parallel diversion. The design-day EBS share and "
            "flight-bank profile constrain composition and time shape. All remain "
            "null unless supported by case-specific evidence."
        ),
        "",
        (
            "ACRP's official design-day guidance uses flight-by-flight schedules "
            "and airport-specific time-of-day/facility profiles "
            f"([ACRP Research Report 163]({source_links['acrp_report_163']})). "
            "IATA's official planning material likewise treats peak forecasting, "
            "design-day schedules, demand-capacity calculations, BHS, and "
            "bottleneck subsystems explicitly "
            f"([ADRM]({source_links['iata_adrm']}), "
            f"[Demand Triggers]({source_links['iata_demand_triggers']}))."
        ),
        "",
        "## Provisional sensitivity descriptors",
        "",
        _markdown_table(
            [
                "Nominal x",
                "Label",
                "Arithmetic bag count",
                "Calibration",
                "Execution",
            ],
            scale_rows,
        ),
        "",
        (
            "Neither 1.2x nor 1.3x is asserted to be a standard design-day "
            "factor or a realistic peak. They are provisional sensitivities "
            "between mild growth and engineering reserve. All descriptor counts use "
            "decimal `ROUND_HALF_UP`; no workload was generated."
        ),
        "",
        "## Capacity protocol",
        "",
        (
            "A future capacity frontier must report offered injections at "
            "5/15/60-minute and source/loader resolution, critical "
            "edge/corridor/merge busy-time utilization, original-entry p95/p99 "
            "tails, deadline misses, separate source and in-network backlog, "
            "post-peak drain-to-zero time, service level, and unresolved "
            "deadlocks. A run is not stable merely because it terminates."
        ),
        "",
        (
            "MAPF/MAPD literature is useful only for auxiliary diagnostics here. "
            "MAPD models online task arrivals "
            f"([AAMAS 2017]({source_links['mapd_aamas_2017']})); lifelong MAPF "
            "defines time-based throughput and reports map-specific density "
            f"effects ([AAAI 2021]({source_links['lifelong_mapf_aaai_2021']})). "
            "Therefore active agents per node may characterize a particular "
            "closed-loop run, but cannot replace airport demand calibration."
        ),
        "",
        "## Phase-L gate",
        "",
        (
            "`BLOCKED_NOT_RUN`: Phase-J is checked by reconstructing its v4 "
            "candidate bundle from the admitted original-scale ledger. Its status is "
            f"`{phase_j['verification_status']}`; the numeric demand multiplier is unknown; and the "
            "1.1 manifest is a descriptor rather than a materialized traceable "
            "workload. The protected map identity does pass."
        ),
        "",
        "No scale runtime was started.",
    ]
    return "\n".join(lines) + "\n"


def build_generation_audit(evidence: Mapping[str, Any]) -> str:
    conversion = evidence["conversion"]
    observed = evidence["observed"]
    lines = [
        "# G4IRSF12-K Original Task Generation Audit",
        "",
        f"Date: {PHASE_DATE}",
        "",
        "status: `PASS_WITH_NEGATIVE_GENERATOR_FINDING`",
        "scaled_workload_generated: `false`",
        "runtime_executed: `false`",
        "",
        "## Finding",
        "",
        (
            "The immutable raw input and processed JSONL exactly reproduce the "
            "active Java loader/split rules for all 28,506 bag IDs and 43,603 "
            "segments. The original project does **not** contain an active "
            "larger-day demand generator: the random initial-task and random-OD "
            "code is commented out, while active code consumes static source "
            "queues loaded from `inputdata.txt`."
        ),
        "",
        (
            "Accordingly, no future scaled input may be called "
            "`original_project_generated`. If the gated deterministic protocol "
            "is later implemented and passes its audits, the strongest allowed "
            "label is `original_rule_replay_scaled_input`."
        ),
        "",
        "## Immutable identity",
        "",
        _markdown_table(
            ["Artifact", "SHA-256", "Status"],
            [
                (
                    RAW_INPUT_PATH.as_posix(),
                    evidence["hashes"]["raw_input_sha256"],
                    "MATCH",
                ),
                (
                    PROCESSED_INPUT_PATH.as_posix(),
                    evidence["hashes"]["processed_input_raw_sha256"],
                    "MATCH",
                ),
                (
                    JAVA_MAIN_PATH.as_posix(),
                    evidence["hashes"]["java_main_sha256"],
                    "MATCH",
                ),
                (
                    JAVA_TASKS_PATH.as_posix(),
                    evidence["hashes"]["java_tasks_sha256"],
                    "MATCH",
                ),
                (
                    MAP_PATH.as_posix(),
                    evidence["hashes"]["map_raw_sha256"],
                    "MATCH",
                ),
            ],
        ),
        "",
        "## Raw schema and audited transformation",
        "",
        f"Raw header: `{evidence['raw_header']}`",
        "",
        _markdown_table(
            ["Condition", "Processed segment rule", "Validated count"],
            [
                (
                    "`STD - EntryTime < 4800`",
                    "one direct segment: raw start -> raw goal at EntryTime",
                    f"{conversion['direct_bag_count']:,} bags",
                ),
                (
                    "`STD - EntryTime >= 4800`",
                    "storage_in: raw start -> 47 at EntryTime",
                    f"{conversion['early_split_bag_count']:,} bags",
                ),
                (
                    "same early bag",
                    "storage_out: 52 -> raw goal at STD - 2700",
                    f"{conversion['early_split_bag_count']:,} bags",
                ),
            ],
        ),
        "",
        (
            "Both segments keep the original integer `task_id`/`pallet_id`; "
            "`segment_id` adds `direct`, `storage_in`, or `storage_out`. Therefore "
            "bag-level metrics must group by original task ID, not treat 43,603 "
            "segments as independent bags."
        ),
        "",
        "The conversion was checked row-for-row, including source line, original and processed start/goal, EntryTime, STD, pass time, leg, and segment ID.",
        "",
        "## Business labels, physical nodes, and OD",
        "",
        (
            "The raw `Loader` labels preserve the seven paper totals: "
            f"`{json.dumps(observed['loader_station_counts'], sort_keys=True)}`. "
            "The raw `star` field instead yields physical source nodes: "
            f"`{json.dumps(observed['physical_source_node_counts'], sort_keys=True)}`."
        ),
        "",
        (
            "The raw `Unloader` label has five values, while the raw goal field "
            "uses map nodes 48/49/50. Both label-level and node-level OD mixes "
            "must be audited because the processed JSONL does not retain the "
            "`Loader`/`Unloader` text columns."
        ),
        "",
        "## Active Java release behavior",
        "",
        (
            "1. `Main.ReadTaskList` loads `inputdata.txt`, applies the 4,800 s "
            "early rule, and adds split storage-out work at node 52 with "
            "`pass_time = STD - 2700`."
        ),
        (
            "2. Each per-source list is sorted by `pass_time`; the main loop "
            "starts at epoch 8,260 and advances in one-second steps."
        ),
        (
            "3. `Tasks.generate_tasks` considers only the queue head. A source "
            "must have no unfinished task from that source, and the head is "
            "eligible when `pass_time - epoch < 1`. At most one head is removed "
            "from a source during an epoch."
        ),
        (
            "4. The emitted runtime task keeps the source bag ID and goal. The "
            "nearby code that would choose a random goal is commented out."
        ),
        (
            "5. Fault and repair events are runtime probability draws over map "
            "edges; they are not demand records in `inputdata.txt`. The delay "
            "draw block is also commented out. A demand scaler must not invent "
            "fault/repair/pass-time values."
        ),
        "",
        "## Negative generator finding",
        "",
        (
            "No active code derives a new flight schedule, loader/unloader mix, "
            "EntryTime, STD, local/transfer split, or larger design day. Existing "
            "G4IRSF2 high-flow data was correctly labeled "
            "`distribution_preserving_resample`; it is not evidence of an "
            "original Java demand generator and is not used to calibrate this "
            "multiplier."
        ),
        "",
        "## Future protocol, not executed",
        "",
        (
            "After every Phase-L gate passes, retain each baseline bag once, "
            "allocate only the additional bags across fixed strata using largest "
            "remainders, and select donors by SHA-256 order with seed 20260723. "
            "Strata include clock hour, Loader, Unloader, physical start/goal, "
            "early-split state, and deadline-lead bin. Assign new IDs and reapply "
            "the exact Java split rules without time compression."
        ),
        "",
        (
            "Before any run, audit hourly and rolling-window arrival shape, "
            "business and physical OD shares, early/EBS share and dwell, deadline "
            "lead, and static directed route lower bounds. Drift tolerances must "
            "be fixed before materialization and cannot turn a sensitivity into "
            "a real-demand claim."
        ),
        "",
        "Current execution policy: `DESCRIPTORS_ONLY_NO_SCALING_RUN`.",
    ]
    return "\n".join(lines) + "\n"


def render_bundle(evidence: Mapping[str, Any]) -> dict[Path, str]:
    candidate_rows = _candidate_rows(evidence)
    config = build_protocol_config(evidence)
    outputs: dict[Path, str] = {
        CONFIG_PATH: _json_text(config),
        CALIBRATION_INPUTS_PATH: _csv_text(
            _calibration_input_rows(evidence),
            (
                "section",
                "field",
                "status",
                "value",
                "unit",
                "source",
                "evidence_or_formula",
                "claim_boundary",
            ),
        ),
        SCALE_ENVELOPE_PATH: _csv_text(
            candidate_rows,
            (
                "scale_id",
                "nominal_multiplier",
                "classification",
                "target_bag_count_arithmetic_only",
                "estimated_segment_count_if_baseline_mix_preserved",
                "calibration_status",
                "calibrated_real_demand_claim",
                "historical_day_claim",
                "candidate_workload_materialized",
                "references_existing_immutable_input",
                "runtime_executed",
                "execution_authorized",
                "phase_l_status",
                "critical_utilization",
                "original_entry_tth_p95_seconds",
                "original_entry_tth_p99_seconds",
                "deadline_miss_rate",
                "peak_backlog",
                "post_peak_backlog_clearance_seconds",
                "unresolved_deadlock_count",
                "claim_boundary",
            ),
        ),
        AIRPORT_REPORT_PATH: build_airport_report(evidence, candidate_rows),
        GENERATION_AUDIT_PATH: build_generation_audit(evidence),
    }
    for row in candidate_rows:
        scale_id = str(row["scale_id"])
        kind = "baseline" if scale_id == "1p0" else "candidate"
        outputs[
            MANIFEST_DIR / f"demand_{scale_id}_{kind}_manifest.json"
        ] = _json_text(build_candidate_manifest(evidence, row))
    return outputs


def write_bundle(root: Path, outputs: Mapping[Path, str]) -> None:
    for relative_path, content in outputs.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def check_bundle(root: Path, outputs: Mapping[Path, str]) -> None:
    errors: list[str] = []
    for relative_path, expected in outputs.items():
        path = root / relative_path
        if not path.exists():
            errors.append(f"missing {relative_path.as_posix()}")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            errors.append(f"stale {relative_path.as_posix()}")
    if errors:
        raise ValueError("; ".join(errors))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="publish deterministic Phase-K config, reports, tables, and manifests",
    )
    args = parser.parse_args(argv)
    evidence = collect_demand_evidence(ROOT)
    outputs = render_bundle(evidence)
    if args.write:
        write_bundle(ROOT, outputs)
        action = "published"
    else:
        check_bundle(ROOT, outputs)
        action = "validated"
    print(
        json.dumps(
            {
                "action": action,
                "phase_k_status": evidence["calibration"]["phase_k_status"],
                "calibrated_multiplier_status": evidence["calibration"][
                    "calibrated_multiplier_status"
                ],
                "phase_l_status": "BLOCKED_NOT_RUN",
                "bag_count": evidence["conversion"]["raw_bag_count"],
                "segment_count": evidence["conversion"]["processed_segment_count"],
                "output_count": len(outputs),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
