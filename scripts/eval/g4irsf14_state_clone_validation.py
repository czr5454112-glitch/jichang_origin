"""Independent, fail-closed validation for G4IRSF14 Stage 14E evidence.

The generator is deliberately not imported here.  This module validates the
six published Stage 14E artifacts from raw hashes, raw branch counters and raw
branch metrics, including content-addressed exact-binary native JSONL records.
Summary booleans are neither accepted nor used as evidence.

The validator does not attest that arbitrary bytes were produced by a trusted
machine.  It does make every accepted row content-addressed, binds it to the
canonical map/task and frozen G4IRSF13 inputs, rejects duplicate causal
opportunities, and recomputes all gates that can be established from the
published evidence.  The repository now has an exact-binary no-op
checkpoint/restore/rerun mechanism, and this validator can independently
recheck its raw three-way fidelity record.  That mechanism is necessary but is
not a causal label: the formal entry point remains blocked until every I1--I5
label has an exact-binary one-shot baseline/treatment rerun and the canonical
original-task campaign contains at least 2,000 complete labels with a non-zero
H_system cohort.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
from typing import Any, Iterable, Mapping, Sequence


SCHEMA = "czr005.g4irsf14.matched_runtime_state_clone.v2"
FIDELITY_SCHEMA = "czr005.g4irsf14.clone_fidelity.v2"
INTERVENTION_SCHEMA = "czr005.g4irsf14.causal_intervention.v3"
OUTCOME_SCHEMA = "czr005.g4irsf14.clone_outcome.v3"
LEDGER_SCHEMA = "czr005.g4irsf14.causal_component_ledger.v3"
MANIFEST_SCHEMA = "czr005.g4irsf14.clone_manifest.v3"
NATIVE_EVIDENCE_SCHEMA = (
    "czr005.g4irsf14.exact_binary_intervention_rerun.v1"
)
NATIVE_BRANCH_SCHEMA = "czr005.g4irsf14.exact_binary_branch.v1"
PROTOCOL_STATUS = (
    "NOOP_EXACT_BINARY_FIDELITY_AVAILABLE_"
    "FORMAL_CAUSAL_EVIDENCE_BLOCKED"
)
FORMAL_CAUSAL_BLOCKER = (
    "MISSING_EXACT_BINARY_I1_I5_ONE_SHOT_RERUN_AND_"
    "ORIGINAL_TASK_2000_H_SYSTEM_FORMAL_EVIDENCE"
)

MIN_MATCHED_INTERVENTIONS = 2_000
FORMAL_HORIZONS = {"H_bag", "H_system"}
SPLITS = {"train", "validation", "audit"}

REPORT_PATH = "outputs/reports/g4irsf14_matched_state_clone_report.md"
FIDELITY_PATH = "outputs/tables/g4irsf14_clone_fidelity.csv"
INTERVENTION_PATH = "outputs/tables/g4irsf14_causal_interventions.csv"
LEDGER_PATH = "outputs/tables/g4irsf14_causal_component_ledger.csv"
MANIFEST_PATH = "artifacts/datasets/g4irsf14_clone_manifest.json"
NATIVE_EVIDENCE_PATH = (
    "outputs/tables/g4irsf14_exact_binary_intervention_reruns.jsonl"
)

CANONICAL_MAP_PATH = "data/processed/maps/map2.json"
CANONICAL_MAP_RAW_SHA256 = (
    "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
)
CANONICAL_MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
CANONICAL_TASK_PATH = "data/processed/tasks/inputdata.jsonl"
CANONICAL_TASK_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
CANONICAL_SEGMENT_COUNT = 43_603
CANONICAL_RAW_BAG_COUNT = 28_506
FROZEN_G13_POLICY_PATH = "artifacts/policies/g4irsf13_f2_frozen_baseline.json"
FROZEN_G13_POLICY_FILE_SHA256 = (
    "9fdbb15c5446ac1dd693d0fdb1fdc87aba550e104706515f137859f2f3950054"
)
FROZEN_G13_MODEL_PATH = "artifacts/models/g4e_risk_calibrated_policy.json"
FROZEN_G13_MODEL_FILE_SHA256 = (
    "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
)
G13_PER_BAG_PATH = "outputs/tables/g4irsf13_per_bag_delta.csv"
G13_PER_BAG_FILE_SHA256 = (
    "fc3dde5aa958d23be4a186e0727702db6895980847d1473b21c5134d002ca551"
)
G13_DELAY_LEDGER_PATH = "outputs/tables/g4irsf13_delay_component_ledger.csv"
G13_DELAY_LEDGER_FILE_SHA256 = (
    "cd90509cdd134f4e1cc2653438e0ca61e0366f7ca0f166c40d79ab18fbdef847"
)

REQUIRED_FIDELITY_HASHES = (
    "complete_bags_sha256",
    "segment_result_sha256",
    "junction_state_sha256",
    "algorithm_summary_sha256",
    "deterministic_result_sha256",
)

# This inventory is intentionally exact.  A newly introduced mutable runtime
# field must change the schema and validator instead of silently escaping the
# clone boundary.
REQUIRED_STATE_COMPONENTS = (
    "event_queue_sha256",
    "current_time_sha256",
    "bags_sha256",
    "source_queues_sha256",
    "junction_queues_sha256",
    "local_service_calendars_sha256",
    "corridor_state_sha256",
    "scheduled_incoming_sha256",
    "credits_sha256",
    "merge_grants_sha256",
    "fault_state_sha256",
    "pibt_owner_state_sha256",
    "deterministic_counters_sha256",
    "scorer_state_sha256",
    "result_accumulator_sha256",
    "current_runtime_hashes_sha256",
    "congestion_beacons_sha256",
    "microphase_state_sha256",
)

INTERVENTION_ACTION_FIELD = {
    "I1_source_order_swap": "source_order",
    "I2_merge_request_order_swap": "merge_request_order",
    "I3_next_edge": "next_edge",
    "I4_hold_release": "release",
    "I5_pibt_trigger": "pibt_enabled",
}
INTERVENTION_BOUNDARY_KIND = {
    "I1_source_order_swap": "source_arbitration",
    "I2_merge_request_order_swap": "merge_grant_arbitration",
    "I3_next_edge": "junction_route_arbitration",
    "I4_hold_release": "hold_release_opportunity",
    "I5_pibt_trigger": "pibt_ready_slice",
}
INTERVENTION_ALLOWED_CHANGED_FIELDS = {
    "I1_source_order_swap": ("source_ready_order",),
    "I2_merge_request_order_swap": ("pending_merge_request_order",),
    "I3_next_edge": ("selected_next_node",),
    "I4_hold_release": ("release",),
    "I5_pibt_trigger": ("pibt_enabled",),
}
NATIVE_INTERVENTION_FIELDS = (
    "runtime_bag_id",
    "peer_runtime_bag_id",
    "merge_request_id",
    "peer_merge_request_id",
    "selected_next_node",
    "selected_boolean",
)

METRICS = (
    "affected_bag_completion_seconds",
    "local_group_delay_seconds",
    "system_mean_seconds",
    "system_p95_seconds",
    "system_p99_seconds",
    "source_wait_seconds",
    "network_wait_seconds",
    "path_length",
    "grant_wait_seconds",
    "deadline_miss_count",
)
DELTA_FIELDS = tuple(f"{name}_delta" for name in METRICS)

BRANCH_INVARIANTS = (
    "intervention_hit_count",
    "completed_affected_bag_count",
    "completed_horizon_entity_count",
    "unsafe_entry_count",
    "reservation_conflict_count",
    "runtime_full_astar_call_count",
    "runtime_global_scan_count",
    "runtime_future_route_read_count",
    "runtime_future_schedule_read_count",
    "teacher_input_count",
    "priority_teacher_input_count",
    "scorer_teacher_input_count",
    "full_future_routes_stored",
    "bag_future_path_field_present",
    "max_selected_edges_per_bag",
    "reservation_depth",
    "two_step_reservation_count",
    "failed_segment_count",
    "unresolved_deadlock_count",
    "event_limit_reached",
    "time_limit_reached",
    "merge_grant_conservation_holds",
    "merge_grant_active_bijection_holds",
    "merge_grant_runtime_owned_capability",
    "merge_grant_exact_slot_no_future_shift",
    "merge_grant_final_active_unconsumed",
    "merge_grant_outstanding_request_count",
    "merge_grant_stale_arbitration_count",
    "merge_grant_lifecycle_dropped_count",
    "merge_grant_lifecycle_complete",
    "merge_grant_active_state_integrity_pass",
    "merge_grant_protocol_integrity_pass",
    "stale_arbitration_event_count",
    "artificial_batch_delay_seconds",
)

BRANCH_BOOLEAN_INVARIANTS = {
    "bag_future_path_field_present",
    "event_limit_reached",
    "time_limit_reached",
    "merge_grant_conservation_holds",
    "merge_grant_active_bijection_holds",
    "merge_grant_runtime_owned_capability",
    "merge_grant_exact_slot_no_future_shift",
    "merge_grant_lifecycle_complete",
    "merge_grant_active_state_integrity_pass",
    "merge_grant_protocol_integrity_pass",
}
BRANCH_DECIMAL_INVARIANTS = {"artificial_batch_delay_seconds"}

PRIORITY_COHORTS = (
    "top_1_percent_delta_286",
    "no_divergence_representative",
    "early_band",
    "tight_slack",
    "storage_in",
    "storage_out",
    "goal_50",
    "hour_6",
    "source_0",
    "source_1",
    "source_2",
    "source_53",
    "node_52",
    "node_19_negative_control",
    "node_22_negative_control",
    "p2_involved",
    "high_merge_request_cardinality",
    "grant_wait_tail",
)

SAMPLING_FUNNEL_FIELDS = (
    "static_opportunity_count",
    "static_registry_sha256",
    "h_local_screened_count",
    "h_local_registry_sha256",
    "h_bag_completed_count",
    "h_bag_registry_sha256",
    "h_system_completed_count",
    "h_system_registry_sha256",
)

PIBT_SLICE_FIELDS = (
    "pibt_ready_bag_ids",
    "pibt_ready_current_nodes",
    "pibt_owner_resources",
    "pibt_owner_bag_ids",
    "pibt_candidate_bag_ids",
    "pibt_candidate_next_nodes",
    "pibt_candidate_edge_resources",
    "pibt_candidate_expected_fault_generations",
    "pibt_candidate_required_resource_offsets",
    "pibt_candidate_required_resources",
)

BOUNDARY_FIELDS = (
    "clone_group_id",
    "boundary_sha256",
    "decision_boundary_kind",
    "decision_time_bits",
    "decision_event_seq",
    "node",
    "runtime_bag_id",
    "baseline_next_node",
    "baseline_release",
    "baseline_pibt_enabled",
    "pibt_owner_runtime_bag_id",
    "source_ready_order",
    "pending_merge_request_order",
    "legal_next_edges",
    *PIBT_SLICE_FIELDS,
    "ready_set_sha256",
    "runtime_state_sha256",
    "state_components",
    "queue_top_not_popped",
    "staged_event_sink_empty",
    "runtime_global_scan_count",
    "runtime_future_route_read_count",
    "runtime_future_schedule_read_count",
    "reservation_depth",
    "max_selected_edges_per_bag",
)

NATIVE_RECORD_FIELDS = (
    "schema",
    "evidence_scope",
    "formal_pass_claimed",
    "actual_loaded_cpp_binary_path",
    "actual_loaded_cpp_binary_sha256",
    "inputs",
    "frozen_controls",
    "event_ordinal",
    "checkpoint",
    "intervention",
    "horizon",
    "priority_cohort_tags",
    "baseline",
    "treatment",
    "native_record_sha256",
)
NATIVE_INPUT_FIELDS = (
    "map_path",
    "map_raw_sha256",
    "map_semantic_sha256",
    "task_path",
    "task_sha256",
    "segment_count",
    "raw_bag_count",
    "demand_scale",
    "expanded_workload_used",
)
NATIVE_CHECKPOINT_FIELDS = (
    "boundary",
    "checkpoint_record_sha256",
)
NATIVE_INTERVENTION_RECORD_FIELDS = (
    "kind",
    "intervention_id",
    "intervention_token_sha256",
    "action",
    "allowed_changed_fields",
)
NATIVE_HORIZON_FIELDS = (
    "kind",
    "affected_bag_ids",
    "horizon_entity_ids",
    "horizon_entity_set_sha256",
)
NATIVE_BRANCH_FIELDS = (
    "start_state_sha256",
    "start_state_components",
    "terminal_state_sha256",
    "terminal_state_components",
    "branch_finalized",
    "completed_affected_bag_ids",
    "completed_horizon_entity_ids",
    "stop_reason",
    "replay_hashes",
    "invariants",
    "metrics",
    "branch_record_sha256",
)

FIDELITY_COLUMNS = (
    "schema",
    "fidelity_id",
    "clone_group_id",
    "boundary_sha256",
    "decision_boundary_kind",
    "decision_time_bits",
    "decision_event_seq",
    "node",
    "runtime_bag_id",
    "baseline_next_node",
    "baseline_release",
    "baseline_pibt_enabled",
    "pibt_owner_runtime_bag_id",
    "source_ready_order_json",
    "pending_merge_request_order_json",
    "legal_next_edges_json",
    *(f"{name}_json" for name in PIBT_SLICE_FIELDS),
    "ready_set_sha256",
    "runtime_state_sha256",
    "state_components_json",
    "queue_top_not_popped",
    "staged_event_sink_empty",
    "runtime_global_scan_count",
    "runtime_future_route_read_count",
    "runtime_future_schedule_read_count",
    "reservation_depth",
    "max_selected_edges_per_bag",
    "original_action_sha256",
    "clone_action_sha256",
    *(f"original_{name}" for name in REQUIRED_FIDELITY_HASHES),
    *(f"clone_{name}" for name in REQUIRED_FIDELITY_HASHES),
    "evidence_row_sha256",
)

INTERVENTION_COLUMNS = (
    "schema",
    "intervention_id",
    "clone_group_id",
    "intervention_token_sha256",
    "native_record_sha256",
    "boundary_sha256",
    "decision_boundary_kind",
    "decision_time_bits",
    "decision_event_seq",
    "node",
    "runtime_bag_id",
    "baseline_next_node",
    "baseline_release",
    "baseline_pibt_enabled",
    "pibt_owner_runtime_bag_id",
    "source_ready_order_json",
    "pending_merge_request_order_json",
    "legal_next_edges_json",
    *(f"{name}_json" for name in PIBT_SLICE_FIELDS),
    "ready_set_sha256",
    "runtime_state_sha256",
    "state_components_json",
    "queue_top_not_popped",
    "staged_event_sink_empty",
    "runtime_global_scan_count",
    "runtime_future_route_read_count",
    "runtime_future_schedule_read_count",
    "reservation_depth",
    "max_selected_edges_per_bag",
    "intervention_kind",
    "horizon",
    *(f"intervention_{name}" for name in NATIVE_INTERVENTION_FIELDS),
    "split",
    "raw_bag_ids_json",
    "raw_task_ids_json",
    "segment_ids_json",
    "horizon_entity_ids_json",
    "horizon_entity_set_sha256",
    "baseline_start_state_sha256",
    "treatment_start_state_sha256",
    "affected_bag_count",
    "required_horizon_completion_count",
    *(f"baseline_{name}" for name in BRANCH_INVARIANTS),
    *(f"treatment_{name}" for name in BRANCH_INVARIANTS),
    *(f"baseline_{name}" for name in METRICS),
    *(f"treatment_{name}" for name in METRICS),
    *DELTA_FIELDS,
    "baseline_outcome_sha256",
    "treatment_outcome_sha256",
    "evidence_row_sha256",
)

LEDGER_COLUMNS = (
    "schema",
    "intervention_kind",
    "complete_label_count",
    "h_bag_count",
    "h_system_count",
    "improving_count",
    "non_improving_count",
    *(field for metric in METRICS for field in (
        f"sum_{metric}_delta",
        f"mean_{metric}_delta",
    )),
)


class CloneValidationError(ValueError):
    """Raised when evidence cannot be accepted as a causal clone label."""


class CanonicalFields:
    """Exact Python implementation of the native v2 canonical wire format."""

    MAGIC = b"CZR005-CANONICAL-FIELDS\x02"

    def __init__(self) -> None:
        self._payload = bytearray(self.MAGIC)

    def _begin(self, name: str, tag: bytes) -> None:
        encoded = name.encode("utf-8")
        if len(encoded) > 0xFFFFFFFF:
            raise CloneValidationError("canonical field name is too long")
        self._payload.extend(struct.pack(">I", len(encoded)))
        self._payload.extend(encoded)
        self._payload.extend(tag)

    def string(self, name: str, value: str) -> None:
        encoded = value.encode("utf-8")
        self._begin(name, b"s")
        self._payload.extend(struct.pack(">Q", len(encoded)))
        self._payload.extend(encoded)

    def integer(self, name: str, value: int) -> None:
        if not -(1 << 63) <= value < (1 << 63):
            raise CloneValidationError(f"{name} is outside int64")
        self._begin(name, b"i")
        self._payload.extend(struct.pack(">q", value))

    def unsigned_integer(self, name: str, value: int) -> None:
        if not 0 <= value < (1 << 64):
            raise CloneValidationError(f"{name} is outside uint64")
        self._begin(name, b"u")
        self._payload.extend(struct.pack(">Q", value))

    def boolean(self, name: str, value: bool) -> None:
        if not isinstance(value, bool):
            raise CloneValidationError(f"{name} must be boolean")
        self._begin(name, b"b")
        self._payload.append(1 if value else 0)

    def floating(self, name: str, value: float) -> None:
        parsed = float(value)
        if parsed != parsed or parsed in {float("inf"), float("-inf")}:
            raise CloneValidationError(f"{name} must be finite")
        self._begin(name, b"d")
        self._payload.extend(struct.pack(">d", parsed))

    def integers(self, name: str, values: Sequence[int]) -> None:
        self._begin(name, b"I")
        self._payload.extend(struct.pack(">Q", len(values)))
        for value in values:
            if not isinstance(value, int) or isinstance(value, bool):
                raise CloneValidationError(f"{name} must contain integers")
            if not -(1 << 31) <= value < (1 << 31):
                raise CloneValidationError(f"{name} value is outside int32")
            self._payload.extend(
                struct.pack(">Q", value & 0xFFFFFFFFFFFFFFFF)
            )

    def unsigned_integers(self, name: str, values: Sequence[int]) -> None:
        self._begin(name, b"U")
        self._payload.extend(struct.pack(">Q", len(values)))
        for value in values:
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not 0 <= value < (1 << 64)
            ):
                raise CloneValidationError(f"{name} must contain uint64 values")
            self._payload.extend(struct.pack(">Q", value))

    def signed_integers(
        self,
        name: str,
        values: Sequence[int],
    ) -> None:
        self._begin(name, b"L")
        self._payload.extend(struct.pack(">Q", len(values)))
        for value in values:
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not -(1 << 63) <= value < (1 << 63)
            ):
                raise CloneValidationError(
                    f"{name} must contain int64 values"
                )
            self._payload.extend(
                struct.pack(">Q", value & 0xFFFFFFFFFFFFFFFF)
            )

    def payload(self) -> bytes:
        return bytes(self._payload)

    def sha256(self) -> str:
        return hashlib.sha256(self.payload()).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_text_sha256(path: Path) -> str:
    text = path.read_bytes().decode("utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise CloneValidationError("non-finite decimal")
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def canonical_mean(total: Decimal, count: int) -> str:
    if count <= 0:
        raise CloneValidationError("mean denominator must be positive")
    with localcontext() as context:
        context.prec = 50
        return canonical_decimal(total / Decimal(count))


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    )


def _require_sha256(label: str, value: object) -> str:
    if not _is_sha256(value):
        raise CloneValidationError(
            f"{label} must be a 64-character lower-case SHA-256"
        )
    return str(value)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: Iterable[str],
    label: str,
) -> None:
    expected_set = set(expected)
    missing = sorted(expected_set - set(value))
    extra = sorted(set(value) - expected_set)
    if missing or extra:
        raise CloneValidationError(
            f"{label} schema mismatch: missing={missing}, extra={extra}"
        )


def _require_string(label: str, value: object) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise CloneValidationError(f"{label} must be a non-empty canonical string")
    return value


def _require_int(
    label: str,
    value: object,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool):
        raise CloneValidationError(f"{label} must be an integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r"0|-?[1-9][0-9]*", value):
        parsed = int(value)
    else:
        raise CloneValidationError(f"{label} must be a canonical integer")
    if minimum is not None and parsed < minimum:
        raise CloneValidationError(f"{label} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise CloneValidationError(f"{label} must be <= {maximum}")
    return parsed


def _require_bool(label: str, value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value == "true":
        return True
    if value == "false":
        return False
    raise CloneValidationError(f"{label} must be true or false")


def _require_decimal(label: str, value: object) -> Decimal:
    if isinstance(value, bool):
        raise CloneValidationError(f"{label} must be numeric")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise CloneValidationError(f"{label} must be numeric") from error
    if not parsed.is_finite():
        raise CloneValidationError(f"{label} must be finite")
    if str(value) != canonical_decimal(parsed):
        raise CloneValidationError(
            f"{label} must use canonical decimal text"
        )
    return parsed


def _parse_canonical_json(label: str, value: object) -> Any:
    if not isinstance(value, str):
        raise CloneValidationError(f"{label} must be canonical JSON text")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise CloneValidationError(f"{label} is invalid JSON") from error
    if canonical_json(parsed) != value:
        raise CloneValidationError(f"{label} is not canonical JSON")
    return parsed


def _require_id_list(label: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise CloneValidationError(f"{label} must be a non-empty array")
    if any(
        not isinstance(item, str) or not item or item.strip() != item
        for item in value
    ):
        raise CloneValidationError(f"{label} must contain canonical strings")
    if value != sorted(set(value)):
        raise CloneValidationError(f"{label} must be sorted and duplicate-free")
    return tuple(value)


def canonical_state_component_sha256(
    state_components: Mapping[str, object],
) -> str:
    _require_exact_keys(
        state_components,
        REQUIRED_STATE_COMPONENTS,
        "runtime-state inventory",
    )
    fields = CanonicalFields()
    fields.string("schema", SCHEMA)
    for name in REQUIRED_STATE_COMPONENTS:
        value = _require_sha256(name, state_components[name])
        native_name = name.removesuffix("_sha256")
        fields.string(native_name, value)
    return fields.sha256()


def _require_int_array(
    label: str,
    value: object,
    *,
    unsigned: bool = False,
    bits: int | None = None,
    duplicate_free: bool = True,
) -> list[int]:
    if not isinstance(value, list):
        raise CloneValidationError(f"{label} must be an ordered array")
    width = bits if bits is not None else (64 if unsigned else 32)
    if width not in {32, 64}:
        raise AssertionError("integer arrays support only 32- or 64-bit widths")
    minimum = 0 if unsigned else -(1 << (width - 1))
    maximum = (1 << width) - 1 if unsigned else (1 << (width - 1)) - 1
    normalized = [
        _require_int(
            f"{label}[{index}]",
            item,
            minimum=minimum,
            maximum=maximum,
        )
        for index, item in enumerate(value)
    ]
    if duplicate_free and len(normalized) != len(set(normalized)):
        raise CloneValidationError(f"{label} must be duplicate-free")
    return normalized


def _time_from_bits(value: object) -> tuple[str, float]:
    if not isinstance(value, str) or re.fullmatch(
        r"[0-9a-f]{16}", value
    ) is None:
        raise CloneValidationError(
            "decision_time_bits must be a lower-case IEEE-754 bit pattern"
        )
    parsed = struct.unpack(">d", bytes.fromhex(value))[0]
    if parsed != parsed or parsed in {float("inf"), float("-inf")} or parsed < 0:
        raise CloneValidationError("decision time must be finite and non-negative")
    return value, parsed


def _append_pibt_slice_fields(
    fields: CanonicalFields,
    row: Mapping[str, object],
) -> None:
    fields.integers("pibt_ready_bag_ids", row["pibt_ready_bag_ids"])
    fields.integers(
        "pibt_ready_current_nodes", row["pibt_ready_current_nodes"]
    )
    fields.signed_integers(
        "pibt_owner_resources", row["pibt_owner_resources"]
    )
    fields.integers("pibt_owner_bag_ids", row["pibt_owner_bag_ids"])
    fields.integers(
        "pibt_candidate_bag_ids", row["pibt_candidate_bag_ids"]
    )
    fields.integers(
        "pibt_candidate_next_nodes", row["pibt_candidate_next_nodes"]
    )
    fields.signed_integers(
        "pibt_candidate_edge_resources",
        row["pibt_candidate_edge_resources"],
    )
    fields.unsigned_integers(
        "pibt_candidate_expected_fault_generations",
        row["pibt_candidate_expected_fault_generations"],
    )
    fields.unsigned_integers(
        "pibt_candidate_required_resource_offsets",
        row["pibt_candidate_required_resource_offsets"],
    )
    fields.signed_integers(
        "pibt_candidate_required_resources",
        row["pibt_candidate_required_resources"],
    )


def _native_boundary_payload(
    row: Mapping[str, object],
    *,
    include_clone_group_id: bool,
) -> bytes:
    fields = CanonicalFields()
    fields.string("schema", SCHEMA)
    if include_clone_group_id:
        fields.string("clone_group_id", str(row["clone_group_id"]))
    fields.string("kind", str(row["decision_boundary_kind"]))
    _, time_value = _time_from_bits(row["decision_time_bits"])
    fields.floating("time", time_value)
    fields.unsigned_integer("event_seq", int(row["decision_event_seq"]))
    fields.integer("node", int(row["node"]))
    fields.integer("runtime_bag_id", int(row["runtime_bag_id"]))
    fields.integer("baseline_next_node", int(row["baseline_next_node"]))
    fields.boolean("baseline_release", bool(row["baseline_release"]))
    fields.boolean(
        "baseline_pibt_enabled", bool(row["baseline_pibt_enabled"])
    )
    fields.integer(
        "pibt_owner_runtime_bag_id",
        int(row["pibt_owner_runtime_bag_id"]),
    )
    fields.integers("source_ready_order", row["source_ready_order"])
    fields.unsigned_integers(
        "pending_merge_request_order",
        row["pending_merge_request_order"],
    )
    fields.integers("legal_next_edges", row["legal_next_edges"])
    _append_pibt_slice_fields(fields, row)
    fields.string("runtime_state_sha256", str(row["runtime_state_sha256"]))
    fields.boolean("queue_top_not_popped", bool(row["queue_top_not_popped"]))
    fields.boolean(
        "staged_event_sink_empty", bool(row["staged_event_sink_empty"])
    )
    fields.integer(
        "runtime_global_scan_count", int(row["runtime_global_scan_count"])
    )
    fields.integer(
        "runtime_future_route_read_count",
        int(row["runtime_future_route_read_count"]),
    )
    fields.integer(
        "runtime_future_schedule_read_count",
        int(row["runtime_future_schedule_read_count"]),
    )
    fields.integer("reservation_depth", int(row["reservation_depth"]))
    fields.integer(
        "max_selected_edges_per_bag",
        int(row["max_selected_edges_per_bag"]),
    )
    return fields.payload()


def canonical_ready_set_sha256(row: Mapping[str, object]) -> str:
    fields = CanonicalFields()
    fields.string("schema", SCHEMA)
    fields.string("kind", str(row["decision_boundary_kind"]))
    fields.integer("node", int(row["node"]))
    fields.integers("source_ready_order", row["source_ready_order"])
    fields.unsigned_integers(
        "pending_merge_request_order",
        row["pending_merge_request_order"],
    )
    fields.integers("legal_next_edges", row["legal_next_edges"])
    _append_pibt_slice_fields(fields, row)
    return fields.sha256()


def expected_clone_group_id(row: Mapping[str, object]) -> str:
    fields = CanonicalFields()
    fields.string("schema", SCHEMA)
    fields.string(
        "runtime_state_sha256",
        _require_sha256(
            "runtime_state_sha256", row.get("runtime_state_sha256")
        ),
    )
    return fields.sha256()


def expected_boundary_sha256(row: Mapping[str, object]) -> str:
    return hashlib.sha256(
        _native_boundary_payload(row, include_clone_group_id=True)
    ).hexdigest()


def _validate_boundary(row: Mapping[str, object]) -> dict[str, object]:
    kind = _require_string(
        "decision_boundary_kind", row.get("decision_boundary_kind")
    )
    if kind not in set(INTERVENTION_BOUNDARY_KIND.values()):
        raise CloneValidationError(f"unknown decision boundary kind: {kind}")
    time_bits, _ = _time_from_bits(row.get("decision_time_bits"))
    event_seq = _require_int(
        "decision_event_seq", row.get("decision_event_seq"), minimum=1
    )
    node = _require_int("node", row.get("node"), minimum=0)
    runtime_bag_id = _require_int("runtime_bag_id", row.get("runtime_bag_id"))
    baseline_next_node = _require_int(
        "baseline_next_node", row.get("baseline_next_node")
    )
    baseline_release = _require_bool(
        "baseline_release", row.get("baseline_release")
    )
    baseline_pibt = _require_bool(
        "baseline_pibt_enabled", row.get("baseline_pibt_enabled")
    )
    pibt_owner = _require_int(
        "pibt_owner_runtime_bag_id",
        row.get("pibt_owner_runtime_bag_id"),
    )
    source_ready = _require_int_array(
        "source_ready_order", row.get("source_ready_order")
    )
    pending_merge = _require_int_array(
        "pending_merge_request_order",
        row.get("pending_merge_request_order"),
        unsigned=True,
    )
    legal_edges = _require_int_array(
        "legal_next_edges", row.get("legal_next_edges")
    )
    pibt_ready_bag_ids = _require_int_array(
        "pibt_ready_bag_ids", row.get("pibt_ready_bag_ids")
    )
    pibt_ready_current_nodes = _require_int_array(
        "pibt_ready_current_nodes",
        row.get("pibt_ready_current_nodes"),
        duplicate_free=False,
    )
    pibt_owner_resources = _require_int_array(
        "pibt_owner_resources",
        row.get("pibt_owner_resources"),
        bits=64,
    )
    pibt_owner_bag_ids = _require_int_array(
        "pibt_owner_bag_ids",
        row.get("pibt_owner_bag_ids"),
        duplicate_free=False,
    )
    pibt_candidate_bag_ids = _require_int_array(
        "pibt_candidate_bag_ids",
        row.get("pibt_candidate_bag_ids"),
        duplicate_free=False,
    )
    pibt_candidate_next_nodes = _require_int_array(
        "pibt_candidate_next_nodes",
        row.get("pibt_candidate_next_nodes"),
        duplicate_free=False,
    )
    pibt_candidate_edge_resources = _require_int_array(
        "pibt_candidate_edge_resources",
        row.get("pibt_candidate_edge_resources"),
        bits=64,
        duplicate_free=False,
    )
    pibt_candidate_expected_fault_generations = _require_int_array(
        "pibt_candidate_expected_fault_generations",
        row.get("pibt_candidate_expected_fault_generations"),
        unsigned=True,
        duplicate_free=False,
    )
    pibt_candidate_required_resource_offsets = _require_int_array(
        "pibt_candidate_required_resource_offsets",
        row.get("pibt_candidate_required_resource_offsets"),
        unsigned=True,
        duplicate_free=False,
    )
    pibt_candidate_required_resources = _require_int_array(
        "pibt_candidate_required_resources",
        row.get("pibt_candidate_required_resources"),
        bits=64,
        duplicate_free=False,
    )
    pibt_vectors = {
        "pibt_ready_bag_ids": pibt_ready_bag_ids,
        "pibt_ready_current_nodes": pibt_ready_current_nodes,
        "pibt_owner_resources": pibt_owner_resources,
        "pibt_owner_bag_ids": pibt_owner_bag_ids,
        "pibt_candidate_bag_ids": pibt_candidate_bag_ids,
        "pibt_candidate_next_nodes": pibt_candidate_next_nodes,
        "pibt_candidate_edge_resources": pibt_candidate_edge_resources,
        "pibt_candidate_expected_fault_generations": (
            pibt_candidate_expected_fault_generations
        ),
        "pibt_candidate_required_resource_offsets": (
            pibt_candidate_required_resource_offsets
        ),
        "pibt_candidate_required_resources": (
            pibt_candidate_required_resources
        ),
    }
    if kind == INTERVENTION_BOUNDARY_KIND["I5_pibt_trigger"]:
        candidate_count = len(pibt_candidate_bag_ids)
        valid_i5_shape = (
            baseline_pibt
            and runtime_bag_id >= 0
            and pibt_owner == runtime_bag_id
            and bool(pibt_ready_bag_ids)
            and bool(pibt_owner_resources)
            and bool(pibt_candidate_bag_ids)
            and len(pibt_ready_current_nodes) == len(pibt_ready_bag_ids)
            and len(pibt_owner_resources) == len(pibt_owner_bag_ids)
            and len(pibt_candidate_next_nodes) == candidate_count
            and len(pibt_candidate_edge_resources) == candidate_count
            and len(pibt_candidate_expected_fault_generations)
            == candidate_count
            and len(pibt_candidate_required_resource_offsets)
            == candidate_count + 1
            and pibt_candidate_required_resource_offsets[0] == 0
            and pibt_candidate_required_resource_offsets[-1]
            == len(pibt_candidate_required_resources)
            and pibt_owner in pibt_ready_bag_ids
        )
        if not valid_i5_shape:
            raise CloneValidationError(
                "I5 boundary must bind one complete applicable PIBT slice"
            )
        ready_bags = set(pibt_ready_bag_ids)
        if any(owner not in ready_bags for owner in pibt_owner_bag_ids):
            raise CloneValidationError(
                "PIBT owner map references a bag outside the ready slice"
            )
        for index, candidate_bag_id in enumerate(
            pibt_candidate_bag_ids
        ):
            begin = pibt_candidate_required_resource_offsets[index]
            end = pibt_candidate_required_resource_offsets[index + 1]
            candidate_edge_resource = pibt_candidate_edge_resources[index]
            if (
                pibt_candidate_next_nodes[index] < 0
                or candidate_bag_id not in ready_bags
                or begin >= end
                or end > len(pibt_candidate_required_resources)
                or candidate_edge_resource
                not in pibt_candidate_required_resources[begin:end]
            ):
                raise CloneValidationError(
                    "PIBT candidate set is not a valid ordered slice"
                )
    elif any(pibt_vectors.values()):
        raise CloneValidationError(
            "non-I5 boundary cannot carry PIBT slice state"
        )
    queue_pre_pop = _require_bool(
        "queue_top_not_popped", row.get("queue_top_not_popped")
    )
    sink_empty = _require_bool(
        "staged_event_sink_empty", row.get("staged_event_sink_empty")
    )
    if not queue_pre_pop or not sink_empty:
        raise CloneValidationError(
            "clone boundary is not queue-top pre-pop with an empty staged sink"
        )
    global_scans = _require_int(
        "runtime_global_scan_count",
        row.get("runtime_global_scan_count"),
        minimum=0,
    )
    future_route = _require_int(
        "runtime_future_route_read_count",
        row.get("runtime_future_route_read_count"),
        minimum=0,
    )
    future_schedule = _require_int(
        "runtime_future_schedule_read_count",
        row.get("runtime_future_schedule_read_count"),
        minimum=0,
    )
    if global_scans or future_route or future_schedule:
        raise CloneValidationError("clone boundary leaked global/future state")
    reservation_depth = _require_int(
        "reservation_depth", row.get("reservation_depth"), minimum=0
    )
    max_edges = _require_int(
        "max_selected_edges_per_bag",
        row.get("max_selected_edges_per_bag"),
        minimum=0,
    )
    if reservation_depth != 1 or max_edges > 1:
        raise CloneValidationError("clone boundary violates one-edge semantics")
    components = row.get("state_components")
    if not isinstance(components, Mapping):
        raise CloneValidationError("state_components must be an object")
    state_sha = canonical_state_component_sha256(components)
    if row.get("runtime_state_sha256") != state_sha:
        raise CloneValidationError(
            "runtime_state_sha256 does not bind the complete state inventory"
        )
    normalized = {
        **dict(row),
        "decision_boundary_kind": kind,
        "decision_time_bits": time_bits,
        "decision_event_seq": event_seq,
        "node": node,
        "runtime_bag_id": runtime_bag_id,
        "baseline_next_node": baseline_next_node,
        "baseline_release": baseline_release,
        "baseline_pibt_enabled": baseline_pibt,
        "pibt_owner_runtime_bag_id": pibt_owner,
        "source_ready_order": source_ready,
        "pending_merge_request_order": pending_merge,
        "legal_next_edges": legal_edges,
        **pibt_vectors,
        "runtime_state_sha256": state_sha,
        "state_components": dict(components),
        "queue_top_not_popped": queue_pre_pop,
        "staged_event_sink_empty": sink_empty,
        "runtime_global_scan_count": global_scans,
        "runtime_future_route_read_count": future_route,
        "runtime_future_schedule_read_count": future_schedule,
        "reservation_depth": reservation_depth,
        "max_selected_edges_per_bag": max_edges,
    }
    ready_sha = canonical_ready_set_sha256(normalized)
    if row.get("ready_set_sha256") != ready_sha:
        raise CloneValidationError("ready_set_sha256 mismatch")
    normalized["ready_set_sha256"] = ready_sha
    clone_group = expected_clone_group_id(normalized)
    if row.get("clone_group_id") != clone_group:
        raise CloneValidationError(
            "clone_group_id differs from native outcome-free identity"
        )
    normalized["clone_group_id"] = clone_group
    boundary_sha = expected_boundary_sha256(normalized)
    if row.get("boundary_sha256") != boundary_sha:
        raise CloneValidationError("boundary_sha256 differs from native payload")
    normalized["boundary_sha256"] = boundary_sha
    return normalized


def expected_fidelity_id(row: Mapping[str, object]) -> str:
    return canonical_sha256(
        {
            "schema": FIDELITY_SCHEMA,
            "clone_group_id": row["clone_group_id"],
            "noop_action_sha256": row["original_action_sha256"],
        }
    )


def _fidelity_row_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in row.items()
        if key != "evidence_row_sha256"
    }


def validate_fidelity_row(
    row: Mapping[str, object],
) -> dict[str, object]:
    if row.get("schema") != FIDELITY_SCHEMA:
        raise CloneValidationError("fidelity row schema mismatch")
    normalized = _validate_boundary(row)
    original_action = _require_sha256(
        "original_action_sha256", row.get("original_action_sha256")
    )
    clone_action = _require_sha256(
        "clone_action_sha256", row.get("clone_action_sha256")
    )
    if original_action != clone_action:
        raise CloneValidationError("no-op clone changed the selected action")
    original = row.get("original_hashes")
    replay = row.get("clone_hashes")
    if not isinstance(original, Mapping) or not isinstance(replay, Mapping):
        raise CloneValidationError("fidelity row lacks raw hash sets")
    _require_exact_keys(
        original, REQUIRED_FIDELITY_HASHES, "original fidelity hashes"
    )
    _require_exact_keys(
        replay, REQUIRED_FIDELITY_HASHES, "clone fidelity hashes"
    )
    exact = True
    for name in REQUIRED_FIDELITY_HASHES:
        left = _require_sha256(f"original.{name}", original[name])
        right = _require_sha256(f"clone.{name}", replay[name])
        exact = exact and left == right
    if not exact:
        raise CloneValidationError(
            "clone replay fidelity is below 100% from the five raw hashes"
        )
    normalized.update(
        {
            "schema": FIDELITY_SCHEMA,
            "original_action_sha256": original_action,
            "clone_action_sha256": clone_action,
            "original_hashes": dict(original),
            "clone_hashes": dict(replay),
        }
    )
    fidelity_id = expected_fidelity_id(normalized)
    if row.get("fidelity_id") != fidelity_id:
        raise CloneValidationError("fidelity_id is not content-addressed")
    normalized["fidelity_id"] = fidelity_id
    evidence_sha = canonical_sha256(_fidelity_row_payload(normalized))
    if row.get("evidence_row_sha256") != evidence_sha:
        raise CloneValidationError("fidelity evidence_row_sha256 mismatch")
    normalized["evidence_row_sha256"] = evidence_sha
    return normalized


def validate_fidelity_rows(
    rows: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    normalized = [validate_fidelity_row(row) for row in rows]
    if not normalized:
        raise CloneValidationError("no baseline no-op clone fidelity rows")
    ids = [str(row["fidelity_id"]) for row in normalized]
    groups = [str(row["clone_group_id"]) for row in normalized]
    row_hashes = [str(row["evidence_row_sha256"]) for row in normalized]
    if len(set(ids)) != len(ids):
        raise CloneValidationError("duplicate fidelity_id")
    if len(set(groups)) != len(groups):
        raise CloneValidationError("duplicate no-op clone boundary")
    if len(set(row_hashes)) != len(row_hashes):
        raise CloneValidationError("duplicate fidelity evidence row")
    return {
        "fidelity_clone_count": len(normalized),
        "fidelity_exact_match_count": len(normalized),
        "clone_replay_fidelity": "1",
        "fidelity_manifest_sha256": canonical_sha256(sorted(row_hashes)),
    }


def _validate_native_intervention(
    row: Mapping[str, object],
    boundary: Mapping[str, object],
) -> dict[str, object]:
    action = row.get("intervention")
    if not isinstance(action, Mapping):
        raise CloneValidationError("intervention must be an object")
    _require_exact_keys(
        action, NATIVE_INTERVENTION_FIELDS, "native intervention"
    )
    normalized = {
        "runtime_bag_id": _require_int(
            "intervention.runtime_bag_id", action["runtime_bag_id"]
        ),
        "peer_runtime_bag_id": _require_int(
            "intervention.peer_runtime_bag_id",
            action["peer_runtime_bag_id"],
        ),
        "merge_request_id": _require_int(
            "intervention.merge_request_id",
            action["merge_request_id"],
            minimum=0,
        ),
        "peer_merge_request_id": _require_int(
            "intervention.peer_merge_request_id",
            action["peer_merge_request_id"],
            minimum=0,
        ),
        "selected_next_node": _require_int(
            "intervention.selected_next_node",
            action["selected_next_node"],
        ),
        "selected_boolean": _require_bool(
            "intervention.selected_boolean",
            action["selected_boolean"],
        ),
    }
    kind = str(row["intervention_kind"])
    bag = normalized["runtime_bag_id"]
    peer = normalized["peer_runtime_bag_id"]
    request = normalized["merge_request_id"]
    peer_request = normalized["peer_merge_request_id"]
    next_node = normalized["selected_next_node"]
    selected = normalized["selected_boolean"]
    if kind == "I1_source_order_swap":
        valid = (
            request == 0
            and peer_request == 0
            and next_node == -1
            and selected is False
            and bag != peer
            and bag == boundary["runtime_bag_id"]
            and bag in boundary["source_ready_order"]
            and peer in boundary["source_ready_order"]
        )
    elif kind == "I2_merge_request_order_swap":
        valid = (
            bag == -1
            and peer == -1
            and next_node == -1
            and selected is False
            and request > 0
            and request != peer_request
            and request == boundary["pending_merge_request_order"][0]
            and request in boundary["pending_merge_request_order"]
            and peer_request in boundary["pending_merge_request_order"]
        )
    elif kind == "I3_next_edge":
        valid = (
            peer == -1
            and request == 0
            and peer_request == 0
            and selected is False
            and bag == boundary["runtime_bag_id"]
            and next_node != boundary["baseline_next_node"]
            and next_node in boundary["legal_next_edges"]
        )
    elif kind == "I4_hold_release":
        valid = (
            peer == -1
            and request == 0
            and peer_request == 0
            and next_node == -1
            and bag == boundary["runtime_bag_id"]
            and boundary["baseline_release"] is True
            and selected is False
        )
    else:
        valid = (
            peer == -1
            and request == 0
            and peer_request == 0
            and next_node == -1
            and bag == boundary["runtime_bag_id"]
            and selected != boundary["baseline_pibt_enabled"]
        )
    if not valid:
        raise CloneValidationError(
            f"{kind} does not encode exactly one legal native action"
        )
    return normalized


def _native_intervention_payload(
    row: Mapping[str, object],
    *,
    include_horizon: bool,
) -> bytes:
    action = row["intervention"]
    fields = CanonicalFields()
    fields.string("schema", SCHEMA)
    fields.string("boundary_sha256", str(row["boundary_sha256"]))
    fields.string("kind", str(row["intervention_kind"]))
    if include_horizon:
        fields.string("horizon", str(row["horizon"]))
    fields.integer("runtime_bag_id", int(action["runtime_bag_id"]))
    fields.integer(
        "peer_runtime_bag_id", int(action["peer_runtime_bag_id"])
    )
    fields.unsigned_integer(
        "merge_request_id", int(action["merge_request_id"])
    )
    fields.unsigned_integer(
        "peer_merge_request_id", int(action["peer_merge_request_id"])
    )
    fields.integer("selected_next_node", int(action["selected_next_node"]))
    fields.boolean("selected_boolean", bool(action["selected_boolean"]))
    return fields.payload()


def expected_intervention_token_sha256(row: Mapping[str, object]) -> str:
    """Causal action token; unlike the native ID it intentionally omits horizon."""

    return hashlib.sha256(
        _native_intervention_payload(row, include_horizon=False)
    ).hexdigest()


def expected_intervention_id(row: Mapping[str, object]) -> str:
    """Exact native ``G4IRSF14CloneIntervention::intervention_sha256``."""

    return hashlib.sha256(
        _native_intervention_payload(row, include_horizon=True)
    ).hexdigest()


def _normalize_branch_invariants(
    prefix: str,
    raw: object,
) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise CloneValidationError(f"{prefix}_invariants must be an object")
    _require_exact_keys(raw, BRANCH_INVARIANTS, f"{prefix} invariants")
    normalized: dict[str, object] = {}
    for name in BRANCH_INVARIANTS:
        label = f"{prefix}.{name}"
        if name in BRANCH_BOOLEAN_INVARIANTS:
            normalized[name] = _require_bool(label, raw[name])
        elif name in BRANCH_DECIMAL_INVARIANTS:
            normalized[name] = _require_decimal(label, raw[name])
        else:
            normalized[name] = _require_int(label, raw[name], minimum=0)
    return normalized


def _normalize_metrics(prefix: str, raw: object) -> dict[str, Decimal]:
    if not isinstance(raw, Mapping):
        raise CloneValidationError(f"{prefix}_metrics must be an object")
    _require_exact_keys(raw, METRICS, f"{prefix} metrics")
    return {
        name: _require_decimal(f"{prefix}.{name}", raw[name])
        for name in METRICS
    }


def _outcome_sha256(
    metrics: Mapping[str, Decimal],
    invariants: Mapping[str, object],
) -> str:
    return canonical_sha256(
        {
            "schema": OUTCOME_SCHEMA,
            "metrics": metrics,
            "invariants": invariants,
        }
    )


def _intervention_row_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in row.items()
        if key != "evidence_row_sha256"
    }


def validate_intervention_row(
    row: Mapping[str, object],
) -> dict[str, object]:
    if row.get("schema") != INTERVENTION_SCHEMA:
        raise CloneValidationError("intervention row schema mismatch")
    boundary = _validate_boundary(row)
    kind = row.get("intervention_kind")
    if kind not in INTERVENTION_ACTION_FIELD:
        raise CloneValidationError(f"unknown intervention kind: {kind}")
    if boundary["decision_boundary_kind"] != INTERVENTION_BOUNDARY_KIND[kind]:
        raise CloneValidationError(
            f"{kind} is attached to the wrong decision boundary"
        )
    horizon = row.get("horizon")
    if horizon == "H_local":
        raise CloneValidationError("H_local is screening-only and cannot be a label")
    if horizon not in FORMAL_HORIZONS:
        raise CloneValidationError(f"unknown formal horizon: {horizon}")
    split = row.get("split")
    if split not in SPLITS:
        raise CloneValidationError(f"invalid data split: {split}")
    native_record_sha = _require_sha256(
        "native_record_sha256", row.get("native_record_sha256")
    )
    intervention = _validate_native_intervention(row, boundary)

    if row.get("baseline_start_state_sha256") != boundary[
        "runtime_state_sha256"
    ]:
        raise CloneValidationError("baseline fork start-state mismatch")
    if row.get("treatment_start_state_sha256") != boundary[
        "runtime_state_sha256"
    ]:
        raise CloneValidationError("treatment fork start-state mismatch")

    normalized: dict[str, object] = {
        **boundary,
        "schema": INTERVENTION_SCHEMA,
        "intervention_kind": kind,
        "horizon": horizon,
        "split": split,
        "native_record_sha256": native_record_sha,
        "raw_bag_ids": list(
            _require_id_list("raw_bag_ids", row.get("raw_bag_ids"))
        ),
        "raw_task_ids": list(
            _require_id_list("raw_task_ids", row.get("raw_task_ids"))
        ),
        "segment_ids": list(
            _require_id_list("segment_ids", row.get("segment_ids"))
        ),
        "horizon_entity_ids": list(
            _require_id_list(
                "horizon_entity_ids", row.get("horizon_entity_ids")
            )
        ),
        "baseline_start_state_sha256": boundary["runtime_state_sha256"],
        "treatment_start_state_sha256": boundary["runtime_state_sha256"],
        "intervention": intervention,
    }
    horizon_entity_set_sha = canonical_sha256(
        {
            "schema": INTERVENTION_SCHEMA,
            "horizon": horizon,
            "horizon_entity_ids": normalized["horizon_entity_ids"],
        }
    )
    if row.get("horizon_entity_set_sha256") != horizon_entity_set_sha:
        raise CloneValidationError(
            "horizon_entity_set_sha256 does not bind its cohort"
        )
    normalized["horizon_entity_set_sha256"] = horizon_entity_set_sha

    affected = _require_int(
        "affected_bag_count", row.get("affected_bag_count"), minimum=1
    )
    if affected != len(normalized["raw_bag_ids"]):
        raise CloneValidationError(
            "affected_bag_count differs from unique raw_bag_ids"
        )
    required_horizon = _require_int(
        "required_horizon_completion_count",
        row.get("required_horizon_completion_count"),
        minimum=1,
    )
    if required_horizon != len(normalized["horizon_entity_ids"]):
        raise CloneValidationError(
            "horizon completion denominator differs from cohort identity"
        )
    if horizon == "H_bag":
        if normalized["horizon_entity_ids"] != normalized["raw_bag_ids"]:
            raise CloneValidationError(
                "H_bag cohort must be exactly the affected bag set"
            )
    else:
        if not set(normalized["raw_bag_ids"]).issubset(
            set(normalized["horizon_entity_ids"])
        ):
            raise CloneValidationError(
                "H_system selected cohort omits an affected bag"
            )
        if len(normalized["horizon_entity_ids"]) <= len(
            normalized["raw_bag_ids"]
        ):
            raise CloneValidationError(
                "H_system cohort must strictly exceed the affected bag set"
            )
    normalized.update(
        {
            "affected_bag_count": affected,
            "required_horizon_completion_count": required_horizon,
        }
    )

    token = expected_intervention_token_sha256(normalized)
    if row.get("intervention_token_sha256") != token:
        raise CloneValidationError(
            "intervention token is not content-addressed from outcome-free fields"
        )
    normalized["intervention_token_sha256"] = token
    intervention_id = expected_intervention_id(normalized)
    if row.get("intervention_id") != intervention_id:
        raise CloneValidationError(
            "intervention_id is not content-addressed from outcome-free fields"
        )
    normalized["intervention_id"] = intervention_id

    baseline_invariants = _normalize_branch_invariants(
        "baseline", row.get("baseline_invariants")
    )
    treatment_invariants = _normalize_branch_invariants(
        "treatment", row.get("treatment_invariants")
    )
    if baseline_invariants["intervention_hit_count"] != 0:
        raise CloneValidationError("baseline fork consumed an intervention token")
    if treatment_invariants["intervention_hit_count"] != 1:
        raise CloneValidationError(
            "treatment intervention did not hit exactly once"
        )
    for prefix, invariants in (
        ("baseline", baseline_invariants),
        ("treatment", treatment_invariants),
    ):
        if invariants["completed_affected_bag_count"] != affected:
            raise CloneValidationError(
                f"{prefix} did not complete every affected bag"
            )
        if invariants["completed_horizon_entity_count"] != required_horizon:
            raise CloneValidationError(f"{prefix} horizon is incomplete")
        for field in (
            "unsafe_entry_count",
            "reservation_conflict_count",
            "runtime_full_astar_call_count",
            "runtime_global_scan_count",
            "runtime_future_route_read_count",
            "runtime_future_schedule_read_count",
            "teacher_input_count",
            "priority_teacher_input_count",
            "scorer_teacher_input_count",
            "full_future_routes_stored",
            "two_step_reservation_count",
            "failed_segment_count",
            "unresolved_deadlock_count",
            "merge_grant_final_active_unconsumed",
            "merge_grant_outstanding_request_count",
            "merge_grant_stale_arbitration_count",
            "merge_grant_lifecycle_dropped_count",
            "stale_arbitration_event_count",
            "artificial_batch_delay_seconds",
        ):
            if invariants[field] != 0:
                raise CloneValidationError(
                    f"{prefix} invariant failed: {field}"
                )
        if invariants["teacher_input_count"] != (
            invariants["priority_teacher_input_count"]
            + invariants["scorer_teacher_input_count"]
        ):
            raise CloneValidationError(
                f"{prefix} teacher-input aggregate is inconsistent"
            )
        if invariants["bag_future_path_field_present"] is not False:
            raise CloneValidationError(
                f"{prefix} retained a future-path field"
            )
        for field in (
            "merge_grant_conservation_holds",
            "merge_grant_active_bijection_holds",
            "merge_grant_runtime_owned_capability",
            "merge_grant_exact_slot_no_future_shift",
            "merge_grant_lifecycle_complete",
            "merge_grant_active_state_integrity_pass",
            "merge_grant_protocol_integrity_pass",
        ):
            if invariants[field] is not True:
                raise CloneValidationError(
                    f"{prefix} live merge integrity failed: {field}"
                )
        if invariants["max_selected_edges_per_bag"] > 1:
            raise CloneValidationError(
                f"{prefix} selected more than one next edge"
            )
        if invariants["reservation_depth"] != 1:
            raise CloneValidationError(
                f"{prefix} reservation depth is not one"
            )
        if invariants["event_limit_reached"] or invariants[
            "time_limit_reached"
        ]:
            raise CloneValidationError(f"{prefix} reached a runtime limit")

    baseline_metrics = _normalize_metrics(
        "baseline", row.get("baseline_metrics")
    )
    treatment_metrics = _normalize_metrics(
        "treatment", row.get("treatment_metrics")
    )
    for prefix, metrics in (
        ("baseline", baseline_metrics),
        ("treatment", treatment_metrics),
    ):
        for name, value in metrics.items():
            if value < 0:
                raise CloneValidationError(
                    f"{prefix}.{name} must be non-negative"
                )
        deadline = metrics["deadline_miss_count"]
        if deadline != deadline.to_integral_value():
            raise CloneValidationError(
                f"{prefix}.deadline_miss_count must be an integer"
            )
    deltas_raw = row.get("deltas")
    if not isinstance(deltas_raw, Mapping):
        raise CloneValidationError("deltas must be an object")
    _require_exact_keys(deltas_raw, DELTA_FIELDS, "causal deltas")
    deltas: dict[str, Decimal] = {}
    for metric in METRICS:
        field = f"{metric}_delta"
        claimed = _require_decimal(field, deltas_raw[field])
        recomputed = treatment_metrics[metric] - baseline_metrics[metric]
        if claimed != recomputed:
            raise CloneValidationError(
                f"{field} does not equal treatment minus baseline"
            )
        deltas[field] = recomputed

    baseline_outcome = _outcome_sha256(
        baseline_metrics, baseline_invariants
    )
    treatment_outcome = _outcome_sha256(
        treatment_metrics, treatment_invariants
    )
    if row.get("baseline_outcome_sha256") != baseline_outcome:
        raise CloneValidationError("baseline outcome hash mismatch")
    if row.get("treatment_outcome_sha256") != treatment_outcome:
        raise CloneValidationError("treatment outcome hash mismatch")

    normalized.update(
        {
            "baseline_invariants": baseline_invariants,
            "treatment_invariants": treatment_invariants,
            "baseline_metrics": baseline_metrics,
            "treatment_metrics": treatment_metrics,
            "deltas": deltas,
            "baseline_outcome_sha256": baseline_outcome,
            "treatment_outcome_sha256": treatment_outcome,
        }
    )
    evidence_sha = canonical_sha256(_intervention_row_payload(normalized))
    if row.get("evidence_row_sha256") != evidence_sha:
        raise CloneValidationError("intervention evidence_row_sha256 mismatch")
    normalized["evidence_row_sha256"] = evidence_sha
    return normalized


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def validate_split_disjointness(
    rows: Sequence[Mapping[str, object]],
) -> int:
    """Union shared state/clone/task/segment/ready-set IDs, then audit splits."""

    dsu = _DisjointSet(len(rows))
    owners: dict[tuple[str, str], int] = {}
    for index, row in enumerate(rows):
        keys: list[tuple[str, str]] = [
            ("runtime_state", str(row["runtime_state_sha256"])),
            ("clone_group", str(row["clone_group_id"])),
            ("ready_set", str(row["ready_set_sha256"])),
        ]
        for field, category in (
            ("raw_bag_ids", "bag"),
            ("raw_task_ids", "task"),
            ("segment_ids", "segment"),
        ):
            keys.extend((category, str(value)) for value in row[field])
        for key in keys:
            if key in owners:
                dsu.union(index, owners[key])
            else:
                owners[key] = index
    component_splits: dict[int, set[str]] = defaultdict(set)
    for index, row in enumerate(rows):
        component_splits[dsu.find(index)].add(str(row["split"]))
    crossing = [
        sorted(splits)
        for splits in component_splits.values()
        if len(splits) != 1
    ]
    if crossing:
        raise CloneValidationError(
            "union-find split leakage across "
            "state/clone/task/segment/ready-set: "
            f"{crossing[:3]}"
        )
    return len(component_splits)


def _validate_unique_interventions(
    rows: Sequence[Mapping[str, object]],
) -> None:
    for field, label in (
        ("intervention_id", "intervention IDs"),
        ("evidence_row_sha256", "intervention evidence rows"),
    ):
        values = [str(row[field]) for row in rows]
        if len(values) != len(set(values)):
            raise CloneValidationError(f"duplicate {label}")
    opportunities = [
        (
            str(row["clone_group_id"]),
            str(row["intervention_token_sha256"]),
        )
        for row in rows
    ]
    if len(opportunities) != len(set(opportunities)):
        raise CloneValidationError(
            "duplicate causal token (a second horizon cannot double-count it)"
        )


def _campaign_summary(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    _validate_unique_interventions(rows)
    component_count = validate_split_disjointness(rows)
    horizons = Counter(str(row["horizon"]) for row in rows)
    kinds = Counter(str(row["intervention_kind"]) for row in rows)
    missing_kinds = sorted(set(INTERVENTION_ACTION_FIELD) - set(kinds))
    if missing_kinds:
        raise CloneValidationError(
            f"intervention taxonomy is incomplete: {missing_kinds}"
        )
    non_improving = sum(
        row["deltas"]["affected_bag_completion_seconds_delta"] >= 0
        for row in rows
    )
    row_hashes = sorted(str(row["evidence_row_sha256"]) for row in rows)
    return {
        "matched_intervention_count": len(rows),
        "complete_label_count": len(rows),
        "unique_intervention_count": len(
            {str(row["intervention_token_sha256"]) for row in rows}
        ),
        "h_local_label_count": 0,
        "h_bag_count": horizons["H_bag"],
        "h_system_count": horizons["H_system"],
        "intervention_kind_counts": dict(sorted(kinds.items())),
        "split_component_count": component_count,
        "non_improving_intervention_count": non_improving,
        "intervention_manifest_sha256": canonical_sha256(row_hashes),
    }


def validate_campaign(
    fidelity_rows: Iterable[Mapping[str, object]],
    intervention_rows: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Validate a formal campaign; the 2,000-row gate cannot be overridden."""

    normalized_fidelity = [
        validate_fidelity_row(row) for row in fidelity_rows
    ]
    fidelity = validate_fidelity_rows(normalized_fidelity)
    rows = [validate_intervention_row(row) for row in intervention_rows]
    summary = _campaign_summary(rows)
    if summary["unique_intervention_count"] < MIN_MATCHED_INTERVENTIONS:
        raise CloneValidationError(
            f"unique complete H_bag/H_system interventions "
            f"{summary['unique_intervention_count']} < "
            f"{MIN_MATCHED_INTERVENTIONS}"
        )
    if summary["h_system_count"] <= 0:
        raise CloneValidationError("system-horizon intervention count is zero")
    _validate_fidelity_coverage(normalized_fidelity, rows)
    return {
        **fidelity,
        **summary,
        "campaign_manifest_sha256": canonical_sha256(
            {
                "fidelity_manifest_sha256": fidelity[
                    "fidelity_manifest_sha256"
                ],
                "intervention_manifest_sha256": summary[
                    "intervention_manifest_sha256"
                ],
            }
        ),
    }


def _validate_fidelity_coverage(
    fidelity_rows: Sequence[Mapping[str, object]],
    intervention_rows: Sequence[Mapping[str, object]],
) -> None:
    fidelity_groups = {
        str(row["clone_group_id"]) for row in fidelity_rows
    }
    intervention_groups = {
        str(row["clone_group_id"]) for row in intervention_rows
    }
    missing = sorted(intervention_groups - fidelity_groups)
    if missing:
        raise CloneValidationError(
            "intervention clone groups lack matched no-op fidelity rows: "
            f"{missing[:3]}"
        )


def expected_ledger_rows(
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["intervention_kind"])].append(row)
    expected: list[dict[str, object]] = []
    for kind in sorted(INTERVENTION_ACTION_FIELD):
        group = grouped.get(kind, [])
        if not group:
            raise CloneValidationError(f"ledger lacks causal support for {kind}")
        item: dict[str, object] = {
            "schema": LEDGER_SCHEMA,
            "intervention_kind": kind,
            "complete_label_count": len(group),
            "h_bag_count": sum(row["horizon"] == "H_bag" for row in group),
            "h_system_count": sum(
                row["horizon"] == "H_system" for row in group
            ),
            "improving_count": sum(
                row["deltas"]["affected_bag_completion_seconds_delta"] < 0
                for row in group
            ),
            "non_improving_count": sum(
                row["deltas"]["affected_bag_completion_seconds_delta"] >= 0
                for row in group
            ),
        }
        for metric in METRICS:
            field = f"{metric}_delta"
            total = sum(
                (row["deltas"][field] for row in group),
                start=Decimal(0),
            )
            item[f"sum_{field}"] = canonical_decimal(total)
            item[f"mean_{field}"] = canonical_mean(total, len(group))
        expected.append(item)
    return expected


def validate_ledger_rows(
    rows: Iterable[Mapping[str, object]],
    intervention_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    observed = list(rows)
    expected = expected_ledger_rows(intervention_rows)
    if len(observed) != len(expected):
        raise CloneValidationError(
            "causal component ledger must contain exactly five rows"
        )
    normalized_observed: list[dict[str, object]] = []
    for index, row in enumerate(observed):
        _require_exact_keys(row, LEDGER_COLUMNS, f"ledger row {index}")
        normalized: dict[str, object] = {
            "schema": row.get("schema"),
            "intervention_kind": row.get("intervention_kind"),
        }
        for field in (
            "complete_label_count",
            "h_bag_count",
            "h_system_count",
            "improving_count",
            "non_improving_count",
        ):
            normalized[field] = _require_int(
                f"ledger.{field}", row.get(field), minimum=0
            )
        for metric in METRICS:
            for prefix in ("sum", "mean"):
                field = f"{prefix}_{metric}_delta"
                normalized[field] = canonical_decimal(
                    _require_decimal(f"ledger.{field}", row.get(field))
                )
        normalized_observed.append(normalized)
    normalized_observed.sort(key=lambda row: str(row["intervention_kind"]))
    if normalized_observed != expected:
        raise CloneValidationError(
            "causal component ledger does not recompute from intervention rows"
        )
    return {
        "ledger_manifest_sha256": canonical_sha256(expected),
        "ledger_row_count": len(expected),
    }


def clone_group_fold(clone_group_id: str, fold_count: int) -> int:
    """Deterministic helper; formal split validation uses union-find above."""

    _require_sha256("clone_group_id", clone_group_id)
    if fold_count <= 1:
        raise CloneValidationError("fold_count must exceed one")
    digest = bytes.fromhex(clone_group_id)
    return int.from_bytes(digest[:8], "big") % fold_count


def _decode_boundary_csv(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "clone_group_id": row["clone_group_id"],
        "boundary_sha256": row["boundary_sha256"],
        "decision_boundary_kind": row["decision_boundary_kind"],
        "decision_time_bits": row["decision_time_bits"],
        "decision_event_seq": row["decision_event_seq"],
        "node": row["node"],
        "runtime_bag_id": row["runtime_bag_id"],
        "baseline_next_node": row["baseline_next_node"],
        "baseline_release": row["baseline_release"],
        "baseline_pibt_enabled": row["baseline_pibt_enabled"],
        "pibt_owner_runtime_bag_id": row["pibt_owner_runtime_bag_id"],
        "source_ready_order": _parse_canonical_json(
            "source_ready_order_json", row["source_ready_order_json"]
        ),
        "pending_merge_request_order": _parse_canonical_json(
            "pending_merge_request_order_json",
            row["pending_merge_request_order_json"],
        ),
        "legal_next_edges": _parse_canonical_json(
            "legal_next_edges_json", row["legal_next_edges_json"]
        ),
        **{
            field: _parse_canonical_json(
                f"{field}_json", row[f"{field}_json"]
            )
            for field in PIBT_SLICE_FIELDS
        },
        "ready_set_sha256": row["ready_set_sha256"],
        "runtime_state_sha256": row["runtime_state_sha256"],
        "state_components": _parse_canonical_json(
            "state_components_json", row["state_components_json"]
        ),
        "queue_top_not_popped": row["queue_top_not_popped"],
        "staged_event_sink_empty": row["staged_event_sink_empty"],
        "runtime_global_scan_count": row["runtime_global_scan_count"],
        "runtime_future_route_read_count": row[
            "runtime_future_route_read_count"
        ],
        "runtime_future_schedule_read_count": row[
            "runtime_future_schedule_read_count"
        ],
        "reservation_depth": row["reservation_depth"],
        "max_selected_edges_per_bag": row["max_selected_edges_per_bag"],
    }


def _decode_fidelity_csv_row(row: Mapping[str, object]) -> dict[str, object]:
    _require_exact_keys(row, FIDELITY_COLUMNS, "fidelity CSV row")
    return {
        "schema": row["schema"],
        "fidelity_id": row["fidelity_id"],
        **_decode_boundary_csv(row),
        "original_action_sha256": row["original_action_sha256"],
        "clone_action_sha256": row["clone_action_sha256"],
        "original_hashes": {
            name: row[f"original_{name}"]
            for name in REQUIRED_FIDELITY_HASHES
        },
        "clone_hashes": {
            name: row[f"clone_{name}"]
            for name in REQUIRED_FIDELITY_HASHES
        },
        "evidence_row_sha256": row["evidence_row_sha256"],
    }


def _decode_intervention_csv_row(
    row: Mapping[str, object],
) -> dict[str, object]:
    _require_exact_keys(row, INTERVENTION_COLUMNS, "intervention CSV row")
    return {
        "schema": row["schema"],
        "intervention_id": row["intervention_id"],
        "intervention_token_sha256": row["intervention_token_sha256"],
        "native_record_sha256": row["native_record_sha256"],
        **_decode_boundary_csv(row),
        "intervention_kind": row["intervention_kind"],
        "horizon": row["horizon"],
        "intervention": {
            name: row[f"intervention_{name}"]
            for name in NATIVE_INTERVENTION_FIELDS
        },
        "split": row["split"],
        "raw_bag_ids": _parse_canonical_json(
            "raw_bag_ids_json", row["raw_bag_ids_json"]
        ),
        "raw_task_ids": _parse_canonical_json(
            "raw_task_ids_json", row["raw_task_ids_json"]
        ),
        "segment_ids": _parse_canonical_json(
            "segment_ids_json", row["segment_ids_json"]
        ),
        "horizon_entity_ids": _parse_canonical_json(
            "horizon_entity_ids_json", row["horizon_entity_ids_json"]
        ),
        "horizon_entity_set_sha256": row["horizon_entity_set_sha256"],
        "baseline_start_state_sha256": row[
            "baseline_start_state_sha256"
        ],
        "treatment_start_state_sha256": row[
            "treatment_start_state_sha256"
        ],
        "affected_bag_count": row["affected_bag_count"],
        "required_horizon_completion_count": row[
            "required_horizon_completion_count"
        ],
        "baseline_invariants": {
            name: row[f"baseline_{name}"] for name in BRANCH_INVARIANTS
        },
        "treatment_invariants": {
            name: row[f"treatment_{name}"] for name in BRANCH_INVARIANTS
        },
        "baseline_metrics": {
            name: row[f"baseline_{name}"] for name in METRICS
        },
        "treatment_metrics": {
            name: row[f"treatment_{name}"] for name in METRICS
        },
        "deltas": {name: row[name] for name in DELTA_FIELDS},
        "baseline_outcome_sha256": row["baseline_outcome_sha256"],
        "treatment_outcome_sha256": row["treatment_outcome_sha256"],
        "evidence_row_sha256": row["evidence_row_sha256"],
    }


def _read_csv(
    path: Path,
    expected_columns: Sequence[str],
    decoder: Any | None = None,
) -> list[dict[str, object]]:
    if not path.is_file():
        raise CloneValidationError(f"required artifact missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(expected_columns):
            raise CloneValidationError(
                f"{path.name} columns mismatch: {reader.fieldnames}"
            )
        rows: list[dict[str, object]] = []
        for index, row in enumerate(reader):
            if None in row or any(value is None for value in row.values()):
                raise CloneValidationError(
                    f"{path.name} row {index} has malformed columns"
                )
            rows.append(decoder(row) if decoder is not None else dict(row))
    return rows


def _read_canonical_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        raise CloneValidationError(f"required artifact missing: {path}")
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.rstrip("\r\n")
            if not line:
                raise CloneValidationError(
                    f"{path.name} row {line_number} is blank"
                )
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as error:
                raise CloneValidationError(
                    f"{path.name} row {line_number} is invalid JSON"
                ) from error
            if not isinstance(parsed, Mapping):
                raise CloneValidationError(
                    f"{path.name} row {line_number} must be an object"
                )
            if canonical_json(parsed) != line:
                raise CloneValidationError(
                    f"{path.name} row {line_number} is not canonical JSON"
                )
            rows.append(dict(parsed))
    if not rows:
        raise CloneValidationError(
            "exact-binary native evidence JSONL is empty"
        )
    return rows


def _require_native_json_int(
    label: str,
    value: object,
    *,
    minimum: int | None = None,
) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CloneValidationError(f"{label} must be a native JSON integer")
    if minimum is not None and value < minimum:
        raise CloneValidationError(f"{label} must be >= {minimum}")
    return value


def _expected_native_input_identity() -> dict[str, object]:
    return {
        "map_path": CANONICAL_MAP_PATH,
        "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
        "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        "task_path": CANONICAL_TASK_PATH,
        "task_sha256": CANONICAL_TASK_SHA256,
        "segment_count": CANONICAL_SEGMENT_COUNT,
        "raw_bag_count": CANONICAL_RAW_BAG_COUNT,
        "demand_scale": "1.0",
        "expanded_workload_used": False,
    }


def _expected_native_frozen_controls() -> dict[str, object]:
    return {
        "resource_semantics": "R3_java_node_window_compatible",
        "scorer_mode": "S1_frozen_g4e_legal_local_adapter",
        "scorer_model_sha256": FROZEN_G13_MODEL_FILE_SHA256,
        "pibt_mode": "P2",
        "admission_mode": "off",
        "pressure_mode": "off",
        "priority_mode": "Q0",
        "event_semantics": "E4_batch_plus_destination_merge_request",
        "merge_grant_rule": "M0",
        "scale": 1.0,
        "reservation_depth": 1,
        "max_events": 20_000_000,
        "max_simulation_time": -1.0,
        "trace_limit": 0,
        "event_trace_limit": 0,
    }


def _normalize_priority_cohort_tags(value: object) -> list[str]:
    if not isinstance(value, list):
        raise CloneValidationError(
            "priority_cohort_tags must be an ordered array"
        )
    if any(
        not isinstance(item, str) or item not in PRIORITY_COHORTS
        for item in value
    ):
        raise CloneValidationError(
            "priority_cohort_tags contains an unknown cohort"
        )
    if value != sorted(set(value)):
        raise CloneValidationError(
            "priority_cohort_tags must be sorted and duplicate-free"
        )
    return list(value)


def _validate_native_branch(
    value: object,
    *,
    branch_name: str,
    horizon_kind: str,
    checkpoint_state_sha256: str,
    checkpoint_components: Mapping[str, object],
    affected_bag_ids: Sequence[str],
    horizon_entity_ids: Sequence[str],
    stop_reason: str,
    expected_invariants: Mapping[str, object],
    expected_metrics: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise CloneValidationError(
            f"native {branch_name} branch must be an object"
        )
    _require_exact_keys(
        value, NATIVE_BRANCH_FIELDS, f"native {branch_name} branch"
    )
    components = value["start_state_components"]
    if not isinstance(components, Mapping):
        raise CloneValidationError(
            f"native {branch_name} start_state_components must be an object"
        )
    _require_exact_keys(
        components,
        REQUIRED_STATE_COMPONENTS,
        f"native {branch_name} start-state inventory",
    )
    normalized_components = {
        field: _require_sha256(
            f"native {branch_name}.{field}", components[field]
        )
        for field in REQUIRED_STATE_COMPONENTS
    }
    start_state_sha = _require_sha256(
        f"native {branch_name}.start_state_sha256",
        value["start_state_sha256"],
    )
    if (
        canonical_state_component_sha256(normalized_components)
        != start_state_sha
        or start_state_sha != checkpoint_state_sha256
        or normalized_components != dict(checkpoint_components)
    ):
        raise CloneValidationError(
            f"native {branch_name} branch did not restore the exact checkpoint"
        )
    terminal_components = value["terminal_state_components"]
    if not isinstance(terminal_components, Mapping):
        raise CloneValidationError(
            f"native {branch_name} terminal_state_components must be an object"
        )
    _require_exact_keys(
        terminal_components,
        REQUIRED_STATE_COMPONENTS,
        f"native {branch_name} terminal-state inventory",
    )
    normalized_terminal_components = {
        field: _require_sha256(
            f"native {branch_name}.terminal.{field}",
            terminal_components[field],
        )
        for field in REQUIRED_STATE_COMPONENTS
    }
    terminal_state_sha = _require_sha256(
        f"native {branch_name}.terminal_state_sha256",
        value["terminal_state_sha256"],
    )
    if (
        canonical_state_component_sha256(normalized_terminal_components)
        != terminal_state_sha
    ):
        raise CloneValidationError(
            f"native {branch_name} terminal state does not bind its inventory"
        )
    branch_finalized = value["branch_finalized"]
    if not isinstance(branch_finalized, bool):
        raise CloneValidationError(
            f"native {branch_name}.branch_finalized must be boolean"
        )

    completed_affected = list(
        _require_id_list(
            f"native {branch_name}.completed_affected_bag_ids",
            value["completed_affected_bag_ids"],
        )
    )
    completed_horizon = list(
        _require_id_list(
            f"native {branch_name}.completed_horizon_entity_ids",
            value["completed_horizon_entity_ids"],
        )
    )
    if completed_affected != list(affected_bag_ids):
        raise CloneValidationError(
            f"native {branch_name} affected-bag completion set is incomplete"
        )
    if completed_horizon != list(horizon_entity_ids):
        raise CloneValidationError(
            f"native {branch_name} horizon completion set is incomplete"
        )
    if value["stop_reason"] != stop_reason:
        raise CloneValidationError(
            f"native {branch_name} branch used the wrong horizon stop reason"
        )

    replay_hashes = value["replay_hashes"]
    normalized_replay: dict[str, str] | None
    if horizon_kind == "H_bag":
        if branch_finalized or replay_hashes is not None:
            raise CloneValidationError(
                f"native {branch_name} H_bag branch must stop at the "
                "affected-bag horizon without final replay hashes"
            )
        normalized_replay = None
    else:
        if not branch_finalized or not isinstance(replay_hashes, Mapping):
            raise CloneValidationError(
                f"native {branch_name} H_system branch must be finalized "
                "with replay hashes"
            )
        _require_exact_keys(
            replay_hashes,
            REQUIRED_FIDELITY_HASHES,
            f"native {branch_name} replay hashes",
        )
        normalized_replay = {
            field: _require_sha256(
                f"native {branch_name}.{field}", replay_hashes[field]
            )
            for field in REQUIRED_FIDELITY_HASHES
        }
    raw_invariants = value["invariants"]
    if not isinstance(raw_invariants, Mapping):
        raise CloneValidationError(
            f"native {branch_name} invariants must be an object"
        )
    for field in BRANCH_INVARIANTS:
        raw_field = raw_invariants.get(field)
        if field in BRANCH_BOOLEAN_INVARIANTS:
            if not isinstance(raw_field, bool):
                raise CloneValidationError(
                    f"native {branch_name}.{field} must be boolean"
                )
        elif field not in BRANCH_DECIMAL_INVARIANTS:
            _require_native_json_int(
                f"native {branch_name}.{field}",
                raw_field,
                minimum=0,
            )
    invariants = _normalize_branch_invariants(
        branch_name, raw_invariants
    )
    metrics = _normalize_metrics(branch_name, value["metrics"])
    if invariants != dict(expected_invariants):
        raise CloneValidationError(
            f"native {branch_name} invariants differ from the CSV row"
        )
    if metrics != dict(expected_metrics):
        raise CloneValidationError(
            f"native {branch_name} metrics differ from the CSV row"
        )
    normalized = {
        "start_state_sha256": start_state_sha,
        "start_state_components": normalized_components,
        "terminal_state_sha256": terminal_state_sha,
        "terminal_state_components": normalized_terminal_components,
        "branch_finalized": branch_finalized,
        "completed_affected_bag_ids": completed_affected,
        "completed_horizon_entity_ids": completed_horizon,
        "stop_reason": stop_reason,
        "replay_hashes": normalized_replay,
        "invariants": invariants,
        "metrics": metrics,
    }
    expected_branch_sha = canonical_sha256(
        {
            "schema": NATIVE_BRANCH_SCHEMA,
            "branch": branch_name,
            **normalized,
        }
    )
    if value["branch_record_sha256"] != expected_branch_sha:
        raise CloneValidationError(
            f"native {branch_name} branch_record_sha256 mismatch"
        )
    normalized["branch_record_sha256"] = expected_branch_sha
    return normalized


def validate_native_evidence_record(
    value: object,
    *,
    root: Path,
    generator_provenance: Mapping[str, object],
    intervention_row: Mapping[str, object],
) -> dict[str, object]:
    """Validate one raw exact-binary checkpoint/baseline/treatment record."""

    if not isinstance(value, Mapping):
        raise CloneValidationError("native evidence record must be an object")
    _require_exact_keys(value, NATIVE_RECORD_FIELDS, "native evidence record")
    if value["schema"] != NATIVE_EVIDENCE_SCHEMA:
        raise CloneValidationError("native evidence schema mismatch")
    if value["evidence_scope"] != (
        "EXACT_BINARY_ONE_SHOT_CAUSAL_RERUN_NOT_A_FORMAL_PASS"
    ):
        raise CloneValidationError("native evidence scope mismatch")
    if value["formal_pass_claimed"] is not False:
        raise CloneValidationError(
            "a raw native record must not claim a formal PASS"
        )

    binary_relative = _require_string(
        "generator runtime_binary_path",
        generator_provenance.get("runtime_binary_path"),
    )
    bound_binary = (root / binary_relative).resolve()
    if not bound_binary.is_file():
        raise CloneValidationError("bound native runtime binary is missing")
    bound_binary_sha = _require_sha256(
        "generator runtime_binary_sha256",
        generator_provenance.get("runtime_binary_sha256"),
    )
    if sha256_file(bound_binary) != bound_binary_sha:
        raise CloneValidationError("bound native runtime binary hash mismatch")
    actual_binary_text = _require_string(
        "actual_loaded_cpp_binary_path",
        value["actual_loaded_cpp_binary_path"],
    )
    actual_binary = Path(actual_binary_text)
    if not actual_binary.is_absolute() or actual_binary.resolve() != bound_binary:
        raise CloneValidationError(
            "actual loaded C++ binary path differs from the bound binary"
        )
    actual_binary_sha = _require_sha256(
        "actual_loaded_cpp_binary_sha256",
        value["actual_loaded_cpp_binary_sha256"],
    )
    if actual_binary_sha != bound_binary_sha:
        raise CloneValidationError(
            "actual loaded C++ binary SHA-256 differs from provenance"
        )

    inputs = value["inputs"]
    if not isinstance(inputs, Mapping):
        raise CloneValidationError("native inputs must be an object")
    _require_exact_keys(inputs, NATIVE_INPUT_FIELDS, "native input identity")
    if dict(inputs) != _expected_native_input_identity():
        raise CloneValidationError(
            "native record is not bound to canonical map/task at 1x"
        )
    controls = value["frozen_controls"]
    if not isinstance(controls, Mapping):
        raise CloneValidationError("frozen_controls must be an object")
    if dict(controls) != _expected_native_frozen_controls():
        raise CloneValidationError(
            "native record drifted from R3/S1/P2/C0/Q0/E4/M0 controls"
        )

    event_ordinal = _require_native_json_int(
        "event_ordinal", value["event_ordinal"], minimum=0
    )
    checkpoint = value["checkpoint"]
    if not isinstance(checkpoint, Mapping):
        raise CloneValidationError("native checkpoint must be an object")
    _require_exact_keys(
        checkpoint, NATIVE_CHECKPOINT_FIELDS, "native checkpoint"
    )
    raw_boundary = checkpoint["boundary"]
    if not isinstance(raw_boundary, Mapping):
        raise CloneValidationError(
            "native checkpoint boundary must be an object"
        )
    _require_exact_keys(
        raw_boundary, BOUNDARY_FIELDS, "native checkpoint boundary"
    )
    for field in (
        "baseline_release",
        "baseline_pibt_enabled",
        "queue_top_not_popped",
        "staged_event_sink_empty",
    ):
        if not isinstance(raw_boundary[field], bool):
            raise CloneValidationError(
                f"native checkpoint boundary {field} must be boolean"
            )
    for field in (
        "decision_event_seq",
        "node",
        "runtime_global_scan_count",
        "runtime_future_route_read_count",
        "runtime_future_schedule_read_count",
        "reservation_depth",
        "max_selected_edges_per_bag",
    ):
        _require_native_json_int(
            f"native checkpoint boundary {field}",
            raw_boundary[field],
            minimum=0,
        )
    for field in (
        "runtime_bag_id",
        "baseline_next_node",
        "pibt_owner_runtime_bag_id",
    ):
        _require_native_json_int(
            f"native checkpoint boundary {field}", raw_boundary[field]
        )
    for field in (
        "source_ready_order",
        "pending_merge_request_order",
        "legal_next_edges",
        *PIBT_SLICE_FIELDS,
    ):
        raw_values = raw_boundary[field]
        if not isinstance(raw_values, list) or any(
            not isinstance(item, int) or isinstance(item, bool)
            for item in raw_values
        ):
            raise CloneValidationError(
                f"native checkpoint boundary {field} must contain integers"
            )
    boundary = _validate_boundary(raw_boundary)
    for field in BOUNDARY_FIELDS:
        if boundary[field] != intervention_row[field]:
            raise CloneValidationError(
                f"native checkpoint boundary differs from CSV field {field}"
            )
    expected_checkpoint_sha = canonical_sha256(
        {
            "schema": NATIVE_EVIDENCE_SCHEMA,
            "event_ordinal": event_ordinal,
            "boundary": boundary,
        }
    )
    if checkpoint["checkpoint_record_sha256"] != expected_checkpoint_sha:
        raise CloneValidationError("checkpoint_record_sha256 mismatch")
    checkpoint_state_sha = str(boundary["runtime_state_sha256"])
    checkpoint_components = boundary["state_components"]
    assert isinstance(checkpoint_components, Mapping)

    raw_intervention = value["intervention"]
    if not isinstance(raw_intervention, Mapping):
        raise CloneValidationError(
            "native intervention record must be an object"
        )
    _require_exact_keys(
        raw_intervention,
        NATIVE_INTERVENTION_RECORD_FIELDS,
        "native intervention record",
    )
    expected_kind = str(intervention_row["intervention_kind"])
    if (
        raw_intervention["kind"] != expected_kind
        or raw_intervention["intervention_id"]
        != intervention_row["intervention_id"]
        or raw_intervention["intervention_token_sha256"]
        != intervention_row["intervention_token_sha256"]
        or raw_intervention["action"] != intervention_row["intervention"]
    ):
        raise CloneValidationError(
            "native intervention identity/action differs from the CSV row"
        )
    allowed_changed_fields = raw_intervention["allowed_changed_fields"]
    expected_changed_fields = list(
        INTERVENTION_ALLOWED_CHANGED_FIELDS[expected_kind]
    )
    if allowed_changed_fields != expected_changed_fields:
        raise CloneValidationError(
            "native intervention changed fields outside its one-shot scope"
        )
    normalized_intervention = {
        "kind": expected_kind,
        "intervention_id": intervention_row["intervention_id"],
        "intervention_token_sha256": intervention_row[
            "intervention_token_sha256"
        ],
        "action": dict(intervention_row["intervention"]),
        "allowed_changed_fields": expected_changed_fields,
    }

    raw_horizon = value["horizon"]
    if not isinstance(raw_horizon, Mapping):
        raise CloneValidationError("native horizon must be an object")
    _require_exact_keys(raw_horizon, NATIVE_HORIZON_FIELDS, "native horizon")
    affected_bag_ids = list(
        _require_id_list(
            "native horizon affected_bag_ids",
            raw_horizon["affected_bag_ids"],
        )
    )
    horizon_entity_ids = list(
        _require_id_list(
            "native horizon horizon_entity_ids",
            raw_horizon["horizon_entity_ids"],
        )
    )
    if (
        raw_horizon["kind"] != intervention_row["horizon"]
        or affected_bag_ids != intervention_row["raw_bag_ids"]
        or horizon_entity_ids != intervention_row["horizon_entity_ids"]
        or raw_horizon["horizon_entity_set_sha256"]
        != intervention_row["horizon_entity_set_sha256"]
    ):
        raise CloneValidationError(
            "native horizon identity differs from the CSV row"
        )
    normalized_horizon = {
        "kind": intervention_row["horizon"],
        "affected_bag_ids": affected_bag_ids,
        "horizon_entity_ids": horizon_entity_ids,
        "horizon_entity_set_sha256": intervention_row[
            "horizon_entity_set_sha256"
        ],
    }
    tags = _normalize_priority_cohort_tags(value["priority_cohort_tags"])
    stop_reason = (
        "AFFECTED_BAGS_COMPLETE"
        if intervention_row["horizon"] == "H_bag"
        else "SELECTED_COHORT_DRAINED"
    )
    baseline = _validate_native_branch(
        value["baseline"],
        branch_name="baseline",
        horizon_kind=str(intervention_row["horizon"]),
        checkpoint_state_sha256=checkpoint_state_sha,
        checkpoint_components=checkpoint_components,
        affected_bag_ids=affected_bag_ids,
        horizon_entity_ids=horizon_entity_ids,
        stop_reason=stop_reason,
        expected_invariants=intervention_row["baseline_invariants"],
        expected_metrics=intervention_row["baseline_metrics"],
    )
    treatment = _validate_native_branch(
        value["treatment"],
        branch_name="treatment",
        horizon_kind=str(intervention_row["horizon"]),
        checkpoint_state_sha256=checkpoint_state_sha,
        checkpoint_components=checkpoint_components,
        affected_bag_ids=affected_bag_ids,
        horizon_entity_ids=horizon_entity_ids,
        stop_reason=stop_reason,
        expected_invariants=intervention_row["treatment_invariants"],
        expected_metrics=intervention_row["treatment_metrics"],
    )
    if baseline["invariants"]["intervention_hit_count"] != 0:
        raise CloneValidationError(
            "native baseline branch consumed an intervention token"
        )
    if treatment["invariants"]["intervention_hit_count"] != 1:
        raise CloneValidationError(
            "native treatment branch did not apply exactly one intervention"
        )
    if not (
        baseline["start_state_sha256"]
        == treatment["start_state_sha256"]
        == checkpoint_state_sha
        and baseline["start_state_components"]
        == treatment["start_state_components"]
        == dict(checkpoint_components)
    ):
        raise CloneValidationError(
            "native baseline/treatment branches have different start states"
        )

    normalized = {
        "schema": NATIVE_EVIDENCE_SCHEMA,
        "evidence_scope": (
            "EXACT_BINARY_ONE_SHOT_CAUSAL_RERUN_NOT_A_FORMAL_PASS"
        ),
        "formal_pass_claimed": False,
        "actual_loaded_cpp_binary_path": actual_binary_text,
        "actual_loaded_cpp_binary_sha256": actual_binary_sha,
        "inputs": dict(inputs),
        "frozen_controls": dict(controls),
        "event_ordinal": event_ordinal,
        "checkpoint": {
            "boundary": boundary,
            "checkpoint_record_sha256": expected_checkpoint_sha,
        },
        "intervention": normalized_intervention,
        "horizon": normalized_horizon,
        "priority_cohort_tags": tags,
        "baseline": baseline,
        "treatment": treatment,
    }
    expected_native_sha = canonical_sha256(normalized)
    if value["native_record_sha256"] != expected_native_sha:
        raise CloneValidationError("native_record_sha256 mismatch")
    if intervention_row["native_record_sha256"] != expected_native_sha:
        raise CloneValidationError(
            "intervention CSV row does not bind its raw native record"
        )
    normalized["native_record_sha256"] = expected_native_sha
    return normalized


def validate_native_evidence_records(
    records: Sequence[Mapping[str, object]],
    intervention_rows: Sequence[Mapping[str, object]],
    *,
    root: Path,
    generator_provenance: Mapping[str, object],
) -> dict[str, object]:
    rows_by_native_sha: dict[str, Mapping[str, object]] = {}
    for row in intervention_rows:
        native_sha = _require_sha256(
            "intervention native_record_sha256",
            row["native_record_sha256"],
        )
        if native_sha in rows_by_native_sha:
            raise CloneValidationError(
                "multiple intervention rows bind the same native record"
            )
        rows_by_native_sha[native_sha] = row
    normalized_records: list[dict[str, object]] = []
    seen: set[str] = set()
    cohort_bags: dict[str, set[str]] = {
        cohort: set() for cohort in PRIORITY_COHORTS
    }
    for raw in records:
        declared_sha = _require_sha256(
            "native evidence native_record_sha256",
            raw.get("native_record_sha256"),
        )
        if declared_sha in seen:
            raise CloneValidationError("duplicate raw native evidence record")
        expected_row = rows_by_native_sha.get(declared_sha)
        if expected_row is None:
            raise CloneValidationError(
                "raw native evidence record is not bound by an intervention row"
            )
        normalized = validate_native_evidence_record(
            raw,
            root=root,
            generator_provenance=generator_provenance,
            intervention_row=expected_row,
        )
        normalized_records.append(normalized)
        seen.add(declared_sha)
        affected = set(normalized["horizon"]["affected_bag_ids"])
        for cohort in normalized["priority_cohort_tags"]:
            cohort_bags[cohort].update(affected)
    missing_records = sorted(set(rows_by_native_sha) - seen)
    if missing_records:
        raise CloneValidationError(
            "intervention rows lack raw native evidence records: "
            f"{missing_records[:3]}"
        )
    record_hashes = sorted(seen)
    return {
        "native_record_count": len(normalized_records),
        "native_record_manifest_sha256": canonical_sha256(record_hashes),
        "priority_cohort_coverage_summary": {
            cohort: len(cohort_bags[cohort]) for cohort in PRIORITY_COHORTS
        },
    }


def _expected_provenance() -> dict[str, object]:
    return {
        "map": {
            "path": CANONICAL_MAP_PATH,
            "raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        },
        "task": {
            "path": CANONICAL_TASK_PATH,
            "raw_sha256": CANONICAL_TASK_SHA256,
            "semantic_sha256": CANONICAL_TASK_SHA256,
            "segment_count": CANONICAL_SEGMENT_COUNT,
            "raw_bag_count": CANONICAL_RAW_BAG_COUNT,
        },
        "frozen_g4irsf13_policy": {
            "path": FROZEN_G13_POLICY_PATH,
            "file_sha256": FROZEN_G13_POLICY_FILE_SHA256,
        },
        "frozen_g4e_model": {
            "path": FROZEN_G13_MODEL_PATH,
            "file_sha256": FROZEN_G13_MODEL_FILE_SHA256,
        },
        "g4irsf13_per_bag_delta": {
            "path": G13_PER_BAG_PATH,
            "file_sha256": G13_PER_BAG_FILE_SHA256,
        },
        "g4irsf13_associative_delay_ledger": {
            "path": G13_DELAY_LEDGER_PATH,
            "file_sha256": G13_DELAY_LEDGER_FILE_SHA256,
        },
        "workload": {
            "demand_scale": "1.0",
            "expanded_workload_used": False,
        },
    }


def _validate_provenance(
    provenance: object,
    root: Path,
) -> dict[str, object]:
    if not isinstance(provenance, Mapping):
        raise CloneValidationError("manifest provenance must be an object")
    expected = _expected_provenance()
    if provenance != expected:
        raise CloneValidationError(
            "manifest provenance is not the canonical <=1x G13-frozen tuple"
        )
    for descriptor in (
        expected["map"],
        expected["task"],
        expected["frozen_g4irsf13_policy"],
        expected["frozen_g4e_model"],
        expected["g4irsf13_per_bag_delta"],
        expected["g4irsf13_associative_delay_ledger"],
    ):
        path = root / str(descriptor["path"])
        if not path.is_file():
            raise CloneValidationError(f"protected provenance file missing: {path}")
        expected_raw = str(
            descriptor.get("raw_sha256", descriptor.get("file_sha256"))
        )
        if sha256_file(path) != expected_raw:
            raise CloneValidationError(f"protected provenance drift: {path}")
    if semantic_text_sha256(root / CANONICAL_MAP_PATH) != (
        CANONICAL_MAP_SEMANTIC_SHA256
    ):
        raise CloneValidationError("canonical map semantic hash drift")
    if semantic_text_sha256(root / CANONICAL_TASK_PATH) != CANONICAL_TASK_SHA256:
        raise CloneValidationError("canonical task semantic hash drift")
    return expected


def _canonical_input_id(label: str, value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise CloneValidationError(f"canonical input {label} has invalid identity")
    rendered = str(value)
    if not rendered or rendered.strip() != rendered:
        raise CloneValidationError(
            f"canonical input {label} has non-canonical identity"
        )
    return rendered


def _load_input_identity_index(
    root: Path,
) -> dict[str, dict[str, set[str]]]:
    index: dict[str, dict[str, set[str]]] = {}
    row_count = 0
    task_path = root / CANONICAL_TASK_PATH
    with task_path.open("r", encoding="utf-8", newline="") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise CloneValidationError(
                    f"canonical task row {line_number} is invalid JSON"
                ) from error
            if not isinstance(record, Mapping):
                raise CloneValidationError(
                    f"canonical task row {line_number} is not an object"
                )
            for field in ("pallet_id", "task_id", "segment_id"):
                if field not in record:
                    raise CloneValidationError(
                        f"canonical task row {line_number} lacks {field}"
                    )
            bag_id = _canonical_input_id("pallet_id", record["pallet_id"])
            task_id = _canonical_input_id("task_id", record["task_id"])
            segment_id = _canonical_input_id(
                "segment_id", record["segment_id"]
            )
            entry = index.setdefault(
                bag_id, {"task_ids": set(), "segment_ids": set()}
            )
            entry["task_ids"].add(task_id)
            entry["segment_ids"].add(segment_id)
            row_count += 1
    if row_count != CANONICAL_SEGMENT_COUNT:
        raise CloneValidationError("canonical task segment denominator drift")
    if len(index) != CANONICAL_RAW_BAG_COUNT:
        raise CloneValidationError("canonical task raw-bag denominator drift")
    return index


def validate_input_identity_bindings(
    rows: Sequence[Mapping[str, object]],
    root: Path,
) -> None:
    """Rebuild bag→task/segment membership; reject partial identity claims."""

    index = _load_input_identity_index(root)
    known_bags = set(index)
    for row in rows:
        affected = set(str(value) for value in row["raw_bag_ids"])
        horizon = set(str(value) for value in row["horizon_entity_ids"])
        missing = sorted((affected | horizon) - known_bags)
        if missing:
            raise CloneValidationError(
                f"intervention references unknown canonical bags: {missing[:3]}"
            )
        expected_tasks = sorted(
            {
                task
                for bag_id in affected
                for task in index[bag_id]["task_ids"]
            }
        )
        expected_segments = sorted(
            {
                segment
                for bag_id in affected
                for segment in index[bag_id]["segment_ids"]
            }
        )
        if list(row["raw_task_ids"]) != expected_tasks:
            raise CloneValidationError(
                "raw_task_ids omit or add canonical affected-bag identities"
            )
        if list(row["segment_ids"]) != expected_segments:
            raise CloneValidationError(
                "segment_ids omit or add canonical affected-bag identities"
            )


def _resolve_bound_file(root: Path, label: str, value: object) -> tuple[str, Path]:
    relative_text = _require_string(label, value)
    relative = Path(relative_text)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != relative_text
    ):
        raise CloneValidationError(f"{label} must be a canonical relative path")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise CloneValidationError(f"{label} escapes the artifact root") from error
    if not resolved.is_file():
        raise CloneValidationError(f"{label} is missing: {relative_text}")
    return relative_text, resolved


def _validate_generator_provenance(
    value: object,
    root: Path,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise CloneValidationError("generator_provenance must be an object")
    fields = (
        "runtime_binary_path",
        "runtime_binary_sha256",
        "executor_source_path",
        "source_bundle_sha256",
        "source_files",
        "source_commit_sha",
        "executor_id",
    )
    _require_exact_keys(value, fields, "generator provenance")
    binary_relative, binary_path = _resolve_bound_file(
        root, "runtime_binary_path", value["runtime_binary_path"]
    )
    if not (
        binary_path.name.endswith(".exe")
        or binary_path.name.endswith(".pyd")
        or binary_path.name.endswith(".so")
        or binary_path.name.endswith(".dylib")
    ):
        raise CloneValidationError(
            "runtime_binary_path is not a native executable/module"
        )
    binary_sha = _require_sha256(
        "runtime_binary_sha256", value["runtime_binary_sha256"]
    )
    if sha256_file(binary_path) != binary_sha:
        raise CloneValidationError("runtime binary file hash mismatch")
    raw_source_files = value["source_files"]
    if not isinstance(raw_source_files, list) or not raw_source_files:
        raise CloneValidationError("source_files must be a non-empty array")
    source_files: list[dict[str, str]] = []
    for index, raw in enumerate(raw_source_files):
        if not isinstance(raw, Mapping):
            raise CloneValidationError(f"source file {index} must be an object")
        _require_exact_keys(
            raw,
            ("path", "semantic_sha256", "git_blob_oid"),
            f"source file {index}",
        )
        relative_text, source_path = _resolve_bound_file(
            root, f"source_files[{index}].path", raw["path"]
        )
        declared = _require_sha256(
            f"source_files[{index}].semantic_sha256",
            raw["semantic_sha256"],
        )
        if semantic_text_sha256(source_path) != declared:
            raise CloneValidationError(
                f"generator source file hash mismatch: {relative_text}"
            )
        blob_oid = raw["git_blob_oid"]
        if not isinstance(blob_oid, str) or re.fullmatch(
            r"[0-9a-f]{40}", blob_oid
        ) is None:
            raise CloneValidationError(
                f"source_files[{index}].git_blob_oid is malformed"
            )
        source_files.append(
            {
                "path": relative_text,
                "semantic_sha256": declared,
                "git_blob_oid": blob_oid,
            }
        )
    if source_files != sorted(source_files, key=lambda item: item["path"]):
        raise CloneValidationError("source_files are not in canonical path order")
    source_paths = [item["path"] for item in source_files]
    if len(source_paths) != len(set(source_paths)):
        raise CloneValidationError("source_files contain duplicate paths")
    required_sources = {
        "CMakeLists.txt",
        "cpp/ics_core/io/canonical_map2_reader.hpp",
        "cpp/ics_core/runtime/bounded_local_pibt.hpp",
        "cpp/ics_core/runtime/event_driven_junction.hpp",
        "cpp/ics_core/runtime/expiring_first_edge_credit.hpp",
        "cpp/ics_core/runtime/g4irsf14_state_clone.hpp",
        "cpp/ics_core/runtime/destination_merge_grant.hpp",
        "cpp/ics_core/bindings/czr005_cpp.cpp",
        "src/czr005/cpp_backend.py",
    }
    missing_sources = sorted(required_sources - set(source_paths))
    if missing_sources:
        raise CloneValidationError(
            f"generator source bundle is incomplete: {missing_sources}"
        )
    executor_source, _ = _resolve_bound_file(
        root, "executor_source_path", value["executor_source_path"]
    )
    if executor_source not in source_paths:
        raise CloneValidationError(
            "executor_source_path is not bound by source_files"
        )
    source_bundle_sha = canonical_sha256(source_files)
    if value["source_bundle_sha256"] != source_bundle_sha:
        raise CloneValidationError("source_bundle_sha256 mismatch")
    normalized = {
        "runtime_binary_path": binary_relative,
        "runtime_binary_sha256": binary_sha,
        "executor_source_path": executor_source,
        "source_bundle_sha256": source_bundle_sha,
        "source_files": source_files,
        "source_commit_sha": value["source_commit_sha"],
        "executor_id": _require_string("executor_id", value["executor_id"]),
    }
    if not isinstance(normalized["source_commit_sha"], str) or re.fullmatch(
        r"[0-9a-f]{40}", normalized["source_commit_sha"]
    ) is None:
        raise CloneValidationError("source_commit_sha must be a full commit SHA")
    lowered = normalized["executor_id"].lower()
    if "level_a" in lowered or "projection" in lowered:
        raise CloneValidationError(
            "associative/Level-A executor cannot generate causal labels"
        )
    try:
        actual_head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise CloneValidationError(
            "cannot independently resolve repository HEAD"
        ) from error
    source_commit = str(normalized["source_commit_sha"])
    try:
        ancestor = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "merge-base",
                "--is-ancestor",
                source_commit,
                actual_head,
            ],
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise CloneValidationError(
            "cannot verify source_commit_sha ancestry"
        ) from error
    if ancestor.returncode != 0:
        raise CloneValidationError(
            "source_commit_sha is not an ancestor of checked-out HEAD"
        )
    for descriptor in source_files:
        try:
            actual_blob_oid = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "rev-parse",
                    f"{source_commit}:{descriptor['path']}",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
            source_diff = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "diff",
                    "--quiet",
                    source_commit,
                    "--",
                    descriptor["path"],
                ],
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise CloneValidationError(
                "cannot read bound source blob at source_commit_sha: "
                f"{descriptor['path']}"
            ) from error
        if actual_blob_oid != descriptor["git_blob_oid"]:
            raise CloneValidationError(
                "source git blob OID mismatch: "
                f"{descriptor['path']}"
            )
        if source_diff.returncode != 0:
            raise CloneValidationError(
                "worktree source differs from source_commit_sha: "
                f"{descriptor['path']}"
            )
    return normalized


def _validate_preregistration(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise CloneValidationError("preregistration must be an object")
    fields = (
        "opportunity_manifest_sha256",
        "campaign_seed_sha256",
        "requested_matched_intervention_count",
        "requested_system_horizon_count",
        "registered_opportunities",
    )
    _require_exact_keys(value, fields, "campaign preregistration")
    raw_registered = value["registered_opportunities"]
    if not isinstance(raw_registered, list):
        raise CloneValidationError(
            "registered_opportunities must be an ordered array"
        )
    registration_fields = (
        "clone_group_id",
        "intervention_id",
        "intervention_token_sha256",
        "horizon",
        "split",
        "horizon_entity_set_sha256",
    )
    registered: list[dict[str, str]] = []
    for index, raw in enumerate(raw_registered):
        if not isinstance(raw, Mapping):
            raise CloneValidationError(
                f"registered opportunity {index} must be an object"
            )
        _require_exact_keys(
            raw, registration_fields, f"registered opportunity {index}"
        )
        horizon = raw["horizon"]
        split = raw["split"]
        if horizon not in FORMAL_HORIZONS:
            raise CloneValidationError(
                "registered opportunity has a non-formal horizon"
            )
        if split not in SPLITS:
            raise CloneValidationError(
                "registered opportunity has an invalid split"
            )
        registered.append(
            {
                "clone_group_id": _require_sha256(
                    "registered clone_group_id", raw["clone_group_id"]
                ),
                "intervention_id": _require_sha256(
                    "registered intervention_id", raw["intervention_id"]
                ),
                "intervention_token_sha256": _require_sha256(
                    "registered intervention_token_sha256",
                    raw["intervention_token_sha256"],
                ),
                "horizon": str(horizon),
                "split": str(split),
                "horizon_entity_set_sha256": _require_sha256(
                    "registered horizon_entity_set_sha256",
                    raw["horizon_entity_set_sha256"],
                ),
            }
        )
    canonical_registered = sorted(
        registered,
        key=lambda item: (
            item["intervention_token_sha256"],
            item["clone_group_id"],
        ),
    )
    if registered != canonical_registered:
        raise CloneValidationError(
            "registered opportunities are not in canonical content order"
        )
    tokens = [
        item["intervention_token_sha256"] for item in registered
    ]
    if len(tokens) != len(set(tokens)):
        raise CloneValidationError("duplicate pre-registered causal token")
    if len(registered) < MIN_MATCHED_INTERVENTIONS:
        raise CloneValidationError(
            "pre-registered matched intervention count is below 2000"
        )
    system_count = sum(
        item["horizon"] == "H_system" for item in registered
    )
    if system_count <= 0:
        raise CloneValidationError(
            "pre-registered system-horizon count is zero"
        )
    requested_count = _require_int(
        "requested_matched_intervention_count",
        value["requested_matched_intervention_count"],
        minimum=MIN_MATCHED_INTERVENTIONS,
    )
    requested_system_count = _require_int(
        "requested_system_horizon_count",
        value["requested_system_horizon_count"],
        minimum=1,
    )
    if requested_count != len(registered):
        raise CloneValidationError(
            "requested intervention count differs from registry"
        )
    if requested_system_count != system_count:
        raise CloneValidationError(
            "requested system-horizon count differs from registry"
        )
    opportunity_manifest_sha = canonical_sha256(registered)
    if value["opportunity_manifest_sha256"] != opportunity_manifest_sha:
        raise CloneValidationError(
            "opportunity_manifest_sha256 does not bind the registry"
        )
    normalized = {
        "opportunity_manifest_sha256": opportunity_manifest_sha,
        "campaign_seed_sha256": _require_sha256(
            "campaign_seed_sha256", value["campaign_seed_sha256"]
        ),
        "requested_matched_intervention_count": requested_count,
        "requested_system_horizon_count": requested_system_count,
        "registered_opportunities": registered,
    }
    return normalized


def _validate_priority_cohort_coverage(
    value: object,
    derived: Mapping[str, object],
) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise CloneValidationError(
            "priority_cohort_coverage_summary must be an object"
        )
    _require_exact_keys(
        value, PRIORITY_COHORTS, "priority cohort coverage summary"
    )
    normalized = {
        cohort: _require_int(
            f"priority cohort {cohort}", value[cohort], minimum=0
        )
        for cohort in PRIORITY_COHORTS
    }
    expected = {
        cohort: _require_int(
            f"derived priority cohort {cohort}",
            derived.get(cohort),
            minimum=0,
        )
        for cohort in PRIORITY_COHORTS
    }
    if normalized != expected:
        raise CloneValidationError(
            "priority cohort coverage summary is not derived from native rows"
        )
    if normalized["top_1_percent_delta_286"] < 286:
        raise CloneValidationError(
            "priority cohort coverage omits top-1% delta bags"
        )
    missing = [
        cohort
        for cohort in PRIORITY_COHORTS
        if cohort != "top_1_percent_delta_286"
        and normalized[cohort] <= 0
    ]
    if missing:
        raise CloneValidationError(
            f"priority cohort coverage is incomplete: {missing}"
        )
    return normalized


def _validate_sampling_funnel(
    value: object,
    campaign: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise CloneValidationError("sampling_funnel must be an object")
    _require_exact_keys(value, SAMPLING_FUNNEL_FIELDS, "sampling funnel")
    normalized: dict[str, object] = {}
    for field in SAMPLING_FUNNEL_FIELDS:
        if field.endswith("_sha256"):
            normalized[field] = _require_sha256(field, value[field])
        else:
            normalized[field] = _require_int(field, value[field], minimum=0)
    static_count = int(normalized["static_opportunity_count"])
    local_count = int(normalized["h_local_screened_count"])
    bag_count = int(normalized["h_bag_completed_count"])
    system_count = int(normalized["h_system_completed_count"])
    if not static_count >= local_count >= bag_count >= system_count:
        raise CloneValidationError(
            "sampling funnel counts are not monotone "
            "static->H_local->H_bag->H_system"
        )
    if bag_count != campaign["matched_intervention_count"]:
        raise CloneValidationError(
            "H_bag-complete funnel denominator differs from matched labels"
        )
    if system_count != campaign["h_system_count"] or system_count <= 0:
        raise CloneValidationError(
            "H_system funnel denominator differs from formal labels"
        )
    return normalized


def _validate_report(report: str, summary: Mapping[str, object]) -> None:
    required = (
        f"G4IRSF14-E STATUS: {PROTOCOL_STATUS}",
        "exact-binary no-op fidelity mechanism: available",
        "formal exact-binary I1-I5 one-shot reruns: not established",
        "original-task 2000/H_system formal evidence: not established",
        (
            "clone replay fidelity: 100% "
            f"({summary['fidelity_exact_match_count']}/"
            f"{summary['fidelity_clone_count']})"
        ),
        (
            "protocol-validated matched intervention rows: "
            f"{summary['matched_intervention_count']}"
        ),
        (
            "content-addressed native rerun records: "
            f"{summary['native_record_count']}"
        ),
        f"H_bag labels: {summary['h_bag_count']}",
        f"H_system labels: {summary['h_system_count']}",
        "H_local formal labels: 0",
        "workload ceiling: 1x",
        "Level-A used as causal label: no",
    )
    missing = [token for token in required if token not in report]
    if missing:
        raise CloneValidationError(
            f"matched-state report lacks recomputed claims: {missing}"
        )


def _expected_manifest_summary(
    campaign: Mapping[str, object],
    ledger: Mapping[str, object],
    native_evidence: Mapping[str, object],
) -> dict[str, object]:
    fields = (
        "fidelity_clone_count",
        "fidelity_exact_match_count",
        "clone_replay_fidelity",
        "matched_intervention_count",
        "complete_label_count",
        "unique_intervention_count",
        "h_local_label_count",
        "h_bag_count",
        "h_system_count",
        "intervention_kind_counts",
        "split_component_count",
        "non_improving_intervention_count",
        "fidelity_manifest_sha256",
        "intervention_manifest_sha256",
        "campaign_manifest_sha256",
    )
    return {
        **{field: campaign[field] for field in fields},
        "ledger_row_count": ledger["ledger_row_count"],
        "ledger_manifest_sha256": ledger["ledger_manifest_sha256"],
        "native_record_count": native_evidence["native_record_count"],
        "native_record_manifest_sha256": native_evidence[
            "native_record_manifest_sha256"
        ],
    }


def validate_artifact_protocol(root: Path) -> dict[str, object]:
    """Validate six bound artifacts without granting a formal causal PASS."""

    root = root.resolve()
    manifest_path = root / MANIFEST_PATH
    if not manifest_path.is_file():
        raise CloneValidationError(f"required artifact missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CloneValidationError("clone manifest is invalid JSON") from error
    if not isinstance(manifest, Mapping):
        raise CloneValidationError("clone manifest must be an object")
    manifest_fields = (
        "schema",
        "stage",
        "status",
        "provenance",
        "generator_provenance",
        "preregistration",
        "priority_cohort_coverage_summary",
        "sampling_funnel",
        "campaign_identity_sha256",
        "artifact_bindings",
        "summary",
        "claim_boundary",
        "self_sha256",
    )
    _require_exact_keys(manifest, manifest_fields, "clone manifest")
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise CloneValidationError("clone manifest schema mismatch")
    if (
        manifest["stage"] != "G4IRSF14-E"
        or manifest["status"] != PROTOCOL_STATUS
    ):
        raise CloneValidationError(
            f"clone manifest must remain {PROTOCOL_STATUS}"
        )
    if manifest["claim_boundary"] != (
        "MATCHED_RUNTIME_STATE_CLONE_CAUSAL_LABELS_ONLY"
    ):
        raise CloneValidationError("clone manifest claim boundary mismatch")
    provenance = _validate_provenance(manifest["provenance"], root)
    generator = _validate_generator_provenance(
        manifest["generator_provenance"], root
    )
    preregistration = _validate_preregistration(manifest["preregistration"])

    unsigned = dict(manifest)
    declared_self = unsigned.pop("self_sha256")
    if not _is_sha256(declared_self):
        raise CloneValidationError("manifest self_sha256 is malformed")
    if declared_self != canonical_sha256(unsigned):
        raise CloneValidationError("manifest self_sha256 mismatch")

    bindings = manifest["artifact_bindings"]
    expected_binding_paths = {
        REPORT_PATH,
        FIDELITY_PATH,
        INTERVENTION_PATH,
        LEDGER_PATH,
        NATIVE_EVIDENCE_PATH,
    }
    if not isinstance(bindings, Mapping):
        raise CloneValidationError("artifact_bindings must be an object")
    _require_exact_keys(bindings, expected_binding_paths, "artifact bindings")
    for relative in sorted(expected_binding_paths):
        declared = _require_sha256(
            f"artifact binding {relative}", bindings[relative]
        )
        path = root / relative
        if not path.is_file() or sha256_file(path) != declared:
            raise CloneValidationError(f"artifact binding mismatch: {relative}")

    fidelity_rows = _read_csv(
        root / FIDELITY_PATH,
        FIDELITY_COLUMNS,
        _decode_fidelity_csv_row,
    )
    intervention_rows = _read_csv(
        root / INTERVENTION_PATH,
        INTERVENTION_COLUMNS,
        _decode_intervention_csv_row,
    )
    campaign = validate_campaign(fidelity_rows, intervention_rows)
    normalized_interventions = [
        validate_intervention_row(row) for row in intervention_rows
    ]
    validate_input_identity_bindings(normalized_interventions, root)
    native_rows = _read_canonical_jsonl(root / NATIVE_EVIDENCE_PATH)
    native_evidence = validate_native_evidence_records(
        native_rows,
        normalized_interventions,
        root=root,
        generator_provenance=generator,
    )
    priority_coverage = _validate_priority_cohort_coverage(
        manifest["priority_cohort_coverage_summary"],
        native_evidence["priority_cohort_coverage_summary"],
    )
    sampling_funnel = _validate_sampling_funnel(
        manifest["sampling_funnel"], campaign
    )
    campaign_identity = canonical_sha256(
        {
            "schema": MANIFEST_SCHEMA,
            "provenance": provenance,
            "generator_provenance": generator,
            "preregistration": preregistration,
            "priority_cohort_coverage_summary": priority_coverage,
            "sampling_funnel": sampling_funnel,
        }
    )
    if manifest["campaign_identity_sha256"] != campaign_identity:
        raise CloneValidationError("campaign identity hash mismatch")
    observed_registration = sorted(
        [
            {
                "clone_group_id": str(row["clone_group_id"]),
                "intervention_id": str(row["intervention_id"]),
                "intervention_token_sha256": str(
                    row["intervention_token_sha256"]
                ),
                "horizon": str(row["horizon"]),
                "split": str(row["split"]),
                "horizon_entity_set_sha256": str(
                    row["horizon_entity_set_sha256"]
                ),
            }
            for row in normalized_interventions
        ],
        key=lambda item: (
            item["intervention_token_sha256"],
            item["clone_group_id"],
        ),
    )
    if preregistration["registered_opportunities"] != observed_registration:
        raise CloneValidationError(
            "protocol rows do not match the complete content-addressed registry"
        )
    ledger_rows = _read_csv(root / LEDGER_PATH, LEDGER_COLUMNS)
    ledger = validate_ledger_rows(ledger_rows, normalized_interventions)
    expected_summary = _expected_manifest_summary(
        campaign, ledger, native_evidence
    )
    if manifest["summary"] != expected_summary:
        raise CloneValidationError(
            "manifest summary does not equal independently recomputed evidence"
        )
    report = (root / REPORT_PATH).read_text(encoding="utf-8")
    _validate_report(report, expected_summary)
    return {
        "schema": MANIFEST_SCHEMA,
        "status": PROTOCOL_STATUS,
        "noop_exact_binary_fidelity_mechanism": "AVAILABLE",
        "formal_exact_binary_i1_i5_one_shot_reruns": "NOT_ESTABLISHED",
        "original_task_2000_h_system_formal_evidence": "NOT_ESTABLISHED",
        "manifest_self_sha256": declared_self,
        "campaign_identity_sha256": campaign_identity,
        "priority_cohort_coverage_summary": priority_coverage,
        "sampling_funnel": sampling_funnel,
        **expected_summary,
    }


def validate_artifacts(root: Path) -> dict[str, object]:
    """Fail closed until exact-binary causal reruns and formal evidence exist.

    The protocol validator now binds raw native checkpoint/baseline/treatment
    records to the actual loaded binary and the CSV rows.  A content-addressed
    record is still not an independent re-execution by the validator.  Formal
    PASS remains closed until the canonical original-task campaign exists and
    an independent exact-binary rerun verifier reproduces all accepted rows.
    """

    validate_artifact_protocol(root)
    raise CloneValidationError(
        f"{FORMAL_CAUSAL_BLOCKER}: "
        "content-addressed native records are protocol evidence, not an "
        "independent exact-binary reproduction or formal causal PASS"
    )
