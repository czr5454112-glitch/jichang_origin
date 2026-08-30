#!/usr/bin/env python3
"""Frozen V3R11 synthetic Stage0/Stage1 runner; import has no native/write side effect.

The V3R2 safety population and V3R8 identification cohort are preserved.  The
V3R9/V3R10 evidence fixes are retained by the V3R11 evidence revision.
This runner cannot issue the final Nanning-inclusive GO by itself.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import heapq
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence
ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / 'src'):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))
from czr005.g4irsf32_v3r2_outcome_join import JOINED, join_v3r2_outcomes
from scripts.eval import g4irsf31_map_adapter as map_adapter
PROTOCOL_PATH = ROOT / 'docs/G4IRSF32_v3r3_measurement_semantics_protocol.md'
REGISTRATION_PATH = ROOT / 'docs/G4IRSF32_v3r3_execution_registration.md'
V3R2_PROTOCOL_PATH = ROOT / 'docs/G4IRSF32_v3r2_minimal_protocol.md'
LEDGER_PATH = ROOT / 'docs/G4IRSF32_execution_ledger.md'
EVIDENCE_GAP_CLOSURE_PATH = ROOT / 'docs/G4IRSF32_evidence_gap_closure.md'
HELDOUT_PREREGISTRATION_PATH = ROOT / 'docs/G4IRSF32_scl_heldout_preregistration.md'
USER_CONTRACT_MANIFEST_PATH = ROOT / 'docs/G4IRSF32_user_contract_manifest.md'
USER_ACTION_PLAN_PATH = ROOT / 'docs/contracts/G4IRSF32_cross_map_next_stage_action_plan_20260826.md'
USER_G31_AUDIT_PACK_PATH = ROOT / 'docs/contracts/g4irsf31_audit_evidence_pack_20260826.md'
USER_CONTRACT_FILES = (
    (USER_ACTION_PLAN_PATH, 67791, 'e84b71cc919f77e1f8c9927163f7f7baeb8fdf254b20d28f95569165d68fe1f4'),
    (USER_G31_AUDIT_PACK_PATH, 4771, '7be33410690713a223cd58844616491bb5747b94d0263854f9dbe225ba825140'),
)
TELEMETRY_ADDENDUM_PATH = ROOT / 'docs/G4IRSF32_v3r4_p0_telemetry_completeness_addendum.md'
V3R5_COMMIT_ALIGNED_ADDENDUM_PATH = ROOT / 'docs/G4IRSF32_v3r5_commit_aligned_nanning_p0_addendum.md'
V3R6_BOUNDED_ADDENDUM_PATH = ROOT / 'docs/G4IRSF32_v3r6_bounded_commit_aligned_nanning_p0_addendum.md'
COMMIT_ALIGNED_ADDENDUM_PATH = ROOT / 'docs/G4IRSF32_v3r7_minimal_prearrival_overlap_nanning_p0_addendum.md'
IDENTIFICATION_ADDENDUM_PATH = ROOT / 'docs/G4IRSF32_v3r8_identifiable_synthetic_p0_addendum.md'
STAGE0_METADATA_PARITY_ADDENDUM_PATH = ROOT / 'docs/G4IRSF32_v3r9_stage0_metadata_parity_addendum.md'
PAIR_BINDING_ADDENDUM_PATH = ROOT / 'docs/G4IRSF32_v3r10_pair_binding_addendum.md'
DEEP_REPLAY_COMPATIBILITY_ADDENDUM_PATH = ROOT / 'docs/G4IRSF32_v3r11_deep_replay_compatibility_addendum.md'
NANNING_SELECTOR_PATH = ROOT / 'scripts/eval/run_g4irsf32_v3r3_nanning_p0_selection.py'
NANNING_SELECTOR_TEST_PATH = ROOT / 'tests/test_g4irsf32_v3r3_nanning_p0_selection.py'
NANNING_CONTROL_SELECTION_PATH = ROOT / 'outputs/tables/g4irsf32_v3r7_nanning_p0_control_selection.json'
RUNNER_PATH = Path(__file__).resolve()
JOIN_PATH = ROOT / 'src/czr005/g4irsf32_v3r2_outcome_join.py'
COMPOSER_PATH = ROOT / 'scripts/eval/run_g4irsf32_v3r3_p0_campaign.py'
COMPOSER_TEST_PATH = ROOT / 'tests/test_g4irsf32_v3r3_p0_campaign.py'
PROTOCOL_ID = 'G4IRSF32_EXTERNAL_COMMIT_LOCAL_VIRTUAL_SLOT_SHADOW_P0_V3R3'
REGISTRATION_ID = 'G4IRSF32_V3R3_EXECUTION_REGISTRATION_20260827'
V3R2_PROTOCOL_ID = 'G4IRSF32_EXTERNAL_COMMIT_LOCAL_VIRTUAL_SLOT_SHADOW_P0_STAGE0_STAGE1_V3R2'
TELEMETRY_ADDENDUM_ID = 'G4IRSF32_V3R4_P0_TELEMETRY_COMPLETENESS_ADDENDUM_20260827'
COMMIT_ALIGNED_ADDENDUM_ID = 'G4IRSF32_V3R7_MINIMAL_PREARRIVAL_OVERLAP_NANNING_P0_ADDENDUM_20260828'
IDENTIFICATION_ADDENDUM_ID = 'G4IRSF32_V3R8_IDENTIFIABLE_SYNTHETIC_P0_20260828'
STAGE0_METADATA_PARITY_ADDENDUM_ID = 'G4IRSF32_V3R9_STAGE0_METADATA_PARITY_P0_20260828'
PAIR_BINDING_ADDENDUM_ID = 'G4IRSF32_V3R10_PAIR_BINDING_P0_20260829'
SYNTHETIC_REVISION_ID = 'G4IRSF32_V3R11_DEEP_REPLAY_COMPATIBILITY_P0_20260829'
CAMPAIGN_REVISION_ID = 'G4IRSF32_V3R11_P0_CAMPAIGN_20260829'
IMPLEMENTATION_PARENT = '46cc46ab6bc121628fd6357e9f3c7636745fd732'
PROTOCOL_SHA256 = 'ac4c92b3e3090254799b1c12c723786d3a4116bbc9c1c1aaf6bf454afc5e5c1e'
REGISTRATION_SHA256 = '8264616947c6f84d97a2b7642bcbac07dbd45a54c5df17b8f0829ed511e5face'
V3R2_PROTOCOL_SHA256 = 'd24f9d3a33fdb0edc2c60a20fb0d246ca4e10ce88d936c361b0ef3e6b69f8d5e'
TELEMETRY_ADDENDUM_SHA256 = '6817ff59f2001a9605e8fcf29a06d28dcb1a51e7e3aea00f819003bce6ff9811'
COMMIT_ALIGNED_ADDENDUM_SHA256 = '1733b7311d996eef27ac70097c11984d90d9e929b5e49c9fb6645bd471537531'
IDENTIFICATION_ADDENDUM_SHA256 = '6805fc99b22c8db3669b030702a62deb1f7f1f65611da8ab63d4e110dd7db286'
STAGE0_METADATA_PARITY_ADDENDUM_SHA256 = 'fe5ab0824ae3b385216db802e19dabeb6aa7cc89ec4da6cfac7e301c03fd48b9'
PAIR_BINDING_ADDENDUM_SHA256 = '3a3311f0ef6c371d7f9a8a0d90074a32d3071765a2227b406bca0f972be705e0'
DEEP_REPLAY_COMPATIBILITY_ADDENDUM_SHA256 = '1ff586be4316e98999fcee1c05e5275b0fe6233928de2cebe20b2f3a129a3ba5'
SCHEMA = 'czr005.g4irsf32.external_commit_local_virtual.v3r11'
ORDINARY_TRACE_SCHEMA_ID = 'czr005.g4irsf11.decision_trace.v1'
TRACE_SCHEMA_ID = 'czr005.g4irsf32.external_commit_local_virtual_slot_shadow.v3r4'
ROW_KEY = 'source_aware_destination_service_shadow'
MODE = 'shadow'
OUTPUT_JSON = ROOT / 'outputs/tables/g4irsf32_v3r11_synthetic_stage01.json'
OUTPUT_MD = ROOT / 'outputs/reports/g4irsf32_v3r11_synthetic_stage01.md'
G31_BINARY = Path('C:\\tmp\\g4irsf32_v3r2_g31_build\\python\\Release\\czr005_cpp.cp311-win_amd64.pyd')
G31_BINARY_SHA256 = '35a43037b0881aca3b92732541126ee71c2d431d537a13e07918777c8b7cce59'
G32_BINARY_GLOB = ROOT / 'build_g32_v3r2/python/Release'
NATIVE_PROOF_EXE = ROOT / 'build_g32_v3r2/Release/test_event_driven_junction.exe'
NATIVE_PROOF_PREFIX = 'G4IRSF32_V3R2_NATIVE_PROOF_JSON='
NATIVE_PROOF_SCHEMA = 'czr005.g4irsf32.native_proof.v3r2'
NATIVE_PROOF_TEST_ID = 'g4irsf32_v3r2_focused_native'
NATIVE_PROOF_ASSERTIONS = ('pure_calendar_helper', 'generic_storage_role_validation', 'direct_unique_publish', 'j2_unique_publish', 'j2_direct_duplicate_suppressed', 'direct_after_stage_rollback_exact', 'j2_after_stage_rollback_exact', 'trace_limit_fail_before_commit', 'action_inert_invariants')
NESTED_PROOF_EXE = ROOT / 'build_g32_v3r2/Release/test_destination_merge_grant_real_map.exe'
NESTED_PROOF_PREFIX = 'G4IRSF32_V3R2_NESTED_PROOF_JSON='
NESTED_PROOF_SCHEMA = 'czr005.g4irsf32.nested_proof.v3r2'
NESTED_PROOF_TEST_ID = 'g4irsf32_v3r2_nested_j2_pibt'
NESTED_PROOF_ASSERTION = 'nested_shadow_budget'
WORKER_PREFIX = 'G4IRSF32_V3R2_OFF_WORKER_JSON='
MAP2_PATH = ROOT / 'data/processed/maps/map2.json'
MAP2_WORKLOAD_PATH = ROOT / 'data/processed/tasks/inputdata.jsonl'
MAP2_RAW_SHA256 = '9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4'
MAP2_PROFILE_SHA256 = '3659dffdaf412739a69066b6c79dba4b83e4e3144612235f335f7c7aa5a7e323'
MAP2_POTENTIAL_SHA256 = 'c96d2095404d042558858d175db460af1faf378853a8ebdac9a92767e617e006'
MAP2_ROWS_SHA256 = '96f5d5447275fee06b8d9234b42f5b57004f0617304d08a89d19aa3a646e4803'
MAP2_SEGMENTS = tuple((f'{index}:{leg}' for index in range(4) for leg in ('storage_in', 'storage_out')))
MAP2_SCENARIO = 'g4irsf32_v3r2_map2_sentinel'
FINAL_GO = 'GO_V3R11_EXTERNAL_COMMIT_LOCAL_VIRTUAL_RELATION_AND_NANNING_P1_REVIEW_ALLOWED'
SYNTHETIC_PASS = 'V3R11_SYNTHETIC_P0_PASS_NANNING_PENDING'
NO_GO = 'NO_GO_V3R11_EXTERNAL_COMMIT_LOCAL_VIRTUAL_NOT_SUPPORTED'
STAGE0_NO_GO = 'NO_GO_V3R11_STAGE0_CONTRACT'
STAGE0_PASS = 'V3R11_STAGE0_PASS'
FORMAL_EXECUTION_BLOCKED_REASON = ''
LEGACY_WAIT_THRESHOLD = 120.0
SERVICE_SECONDS = (1.0, 1.5, 2.0, 3.0)
BAG_COUNTS = (8, 32, 128)
FLOW_PATTERNS = ('external_only', 'local_only', 'simultaneous_local_first', 'simultaneous_external_first', 'local_burst_first', 'external_burst_first', 'alternating_local_first', 'alternating_external_first', 'local_backlog_external_sparse', 'external_backlog_local_sparse')
NEGATIVE_CONTROLS = frozenset({'external_only', 'local_only'})
MIXED_FLOWS = frozenset(FLOW_PATTERNS) - NEGATIVE_CONTROLS
TASK_BASE = 32032000
IDENTIFICATION_TASK_BASE = TASK_BASE + 128 * 120
IDENTIFICATION_FLOW_PATTERNS = tuple(f'identification_p{index}' for index in range(4))
IDENTIFICATION_DELTAS_US = {
    'identification_p0': (12_500, 25_000, 37_500),
    'identification_p1': (25_000, 37_500, 12_500),
    'identification_p2': (37_500, 12_500, 25_000),
    'identification_p3': (37_500, 25_000, 12_500),
}
IDENTIFICATION_INITIAL_US = 10_000_000
IDENTIFICATION_TRAVEL_US = 50_000
IDENTIFICATION_STORAGE_US = 1_000
EPSILON = 1e-09
RESOURCE_RATIO_LIMIT = 1.1
BOOTSTRAP_SEED = 3200260827
BOOTSTRAP_DRAWS = 10000
WILSON_Z = 1.959963984540054
MIN_DIRECTIONAL_CASES = 24
MIN_PRIMARY_BAGS = 128
MIN_MIXED_FLOWS = 4
NS = 'source_aware_destination_service_'
CENSUS_PARTS = ('no_local_count', 'local_guard_fail_count', 'non_overlap_count', 'staged_rollback_count', 'observation_stored_count', 'observation_dropped_count')
SHADOW_ZERO = ('action_change_count', 'calendar_mutation_count', 'future_release_read_count', 'global_scan_count')
SOURCE_BUNDLE_PATHS = (
    ROOT / '.gitattributes',
    PROTOCOL_PATH, REGISTRATION_PATH, V3R2_PROTOCOL_PATH, LEDGER_PATH,
    EVIDENCE_GAP_CLOSURE_PATH, HELDOUT_PREREGISTRATION_PATH, USER_CONTRACT_MANIFEST_PATH,
    USER_ACTION_PLAN_PATH, USER_G31_AUDIT_PACK_PATH,
    TELEMETRY_ADDENDUM_PATH,
    V3R5_COMMIT_ALIGNED_ADDENDUM_PATH, V3R6_BOUNDED_ADDENDUM_PATH,
    COMMIT_ALIGNED_ADDENDUM_PATH, IDENTIFICATION_ADDENDUM_PATH,
    STAGE0_METADATA_PARITY_ADDENDUM_PATH, PAIR_BINDING_ADDENDUM_PATH,
    DEEP_REPLAY_COMPATIBILITY_ADDENDUM_PATH,
    JOIN_PATH, RUNNER_PATH,
    COMPOSER_PATH,
    ROOT / 'scripts/eval/g4irsf11_fixed_map.py',
    ROOT / 'scripts/eval/g4irsf14_opportunity_census.py',
    ROOT / 'scripts/eval/g4irsf31_map_adapter.py',
    ROOT / 'scripts/eval/run_g4irsf26_paper_experiments.py',
    ROOT / 'scripts/eval/run_g4irsf27_fault_values.py',
    ROOT / 'scripts/eval/run_g4irsf28_service_potential.py',
    ROOT / 'scripts/eval/run_g4irsf31_map2_native.py',
    ROOT / 'scripts/eval/run_g4irsf31_nanning_native.py',
    NANNING_SELECTOR_PATH,
    ROOT / 'src/czr005/cpp_backend.py',
    ROOT / 'cpp/ics_core/bindings/czr005_cpp.cpp',
    ROOT / 'cpp/ics_core/runtime/event_driven_junction.hpp',
    ROOT / 'cpp/tests/test_event_driven_junction.cpp', ROOT / 'cpp/tests/test_destination_merge_grant_real_map.cpp', ROOT / 'CMakeLists.txt',
    ROOT / 'tests/test_g4irsf32_v3r2_runtime.py',
    ROOT / 'tests/test_g4irsf32_v3r2_outcome_join.py',
    ROOT / 'tests/test_g4irsf32_v3r2_external_commit_local_virtual_shadow.py',
    NANNING_SELECTOR_TEST_PATH,
    COMPOSER_TEST_PATH,
    MAP2_PATH, MAP2_WORKLOAD_PATH,
)
IMPLEMENTATION_ALLOWED_PATHS = frozenset({'.gitattributes', 'cpp/ics_core/runtime/event_driven_junction.hpp', 'cpp/ics_core/bindings/czr005_cpp.cpp', 'src/czr005/cpp_backend.py', 'src/czr005/g4irsf32_v3r2_outcome_join.py', 'scripts/eval/run_g4irsf32_v3r2_external_commit_local_virtual_shadow.py', 'scripts/eval/run_g4irsf32_v3r3_nanning_p0_selection.py', 'scripts/eval/run_g4irsf32_v3r3_p0_campaign.py', 'cpp/tests/test_event_driven_junction.cpp', 'cpp/tests/test_destination_merge_grant_real_map.cpp', 'tests/test_g4irsf32_v3r2_runtime.py', 'tests/test_g4irsf32_v3r2_outcome_join.py', 'tests/test_g4irsf32_v3r2_external_commit_local_virtual_shadow.py', 'tests/test_g4irsf32_v3r3_nanning_p0_selection.py', 'tests/test_g4irsf32_v3r3_p0_campaign.py', 'docs/G4IRSF32_v3r2_minimal_protocol.md', 'docs/G4IRSF32_v3r3_measurement_semantics_protocol.md', 'docs/G4IRSF32_v3r3_execution_registration.md', 'docs/G4IRSF32_execution_ledger.md', 'docs/G4IRSF32_evidence_gap_closure.md', 'docs/G4IRSF32_scl_heldout_preregistration.md', 'docs/G4IRSF32_v3r4_p0_telemetry_completeness_addendum.md', 'docs/G4IRSF32_v3r5_commit_aligned_nanning_p0_addendum.md', 'docs/G4IRSF32_v3r6_bounded_commit_aligned_nanning_p0_addendum.md', 'outputs/tables/g4irsf32_v3r3_nanning_p0_control_selection_attempt1_no_go.json', 'outputs/tables/g4irsf32_v3r3_nanning_p0_control_selection_attempt2_no_go.json', 'outputs/tables/g4irsf32_v3r3_nanning_p0_control_selection_attempt3_no_go.json', 'outputs/tables/g4irsf32_v3r3_nanning_p0_control_selection_attempt4_no_event.json', 'outputs/tables/g4irsf32_v3r3_nanning_p0_control_selection.json', 'outputs/tables/g4irsf32_v3r5_nanning_p0_control_selection_attempt1_audit_failed.json', 'outputs/tables/g4irsf32_v3r5_nanning_p0_control_selection.json', 'outputs/tables/g4irsf32_v3r6_nanning_p0_control_selection.json', 'outputs/tables/g4irsf32_v3r3_external_commit_local_virtual_shadow.json', 'outputs/reports/g4irsf32_v3r3_external_commit_local_virtual_shadow.md', 'outputs/tables/g4irsf32_source_aware_shadow.json', 'outputs/reports/g4irsf32_source_aware_shadow.md'})
IMPLEMENTATION_ALLOWED_PATHS = IMPLEMENTATION_ALLOWED_PATHS | frozenset({
    'docs/G4IRSF32_v3r7_minimal_prearrival_overlap_nanning_p0_addendum.md',
    'docs/G4IRSF32_v3r8_identifiable_synthetic_p0_addendum.md',
    'docs/G4IRSF32_v3r9_stage0_metadata_parity_addendum.md',
    'docs/G4IRSF32_v3r10_pair_binding_addendum.md',
    'docs/G4IRSF32_v3r11_deep_replay_compatibility_addendum.md',
    'docs/G4IRSF32_user_contract_manifest.md',
    'docs/contracts/G4IRSF32_cross_map_next_stage_action_plan_20260826.md',
    'docs/contracts/g4irsf31_audit_evidence_pack_20260826.md',
    'outputs/tables/g4irsf32_v3r6_nanning_p0_control_selection_attempt1_audit_failed.json',
    'outputs/tables/g4irsf32_v3r7_nanning_p0_control_selection.json',
    'outputs/tables/g4irsf32_v3r7_synthetic_stage01_attempt1_no_go.json',
    'outputs/tables/g4irsf32_v3r7_p0_campaign_attempt1_no_go.json',
    'outputs/reports/g4irsf32_v3r7_p0_campaign_attempt1_no_go.md',
    'outputs/tables/g4irsf32_v3r8_synthetic_stage01.json',
    'outputs/reports/g4irsf32_v3r8_synthetic_stage01.md',
    'outputs/tables/g4irsf32_v3r8_p0_campaign.json',
    'outputs/reports/g4irsf32_v3r8_p0_campaign.md',
    'outputs/tables/g4irsf32_v3r9_synthetic_stage01.json',
    'outputs/reports/g4irsf32_v3r9_synthetic_stage01.md',
    'outputs/tables/g4irsf32_v3r9_p0_campaign.json',
    'outputs/reports/g4irsf32_v3r9_p0_campaign.md',
    'outputs/tables/g4irsf32_v3r10_synthetic_stage01.json',
    'outputs/reports/g4irsf32_v3r10_synthetic_stage01.md',
    'outputs/tables/g4irsf32_v3r10_p0_campaign.json',
    'outputs/reports/g4irsf32_v3r10_p0_campaign.md',
    'outputs/tables/g4irsf32_v3r11_synthetic_stage01.json',
    'outputs/reports/g4irsf32_v3r11_synthetic_stage01.md',
    'outputs/tables/g4irsf32_v3r11_p0_campaign.json',
    'outputs/reports/g4irsf32_v3r11_p0_campaign.md',
})
Executor = Callable[..., Mapping[str, Any]]
Worker = Callable[[Mapping[str, Any], Path], Mapping[str, Any]]
@dataclass(frozen=True, order=True)
class V3R2Case:
    service_seconds: float
    bag_count: int
    flow_pattern: str

    @property
    def case_id(self) -> str:
        service = str(self.service_seconds).replace('.', 'p')
        return f'v3r2_{self.flow_pattern}__n{self.bag_count}__service_{service}s'

    @property
    def scenario(self) -> str:
        return f'g4irsf32_v3r2_{self.case_id}'
def registered_cases() -> tuple[V3R2Case, ...]:
    return tuple((V3R2Case(service, count, flow) for service in SERVICE_SECONDS for count in BAG_COUNTS for flow in FLOW_PATTERNS))

@dataclass(frozen=True, order=True)
class IdentificationCase:
    service_seconds: float
    bag_count: int
    replica: int
    permutation_index: int

    @property
    def flow_pattern(self) -> str:
        return IDENTIFICATION_FLOW_PATTERNS[self.permutation_index]

    @property
    def case_id(self) -> str:
        service = str(self.service_seconds).replace('.', 'p')
        return (
            f'v3r8_{self.flow_pattern}__n{self.bag_count}__'
            f'service_{service}s__r{self.replica}'
        )

    @property
    def scenario(self) -> str:
        return f'g4irsf32_{self.case_id}'

def identification_cases() -> tuple[IdentificationCase, ...]:
    cases = []
    for service_ordinal, service in enumerate(SERVICE_SECONDS):
        for population_ordinal, count in enumerate(BAG_COUNTS):
            for replica in range(2):
                permutation = (service_ordinal + population_ordinal + 2 * replica) % 4
                cases.append(IdentificationCase(service, count, replica, permutation))
    return tuple(cases)

def _case_ordinal(case: V3R2Case) -> int:
    try:
        return registered_cases().index(case)
    except ValueError as error:
        raise ValueError(f'unregistered V3R2 case: {case}') from error

def _identification_case_ordinal(case: IdentificationCase) -> int:
    try:
        return identification_cases().index(case)
    except ValueError as error:
        raise ValueError(f'unregistered V3R8 identification case: {case}') from error

def flow_schedule(case: V3R2Case) -> list[tuple[str, float]]:
    if case not in registered_cases():
        raise ValueError(f'unregistered V3R2 case: {case}')
    n, service, flow = (case.bag_count, case.service_seconds, case.flow_pattern)
    if flow == 'external_only':
        return [('external', 0.0)] * n
    if flow == 'local_only':
        return [('local', 0.0)] * n
    if flow.startswith('simultaneous_'):
        first = 'local' if flow.endswith('local_first') else 'external'
        other = 'external' if first == 'local' else 'local'
        return [(first if index % 2 == 0 else other, 0.0) for index in range(n)]
    if flow in {'local_burst_first', 'external_burst_first'}:
        first = 'local' if flow.startswith('local_') else 'external'
        other = 'external' if first == 'local' else 'local'
        return [(first, 0.0)] * (n // 2) + [(other, 0.25 * service)] * (n // 2)
    if flow.startswith('alternating_'):
        first = 'local' if flow.endswith('local_first') else 'external'
        other = 'external' if first == 'local' else 'local'
        return [(first if index % 2 == 0 else other, index // 2 * 0.2 * service) for index in range(n)]
    dominant = 'local' if flow.startswith('local_backlog') else 'external'
    sparse = 'external' if dominant == 'local' else 'local'
    return [(dominant, index * 0.05 * service) for index in range(3 * n // 4)] + [(sparse, (index + 0.5) * 1.5 * service) for index in range(n // 4)]

def build_bag_rows(case: V3R2Case, *, external_start: int=0) -> list[dict[str, Any]]:
    schedule = flow_schedule(case)
    deadline = max((release for _origin, release in schedule)) + (case.bag_count * case.service_seconds * 10.0 + 100.0)
    ordinals: Counter[str] = Counter()
    base = TASK_BASE + 128 * _case_ordinal(case)
    rows = []
    for index, (origin, release) in enumerate(schedule):
        ordinals[origin] += 1
        rows.append({'segment_id': f'{case.case_id}:{origin}:{ordinals[origin]:04d}', 'task_id': base + index, 'pass_time': float(release), 'std': float(deadline), 'start': external_start if origin == 'external' else 1, 'goal': 3, 'source': origin})
    return rows

def identification_schedule(case: IdentificationCase) -> list[tuple[str, int, str]]:
    if case not in identification_cases():
        raise ValueError(f'unregistered V3R8 identification case: {case}')
    service_us = round(case.service_seconds * 1_000_000)
    if service_us % 2:
        raise ValueError('identification service must have an exact half quantum')
    schedule: list[tuple[str, int, str]] = [
        ('local', IDENTIFICATION_INITIAL_US, 'L0')
    ]
    local_start = IDENTIFICATION_INITIAL_US
    for index, delta_us in enumerate(
        IDENTIFICATION_DELTAS_US[case.flow_pattern], start=1
    ):
        local_complete = local_start + service_us
        schedule.append(('local', local_start + service_us // 2, f'L{index}'))
        external_commit = local_complete - IDENTIFICATION_TRAVEL_US + delta_us
        schedule.append(
            ('external', external_commit - IDENTIFICATION_STORAGE_US, f'E{index}')
        )
        external_arrival = local_complete + delta_us
        local_start = external_arrival + service_us
    core_end = local_start + service_us
    for filler in range(case.bag_count - len(schedule)):
        release = core_end + 10 * service_us + filler * (2 * service_us + 1_000_000)
        schedule.append(('external', release, f'F{filler + 1:03d}'))
    if len(schedule) != case.bag_count:
        raise ValueError('identification schedule population mismatch')
    return schedule

def build_identification_bag_rows(
    case: IdentificationCase, *, external_start: int=0
) -> list[dict[str, Any]]:
    schedule = identification_schedule(case)
    deadline = max(release for _origin, release, _label in schedule) / 1_000_000
    deadline += case.bag_count * case.service_seconds * 10.0 + 100.0
    base = IDENTIFICATION_TASK_BASE + 128 * _identification_case_ordinal(case)
    rows = []
    for index, (origin, release_us, label) in enumerate(schedule):
        rows.append(
            {
                'segment_id': f'{case.case_id}:{label}',
                'task_id': base + index,
                'pass_time': release_us / 1_000_000,
                'std': float(deadline),
                'start': external_start if origin == 'external' else 1,
                'goal': 3,
                'source': origin,
            }
        )
    return rows

def motif_profile(service: float, *, j2: bool=False) -> map_adapter.RuntimeMapProfile:
    if service not in SERVICE_SECONDS:
        raise ValueError('service is outside the frozen population')
    nodes = ((0, 7, 0.0, 0, 0, (1,)), (1, 1, service, 1, 0, (2,)), (2, 4, 0.0, 2, 0, (3,)), (3, 2, 0.0, 3, 0, ()))
    edges = ((0, 1, 0.05, 1.0), (1, 2, 0.05, 1.0), (2, 3, 0.05, 1.0))
    if j2:
        nodes += ((4, 7, 0.0, 0, 1, (1,)),)
        edges += ((4, 1, 0.05, 1.0),)
    return map_adapter.RuntimeMapProfile(name=f'g4irsf32_v3r2_s{service}' + ('_j2' if j2 else ''), source_path=PROTOCOL_PATH, node_records=nodes, edge_records=edges, start_nodes=(0, 1, 4) if j2 else (0, 1), goal_nodes=(3,), storage_source_nodes=(0, 4) if j2 else (0,))
REQUEST_PROJECTION: Mapping[str, Any] = {'queue_discipline': 'fifo', 'retry_interval': 0.25, 'minimum_service_seconds': 0.001, 'dispatch_headway_seconds': 0.001, 'history_limit': 8, 'max_decisions_per_bag': 512, 'max_events': 2000000, 'max_simulation_time': -1.0, 'trace_limit': 200000, 'event_trace_limit': 200000, 'summary_only': False, 'trace_shard_count': 1, 'trace_shard_index': 0, 'local_queue_capacity': 0, 'deadlock_retry_threshold': 8, 'diagnostic_hops': 2, 'enable_source_admission': False, 'enable_backpressure': False, 'enable_pibt_lite': False, 'enable_deadlock_escape': True, 'enable_fault_policy': True, 'fault_windows': [], 'scale': 1.0, 'resource_semantics': 'R3_java_node_window_compatible', 'entry_headway_seconds': 0.001, 'pressure_mode': 'off', 'pressure_weight': 2.0, 'pressure_age_weight': 0.05, 'pressure_distance_bias': 0.25, 'admission_mode': 'off', 'credit_validity_seconds': 1.0, 'credit_snapshot_max_age_seconds': 1.0, 'credit_capacity_per_edge': 1, 'credit_lifecycle_limit': 512, 'pibt_mode': 'P2', 'pibt_max_depth': 2, 'pibt_max_ready_bags': 8, 'pibt_max_local_resources': 32, 'pibt_max_candidates_per_bag': 8, 'priority_mode': 'Q0', 'pibt_preference_mode': 'current', 'pibt_regret_prior_records': [], 'selective_credit_contention_threshold': 1, 'scorer_mode': 'S4_queue_aware_rule_only', 'framework_mode': 'event_loop_one_step', 'event_semantics': 'E4_batch_plus_destination_merge_request', 'merge_grant_rule': 'M3', 'merge_grant_timing_mode': 'jit_fair_aging_deadline', 'merge_grant_max_pending_requests': 256, 'merge_grant_lifecycle_limit': 8192, 'g4irsf20_event_hotpath_policy': 'E2', 'g4irsf16_supervisor_mode': 'off', 'enable_opportunity_telemetry': False, 'opportunity_trace_limit': 0, 'enable_s4_local_potential_descent_guard': True, 'enable_s4_direct_neighbor_merge_calendar_visibility': True, 'complete_on_goal_arrival': True, 'source_aware_destination_service_trace_limit': 200000}
REQUEST_DATA_KEYS = frozenset({'node_records', 'edge_records', 'heuristic_time', 'bag_records', 'scenario', 'source_aware_destination_service_mode', 'storage_source_nodes'})
REQUEST_BINARY_LOCATOR_KEYS = frozenset({'expected_binary_path', 'search_path'})
FROZEN_REQUEST_KEYS = frozenset(REQUEST_PROJECTION) | REQUEST_DATA_KEYS

def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')

def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()

def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()

def _binary_unchanged_gate(name: str, path: Path, expected: str) -> dict[str, Any]:
    try: actual, error = (file_sha256(path), None)
    except OSError as caught: actual, error = (None, f'{type(caught).__name__}: {caught}')
    return gate(name, actual == expected, {'expected': expected, 'actual': actual, 'error': error})

def _portable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {key: _portable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    return value

def request_sha256(request: Mapping[str, Any]) -> str:
    return canonical_sha256({key: _portable(value) for key, value in request.items() if key not in {'expected_binary_path', 'search_path'}})

def ordinary_request_sha256(request: Mapping[str, Any]) -> str:
    ignored = {'expected_binary_path', 'search_path', 'source_aware_destination_service_mode', 'source_aware_destination_service_trace_limit'}
    return canonical_sha256({key: _portable(value) for key, value in request.items() if key not in ignored})

def profile_sha256(request: Mapping[str, Any]) -> str:
    nodes = request.get('node_records', [])
    return canonical_sha256({'node_records': nodes, 'edge_records': request.get('edge_records', []), 'start_nodes': sorted((int(row[0]) for row in nodes if int(row[1]) in {1, 7})), 'goal_nodes': sorted((int(row[0]) for row in nodes if int(row[1]) == 2)), 'storage_source_nodes': request.get('storage_source_nodes', [])})

def _build_profile_request(profile: map_adapter.RuntimeMapProfile, rows: Sequence[Mapping[str, Any]], *, scenario: str, mode: str, binary: Path | None, edge_speed: float | None=None) -> tuple[dict[str, Any], dict[str, Any]]:
    if mode not in {'off', MODE}:
        raise ValueError(f'V3R2 supports only off|shadow, not {mode!r}')
    request, potential = map_adapter.build_s4_request(profile, rows, binary=binary, scenario=scenario, max_events=2000000, max_simulation_time=-1.0, trace_limit=200000, event_trace_limit=200000, summary_only=False, edge_speed_mps=edge_speed, enable_s4_local_potential_descent_guard=True, enable_s4_direct_neighbor_merge_calendar_visibility=True, complete_on_goal_arrival=True)
    request.update(source_aware_destination_service_mode=mode, source_aware_destination_service_trace_limit=200000, fault_windows=[])
    assert_request_projection(request, mode, list(profile.storage_source_nodes), scenario)
    return (request, potential)

def build_request(case: V3R2Case, *, mode: str, binary: Path | None=None, j2: bool=False) -> tuple[dict[str, Any], dict[str, Any]]:
    return _build_profile_request(motif_profile(case.service_seconds, j2=j2), build_bag_rows(case, external_start=4 if j2 else 0), scenario=case.scenario + ('__j2_fixture' if j2 else ''), mode=mode, binary=binary)

def build_identification_request(
    case: IdentificationCase, *, mode: str, binary: Path | None=None
) -> tuple[dict[str, Any], dict[str, Any]]:
    return _build_profile_request(
        motif_profile(case.service_seconds),
        build_identification_bag_rows(case),
        scenario=case.scenario,
        mode=mode,
        binary=binary,
    )

def assert_request_projection(request: Mapping[str, Any], mode: str, storage: list[int], scenario: str) -> None:
    expected = {**REQUEST_PROJECTION, 'storage_source_nodes': storage}
    mismatches = {key: {'expected': value, 'actual': request.get(key)} for key, value in expected.items() if request.get(key) != value}
    if request.get('source_aware_destination_service_mode') != mode:
        mismatches['source_aware_destination_service_mode'] = {'expected': mode, 'actual': request.get('source_aware_destination_service_mode')}
    if request.get('scenario') != scenario:
        mismatches['scenario'] = {'expected': scenario, 'actual': request.get('scenario')}
    starts = {int(row[0]) for row in request.get('node_records', []) if int(row[1]) in {1, 7}}
    if not storage or len(storage) != len(set(storage)) or (not set(storage) <= starts):
        mismatches['storage_source_nodes'] = {'expected': 'nonempty unique start subset', 'actual': storage}
    actual_keys = set(request)
    locator_keys = actual_keys & REQUEST_BINARY_LOCATOR_KEYS
    if locator_keys and locator_keys != REQUEST_BINARY_LOCATOR_KEYS:
        mismatches['binary_locator_keys'] = {'expected': sorted(REQUEST_BINARY_LOCATOR_KEYS), 'actual': sorted(locator_keys)}
    expected_keys = FROZEN_REQUEST_KEYS | (REQUEST_BINARY_LOCATOR_KEYS if locator_keys else frozenset())
    missing = expected_keys - actual_keys
    unexpected = actual_keys - expected_keys
    if missing:
        mismatches['missing_request_keys'] = sorted(missing, key=str)
    if unexpected:
        mismatches['unexpected_request_keys'] = sorted(unexpected, key=str)
    if mismatches:
        raise ValueError(f'request violates frozen V3R2 projection: {mismatches}')

def case_manifest(case: V3R2Case) -> dict[str, Any]:
    rows = build_bag_rows(case)
    return {'cohort': 'safety_regression', 'replica': None, 'case_id': case.case_id, 'scenario': case.scenario, 'service_seconds': case.service_seconds, 'bag_count': case.bag_count, 'flow_pattern': case.flow_pattern, 'negative_control': case.flow_pattern in NEGATIVE_CONTROLS, 'bag_rows': rows, 'bag_rows_sha256': canonical_sha256(rows)}

def identification_case_manifest(case: IdentificationCase) -> dict[str, Any]:
    rows = build_identification_bag_rows(case)
    expected_x = [
        case.service_seconds + delta_us / 1_000_000
        for delta_us in IDENTIFICATION_DELTAS_US[case.flow_pattern]
    ]
    return {'cohort': 'identification', 'replica': case.replica, 'case_id': case.case_id, 'scenario': case.scenario, 'service_seconds': case.service_seconds, 'bag_count': case.bag_count, 'flow_pattern': case.flow_pattern, 'negative_control': False, 'expected_x_insert_seconds': expected_x, 'bag_rows': rows, 'bag_rows_sha256': canonical_sha256(rows)}

def population_manifest() -> dict[str, Any]:
    identities = {
        'measurement_protocol': {'id': PROTOCOL_ID, 'path': PROTOCOL_PATH.relative_to(ROOT).as_posix(), 'sha256': file_sha256(PROTOCOL_PATH), 'expected_sha256': PROTOCOL_SHA256},
        'execution_registration': {'id': REGISTRATION_ID, 'path': REGISTRATION_PATH.relative_to(ROOT).as_posix(), 'sha256': file_sha256(REGISTRATION_PATH), 'expected_sha256': REGISTRATION_SHA256},
        'preserved_v3r2_protocol': {'id': V3R2_PROTOCOL_ID, 'path': V3R2_PROTOCOL_PATH.relative_to(ROOT).as_posix(), 'sha256': file_sha256(V3R2_PROTOCOL_PATH), 'expected_sha256': V3R2_PROTOCOL_SHA256},
        'telemetry_completeness_addendum': {'id': TELEMETRY_ADDENDUM_ID, 'path': TELEMETRY_ADDENDUM_PATH.relative_to(ROOT).as_posix(), 'sha256': file_sha256(TELEMETRY_ADDENDUM_PATH), 'expected_sha256': TELEMETRY_ADDENDUM_SHA256},
        'commit_aligned_nanning_addendum': {'id': COMMIT_ALIGNED_ADDENDUM_ID, 'path': COMMIT_ALIGNED_ADDENDUM_PATH.relative_to(ROOT).as_posix(), 'sha256': file_sha256(COMMIT_ALIGNED_ADDENDUM_PATH), 'expected_sha256': COMMIT_ALIGNED_ADDENDUM_SHA256},
        'identification_addendum': {'id': IDENTIFICATION_ADDENDUM_ID, 'path': IDENTIFICATION_ADDENDUM_PATH.relative_to(ROOT).as_posix(), 'sha256': file_sha256(IDENTIFICATION_ADDENDUM_PATH), 'expected_sha256': IDENTIFICATION_ADDENDUM_SHA256},
        'stage0_metadata_parity_addendum': {'id': STAGE0_METADATA_PARITY_ADDENDUM_ID, 'path': STAGE0_METADATA_PARITY_ADDENDUM_PATH.relative_to(ROOT).as_posix(), 'sha256': file_sha256(STAGE0_METADATA_PARITY_ADDENDUM_PATH), 'expected_sha256': STAGE0_METADATA_PARITY_ADDENDUM_SHA256},
        'pair_binding_addendum': {'id': PAIR_BINDING_ADDENDUM_ID, 'path': PAIR_BINDING_ADDENDUM_PATH.relative_to(ROOT).as_posix(), 'sha256': file_sha256(PAIR_BINDING_ADDENDUM_PATH), 'expected_sha256': PAIR_BINDING_ADDENDUM_SHA256},
        'deep_replay_compatibility_addendum': {'id': SYNTHETIC_REVISION_ID, 'path': DEEP_REPLAY_COMPATIBILITY_ADDENDUM_PATH.relative_to(ROOT).as_posix(), 'sha256': file_sha256(DEEP_REPLAY_COMPATIBILITY_ADDENDUM_PATH), 'expected_sha256': DEEP_REPLAY_COMPATIBILITY_ADDENDUM_SHA256},
    }
    drift = {name: value for name, value in identities.items() if value['sha256'] != value['expected_sha256']}
    if drift:
        raise ValueError(f'V3R3 protocol identity drift: {drift}')
    safety_cases = [case_manifest(case) for case in registered_cases()]
    identification = [
        identification_case_manifest(case) for case in identification_cases()
    ]
    cohorts = {
        'safety_regression': {
            'case_count': len(safety_cases),
            'cases': safety_cases,
            'cases_sha256': canonical_sha256(safety_cases),
        },
        'identification': {
            'case_count': len(identification),
            'cases': identification,
            'cases_sha256': canonical_sha256(identification),
        },
    }
    return {'schema': SCHEMA, 'protocol_id': PROTOCOL_ID, 'synthetic_revision_id': SYNTHETIC_REVISION_ID, 'campaign_revision_id': CAMPAIGN_REVISION_ID, 'historical_control_revision_id': COMMIT_ALIGNED_ADDENDUM_ID, 'implementation_parent': IMPLEMENTATION_PARENT, 'protocol_sha256': identities['measurement_protocol']['sha256'], 'protocol_identities': identities, 'native_row_schema_id': TRACE_SCHEMA_ID, 'native_row_schema_revision': 'V3R4_TELEMETRY_COMPLETENESS', 'services': list(SERVICE_SECONDS), 'bag_counts': list(BAG_COUNTS), 'safety_flows': list(FLOW_PATTERNS), 'identification_flows': list(IDENTIFICATION_FLOW_PATTERNS), 'task_bases': {'safety_regression': TASK_BASE, 'identification': IDENTIFICATION_TASK_BASE}, 'case_count': len(safety_cases) + len(identification), 'cohorts': cohorts, 'cohorts_sha256': canonical_sha256(cohorts)}

def map2_fixture(*, mode: str, binary: Path | None=None) -> tuple[dict[str, Any], dict[str, Any]]:
    from scripts.eval import run_g4irsf31_map2_native as map2
    profile = map2.map2_profile()
    workload = map2.load_workload(1)
    rows = [dict(row) for row in workload.rows[:8]]
    profile_value = {'node_records': profile.node_records, 'edge_records': profile.edge_records, 'start_nodes': profile.start_nodes, 'goal_nodes': profile.goal_nodes, 'storage_source_nodes': profile.storage_source_nodes}
    hashes = {'raw': file_sha256(MAP2_PATH), 'profile': canonical_sha256(profile_value), 'rows': canonical_sha256(rows)}
    if hashes != {'raw': MAP2_RAW_SHA256, 'profile': MAP2_PROFILE_SHA256, 'rows': MAP2_ROWS_SHA256} or tuple((row.get('segment_id') for row in rows)) != MAP2_SEGMENTS or len(profile.node_records) != 54 or (len(profile.edge_records) != 69) or (profile.storage_source_nodes != (52,)):
        raise ValueError(f'map2 frozen profile/workload drift: {hashes}')
    request, _contract = _build_profile_request(profile, rows, scenario=MAP2_SCENARIO, mode=mode, binary=binary, edge_speed=2.5)
    hashes['potential'] = canonical_sha256(request['heuristic_time'])
    if hashes['potential'] != MAP2_POTENTIAL_SHA256:
        raise ValueError(f"map2 frozen potential drift: {hashes['potential']}")
    return (request, {**hashes, 'segments': list(MAP2_SEGMENTS), 'storage_source_nodes': [52]})
INTEGER_FIELDS = ('observation_ordinal', 'opportunity_id', 'event_seq', 'node', 'calendar_generation_before', 'seam_kind_code', 'external_path_code', 'external_task_id', 'external_runtime_bag_id', 'external_upstream_node', 'external_direct_episode_event_seq', 'external_request_id', 'external_request_lineage', 'external_request_generation', 'external_junction_queue_generation', 'local_task_id', 'local_runtime_bag_id', 'local_source_ready_count', 'external_scheduled_incoming_count', 'destination_pending_count', 'local_choose_bag_index', 'local_escape_token_runtime_bag_id', 'selected_action_from_node', 'selected_action_to_node', 'selected_action_kind_code', 'local_origin_code', 'external_origin_code')
FLOAT_FIELDS = ('event_time', 'external_slot_start_seconds', 'external_slot_end_seconds', 'external_service_seconds', 'external_projected_arrival', 'local_service_seconds', 'local_source_uncovered_service_work_seconds', 'oldest_local_wait_age_seconds', 'oldest_external_wait_age_seconds', 'local_source_enqueued_at', 'local_release', 'local_deadline', 'L0', 'service_calendar_next_free_seconds', 'existing_calendar_wait_seconds', 'L1', 'X_insert', 'H_gap', 'overlap_seconds', 'epsilon')
FLAG_FIELDS = ('has_direct_episode_identity', 'has_j2_identity', 'local_queue_nonempty', 'local_bag_exists', 'local_released_live', 'local_source_queue_at_node', 'local_distinct_from_external', 'local_service_required', 'local_guards_passed', 'action_changed')
ZERO_COUNTERS = ('future_release_read_count', 'global_scan_count', 'calendar_mutation_count')
J2_FIELDS = ('external_request_id', 'external_request_lineage', 'external_request_generation', 'external_junction_queue_generation')

def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f'{label} must be an integer')
    return value

def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{label} must be numeric')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f'{label} must be finite')
    return result

def _flag(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    raise ValueError(f'{label} must be bool or integer 0|1')

def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f'{label} must be an object')
    return value

def _object_rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)) or not all((isinstance(row, Mapping) for row in value)):
        raise ValueError(f'{label} must be a sequence of objects')
    return list(value)

def _close(left: Any, right: Any, epsilon: float=EPSILON) -> bool:
    return math.isclose(_finite(left, 'left'), _finite(right, 'right'), rel_tol=0.0, abs_tol=epsilon)

def physical_commit_identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    path = _integer(row.get('external_path_code'), 'external_path_code')
    common = (_integer(row.get('external_runtime_bag_id'), 'external_runtime_bag_id'), _integer(row.get('external_task_id'), 'external_task_id'), _integer(row.get('external_upstream_node'), 'external_upstream_node'), _integer(row.get('node'), 'node'))
    if path == 1:
        return ('DIRECT', _integer(row.get('external_direct_episode_event_seq'), 'external_direct_episode_event_seq'), *common)
    if path == 2:
        return ('J2', *(_integer(row.get(field), field) for field in J2_FIELDS), *common)
    raise ValueError('external_path_code must be 1 or 2')

def normalize_numeric_rows(case_id: str, raw_rows: Any, service_by_node: Mapping[int, float], *, metadata: Mapping[str, Any] | None=None) -> list[dict[str, Any]]:
    if not isinstance(raw_rows, (list, tuple)):
        raise ValueError('V3R4 row vector must be a sequence')
    expected = set(INTEGER_FIELDS + FLOAT_FIELDS + FLAG_FIELDS + ZERO_COUNTERS)
    normalized = []
    for index, value in enumerate(raw_rows):
        if not isinstance(value, Mapping) or set(value) != expected:
            actual = set(value) if isinstance(value, Mapping) else set()
            raise ValueError(f'row[{index}] keys differ from frozen schema: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}')
        if any((isinstance(item, (str, bytes, list, tuple, dict)) for item in value.values())):
            raise ValueError(f'row[{index}] native fields must be scalar numeric/enum/bool')
        row = dict(value)
        for field in INTEGER_FIELDS + ZERO_COUNTERS:
            _integer(row[field], f'row[{index}].{field}')
        for field in FLOAT_FIELDS:
            _finite(row[field], f'row[{index}].{field}')
        flags = {field: _flag(row[field], f'row[{index}].{field}') for field in FLAG_FIELDS}
        node, path = (row['node'], row['external_path_code'])
        service = service_by_node.get(node)
        if service is None or service <= 0.0:
            raise ValueError(f'row[{index}] node has no frozen positive service')
        identity = (row['seam_kind_code'], path, flags['has_direct_episode_identity'], flags['has_j2_identity'])
        e0, e1, epsilon = (row['external_slot_start_seconds'], row['external_slot_end_seconds'], row['epsilon'])
        overlap = max(0.0, min(row['L0'] + service, e1) - max(row['L0'], e0))
        invariants = (identity in {(1, 1, True, False), (2, 2, False, True)}, path != 1 or all((row[field] == 0 for field in J2_FIELDS)), path != 2 or row['external_direct_episode_event_seq'] == 0, path != 1 or row['external_direct_episode_event_seq'] == row['event_seq'], path != 2 or all((row[field] > 0 for field in J2_FIELDS)), epsilon == EPSILON, abs(e1 - e0 - service) <= EPSILON, abs(row['external_service_seconds'] - service) <= EPSILON, abs(row['local_service_seconds'] - service) <= EPSILON, row['local_source_ready_count'] > 0, row['local_choose_bag_index'] < row['local_source_ready_count'], abs(row['local_source_uncovered_service_work_seconds'] - row['local_source_ready_count'] * service) <= EPSILON, row['external_scheduled_incoming_count'] >= 0, row['destination_pending_count'] >= 0, row['oldest_local_wait_age_seconds'] >= 0.0, row['oldest_external_wait_age_seconds'] >= 0.0, row['destination_pending_count'] != 0 or row['oldest_external_wait_age_seconds'] == 0.0, abs(row['service_calendar_next_free_seconds'] - row['L0']) <= EPSILON, row['existing_calendar_wait_seconds'] >= 0.0, abs(row['existing_calendar_wait_seconds'] - (row['L0'] - row['event_time'])) <= EPSILON, row['selected_action_from_node'] == row['external_upstream_node'], row['selected_action_to_node'] == node, row['selected_action_kind_code'] == row['seam_kind_code'], row['local_origin_code'] == 1, row['external_origin_code'] == 2, abs(row['L1'] - row['L0'] - row['X_insert']) <= EPSILON, abs(row['L1'] - e0 - row['H_gap']) <= EPSILON, abs(row['overlap_seconds'] - overlap) <= EPSILON, row['L0'] >= row['event_time'] - EPSILON, row['L1'] >= row['event_time'] - EPSILON, row['L1'] >= e1 - EPSILON, row['H_gap'] >= -EPSILON, row['X_insert'] > 0.0, row['overlap_seconds'] > 0.0, row['external_upstream_node'] >= 0, row['external_upstream_node'] != node, row['local_runtime_bag_id'] != row['external_runtime_bag_id'], row['local_release'] <= row['event_time'] + EPSILON, row['local_source_enqueued_at'] >= row['local_release'] - EPSILON, row['local_source_enqueued_at'] <= row['event_time'] + EPSILON, row['local_deadline'] + EPSILON >= row['event_time'], row['observation_ordinal'] > 0, row['opportunity_id'] > 0, row['event_seq'] > 0, row['calendar_generation_before'] >= 0, row['local_choose_bag_index'] >= 0, row['local_escape_token_runtime_bag_id'] >= -1, all((flags[field] for field in FLAG_FIELDS[2:-1])), not flags['action_changed'], all((row[field] == 0 for field in ZERO_COUNTERS)))
        if not all(invariants):
            raise ValueError(f'row[{index}] violates frozen V3R4 invariants')
        row.update(case_id=case_id, **dict(metadata or {}))
        normalized.append(row)
    ordinals = [row['observation_ordinal'] for row in normalized]
    physical_ids = [(row['case_id'], *physical_commit_identity(row)) for row in normalized]
    if ordinals != list(range(1, len(ordinals) + 1)):
        raise ValueError('V3R4 observation ordinals must be ordered, unique, and contiguous from one')
    if len(physical_ids) != len(set(physical_ids)):
        raise ValueError('V3R4 physical commit identity is not unique')
    return normalized

def _services(request: Mapping[str, Any]) -> dict[int, float]:
    minimum = _finite(request.get('minimum_service_seconds'), 'request.minimum_service_seconds')
    rows = request.get('node_records')
    if minimum <= 0.0 or not isinstance(rows, (list, tuple)):
        raise ValueError('request service profile is missing or invalid')
    services = {}
    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            raise ValueError(f'node_records[{index}] is malformed')
        node, raw = (_integer(row[0], f'node_records[{index}].node'), _finite(row[2], f'node_records[{index}].service'))
        if node in services or raw < 0.0:
            raise ValueError('request node service identity is duplicate or negative')
        services[node] = max(raw, minimum)
    if not services:
        raise ValueError('request has no service node')
    return services

def extract_rows(payload: Mapping[str, Any], *, case_id: str, request: Mapping[str, Any], metadata: Mapping[str, Any] | None=None) -> list[dict[str, Any]]:
    context = _mapping(payload.get('trace_context'), 'payload.trace_context')
    if context.get('schema_id') != ORDINARY_TRACE_SCHEMA_ID or context.get('source_aware_destination_service_schema_id') != TRACE_SCHEMA_ID:
        raise ValueError('payload lacks the sole namespaced V3R4 shadow schema')
    if ROW_KEY not in payload:
        raise ValueError(f'missing sole V3R4 row vector {ROW_KEY!r}')
    return normalize_numeric_rows(case_id, payload[ROW_KEY], _services(request), metadata=metadata)

def _ordinary_health(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    summary = _mapping(payload.get('summary'), 'payload.summary')
    context = _mapping(payload.get('trace_context'), 'payload.trace_context')
    decisions = _object_rows(payload.get('decisions'), 'payload.decisions')
    holds = _object_rows(payload.get('hold_attempts'), 'payload.hold_attempts')
    checks = (context.get('schema_id') == ORDINARY_TRACE_SCHEMA_ID, summary.get('event_trace_truncated') is False, summary.get('decision_trace_truncated') is False, _integer(summary.get('trace_shard_count'), 'trace_shard_count') == 1, _integer(summary.get('trace_shard_index'), 'trace_shard_index') == 0, _summary_int(summary, 'decision_trace_stored_count') == len(decisions), _summary_int(summary, 'hold_trace_stored_count') == len(holds), summary.get('event_limit_reached') is False, summary.get('time_limit_reached') is False)
    if not all(checks):
        raise ValueError('ordinary payload is incomplete, truncated, or sharded')
    return (summary, context)

def _base_episodes(case_id: str, payload: Mapping[str, Any], service_by_node: Mapping[int, float]) -> tuple[list[dict[str, Any]], list[Mapping[str, Any]], dict[int, Mapping[str, Any]]]:
    _ordinary_health(payload)
    bags = _object_rows(payload.get('bags'), 'payload.bags')
    events = _object_rows(payload.get('events'), 'payload.events')
    by_bag: dict[int, Mapping[str, Any]] = {}
    for index, bag in enumerate(bags):
        bag_id = _integer(bag.get('runtime_bag_id'), f'bags[{index}].runtime_bag_id')
        _integer(bag.get('task_id'), f'bags[{index}].task_id')
        if bag_id in by_bag:
            raise ValueError('duplicate runtime bag identity')
        by_bag[bag_id] = bag
    seen: set[int] = set()
    episodes = []
    for index, event in enumerate(events):
        seq = _integer(event.get('seq'), f'events[{index}].seq')
        if seq in seen:
            raise ValueError('ordinary event seq is not unique')
        seen.add(seq)
        if event.get('event') != 'JUNCTION_SERVICE_COMPLETE':
            continue
        node = _integer(event.get('node'), 'completion node')
        if node not in service_by_node:
            raise ValueError('service completion references a node outside the frozen profile')
        bag_id = _integer(event.get('runtime_bag_id'), 'completion bag')
        task_id = _integer(event.get('task_id'), 'completion task')
        bag = by_bag.get(bag_id)
        if bag is None or bag.get('task_id') != task_id or event.get('reason') != 'junction_service_complete' or (event.get('to_node') != node) or (_integer(event.get('from_node'), 'completion upstream') < -1):
            raise ValueError('service completion has inconsistent ordinary identity')
        complete = _finite(event.get('time'), 'completion time')
        start = complete - service_by_node[node]
        if start < -EPSILON:
            raise ValueError('service completion implies negative start')
        episodes.append({'case_id': case_id, 'runtime_bag_id': bag_id, 'node': node, 'completion_event_seq': seq, 'actual_L_service_start': start, 'actual_L_service_complete': complete})
    return (episodes, events, by_bag)

def _unique(rows: Sequence[Mapping[str, Any]], label: str) -> Mapping[str, Any]:
    if len(rows) != 1:
        raise ValueError(f'{label} must match exactly once, got {len(rows)}')
    return rows[0]

def build_service_episodes(case_id: str, payload: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], request: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Bind each row to unique ordinary DIRECT/J2 provenance and L completion."""
    summary, context = _ordinary_health(payload)
    if context.get('source_aware_destination_service_schema_id') != TRACE_SCHEMA_ID or summary.get(NS + 'mode') != MODE or summary.get('merge_grant_lifecycle_complete') is not True or (_integer(summary.get('merge_grant_lifecycle_dropped_count'), 'lifecycle dropped') != 0):
        raise ValueError('shadow/lifecycle telemetry is incomplete')
    services = _services(request)
    episodes, events, bags = _base_episodes(case_id, payload, services)
    decisions = _object_rows(payload.get('decisions'), 'payload.decisions')
    lifecycle = _object_rows(payload.get('merge_grant_lifecycle'), 'payload.merge_grant_lifecycle')

    def edge_event(event: Mapping[str, Any], row: Mapping[str, Any], kind: str, reason: str | None) -> bool:
        node, upstream = (row['node'], row['external_upstream_node'])
        expected_time = row['event_time'] if kind == 'EDGE_ENTER' else row['external_slot_start_seconds']
        return event.get('event') == kind and event.get('runtime_bag_id') == row['external_runtime_bag_id'] and (event.get('task_id') == row['external_task_id']) and (event.get('node') == (upstream if kind == 'EDGE_ENTER' else node)) and (event.get('from_node') == upstream) and (event.get('to_node') == node) and _close(event.get('time'), expected_time, row['epsilon']) and (reason is None or event.get('reason') == reason)
    for row in rows:
        epsilon, bag_id, task_id = (row['epsilon'], row['external_runtime_bag_id'], row['external_task_id'])
        upstream, node = (row['external_upstream_node'], row['node'])
        e0, e1, event_time = (row['external_slot_start_seconds'], row['external_slot_end_seconds'], row['event_time'])
        if bags.get(bag_id, {}).get('task_id') != task_id or not _close(row['external_projected_arrival'], e0, epsilon) or e0 < event_time - epsilon:
            raise ValueError('external row identity/arrival is inconsistent')
        completion = _unique([episode for episode in episodes if episode['runtime_bag_id'] == bag_id and episode['node'] == node and _close(episode['actual_L_service_start'], e0, epsilon) and _close(episode['actual_L_service_complete'], e1, epsilon)], 'external L completion')
        _unique([event for event in events if edge_event(event, row, 'EDGE_EXIT', None)], 'external EDGE_EXIT')
        if row['external_path_code'] == 1:
            commit_seq = row['external_direct_episode_event_seq']
            _unique([decision for decision in decisions if isinstance(decision.get('metadata'), Mapping) and decision['metadata'].get('trace_kind') == 'committed_edge_action' and (decision['metadata'].get('arrive_event_seq') == commit_seq) and (decision['metadata'].get('runtime_bag_id') == bag_id) and (decision.get('task_id') == task_id) and (decision.get('current_node') == upstream) and (decision.get('selected_next') == node) and _close(decision.get('event_time'), event_time, epsilon)], 'DIRECT committed decision')
            _unique([event for event in events if edge_event(event, row, 'EDGE_ENTER', 'one_step_reservation_committed')], 'DIRECT EDGE_ENTER')
            identity = {'direct_commit_event_seq': commit_seq}
        else:
            committed = _unique([item for item in lifecycle if item.get('state') == 'COMMITTED' and item.get('reason') == 'exact_slot_committed' and (item.get('request_id') == row['external_request_id']) and (item.get('lineage') == row['external_request_lineage']) and (item.get('request_generation') == row['external_request_generation']) and (item.get('junction_queue_generation') == row['external_junction_queue_generation']) and (item.get('runtime_bag_id') == bag_id) and (item.get('task_id') == task_id) and (item.get('upstream_node') == upstream) and (item.get('destination_node') == node) and (item.get('edge_from_node') == upstream) and (item.get('edge_to_node') == node) and _close(item.get('projected_arrival'), e0, epsilon) and _close(item.get('destination_service_seconds'), services[node], epsilon) and _close(item.get('slot_start'), e0, epsilon) and _close(item.get('slot_end'), e1, epsilon) and _close(item.get('time'), event_time, epsilon) and (item.get('observed_claimed_request_generation') == row['external_request_generation']) and (item.get('observed_claimed_junction_queue_generation') == row['external_junction_queue_generation']) and (item.get('observed_claimed_owner_runtime_bag_id') == bag_id) and (item.get('observed_claimed_edge_from_node') == upstream) and (item.get('observed_claimed_edge_to_node') == node) and (item.get('observed_claimed_destination_node') == node)], 'J2 committed lifecycle')
            generation = _integer(committed.get('calendar_generation'), 'J2 calendar generation')
            if generation != row['calendar_generation_before'] + 1 or committed.get('observed_claimed_calendar_generation') != generation:
                raise ValueError('J2 committed calendar generation mismatch')
            _unique([event for event in events if edge_event(event, row, 'EDGE_ENTER', 'one_step_merge_grant_committed')], 'J2 EDGE_ENTER')
            identity = {'request_id': row['external_request_id'], 'request_lineage': row['external_request_lineage'], 'request_generation': row['external_request_generation'], 'junction_queue_generation': row['external_junction_queue_generation'], 'slot_node': node, 'slot_start': e0, 'slot_end': e1, 'slot_calendar_generation_before': generation - 1}
        transit = max(0.0, e0 - event_time)
        external = {**identity, 'actual_subsequent_source_wait': 0.0, 'actual_subsequent_junction_wait': 0.0, 'actual_transit_seconds': transit, 'actual_subsequent_calendar_wait': 0.0, 'actual_subsequent_wait': transit}
        target = _unique([episode for episode in episodes if episode['completion_event_seq'] == completion['completion_event_seq']], 'external normalized episode')
        for field, value in external.items():
            if field in target and target[field] != value:
                raise ValueError('one service episode has conflicting external identity')
            target[field] = value
    return episodes

NONDETERMINISTIC_SUMMARY_KEYS = frozenset({'runtime_seconds', 'event_throughput_per_second', 'decision_latency_us_p50', 'decision_latency_us_p95', 'decision_latency_us_p99'})
ORDINARY_RESOURCE_SUMMARY_KEYS = frozenset({'cpp_internal_accounted_bytes', 'internal_state_bytes'})
LOADED_BINARY_KEYS = frozenset({'loaded_cpp_binary_path', 'loaded_cpp_binary_sha256'})

def _ordinary_payload_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    summary, context = _ordinary_health(payload)
    projected: dict[str, Any] = {}
    for key, value in payload.items():
        if key in LOADED_BINARY_KEYS or key == ROW_KEY:
            continue
        if key == 'summary':
            projected[key] = {name: item for name, item in summary.items() if name not in NONDETERMINISTIC_SUMMARY_KEYS and name not in ORDINARY_RESOURCE_SUMMARY_KEYS and name not in LOADED_BINARY_KEYS and not name.startswith(NS)}
        elif key == 'trace_context':
            projected[key] = {name: item for name, item in context.items() if not name.startswith(NS)}
        else:
            projected[key] = value
    return projected

def exact_off_extension_absent(payload: Mapping[str, Any]) -> bool:
    summary, context = _ordinary_health(payload)
    return not any(isinstance(key, str) and key.startswith(NS) for mapping in (payload, summary, context) for key in mapping)

def exact_off_accounting(payload: Mapping[str, Any]) -> dict[str, Any]:
    summary, _context = _ordinary_health(payload)
    return {key: _finite(summary.get(key), f'summary.{key}') for key in sorted(ORDINARY_RESOURCE_SUMMARY_KEYS)}

def ordinary_payload_hashes(payload: Mapping[str, Any]) -> dict[str, str]:
    projection = _ordinary_payload_projection(payload)
    summary = _mapping(projection.get('summary'), 'projected summary')
    parts = {'actions': [projection.get('decisions'), projection.get('hold_attempts')], 'timing': projection.get('bags'), 'calendar_state': projection.get('junction_state'), 'events': projection.get('events'), 'merge_lifecycle': projection.get('merge_grant_lifecycle'), 'result_contract': {key: summary.get(key) for key in ('requested_count', 'completed_count', 'failed_count', 'event_count', 'decision_count', 'reservation_conflicts', 'safe_execution_pass', 'unresolved_deadlock_count', 'merge_grant_conservation_holds', 'merge_grant_active_bijection_holds', 'merge_grant_protocol_integrity_pass')}, 'deterministic_payload': projection}
    hashes = {name: canonical_sha256(value) for name, value in parts.items()}
    hashes['physical_state'] = canonical_sha256([parts['timing'], parts['calendar_state']])
    hashes['ordinary_payload'] = canonical_sha256(projection)
    return hashes

def shadow_extension_sha256(payload: Mapping[str, Any]) -> str:
    summary, context = _ordinary_health(payload)
    return canonical_sha256({'payload': {key: value for key, value in payload.items() if isinstance(key, str) and key.startswith(NS)}, 'summary': {key: value for key, value in summary.items() if isinstance(key, str) and key.startswith(NS)}, 'trace_context': {key: value for key, value in context.items() if isinstance(key, str) and key.startswith(NS)}})

def _shadow_repeat_gate(baseline: Mapping[str, Any], baseline_rows: Sequence[Mapping[str, Any]], baseline_join: Mapping[str, Any], repeated: Mapping[str, Any], repeated_rows: Sequence[Mapping[str, Any]], repeated_join: Mapping[str, Any]) -> dict[str, Any]:
    try:
        hashes = {'ordinary': [canonical_sha256(ordinary_payload_hashes(value)) for value in (baseline, repeated)], 'extension': [shadow_extension_sha256(value) for value in (baseline, repeated)], 'rows': [canonical_sha256(value) for value in (baseline_rows, repeated_rows)], 'join': [canonical_sha256(value) for value in (baseline_join, repeated_join)]}
        census = _shadow_census(_mapping(repeated.get('summary'), 'repeat summary'), repeated_rows, repeated); resources = _resource_values(repeated, shadow=True)
        return gate('shadow_repeat_exact', all(left == right for left, right in hashes.values()) and census['pass'], {'hashes': hashes, 'repeat_census': census, 'repeat_resources': resources, 'error': None})
    except (KeyError, TypeError, ValueError) as error:
        return gate('shadow_repeat_exact', False, {'hashes': locals().get('hashes', {}), 'repeat_census': None, 'repeat_resources': None, 'error': f'{type(error).__name__}: {error}'})

def _loaded_binary(payload: Mapping[str, Any]) -> tuple[str, str]:
    summary = _mapping(payload.get('summary'), 'payload.summary')
    path, digest = (payload.get('loaded_cpp_binary_path'), payload.get('loaded_cpp_binary_sha256'))
    if not isinstance(path, str) or not path or (not _sha_text(digest)) or (summary.get('loaded_cpp_binary_path') != path) or (summary.get('loaded_cpp_binary_sha256') != digest):
        raise ValueError('loaded C++ binary identity is missing or inconsistent')
    return (path, digest)

def _summary_int(summary: Mapping[str, Any], key: str) -> int:
    return _integer(summary.get(key), f'summary.{key}')

def legacy_wait_over_120(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Independently bind the unchanged native legacy-wait diagnostic."""
    summary = _mapping(payload.get('summary'), 'payload.summary')
    records = []
    for index, bag in enumerate(_object_rows(payload.get('bags'), 'payload.bags')):
        runtime_id = _integer(bag.get('runtime_bag_id'), f'bags[{index}].runtime_bag_id')
        segment, source = (bag.get('segment_id'), bag.get('source'))
        if not isinstance(segment, str) or not segment or not isinstance(source, str) or not source:
            raise ValueError('legacy wait vector requires exact segment/source identity')
        native = bag.get('starved')
        if not isinstance(native, bool):
            raise ValueError('native bag.starved must be bool')
        wait = _finite(bag.get('total_local_wait'), 'bag.total_local_wait')
        records.append({'runtime_bag_id': runtime_id, 'segment_id': segment, 'task_id': _integer(bag.get('task_id'), 'bag.task_id'), 'source': source, 'total_local_wait': wait, 'native_starved': native, 'recomputed_wait_over_120': wait > LEGACY_WAIT_THRESHOLD})
    records.sort(key=lambda row: row['runtime_bag_id'])
    contiguous = [row['runtime_bag_id'] for row in records] == list(range(len(records)))
    by_origin: dict[str, dict[str, Any]] = {}
    for source in sorted({row['source'] for row in records}):
        selected = [row for row in records if row['source'] == source]
        by_origin[source] = {'bag_count': len(selected), 'wait_over_120_count': sum(row['recomputed_wait_over_120'] for row in selected), 'maximum_wait': max(row['total_local_wait'] for row in selected)}
    recomputed = sum(row['recomputed_wait_over_120'] for row in records)
    native_count = _summary_int(summary, 'starvation_count')
    flags_match = all(row['native_starved'] == row['recomputed_wait_over_120'] for row in records)
    vector_hash = canonical_sha256(records)
    return {'pass': bool(records) and contiguous and flags_match and native_count == recomputed, 'threshold_seconds': LEGACY_WAIT_THRESHOLD, 'bag_count': len(records), 'native_summary_count': native_count, 'recomputed_count': recomputed, 'runtime_ids_contiguous': contiguous, 'native_flags_match': flags_match, 'ordered_identities': [[row[key] for key in ('runtime_bag_id', 'segment_id', 'task_id', 'source')] for row in records], 'ordered_waits': [row['total_local_wait'] for row in records], 'ordered_flags': [row['native_starved'] for row in records], 'ordered_recomputed_flags': [row['recomputed_wait_over_120'] for row in records], 'per_origin': by_origin, 'maximum_wait': max((row['total_local_wait'] for row in records), default=None), 'ordered_vector_sha256': vector_hash}

def legacy_wait_pair(off: Mapping[str, Any], shadow: Mapping[str, Any]) -> dict[str, Any]:
    off_audit, shadow_audit = (legacy_wait_over_120(off), legacy_wait_over_120(shadow))
    checks = {'off_native_consistent': off_audit['pass'], 'shadow_native_consistent': shadow_audit['pass'], 'count_exact': off_audit['recomputed_count'] == shadow_audit['recomputed_count'], 'ordered_identities_exact': off_audit['ordered_identities'] == shadow_audit['ordered_identities'], 'ordered_waits_exact': off_audit['ordered_waits'] == shadow_audit['ordered_waits'], 'ordered_flags_exact': off_audit['ordered_flags'] == shadow_audit['ordered_flags'], 'per_origin_exact': off_audit['per_origin'] == shadow_audit['per_origin'], 'ordered_vector_hash_exact': off_audit['ordered_vector_sha256'] == shadow_audit['ordered_vector_sha256']}
    return {'pass': all(checks.values()), 'checks': checks, 'off': off_audit, 'shadow': shadow_audit}

def _bag_population_identity(payload: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    records = request.get('bag_records')
    if not isinstance(records, (list, tuple)):
        raise ValueError('request.bag_records must be a sequence')
    expected = []
    for index, record in enumerate(records):
        if not isinstance(record, (list, tuple)) or len(record) != 7:
            raise ValueError(f'request.bag_records[{index}] must have seven fields')
        segment, task, release, deadline, start, goal, source = record
        if not isinstance(segment, str) or not segment or not isinstance(source, str) or not source:
            raise ValueError('request bag segment/source identity must be nonempty text')
        expected.append((index, segment, _integer(task, 'request task'), _finite(release, 'request release'), _finite(deadline, 'request deadline'), _integer(start, 'request start'), _integer(goal, 'request goal'), source))
    bags = _object_rows(payload.get('bags'), 'payload.bags')
    actual = []
    by_runtime: dict[int, Mapping[str, Any]] = {}
    for index, bag in enumerate(bags):
        runtime_id = _integer(bag.get('runtime_bag_id'), f'bags[{index}].runtime_bag_id')
        if runtime_id in by_runtime:
            raise ValueError('duplicate runtime bag identity')
        by_runtime[runtime_id] = bag
        segment, source = (bag.get('segment_id'), bag.get('source'))
        if not isinstance(segment, str) or not segment or not isinstance(source, str) or not source:
            raise ValueError('output bag segment/source identity must be nonempty text')
        actual.append((runtime_id, segment, _integer(bag.get('task_id'), 'output task'), _finite(bag.get('release_time'), 'output release'), _finite(bag.get('deadline'), 'output deadline'), _integer(bag.get('start'), 'output start'), _integer(bag.get('goal'), 'output goal'), source))
    expected_segments = [row[1] for row in expected]
    expected_segment_tasks = [(row[1], row[2]) for row in expected]
    actual_segments = [row[1] for row in actual]
    actual_segment_tasks = [(row[1], row[2]) for row in actual]
    exact = actual == expected
    canonical_origin_labels = {'local', 'external'} <= {row[7] for row in expected}
    unique = len(expected_segments) == len(set(expected_segments)) == len(actual_segments) == len(set(actual_segments)) and len(expected_segment_tasks) == len(set(expected_segment_tasks)) == len(actual_segment_tasks) == len(set(actual_segment_tasks))
    events = _object_rows(payload.get('events'), 'payload.events')
    event_sequences: set[int] = set()
    event_sequence_identity_valid = True
    for event_index, event in enumerate(events):
        event_sequence = _integer(
            event.get('seq'), f'events[{event_index}].seq'
        )
        if event_sequence <= 0 or event_sequence in event_sequences:
            event_sequence_identity_valid = False
        event_sequences.add(event_sequence)
    row_links = True
    source_queue_winner = True
    local_telemetry_exact = True
    for index, row in enumerate(_object_rows(payload.get(ROW_KEY, []), ROW_KEY)):
        local_runtime_id = _integer(
            row.get('local_runtime_bag_id'),
            f'row[{index}].local_runtime_bag_id',
        )
        external_runtime_id = _integer(
            row.get('external_runtime_bag_id'),
            f'row[{index}].external_runtime_bag_id',
        )
        local = by_runtime.get(local_runtime_id)
        external = by_runtime.get(external_runtime_id)
        row_node = _integer(row.get('node'), f'row[{index}].node')
        row_event_time = _finite(
            row.get('event_time'), f'row[{index}].event_time'
        )
        row_event_sequence = _integer(
            row.get('event_seq'), f'row[{index}].event_seq'
        )
        external_task_id = _integer(
            row.get('external_task_id'), f'row[{index}].external_task_id'
        )
        external_upstream_node = _integer(
            row.get('external_upstream_node'),
            f'row[{index}].external_upstream_node',
        )
        external_path_code = _integer(
            row.get('external_path_code'), f'row[{index}].external_path_code'
        )
        row_links = row_links and local is not None and external is not None and local.get('task_id') == row.get('local_task_id') and _close(local.get('release_time'), row.get('local_release')) and _close(local.get('deadline'), row.get('local_deadline')) and _integer(local.get('start'), 'local bag start') == row_node and external.get('task_id') == row.get('external_task_id') and (not canonical_origin_labels or (local.get('source') == 'local' and external.get('source') == 'external'))
        expected_marker_reason = {
            1: 'one_step_reservation_committed',
            2: 'one_step_merge_grant_committed',
        }.get(external_path_code)
        marker_candidates: list[tuple[int, Mapping[str, Any]]] = []
        for event_index, event in enumerate(events):
            if event.get('event') != 'EDGE_ENTER':
                continue
            if (
                _integer(
                    event.get('runtime_bag_id'),
                    f'events[{event_index}].runtime_bag_id',
                )
                == external_runtime_id
                and _integer(
                    event.get('task_id'), f'events[{event_index}].task_id'
                )
                == external_task_id
                and _close(event.get('time'), row_event_time)
            ):
                marker_candidates.append((event_index, event))
        marker_valid = (
            event_sequence_identity_valid
            and row_event_sequence > 0
            and expected_marker_reason is not None
            and len(marker_candidates) == 1
        )
        marker_index = 0
        if marker_valid:
            marker_index, marker = marker_candidates[0]
            marker_valid = (
                _integer(marker.get('from_node'), 'external commit marker from_node')
                == external_upstream_node
                and _integer(marker.get('to_node'), 'external commit marker to_node')
                == row_node
                and marker.get('reason') == expected_marker_reason
            )
        queue: list[int] = []
        enqueued_at: dict[int, float] = {}
        updates = (
            event
            for event in events[:marker_index]
            if event.get('event') == 'LOCAL_QUEUE_UPDATE'
            and event.get('node') == row.get('node')
            and event.get('reason') in {'source_enqueue', 'source_dequeue'}
        )
        valid_history = marker_valid
        for event in updates:
            runtime_id = _integer(event.get('runtime_bag_id'), 'local queue runtime bag')
            queue_bag = by_runtime.get(runtime_id)
            event_identity_valid = (
                queue_bag is not None
                and _integer(event.get('task_id'), 'local queue task')
                == _integer(queue_bag.get('task_id'), 'local queue bag task')
                and event.get('segment_id') == queue_bag.get('segment_id')
                and _integer(queue_bag.get('start'), 'local queue bag start') == row_node
                and _finite(event.get('time'), 'local queue event time')
                <= row_event_time + EPSILON
                and (
                    'source' not in event
                    or event.get('source') == queue_bag.get('source')
                )
                and (not canonical_origin_labels or queue_bag.get('source') == 'local')
            )
            if not event_identity_valid:
                valid_history = False
                break
            if event.get('reason') == 'source_enqueue':
                if runtime_id in queue:
                    valid_history = False
                    break
                queue.append(runtime_id)
                enqueued_at[runtime_id] = _finite(event.get('time'), 'source enqueue time')
            else:
                if runtime_id not in queue:
                    valid_history = False
                    break
                queue.remove(runtime_id)
        choose_index = _integer(row.get('local_choose_bag_index'), 'local_choose_bag_index')
        escape_token = _integer(row.get('local_escape_token_runtime_bag_id'), 'local_escape_token_runtime_bag_id')
        expected_index = None
        if escape_token >= -1 and queue and all(runtime_id in enqueued_at for runtime_id in queue):
            expected_index = (
                queue.index(escape_token)
                if escape_token in queue
                else min(
                    range(len(queue)),
                    key=lambda queue_index: (
                        enqueued_at[queue[queue_index]],
                        queue[queue_index],
                    ),
                )
            )
        source_queue_winner = source_queue_winner and valid_history and expected_index is not None and choose_index == expected_index and queue[choose_index] == local_runtime_id and _close(enqueued_at[local_runtime_id], row.get('local_source_enqueued_at'))
        local_telemetry_exact = local_telemetry_exact and valid_history and bool(queue) and all(runtime_id in enqueued_at for runtime_id in queue) and _integer(row.get('local_source_ready_count'), 'local_source_ready_count') == len(queue) and _close(row.get('local_source_uncovered_service_work_seconds'), len(queue) * _finite(row.get('local_service_seconds'), 'local_service_seconds')) and _close(row.get('oldest_local_wait_age_seconds'), max(0.0, _finite(row.get('event_time'), 'event_time') - enqueued_at[queue[0]]))
    return {'pass': exact and unique and event_sequence_identity_valid and row_links and source_queue_winner and local_telemetry_exact, 'exact_ordered_manifest': exact, 'unique_segment_and_segment_task_identity': unique, 'event_sequence_identity_valid': event_sequence_identity_valid, 'shadow_row_bag_links': row_links, 'shadow_row_source_queue_winner': source_queue_winner, 'shadow_row_local_telemetry_exact': local_telemetry_exact, 'expected_sha256': canonical_sha256(expected), 'actual_sha256': canonical_sha256(actual)}

def _shadow_census(summary: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], payload: Mapping[str, Any]) -> dict[str, Any]:
    names = ('external_commit_considered_count', 'direct_external_commit_count', 'j2_exact_commit_count', *CENSUS_PARTS, *SHADOW_ZERO)
    values = {name: _summary_int(summary, NS + name) for name in names}
    considered = values['external_commit_considered_count']
    bags = {
        _integer(bag.get('runtime_bag_id'), 'census bag runtime id'): bag
        for bag in _object_rows(payload.get('bags'), 'payload.bags')
    }
    expected = {'direct': 0, 'j2': 0, 'unclassified': 0}
    for event in _object_rows(payload.get('events'), 'payload.events'):
        if event.get('event') != 'EDGE_ENTER':
            continue
        runtime_id = _integer(event.get('runtime_bag_id'), 'census event runtime id')
        bag = bags.get(runtime_id)
        if bag is None:
            raise ValueError('EDGE_ENTER references an unknown runtime bag')
        if _integer(event.get('to_node'), 'census EDGE_ENTER destination') == _integer(bag.get('goal'), 'census bag goal'):
            continue
        reason = event.get('reason')
        if reason == 'one_step_reservation_committed':
            expected['direct'] += 1
        elif reason == 'one_step_merge_grant_committed':
            expected['j2'] += 1
        else:
            expected['unclassified'] += 1
    expected_considered = expected['direct'] + expected['j2']
    checks = {'partition': considered == sum((values[name] for name in CENSUS_PARTS)), 'seam_partition': considered == values['direct_external_commit_count'] + values['j2_exact_commit_count'], 'ordinary_commit_seam_binding': expected['unclassified'] == 0 and considered == expected_considered and values['direct_external_commit_count'] == expected['direct'] and values['j2_exact_commit_count'] == expected['j2'], 'stored_matches': values['observation_stored_count'] == len(rows), 'zero_drop': values['observation_dropped_count'] == 0, 'inert_local': all((values[name] == 0 for name in SHADOW_ZERO)), 'mode': summary.get(NS + 'mode') == MODE}
    return {'pass': all(checks.values()), **checks, 'values': values, 'ordinary_commit_counts': expected}
SAFETY_ZERO_KEYS = ('reservation_conflicts', 'physical_fault_edge_entry_violation_count', 'runtime_full_astar_calls', 'runtime_full_cie_astar_calls', 'unresolved_deadlock_count', 'scorer_future_route_input_count', 'priority_future_route_input_count', 'first_edge_credit_future_route_count')
CLONE_SAFETY_ZERO_KEYS = ('global_reservation_scan_count', 'priority_global_scan_count', 'scorer_runtime_global_scan_count', 'microphase_runtime_global_scan_count', 'first_edge_credit_global_scan_count', 'scorer_future_schedule_input_count', 'priority_teacher_input_count', 'scorer_teacher_input_count', 'two_step_reservation_count', 'merge_grant_stale_arbitration_count', 'stale_arbitration_event_count')

def _safety(summary: Mapping[str, Any]) -> bool:
    try:
        return summary.get('safe_execution_pass') is True and all((_summary_int(summary, key) == 0 for key in SAFETY_ZERO_KEYS + CLONE_SAFETY_ZERO_KEYS)) and (_summary_int(summary, 'max_edges_selected_per_bag_per_decision') <= 1) and (summary.get('event_limit_reached') is False) and (summary.get('time_limit_reached') is False) and (_finite(summary.get('artificial_batch_delay_seconds'), 'summary.artificial_batch_delay_seconds') == 0.0) and (summary.get('merge_grant_conservation_holds') is True) and (summary.get('merge_grant_active_bijection_holds') is True) and (summary.get('merge_grant_protocol_integrity_pass') is True) and (summary.get('merge_grant_lifecycle_complete') is True) and (_summary_int(summary, 'merge_grant_lifecycle_dropped_count') == 0)
    except (TypeError, ValueError):
        return False

def _global_service_calendar_audit(episodes: Sequence[Mapping[str, Any]], junctions: Sequence[Mapping[str, Any]], request: Mapping[str, Any]) -> dict[str, Any]:
    try:
        services = _services(request)
        records = request.get('bag_records')
        if not isinstance(records, (list, tuple)):
            raise ValueError('request.bag_records must be a sequence')
        goal_by_runtime = {}
        for runtime_id, record in enumerate(records):
            if not isinstance(record, (list, tuple)) or len(record) != 7:
                raise ValueError('request bag record is malformed')
            goal = _integer(record[5], 'request bag goal')
            if goal not in services:
                raise ValueError('request bag goal is not configured')
            goal_by_runtime[runtime_id] = goal
        identities, intervals, completed = [], defaultdict(list), Counter()
        evidence = []
        for episode in episodes:
            bag, node = (_integer(episode.get('runtime_bag_id'), 'service episode bag'), _integer(episode.get('node'), 'service episode node'))
            start, complete = (_finite(episode.get('actual_L_service_start'), 'service episode start'), _finite(episode.get('actual_L_service_complete'), 'service episode complete'))
            completion_event_seq = _integer(episode.get('completion_event_seq'), 'service episode completion event')
            if bag not in goal_by_runtime or node not in services or complete < start or abs((complete - start) - services[node]) > EPSILON:
                raise ValueError('service episode violates the frozen duration/profile')
            if completion_event_seq <= 0:
                raise ValueError('service episode completion event identity is invalid')
            identities.append((bag, node)); intervals[node].append((start, complete)); completed[node] += 1
            evidence.append({'runtime_bag_id': bag, 'node': node, 'start': start, 'complete': complete, 'completion_event_seq': completion_event_seq})
        state = {}
        for row in junctions:
            node, count = (_integer(row.get('node'), 'junction node'), _integer(row.get('service_reservation_count'), 'junction reservation count'))
            if node not in services or node in state or count < 0:
                raise ValueError('junction service state identity/count is invalid')
            state[node] = count
        evidence.sort(key=lambda row: (row['start'], row['complete'], row['completion_event_seq'], row['runtime_bag_id'], row['node']))
        vector_limit = len(records) * max(1, len(state))
        vector_bounded = len(evidence) <= vector_limit
        event_identities = [row['completion_event_seq'] for row in evidence]
        checks = {'unique_bag_node': len(identities) == len(set(identities)), 'completion_event_identity_unique': len(event_identities) == len(set(event_identities)), 'no_node_overlap': all(right[0] >= left[1] - EPSILON for values in intervals.values() for left, right in zip(sorted(values), sorted(values)[1:])), 'reservation_count_match': set(completed) <= set(state) and all(count == completed.get(node, 0) for node, count in state.items()), 'goal_arrival_has_no_service': request.get('complete_on_goal_arrival') is True and all(node != goal_by_runtime[bag] for bag, node in identities), 'evidence_vector_bounded': vector_bounded}
        return {'pass': bool(state) and all(checks.values()), 'checks': checks, 'completion_counts': {str(node): count for node, count in sorted(completed.items())}, 'reservation_counts': {str(node): count for node, count in sorted(state.items())}, 'ordered_service_episodes': evidence, 'service_episodes_sha256': canonical_sha256(evidence), 'service_episode_count': len(evidence), 'evidence_vector_limit': vector_limit, 'evidence_vector_bounded': vector_bounded, 'error': None}
    except (KeyError, TypeError, ValueError) as error:
        return {'pass': False, 'checks': {}, 'completion_counts': {}, 'reservation_counts': {}, 'ordered_service_episodes': [], 'service_episodes_sha256': canonical_sha256([]), 'service_episode_count': 0, 'evidence_vector_limit': 0, 'evidence_vector_bounded': False, 'error': str(error)}

def _service_sequence_audit(episodes: Sequence[Mapping[str, Any]], bags: Sequence[Mapping[str, Any]], *, exact_node: int | None) -> dict[str, Any]:
    by_bag: dict[int, str] = {}
    for bag in bags:
        bag_id, source = (_integer(bag.get('runtime_bag_id'), 'sequence bag id'), bag.get('source'))
        if bag_id in by_bag or not isinstance(source, str) or not source:
            raise ValueError('service sequence bag identity/source is invalid')
        by_bag[bag_id] = source
    selected = [episode for episode in episodes if exact_node is None or episode.get('node') == exact_node]
    sequence = []
    for episode in selected:
        bag_id = _integer(episode.get('runtime_bag_id'), 'sequence episode bag')
        if bag_id not in by_bag:
            raise ValueError('service sequence references an unknown bag')
        sequence.append({'runtime_bag_id': bag_id, 'source': by_bag[bag_id], 'node': _integer(episode.get('node'), 'sequence node'), 'start': _finite(episode.get('actual_L_service_start'), 'sequence start'), 'complete': _finite(episode.get('actual_L_service_complete'), 'sequence complete'), 'completion_event_seq': _integer(episode.get('completion_event_seq'), 'sequence event')})
    sequence.sort(key=lambda row: (row['start'], row['complete'], row['completion_event_seq'], row['runtime_bag_id']))
    bag_ids = [row['runtime_bag_id'] for row in sequence]
    bag_nodes = [(row['runtime_bag_id'], row['node']) for row in sequence]
    exact_L = exact_node is not None
    conservation = len(bag_nodes) == len(set(bag_nodes)) and (not exact_L or (len(bag_ids) == len(set(bag_ids)) and set(bag_ids) == set(by_bag)))
    by_node: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in sequence:
        by_node[row['node']].append(row)
    no_overlap = all(right['start'] >= left['complete'] - EPSILON for values in by_node.values() for left, right in zip(values, values[1:]))
    vector_limit = len(bags) * max(1, len(by_node))
    vector_bounded = len(sequence) <= vector_limit
    expected_origins, observed_origins = (Counter(by_bag.values()), Counter(row['source'] for row in sequence))
    origin_conservation = not exact_L or observed_origins == expected_origins
    origins = [row['source'] for row in sequence]
    maximum_run = 0
    previous, run = (None, 0)
    for origin in origins:
        run = run + 1 if origin == previous else 1
        previous, maximum_run = origin, max(maximum_run, run)
    return {'pass': bool(sequence) and conservation and no_overlap and origin_conservation and vector_bounded, 'exact_L_applicable': exact_L, 'sequence_count': len(sequence), 'evidence_vector_limit': vector_limit, 'evidence_vector_bounded': vector_bounded, 'bag_conservation': conservation, 'origin_conservation': origin_conservation, 'no_overlap': no_overlap, 'requested_origin_counts': dict(sorted(expected_origins.items())), 'service_origin_counts': dict(sorted(observed_origins.items())), 'ordered_service_episodes': sequence, 'ordered_runtime_bag_ids': bag_ids, 'origin_sequence': origins, 'sequence_sha256': canonical_sha256(sequence), 'origin_sequence_sha256': canonical_sha256(origins), 'maximum_consecutive_origin_run': maximum_run}

def _merge_lifecycle_chain_audit(
    lifecycle: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]
) -> dict[str, Any]:
    state_order = {'REQUESTED': 0, 'ISSUED': 1, 'PREPARED': 2, 'COMMITTED': 3, 'CONSUMED': 4, 'EXPIRED': 5, 'REVOKED_FAULT': 6, 'REVOKED_STALE_STATE': 7, 'REVOKED_REPLAN_CURRENT_EDGE': 8, 'ROLLED_BACK': 9}
    terminal_states = {'EXPIRED', 'REVOKED_FAULT', 'REVOKED_STALE_STATE', 'REVOKED_REPLAN_CURRENT_EDGE', 'ROLLED_BACK'}
    active_terminal_states = terminal_states | {'CONSUMED'}
    grouped: dict[tuple[int, int, int, int, int], list[tuple[str, float, int]]] = defaultdict(list)
    lifecycle_order_keys = []
    state_counts: Counter[str] = Counter()
    for row in lifecycle:
        identity = tuple(_integer(row.get(key), 'merge lifecycle identity') for key in ('request_id', 'lineage', 'request_generation', 'junction_queue_generation', 'destination_node'))
        state_name = row.get('state')
        if not isinstance(state_name, str) or state_name not in state_order:
            raise ValueError('merge lifecycle state is invalid')
        time = _finite(row.get('time'), 'merge lifecycle time')
        grant_id = _integer(row.get('grant_id'), 'merge lifecycle grant')
        if grant_id < 0:
            raise ValueError('merge lifecycle grant must be nonnegative')
        grouped[identity].append((state_name, time, grant_id))
        state_counts[state_name] += 1
        lifecycle_order_keys.append((time, identity[-1], identity[0], grant_id, state_order[state_name]))

    chains_valid = True
    final_states: dict[tuple[int, int, int, int, int], str] = {}
    post_commit_states: Counter[str] = Counter()
    for identity, transitions in grouped.items():
        raw_states = [row[0] for row in transitions]
        raw_final_state = raw_states[-1]
        unique_states = len(raw_states) == len(set(raw_states))
        by_state = {row[0]: row for row in transitions}
        state_set = set(raw_states)
        logical_states: list[str] = []
        still_pending_shape = state_set == {'REQUESTED'} and len(raw_states) == 1
        pending_terminal_states = state_set - {'REQUESTED'}
        pending_terminal_shape = (
            len(raw_states) == 2
            and 'REQUESTED' in state_set
            and len(pending_terminal_states) == 1
            and next(iter(pending_terminal_states)) in terminal_states
        )
        committed_base = {'REQUESTED', 'ISSUED', 'PREPARED', 'COMMITTED'}
        committed_tail = state_set - committed_base
        committed_shape = (
            len(raw_states) in {4, 5}
            and committed_base <= state_set
            and (
                not committed_tail
                or (
                    len(committed_tail) == 1
                    and next(iter(committed_tail)) in active_terminal_states
                )
            )
        )
        if unique_states and still_pending_shape:
            logical_states = ['REQUESTED']
        elif unique_states and pending_terminal_shape:
            logical_states = ['REQUESTED', next(iter(pending_terminal_states))]
        elif unique_states and committed_shape:
            logical_states = ['REQUESTED', 'ISSUED', 'PREPARED', 'COMMITTED']
            if committed_tail:
                logical_states.append(next(iter(committed_tail)))

        logical_rows = [by_state[state] for state in logical_states]
        logical_times = [row[1] for row in logical_rows]
        logical_grants = [row[2] for row in logical_rows]
        time_ordered = bool(logical_rows) and all(
            right + EPSILON >= left
            for left, right in zip(logical_times, logical_times[1:])
        )
        still_pending = (
            logical_states == ['REQUESTED'] and logical_grants == [0]
        )
        pending_terminal = (
            len(logical_states) == 2
            and logical_states[0] == 'REQUESTED'
            and logical_states[1] in terminal_states
            and logical_grants == [0, 0]
        )
        committed_prefix = (
            logical_states[:4]
            == ['REQUESTED', 'ISSUED', 'PREPARED', 'COMMITTED']
            and len(logical_states) in {4, 5}
            and logical_grants[0] == 0
            and logical_grants[1] > 0
            and logical_grants[1:]
            == [logical_grants[1]] * (len(logical_grants) - 1)
            and max(logical_times[1:4]) - min(logical_times[1:4]) <= EPSILON
            and (
                len(logical_states) == 4
                or logical_states[4] in active_terminal_states
            )
        )
        chain_valid = time_ordered and (
            still_pending or pending_terminal or committed_prefix
        )
        chains_valid = chains_valid and chain_valid
        final_state = logical_states[-1] if chain_valid else raw_final_state
        final_states[identity] = final_state
        if (
            committed_prefix
            and len(logical_states) == 5
            and logical_states[-1] in terminal_states
        ):
            post_commit_states[logical_states[-1]] += 1

    final_counts = Counter(final_states.values())
    final_committed = final_counts['COMMITTED'] + final_counts['CONSUMED']
    final_revoked = sum(
        final_counts[state]
        for state in terminal_states
        if state.startswith('REVOKED_')
    )
    count_checks = {
        'transition_count_exact': _summary_int(summary, 'merge_grant_lifecycle_transition_count') == len(lifecycle),
        'stored_count_exact': _summary_int(summary, 'merge_grant_lifecycle_stored_count') == len(lifecycle),
        'dropped_count_zero': _summary_int(summary, 'merge_grant_lifecycle_dropped_count') == 0,
        'request_transition_count_exact': _summary_int(summary, 'merge_grant_request_count') == state_counts['REQUESTED'],
        'issued_transition_count_exact': _summary_int(summary, 'merge_grant_issued_transition_count') == state_counts['ISSUED'],
        'prepared_transition_count_exact': _summary_int(summary, 'merge_grant_prepared_transition_count') == state_counts['PREPARED'],
        'committed_transition_count_exact': _summary_int(summary, 'merge_grant_committed_transition_count') == state_counts['COMMITTED'],
        'historical_commit_transition_conservation': state_counts['ISSUED'] == state_counts['PREPARED'] == state_counts['COMMITTED'],
        'current_committed_count_exact': _summary_int(summary, 'merge_grant_issued_count') == _summary_int(summary, 'merge_grant_prepared_count') == _summary_int(summary, 'merge_grant_committed_count') == final_committed,
        'consumed_transition_count_exact': _summary_int(summary, 'merge_grant_consumed_count') == state_counts['CONSUMED'] == final_counts['CONSUMED'],
        'post_commit_revoked_count_exact': _summary_int(summary, 'merge_grant_post_commit_revoked_count') == sum(post_commit_states[state] for state in post_commit_states if state.startswith('REVOKED_')),
        'post_commit_expired_count_exact': _summary_int(summary, 'merge_grant_post_commit_expired_count') == post_commit_states['EXPIRED'],
        'post_commit_rollback_count_exact': _summary_int(summary, 'merge_grant_post_commit_rollback_count') == post_commit_states['ROLLED_BACK'],
        'terminal_state_counts_exact': _summary_int(summary, 'merge_grant_expired_count') == final_counts['EXPIRED'] and _summary_int(summary, 'merge_grant_revoked_count') == final_revoked and _summary_int(summary, 'merge_grant_rolled_back_count') == final_counts['ROLLED_BACK'] and _summary_int(summary, 'merge_grant_terminal_request_count') == sum(final_counts[state] for state in terminal_states),
    }
    return {
        'ordered': lifecycle_order_keys == sorted(lifecycle_order_keys),
        'chains_valid': chains_valid,
        'count_checks': count_checks,
        'counts_exact': all(count_checks.values()),
        'final_states': final_states,
        'last_state_counts': Counter(final_states.values()),
        'state_counts': state_counts,
    }


def _permanent_starvation_audit(payload: Mapping[str, Any], request: Mapping[str, Any], episodes: Sequence[Mapping[str, Any]], population_identity: Mapping[str, Any], *, exact_node: int | None) -> dict[str, Any]:
    summary = _mapping(payload.get('summary'), 'payload.summary')
    bags = _object_rows(payload.get('bags'), 'payload.bags')
    records = request.get('bag_records')
    if not isinstance(records, (list, tuple)):
        raise ValueError('request.bag_records must be a sequence')
    deadlines, goals, requested_origins = ({}, {}, Counter())
    request_active_nodes: set[int] = set()
    for runtime_id, record in enumerate(records):
        if not isinstance(record, (list, tuple)) or len(record) != 7:
            raise ValueError('request bag record is malformed')
        deadlines[runtime_id] = _finite(record[3], 'request deadline')
        goals[runtime_id] = _integer(record[5], 'request goal node')
        source = record[6]
        if not isinstance(source, str) or not source:
            raise ValueError('request origin is invalid')
        requested_origins[source] += 1
        request_active_nodes.add(_integer(record[4], 'request start node'))
        request_active_nodes.add(_integer(record[5], 'request goal node'))
    by_runtime = {_integer(bag.get('runtime_bag_id'), 'permanent bag id'): bag for bag in bags}
    unique_bags = len(by_runtime) == len(bags) == len(records) and set(by_runtime) == set(deadlines)
    late = []
    completed_origins: Counter[str] = Counter()
    completed_exact = unique_bags
    L_counts = Counter(_integer(episode.get('runtime_bag_id'), 'L episode bag') for episode in episodes if exact_node is not None and episode.get('node') == exact_node)
    completion_vector = []
    for runtime_id, bag in sorted(by_runtime.items()):
        finish = _finite(bag.get('finish_time'), 'bag.finish_time')
        source = bag.get('source')
        if runtime_id not in deadlines or not isinstance(source, str) or not source:
            raise ValueError('permanent bag identity/source is invalid')
        completed = bag.get('completed') is True
        completion_vector.append({'runtime_bag_id': runtime_id, 'source': source, 'goal': goals[runtime_id], 'completed': completed, 'finish_time': finish, 'deadline': deadlines[runtime_id], 'L_service_count': L_counts.get(runtime_id, 0)})
        completed_exact = completed_exact and completed
        if finish > deadlines[runtime_id] + EPSILON:
            late.append(runtime_id)
        if completed:
            completed_origins[source] += 1
    junctions = _object_rows(payload.get('junction_state'), 'payload.junction_state')
    configured_nodes = {_integer(row[0], 'request node') for row in request.get('node_records', [])}
    event_active_nodes: set[int] = set()
    for event in _object_rows(payload.get('events'), 'payload.events'):
        for key in ('node', 'from_node', 'to_node'):
            node = _integer(event.get(key), f'event.{key}')
            if node >= 0:
                event_active_nodes.add(node)
    expected_nodes = request_active_nodes | event_active_nodes
    active_nodes_valid = bool(expected_nodes) and expected_nodes <= configured_nodes
    state = {_integer(row.get('node'), 'junction node'): row for row in junctions}
    state_nodes = set(state)
    extra_state_inert = all(_summary_int(state[node], 'service_reservation_count') == 0 for node in state_nodes - expected_nodes)
    exact_junctions = active_nodes_valid and len(state) == len(junctions) and expected_nodes <= state_nodes <= configured_nodes and extra_state_inert
    junction_vector = sorted(({'node': _integer(row.get('node'), 'junction node'), 'service_reservation_count': _summary_int(row, 'service_reservation_count'), 'final_source_queue_length': _summary_int(row, 'final_source_queue_length'), 'final_junction_queue_length': _summary_int(row, 'final_junction_queue_length'), 'scheduled_incoming': _summary_int(row, 'scheduled_incoming')} for row in junctions), key=lambda row: row['node'])
    queues_empty = exact_junctions and all(row['final_source_queue_length'] == 0 and row['final_junction_queue_length'] == 0 for row in junction_vector)
    incoming_zero = exact_junctions and all(row['scheduled_incoming'] == 0 for row in junction_vector)
    lifecycle = _object_rows(payload.get('merge_grant_lifecycle'), 'payload.merge_grant_lifecycle')
    lifecycle_audit = _merge_lifecycle_chain_audit(lifecycle, summary)
    final_states = lifecycle_audit['final_states']
    lifecycle_ordered = lifecycle_audit['ordered']
    final_state_vector = [dict(zip(('request_id', 'lineage', 'request_generation', 'junction_queue_generation', 'destination_node'), identity), state=state_name) for identity, state_name in sorted(final_states.items())]
    lifecycle_last_state_counts = lifecycle_audit['last_state_counts']
    merge_requests = _summary_int(summary, 'merge_grant_request_count')
    merge_committed = _summary_int(summary, 'merge_grant_committed_count')
    merge_terminal = _summary_int(summary, 'merge_grant_terminal_request_count')
    merge_outstanding = _summary_int(summary, 'merge_grant_outstanding_request_count')
    L_once = exact_node is None or (set(L_counts) == set(deadlines) and all(count == 1 for count in L_counts.values()))
    mixed = set(requested_origins) == {'local', 'external'}
    terminal_states = {'EXPIRED', 'REVOKED_FAULT', 'REVOKED_STALE_STATE', 'REVOKED_REPLAN_CURRENT_EDGE', 'ROLLED_BACK'}
    final_consumed = lifecycle_last_state_counts['CONSUMED']
    final_active = lifecycle_last_state_counts['COMMITTED']
    final_terminal = sum(lifecycle_last_state_counts[state_name] for state_name in terminal_states)
    final_outstanding = lifecycle_last_state_counts['REQUESTED']
    final_invalid = lifecycle_last_state_counts['ISSUED'] + lifecycle_last_state_counts['PREPARED']
    summary_active = _summary_int(summary, 'merge_grant_final_active_unconsumed')
    vector_bound = len(records) + len(configured_nodes) + merge_requests
    vector_count = len(completion_vector) + len(junction_vector) + len(final_state_vector)
    checks = {'requested_population_exact': population_identity.get('pass') is True and unique_bags and _summary_int(summary, 'requested_count') == len(records), 'completed_once': completed_exact and _summary_int(summary, 'completed_count') == len(records), 'deadline_complete': not late, 'L_service_once_where_applicable': L_once, 'failed_zero': _summary_int(summary, 'failed_count') == 0, 'final_active_zero': _summary_int(summary, 'final_active_bag_count') == 0, 'unresolved_deadlock_zero': _summary_int(summary, 'unresolved_deadlock_count') == 0, 'limits_not_reached': summary.get('event_limit_reached') is False and summary.get('time_limit_reached') is False, 'active_node_identity_valid': active_nodes_valid, 'active_junction_state_exact': exact_junctions, 'final_queues_empty': queues_empty, 'final_scheduled_incoming_zero': incoming_zero, 'lifecycle_ordered': lifecycle_ordered, 'lifecycle_chains_valid': lifecycle_audit['chains_valid'], 'lifecycle_counts_exact': lifecycle_audit['counts_exact'], 'lifecycle_final_state_complete': len(final_states) == merge_requests and final_invalid == 0, 'lifecycle_consumed_committed_exact': final_consumed + final_active == merge_committed, 'lifecycle_terminal_exact': final_terminal == merge_terminal, 'lifecycle_outstanding_exact': final_outstanding == merge_outstanding, 'lifecycle_active_exact': final_active == summary_active, 'merge_request_conservation': merge_requests == merge_committed + merge_terminal + merge_outstanding, 'final_merge_pending_zero': merge_outstanding == 0 and final_outstanding == 0, 'merge_active_unconsumed_zero': summary_active == 0 and final_active == 0, 'mixed_origin_request_completion': (not mixed) or completed_origins == requested_origins, 'recomputable_vectors_bounded': vector_count <= vector_bound}
    return {'pass': all(checks.values()), 'checks': checks, 'requested_origin_counts': dict(sorted(requested_origins.items())), 'completed_origin_counts': dict(sorted(completed_origins.items())), 'late_runtime_bag_ids': late, 'bag_completion_vector': completion_vector, 'bag_completion_vector_sha256': canonical_sha256(completion_vector), 'junction_final_vector': junction_vector, 'junction_final_vector_sha256': canonical_sha256(junction_vector), 'lifecycle_final_state_vector': final_state_vector, 'lifecycle_final_state_vector_sha256': canonical_sha256(final_state_vector), 'lifecycle_count_checks': lifecycle_audit['count_checks'], 'lifecycle_state_counts': dict(sorted(lifecycle_audit['state_counts'].items())), 'recomputable_vector_count': vector_count, 'recomputable_vector_limit': vector_bound, 'merge_request_accounting': {'request_count': merge_requests, 'committed_count': merge_committed, 'terminal_count': merge_terminal, 'outstanding_count': merge_outstanding, 'final_active_unconsumed': summary_active, 'final_consumed_count': final_consumed, 'final_committed_active_count': final_active, 'final_terminal_count': final_terminal, 'final_outstanding_count': final_outstanding}, 'historical_last_lifecycle_state_counts': dict(sorted(lifecycle_last_state_counts.items())), 'junction_count': len(junctions), 'expected_junction_count': len(expected_nodes), 'configured_junction_count': len(configured_nodes)}

def _service_audit(case_id: str, bag_count: int, expected_origins: set[str], payload: Mapping[str, Any], request: Mapping[str, Any], *, exact_node: int | None) -> dict[str, Any]:
    summary, _context = _ordinary_health(payload)
    services = _services(request)
    episodes, _events, _by_bag = _base_episodes(case_id, payload, services)
    bags = _object_rows(payload.get('bags'), 'payload.bags')
    lifecycle = _object_rows(payload.get('merge_grant_lifecycle'), 'payload.merge_grant_lifecycle')
    junctions = _object_rows(payload.get('junction_state'), 'payload.junction_state')
    global_service = _global_service_calendar_audit(episodes, junctions, request)
    selected = [episode for episode in episodes if exact_node is None or episode['node'] == exact_node]
    counts = Counter((episode['runtime_bag_id'] for episode in selected))
    completed = [bag for bag in bags if bag.get('completed') is True]
    origins = {str(bag.get('source')) for bag in completed}
    committed = [row for row in lifecycle if row.get('state') == 'COMMITTED']
    request_ids = [(row.get('destination_node'), row.get('request_id'), row.get('lineage'), row.get('request_generation'), row.get('junction_queue_generation')) for row in committed]
    grants = [(row.get('destination_node'), row.get('grant_id')) for row in committed]
    node_state = [row for row in junctions if row.get('node') == exact_node]
    population_identity = _bag_population_identity(payload, request)
    legacy_wait = legacy_wait_over_120(payload)
    service_sequence = _service_sequence_audit(episodes, bags, exact_node=exact_node)
    permanent = _permanent_starvation_audit(payload, request, episodes, population_identity, exact_node=exact_node)
    reservation_exact = exact_node is None or (len(node_state) == 1 and _summary_int(node_state[0], 'service_reservation_count') == bag_count)
    complete_once = len(bags) == bag_count and _summary_int(summary, 'requested_count') == bag_count and (_summary_int(summary, 'completed_count') == bag_count) and (_summary_int(summary, 'failed_count') == 0) and (len(completed) == bag_count) and (exact_node is None or (len(counts) == bag_count and all((value == 1 for value in counts.values()))))
    pending = _summary_int(summary, 'merge_grant_peak_pending_requests') <= 256 and _summary_int(summary, 'merge_grant_peak_active_unconsumed') <= 256 and (_summary_int(summary, 'merge_grant_final_active_unconsumed') == 0) and (_summary_int(summary, 'merge_grant_outstanding_request_count') == 0)
    checks = {'complete_once': complete_once, 'exact_request_population_identity': population_identity['pass'], 'origin_coverage': expected_origins <= origins, 'legacy_wait_native_consistent': legacy_wait['pass'], 'permanent_starvation_zero': permanent['pass'], 'service_sequence_conservation': service_sequence['pass'], 'global_service_calendar': global_service['pass'], 'no_overlap_or_duplicate': reservation_exact and global_service['pass'] and len(request_ids) == len(set(request_ids)) and (len(grants) == len(set(grants))), 'pending_bounded': pending, 'safety': _safety(summary), 'junction_state_present': bool(junctions)}
    return {'pass': all(checks.values()), 'checks': checks, 'origins': sorted(origins), 'episode_count': len(selected), 'population_identity': population_identity, 'legacy_wait_over_120': legacy_wait, 'permanent_starvation': permanent, 'service_sequence': service_sequence, 'global_service_calendar': global_service}

def _resource_values(payload: Mapping[str, Any], *, shadow: bool) -> dict[str, float]:
    summary = _mapping(payload.get('summary'), 'payload.summary')
    completed = _summary_int(summary, 'completed_count')
    events = _summary_int(summary, 'event_count')
    junctions = _object_rows(payload.get('junction_state'), 'payload.junction_state')
    local = math.fsum((_finite(row.get('peak_local_state_accounted_bytes'), 'junction base bytes') for row in junctions))
    ordinary_total = _finite(summary.get('cpp_internal_accounted_bytes'), 'cpp internal bytes')
    ordinary_alias = _finite(summary.get('internal_state_bytes'), 'internal state bytes')
    if completed <= 0 or min(events, local, ordinary_total, ordinary_alias) < 0.0 or ordinary_total != ordinary_alias:
        raise ValueError('ordinary resource accounting is negative or internally inconsistent')
    if shadow:
        incremental = _finite(summary.get(NS + 'incremental_local_state_bytes'), 'shadow incremental local bytes')
        internal = _finite(summary.get(NS + 'runtime_internal_accounted_bytes'), 'shadow internal bytes')
        total = _finite(summary.get(NS + 'total_accounted_bytes'), 'shadow total bytes')
        sidecar = _finite(summary.get(NS + 'trace_sidecar_accounted_bytes'), 'shadow sidecar bytes')
        if incremental != 0.0 or min(internal, total, sidecar) < 0.0 or internal + sidecar != total or total != ordinary_total:
            raise ValueError('shadow resource accounting violates the frozen exact decomposition')
        local += incremental
    else:
        internal = total = ordinary_total
        sidecar = 0.0
    return {'events_per_completed': events / completed, 'junction_local_accounted_bytes': local, 'runtime_internal_accounted_bytes': internal, 'trace_sidecar_accounted_bytes': sidecar, 'total_accounted_bytes': total}

def run_case(case: V3R2Case, *, executor: Executor, binary: Path | None=None, j2: bool=False) -> dict[str, Any]:
    off_request, off_potential = build_request(case, mode='off', binary=binary, j2=j2)
    shadow_request, shadow_potential = build_request(case, mode=MODE, binary=binary, j2=j2)
    off, shadow = (executor(**off_request), executor(**shadow_request))
    if not isinstance(off, Mapping) or not isinstance(shadow, Mapping):
        raise ValueError('executor must return mappings')
    metadata = {'cohort': 'safety_regression', 'replica': None, 'service_seconds': case.service_seconds, 'bag_count': case.bag_count, 'flow_pattern': case.flow_pattern}
    rows = extract_rows(shadow, case_id=case.case_id, request=shadow_request, metadata=metadata)
    if case.flow_pattern in NEGATIVE_CONTROLS and rows:
        raise ValueError('negative controls must emit zero admitted rows')
    episodes = build_service_episodes(case.case_id, shadow, rows, shadow_request)
    joined = join_v3r2_outcomes(rows, episodes)
    return {'case': case_manifest(case), 'off': off, 'shadow': shadow, 'off_request': off_request, 'shadow_request': shadow_request, 'rows': rows, 'join': joined, 'profile_sha256': profile_sha256(off_request), 'potential_sha256': canonical_sha256(off_request['heuristic_time']), 'potential_equal': off_potential == shadow_potential, 'off_request_sha256': request_sha256(off_request), 'shadow_request_sha256': request_sha256(shadow_request), 'off_ordinary_request_sha256': ordinary_request_sha256(off_request), 'shadow_ordinary_request_sha256': ordinary_request_sha256(shadow_request)}

def run_identification_case(
    case: IdentificationCase, *, executor: Executor, binary: Path | None=None
) -> dict[str, Any]:
    off_request, off_potential = build_identification_request(
        case, mode='off', binary=binary
    )
    shadow_request, shadow_potential = build_identification_request(
        case, mode=MODE, binary=binary
    )
    off, shadow = (executor(**off_request), executor(**shadow_request))
    if not isinstance(off, Mapping) or not isinstance(shadow, Mapping):
        raise ValueError('executor must return mappings')
    metadata = {
        'cohort': 'identification',
        'replica': case.replica,
        'service_seconds': case.service_seconds,
        'bag_count': case.bag_count,
        'flow_pattern': case.flow_pattern,
    }
    rows = extract_rows(
        shadow,
        case_id=case.case_id,
        request=shadow_request,
        metadata=metadata,
    )
    episodes = build_service_episodes(
        case.case_id, shadow, rows, shadow_request
    )
    joined = join_v3r2_outcomes(rows, episodes)
    return {'case': identification_case_manifest(case), 'off': off, 'shadow': shadow, 'off_request': off_request, 'shadow_request': shadow_request, 'rows': rows, 'join': joined, 'profile_sha256': profile_sha256(off_request), 'potential_sha256': canonical_sha256(off_request['heuristic_time']), 'potential_equal': off_potential == shadow_potential, 'off_request_sha256': request_sha256(off_request), 'shadow_request_sha256': request_sha256(shadow_request), 'off_ordinary_request_sha256': ordinary_request_sha256(off_request), 'shadow_ordinary_request_sha256': ordinary_request_sha256(shadow_request)}

def summarize_case(
    case: V3R2Case | IdentificationCase, result: Mapping[str, Any]
) -> dict[str, Any]:
    off, shadow = (_mapping(result.get('off'), 'off'), _mapping(result.get('shadow'), 'shadow'))
    off_request, shadow_request = (_mapping(result.get('off_request'), 'off_request'), _mapping(result.get('shadow_request'), 'shadow_request'))
    off_summary, shadow_summary = (_mapping(off.get('summary'), 'off.summary'), _mapping(shadow.get('summary'), 'shadow.summary'))
    rows, joined = (_object_rows(result.get('rows'), 'rows'), _mapping(result.get('join'), 'join'))
    expected = {'external'} if case.flow_pattern == 'external_only' else {'local'} if case.flow_pattern == 'local_only' else {'external', 'local'}
    off_audit = _service_audit(case.case_id, case.bag_count, expected, off, off_request, exact_node=1)
    shadow_audit = _service_audit(case.case_id, case.bag_count, expected, shadow, shadow_request, exact_node=1)
    census = _shadow_census(shadow_summary, rows, shadow)
    legacy_wait = legacy_wait_pair(off, shadow)
    parity = ordinary_payload_hashes(off) == ordinary_payload_hashes(shadow)
    request_parity = result.get('off_ordinary_request_sha256') == result.get('shadow_ordinary_request_sha256') and result.get('potential_equal') is True
    binaries = (_loaded_binary(off), _loaded_binary(shadow))
    sequence_parity = {key: off_audit['service_sequence'][key] == shadow_audit['service_sequence'][key] for key in ('sequence_sha256', 'origin_sequence_sha256', 'maximum_consecutive_origin_run')}
    hard = all((off_audit['pass'], shadow_audit['pass'], legacy_wait['pass'], all(sequence_parity.values()), census['pass'], parity, request_parity, binaries[0] == binaries[1], joined.get('status') == JOINED))
    resources = {'off': _resource_values(off, shadow=False), 'shadow': _resource_values(shadow, shadow=True)}
    manifest = (
        identification_case_manifest(case)
        if isinstance(case, IdentificationCase)
        else case_manifest(case)
    )
    return {**{key: manifest[key] for key in ('cohort', 'replica', 'case_id', 'service_seconds', 'bag_count', 'flow_pattern', 'negative_control')}, 'admitted_row_count': len(rows), 'join_status': joined.get('status'), 'census_partition_pass': census['pass'], 'hard_gate_pass': hard, 'off_audit': off_audit, 'shadow_audit': shadow_audit, 'legacy_wait_over_120': legacy_wait, 'service_sequence_parity': sequence_parity, 'census': census, 'ordinary_parity': parity, 'request_parity': request_parity, 'binary_parity': binaries[0] == binaries[1], 'loaded_cpp_binary_path': binaries[0][0], 'loaded_cpp_binary_sha256': binaries[0][1], 'off_hashes': ordinary_payload_hashes(off), 'shadow_hashes': ordinary_payload_hashes(shadow), 'rows_sha256': canonical_sha256(rows), 'pairs_sha256': canonical_sha256(joined.get('pairs')), 'profile_sha256': result.get('profile_sha256'), 'potential_sha256': result.get('potential_sha256'), 'off_request_sha256': result.get('off_request_sha256'), 'shadow_request_sha256': result.get('shadow_request_sha256'), 'off_ordinary_request_sha256': result.get('off_ordinary_request_sha256'), 'shadow_ordinary_request_sha256': result.get('shadow_ordinary_request_sha256'), 'resources': resources}

def merge_joined_pairs(rows: Sequence[Mapping[str, Any]], joined: Mapping[str, Any]) -> list[dict[str, Any]]:
    pairs = _object_rows(joined.get('pairs'), 'join.pairs')
    by_key = {(row['case_id'], row['observation_ordinal'], row['opportunity_id']): row for row in rows}
    if len(by_key) != len(rows):
        raise ValueError('V3R2 row identity is not unique')
    merged = []
    for pair in pairs:
        key = (pair.get('case_id'), pair.get('observation_ordinal'), pair.get('opportunity_id'))
        if key not in by_key:
            raise ValueError('joined pair has no exact source row')
        value = {**by_key[key], **pair}
        if pair.get('primary') and pair.get('status') == JOINED:
            _finite(pair.get('Y_realized'), 'pair.Y_realized')
            _finite(pair.get('A_gap'), 'pair.A_gap')
        merged.append(value)
    return merged

def _average_ranks(values: Sequence[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        stop = start + 1
        while stop < len(ordered) and values[ordered[stop]] == values[ordered[start]]:
            stop += 1
        rank = (start + 1 + stop) / 2.0
        for index in ordered[start:stop]:
            ranks[index] = rank
        start = stop
    return ranks

def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y) or len(x) < 2 or len(set(x)) < 2 or (len(set(y)) < 2):
        return None
    rx, ry = (_average_ranks(x), _average_ranks(y))
    mx, my = (math.fsum(rx) / len(rx), math.fsum(ry) / len(ry))
    numerator = math.fsum(((a - mx) * (b - my) for a, b in zip(rx, ry)))
    denominator = math.sqrt(math.fsum(((a - mx) ** 2 for a in rx)) * math.fsum(((b - my) ** 2 for b in ry)))
    return numerator / denominator if denominator > 0.0 else None

def percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    low, high = (math.floor(position), math.ceil(position))
    return ordered[low] if low == high else ordered[low] + (position - low) * (ordered[high] - ordered[low])

def case_block_bootstrap(case_rhos: Mapping[str, float], *, draws: int=BOOTSTRAP_DRAWS) -> dict[str, Any]:
    values = [case_rhos[key] for key in sorted(case_rhos)]
    if not values or draws <= 0:
        return {'point': None, 'lower_2p5': None, 'seed': BOOTSTRAP_SEED, 'draws': draws}
    rng = random.Random(BOOTSTRAP_SEED)
    estimates = [math.fsum((values[rng.randrange(len(values))] for _ in values)) / len(values) for _ in range(draws)]
    return {'point': math.fsum(values) / len(values), 'lower_2p5': percentile(estimates, 0.025), 'seed': BOOTSTRAP_SEED, 'draws': draws}

def wilson_interval(successes: int, total: int) -> tuple[float | None, float | None]:
    if total <= 0 or successes < 0 or successes > total:
        return (None, None)
    p, z2 = (successes / total, WILSON_Z ** 2)
    center = (p + z2 / (2 * total)) / (1 + z2 / total)
    margin = WILSON_Z * math.sqrt(p * (1 - p) / total + z2 / (4 * total ** 2)) / (1 + z2 / total)
    return (center - margin, center + margin)

def gate(name: str, passed: bool, evidence: Any=None) -> dict[str, Any]:
    return {'name': name, 'pass': bool(passed), 'evidence': evidence}

def evaluate_primary(pairs: Sequence[Mapping[str, Any]], cases: Sequence[Mapping[str, Any]], *, draws: int=BOOTSTRAP_DRAWS) -> dict[str, Any]:
    primary = [pair for pair in pairs if pair.get('primary') and pair.get('status') == JOINED]
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for pair in primary:
        grouped[str(pair['case_id'])].append(pair)
    directional = []
    for case in cases:
        values = grouped.get(str(case.get('case_id')), [])
        x, y = ([float(row['X_insert']) for row in values], [float(row['Y_realized']) for row in values])
        rho = spearman(x, y)
        if case.get('flow_pattern') in MIXED_FLOWS and len(values) >= 2 and rho is not None:
            directional.append({**{key: case.get(key) for key in ('case_id', 'service_seconds', 'bag_count', 'flow_pattern')}, 'pair_count': len(values), 'rho': rho})
    rhos = {str(row['case_id']): float(row['rho']) for row in directional}
    bootstrap = case_block_bootstrap(rhos, draws=draws)
    positive = sum((value > 0.0 for value in rhos.values()))
    share = positive / len(rhos) if rhos else None
    lower, upper = wilson_interval(positive, len(rhos))
    unique_bags = {(pair['case_id'], pair[field]) for pair in primary for field in ('local_runtime_bag_id', 'external_runtime_bag_id')}
    expected_ids = {case.case_id for case in registered_cases()}
    observed_ids = [case.get('case_id') for case in cases]
    controls = [case for case in cases if case.get('flow_pattern') in NEGATIVE_CONTROLS]
    flows = {row['flow_pattern'] for row in directional}
    services = {row['service_seconds'] for row in directional}
    populations = {row['bag_count'] for row in directional}
    gates = [gate('exact_frozen_120_case_population', len(observed_ids) == 120 and set(observed_ids) == expected_ids, len(observed_ids)), gate('directional_case_strata', len(directional) >= MIN_DIRECTIONAL_CASES, len(directional)), gate('unique_primary_bags', len(unique_bags) >= MIN_PRIMARY_BAGS, len(unique_bags)), gate('mixed_flow_coverage', len(flows) >= MIN_MIXED_FLOWS, sorted(flows)), gate('service_coverage', services == set(SERVICE_SECONDS), sorted(services)), gate('population_coverage', populations == set(BAG_COUNTS), sorted(populations)), gate('negative_controls_zero', bool(controls) and all((case.get('admitted_row_count') == 0 for case in controls))), gate('join_and_census_complete', all((case.get('join_status') == JOINED and case.get('census_partition_pass') is True for case in cases))), gate('case_equal_rho_positive', bootstrap['point'] is not None and bootstrap['point'] > 0.0, bootstrap), gate('case_block_rho_lcb_positive', bootstrap['lower_2p5'] is not None and bootstrap['lower_2p5'] > 0.0, bootstrap), gate('positive_rho_share', share is not None and share >= 0.6, share), gate('positive_rho_wilson_lower', lower is not None and lower > 0.5, {'lower': lower, 'upper': upper})]
    return {'pass': all((item['pass'] for item in gates)), 'gates': gates, 'directional_cases': directional, 'bootstrap': bootstrap, 'positive_share': share, 'wilson': {'lower': lower, 'upper': upper}, 'primary_pair_count': len(primary), 'unique_primary_bag_count': len(unique_bags)}

def evaluate_safety_regression(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    expected_ids = {case.case_id for case in registered_cases()}
    observed_ids = [case.get('case_id') for case in cases]
    controls = [case for case in cases if case.get('flow_pattern') in NEGATIVE_CONTROLS]
    gates = [
        gate(
            'exact_frozen_120_case_population',
            len(observed_ids) == 120 and set(observed_ids) == expected_ids,
            len(observed_ids),
        ),
        gate(
            'negative_controls_zero',
            bool(controls)
            and all(case.get('admitted_row_count') == 0 for case in controls),
            len(controls),
        ),
        gate(
            'join_and_census_complete',
            all(
                case.get('join_status') == JOINED
                and case.get('census_partition_pass') is True
                for case in cases
            ),
        ),
        gate(
            'all_hard_safety_gates',
            all(case.get('hard_gate_pass') is True for case in cases),
        ),
    ]
    return {'pass': all(item['pass'] for item in gates), 'gates': gates}

def evaluate_identification_primary(
    pairs: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
    *,
    draws: int=BOOTSTRAP_DRAWS,
) -> dict[str, Any]:
    expected_ids = {case.case_id for case in identification_cases()}
    all_primary = [
        pair
        for pair in pairs
        if pair.get('primary') and pair.get('status') == JOINED
    ]
    unknown_pair_ids = sorted(
        {
            str(pair.get('case_id'))
            for pair in all_primary
            if str(pair.get('case_id')) not in expected_ids
        }
    )
    primary = [
        pair for pair in all_primary if str(pair.get('case_id')) in expected_ids
    ]
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for pair in primary:
        grouped[str(pair['case_id'])].append(pair)
    diagnostics = []
    for case in cases:
        values = grouped.get(str(case.get('case_id')), [])
        x = [float(row['X_insert']) for row in values]
        y = [float(row['Y_realized']) for row in values]
        rho = spearman(x, y)
        diagnostics.append(
            {
                **{
                    key: case.get(key)
                    for key in (
                        'case_id',
                        'service_seconds',
                        'bag_count',
                        'flow_pattern',
                        'replica',
                    )
                },
                'pair_count': len(values),
                'distinct_x': len(set(x)),
                'distinct_y': len(set(y)),
                'rho': rho,
                'directional': len(values) >= 2 and rho is not None,
            }
        )
    directional = [row for row in diagnostics if row['directional']]
    rhos = {str(row['case_id']): float(row['rho']) for row in directional}
    bootstrap = case_block_bootstrap(rhos, draws=draws)
    positive = sum(value > 0.0 for value in rhos.values())
    share = positive / len(rhos) if rhos else None
    lower, upper = wilson_interval(positive, len(rhos))
    unique_bags = {
        (pair['case_id'], pair[field])
        for pair in primary
        for field in ('local_runtime_bag_id', 'external_runtime_bag_id')
    }
    observed_ids = [case.get('case_id') for case in cases]
    flows = {row['flow_pattern'] for row in directional}
    services = {row['service_seconds'] for row in directional}
    populations = {row['bag_count'] for row in directional}
    gates = [
        gate(
            'exact_frozen_24_case_population',
            len(observed_ids) == 24 and set(observed_ids) == expected_ids,
            len(observed_ids),
        ),
        gate('primary_pair_case_population', not unknown_pair_ids, unknown_pair_ids),
        gate('directional_case_strata', len(directional) >= MIN_DIRECTIONAL_CASES, len(directional)),
        gate('unique_primary_bags', len(unique_bags) >= MIN_PRIMARY_BAGS, len(unique_bags)),
        gate('mixed_flow_coverage', len(flows) >= MIN_MIXED_FLOWS, sorted(flows)),
        gate('service_coverage', services == set(SERVICE_SECONDS), sorted(services)),
        gate('population_coverage', populations == set(BAG_COUNTS), sorted(populations)),
        gate(
            'join_and_census_complete',
            all(
                case.get('join_status') == JOINED
                and case.get('census_partition_pass') is True
                for case in cases
            ),
        ),
        gate('case_equal_rho_positive', bootstrap['point'] is not None and bootstrap['point'] > 0.0, bootstrap),
        gate('case_block_rho_lcb_positive', bootstrap['lower_2p5'] is not None and bootstrap['lower_2p5'] > 0.0, bootstrap),
        gate('positive_rho_share', share is not None and share >= 0.6, share),
        gate('positive_rho_wilson_lower', lower is not None and lower > 0.5, {'lower': lower, 'upper': upper}),
    ]
    return {'pass': all(item['pass'] for item in gates), 'gates': gates, 'case_diagnostics': diagnostics, 'directional_cases': directional, 'bootstrap': bootstrap, 'positive_share': share, 'wilson': {'lower': lower, 'upper': upper}, 'primary_pair_count': len(primary), 'unique_primary_bag_count': len(unique_bags)}

def evaluate_resources(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    names = ('events_per_completed', 'junction_local_accounted_bytes', 'runtime_internal_accounted_bytes', 'total_accounted_bytes')
    gates = []
    for name in names:
        ratios = []
        for case in cases:
            try:
                off = _finite(case['resources']['off'][name], f'off {name}')
                shadow = _finite(case['resources']['shadow'][name], f'shadow {name}')
                ratio = shadow / off if off > 0.0 else 1.0 if shadow == 0.0 else math.inf
            except (KeyError, TypeError, ValueError):
                ratio = math.inf
            ratios.append(ratio)
        gates.append(gate('resource_' + name, bool(ratios) and all((ratio <= RESOURCE_RATIO_LIMIT for ratio in ratios)), {'limit': RESOURCE_RATIO_LIMIT, 'max_ratio': max((ratio for ratio in ratios if math.isfinite(ratio)), default=None), 'non_finite': sum((not math.isfinite(ratio) for ratio in ratios))}))
    return {'pass': all((item['pass'] for item in gates)), 'gates': gates}
def _sha_text(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all((character in '0123456789abcdef' for character in value))
def _git_head_text(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all((character in '0123456789abcdef' for character in value.lower()))
def _validated_frozen_source_hashes() -> dict[Path, str]:
    identities = [(path, size, sha256) for path, size, sha256 in USER_CONTRACT_FILES]
    validated: dict[Path, str] = {}
    for path, expected_bytes, expected_sha256 in identities:
        resolved = path.resolve()
        if resolved in validated:
            raise ValueError(f'frozen source identity is duplicated: {path}')
        try:
            actual_bytes = resolved.stat().st_size
            actual_sha256 = file_sha256(resolved)
        except OSError as error:
            raise ValueError(f'frozen source file is unavailable: {path}: {error}') from error
        if actual_bytes != expected_bytes or actual_sha256 != expected_sha256:
            raise ValueError(f'frozen source file identity changed: {path}')
        validated[resolved] = actual_sha256
    return validated

def source_bundle_manifest() -> dict[str, Any]:
    frozen_hashes = _validated_frozen_source_hashes()
    files = []
    for path in SOURCE_BUNDLE_PATHS:
        resolved = path.resolve(strict=True)
        sha256 = frozen_hashes[resolved] if resolved in frozen_hashes else file_sha256(resolved)
        files.append({'path': resolved.relative_to(ROOT).as_posix(), 'sha256': sha256})
    return {'files': files, 'sha256': canonical_sha256(files)}
def implementation_identity(*, command_runner: Callable[..., Any]=subprocess.run) -> dict[str, Any]:
    head_result = command_runner(['git', 'rev-parse', 'HEAD'], cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    head = str(head_result.stdout).strip().lower()
    ancestor_result = command_runner(['git', 'merge-base', '--is-ancestor', IMPLEMENTATION_PARENT, 'HEAD'], cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    diff_result = command_runner(['git', 'diff', '--name-only', IMPLEMENTATION_PARENT + '..HEAD'], cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    changed = {line.strip().replace('\\', '/') for line in str(diff_result.stdout).splitlines() if line.strip()}
    unexpected = sorted(changed - IMPLEMENTATION_ALLOWED_PATHS)
    status_result = command_runner(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    dirty = [line for line in str(status_result.stdout).splitlines() if line.strip()]
    checks = {'head_resolved': head_result.returncode == 0 and _git_head_text(head), 'parent_is_ancestor': ancestor_result.returncode == 0, 'implementation_not_parent': head != IMPLEMENTATION_PARENT, 'diff_paths_allowed': diff_result.returncode == 0 and bool(changed) and not unexpected, 'source_bundle_clean': status_result.returncode == 0 and (not dirty)}
    evidence = {'diff_paths_allowed': {'changed': sorted(changed), 'unexpected': unexpected}, 'source_bundle_clean': dirty}
    gates = [gate('implementation_' + name, passed, evidence.get(name, head)) for name, passed in checks.items()]
    return {'pass': all((item['pass'] for item in gates)), 'head': head, 'changed_paths': sorted(changed), 'unexpected_changed_paths': unexpected, 'dirty_source_paths': dirty, 'gates': gates}
def _reject_json_constant(value: str) -> Any:
    raise ValueError(f'non-finite JSON constant is forbidden: {value}')
def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f'duplicate JSON object key is forbidden: {key!r}')
        value[key] = item
    return value
def _parse_prefixed_stdout(stdout: str, prefix: str) -> Mapping[str, Any]:
    lines = [line[len(prefix):] for line in stdout.splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        raise ValueError(f'expected exactly one {prefix!r} stdout line, got {len(lines)}')
    value = json.loads(
        lines[0],
        parse_constant=_reject_json_constant,
        object_pairs_hook=_strict_json_object,
    )
    return _mapping(value, 'proof/worker stdout JSON')
def read_g32_build_head(g32_binary: Path) -> str:
    from czr005.cpp_backend import load_cpp_module

    binary = g32_binary.resolve(strict=True)
    module = load_cpp_module(binary.parent)
    loaded_path = Path(str(module.__file__)).resolve(strict=True)
    if loaded_path != binary:
        raise ValueError('build-head reader loaded a different G32 binary')
    build_head = getattr(module, 'g4irsf32_v3r2_build_head', None)
    if not _git_head_text(build_head):
        raise ValueError('G32 binary lacks an exact 40-hex build head')
    return str(build_head).lower()

def run_native_proof(executable: Path, g32_binary: Path, *, nested_executable: Path=NESTED_PROOF_EXE, process_runner: Callable[..., Any]=subprocess.run, expected_executable: Path=NATIVE_PROOF_EXE, expected_nested_executable: Path=NESTED_PROOF_EXE, build_head_reader: Callable[[Path], str]=read_g32_build_head) -> dict[str, Any]:
    executable, nested_executable, g32_binary = (executable.resolve(strict=True), nested_executable.resolve(strict=True), g32_binary.resolve(strict=True))
    if executable != expected_executable.resolve(strict=True) or nested_executable != expected_nested_executable.resolve(strict=True):
        raise ValueError('native proof executable path differs from the registered paths')
    executable_sha_before = file_sha256(executable)
    nested_executable_sha_before = file_sha256(nested_executable)
    g32_binary_sha_before = file_sha256(g32_binary)
    completed = process_runner([str(executable)], cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace', check=False); nested_completed = process_runner([str(nested_executable)], cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    proof = _parse_prefixed_stdout(str(completed.stdout), NATIVE_PROOF_PREFIX); nested_proof = _parse_prefixed_stdout(str(nested_completed.stdout), NESTED_PROOF_PREFIX)
    expected_keys = {'schema_id', 'test_id', 'build_head', *NATIVE_PROOF_ASSERTIONS}
    pyd_build_head = build_head_reader(g32_binary)
    executable_sha_after = file_sha256(executable)
    nested_executable_sha_after = file_sha256(nested_executable)
    g32_binary_sha_after = file_sha256(g32_binary)
    proof_build_head, nested_build_head = (str(proof.get('build_head', '')).lower(), str(nested_proof.get('build_head', '')).lower())
    checks = {'exit_zero': completed.returncode == 0, 'fixed_executable': executable == expected_executable.resolve(), 'executable_unchanged': executable_sha_before == executable_sha_after, 'exact_schema': set(proof) == expected_keys, 'schema_id': proof.get('schema_id') == NATIVE_PROOF_SCHEMA, 'test_id': proof.get('test_id') == NATIVE_PROOF_TEST_ID, 'all_native_assertions': all((proof.get(key) is True for key in NATIVE_PROOF_ASSERTIONS)), 'same_build_head': _git_head_text(proof_build_head) and proof_build_head == pyd_build_head, 'nested_exit_zero': nested_completed.returncode == 0, 'fixed_nested_executable': nested_executable == expected_nested_executable.resolve(), 'nested_executable_unchanged': nested_executable_sha_before == nested_executable_sha_after, 'nested_exact_schema': set(nested_proof) == {'schema_id', 'test_id', 'build_head', NESTED_PROOF_ASSERTION}, 'nested_schema_id': nested_proof.get('schema_id') == NESTED_PROOF_SCHEMA, 'nested_test_id': nested_proof.get('test_id') == NESTED_PROOF_TEST_ID, 'nested_assertion': nested_proof.get(NESTED_PROOF_ASSERTION) is True, 'nested_same_build_head': _git_head_text(nested_build_head) and nested_build_head == pyd_build_head, 'g32_binary_unchanged': g32_binary_sha_before == g32_binary_sha_after}
    binding = {'executable_path': str(executable), 'executable_sha256': executable_sha_before, 'executable_sha256_after': executable_sha_after, 'nested_executable_path': str(nested_executable), 'nested_executable_sha256': nested_executable_sha_before, 'nested_executable_sha256_after': nested_executable_sha_after, 'g32_binary_path': str(g32_binary), 'g32_binary_sha256': g32_binary_sha_before, 'g32_binary_sha256_after': g32_binary_sha_after, 'build_head': pyd_build_head, 'proof_build_head': proof_build_head, 'nested_proof_build_head': nested_build_head, 'source_bundle': source_bundle_manifest(), 'exit_code': completed.returncode, 'nested_exit_code': nested_completed.returncode, 'proof': dict(proof), 'nested_proof': dict(nested_proof)}
    gates = [gate('native_proof_' + name, passed, binding if name in {'exit_zero', 'nested_exit_zero'} else None) for name, passed in checks.items()]
    return {'pass': all((item['pass'] for item in gates)), 'gates': gates, **binding}

def _worker_projection(request: Mapping[str, Any], binary: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    loaded = _loaded_binary(payload)
    resolved = binary.resolve(strict=True)
    if Path(loaded[0]).resolve() != resolved or loaded[1] != file_sha256(resolved):
        raise ValueError('worker loaded binary differs from resolved requested binary')
    return {'schema': 'czr005.g4irsf32.v3r2_off_worker.v1', 'binary_path': str(resolved), 'binary_sha256': loaded[1], 'request_sha256': request_sha256(request), 'ordinary_request_sha256': ordinary_request_sha256(request), 'ordinary': ordinary_payload_hashes(payload), 'accounting': exact_off_accounting(payload), 'extension_absent': exact_off_extension_absent(payload)}

def worker_off_json(request_path: Path, binary: Path) -> int:
    request = _mapping(
        json.loads(
            request_path.read_text(encoding='utf-8'),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_strict_json_object,
        ),
        'worker request',
    )
    mode = request.get('source_aware_destination_service_mode', 'off')
    if mode != 'off':
        raise ValueError('worker accepts only omitted/default/explicit off')
    resolved = binary.resolve(strict=True)
    prepared = dict(request)
    prepared.update(expected_binary_path=resolved, search_path=resolved.parent)
    payload = cpp_executor(**prepared)
    print(WORKER_PREFIX + _canonical(_worker_projection(prepared, resolved, payload)).decode('utf-8'))
    return 0

def run_binary_worker(request: Mapping[str, Any], binary: Path, *, process_runner: Callable[..., Any]=subprocess.run) -> Mapping[str, Any]:
    resolved = binary.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='g4irsf32_v3r2_worker_') as directory:
        request_path = Path(directory) / 'request.json'
        request_path.write_bytes(_canonical(_portable(request)))
        completed = process_runner([sys.executable, str(RUNNER_PATH), '--worker-off-json', str(request_path), '--worker-binary', str(resolved)], cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    if completed.returncode != 0:
        raise ValueError(f'isolated off worker failed for {resolved}: {completed.stderr}')
    value = _parse_prefixed_stdout(str(completed.stdout), WORKER_PREFIX)
    if value.get('binary_sha256') != file_sha256(resolved):
        raise ValueError('isolated off worker binary digest mismatch')
    return value
def evaluate_cross_binary_off(request: Mapping[str, Any], g32_binary: Path, *, g31_binary: Path=G31_BINARY, worker: Worker=run_binary_worker, expected_g31_binary: Path=G31_BINARY) -> dict[str, Any]:
    if g31_binary.resolve(strict=True) != expected_g31_binary.resolve(strict=True) or file_sha256(g31_binary.resolve(strict=True)) != G31_BINARY_SHA256:
        raise ValueError('frozen G31 Release binary hash drift')
    ordinary = {key: value for key, value in request.items() if key not in {'source_aware_destination_service_mode', 'source_aware_destination_service_trace_limit', 'expected_binary_path', 'search_path'}}
    explicit = {**ordinary, 'source_aware_destination_service_mode': 'off', 'source_aware_destination_service_trace_limit': 200000}
    runs = {'g31_parent': worker(ordinary, g31_binary), 'g32_omitted': worker(ordinary, g32_binary), 'g32_explicit': worker(explicit, g32_binary), 'g32_repeated': worker(explicit, g32_binary)}
    request_hashes = {str(value.get('ordinary_request_sha256')) for value in runs.values()}
    ordinary_hashes = {canonical_sha256(value.get('ordinary')) for value in runs.values()}
    accounting_hashes = {canonical_sha256(value.get('accounting')) for value in runs.values()}
    gates = [gate('cross_binary_exact_ordinary_request', len(request_hashes) == 1, sorted(request_hashes)), gate('cross_binary_exact_off_payload', len(ordinary_hashes) == 1, sorted(ordinary_hashes)), gate('cross_binary_exact_off_accounting', len(accounting_hashes) == 1, sorted(accounting_hashes)), gate('cross_binary_exact_off_extension_absent', all((value.get('extension_absent') is True for value in runs.values())), {key: value.get('extension_absent') for key, value in runs.items()}), gate('g31_release_binary_exact', runs['g31_parent'].get('binary_sha256') == G31_BINARY_SHA256), gate('g32_omitted_explicit_repeated', canonical_sha256(runs['g32_omitted'].get('ordinary')) == canonical_sha256(runs['g32_explicit'].get('ordinary')) == canonical_sha256(runs['g32_repeated'].get('ordinary')) and canonical_sha256(runs['g32_omitted'].get('accounting')) == canonical_sha256(runs['g32_explicit'].get('accounting')) == canonical_sha256(runs['g32_repeated'].get('accounting')))]
    return {'pass': all((item['pass'] for item in gates)), 'gates': gates, 'runs': runs}
def _prefix(payload: Mapping[str, Any], cutoff: float, *, node: int | None=None, semantic: bool=False) -> dict[str, Any]:
    def keep(row: Mapping[str, Any], time_key: str) -> bool:
        if not isinstance(row.get(time_key), (int, float)) or float(row[time_key]) >= cutoff:
            return False
        if node is None:
            return True
        related = {row.get('node'), row.get('current_node'), row.get('selected_next'), row.get('from_node'), row.get('to_node')}
        candidates = row.get('candidate_next_nodes')
        if isinstance(candidates, (list, tuple)):
            related.update(candidates)
        candidate_records = row.get('candidate_records')
        if isinstance(candidate_records, (list, tuple)):
            related.update(
                candidate.get('next_node')
                for candidate in candidate_records
                if isinstance(candidate, Mapping)
            )
        return node in related
    def project(row: Mapping[str, Any], kind: str) -> dict[str, Any]:
        value = dict(row)
        if semantic:
            for key in ('scenario', 'decision_id'):
                value.pop(key, None)
            if kind == 'events':
                value.pop('seq', None)
            if kind == 'observations':
                for key in ('observation_ordinal', 'opportunity_id', 'event_seq', 'external_direct_episode_event_seq'):
                    value.pop(key, None)
            if isinstance(value.get('metadata'), Mapping):
                value['metadata'] = {key: item for key, item in value['metadata'].items() if key not in {'scenario', 'decision_id', 'arrive_event_seq', 'decision_ordinal', 'priority_enqueue_sequence'}}
        return value
    rows = payload.get(ROW_KEY, [])
    return {'decisions': [project(row, 'decisions') for row in _object_rows(payload.get('decisions'), 'decisions') if keep(row, 'event_time')], 'hold_attempts': [project(row, 'hold_attempts') for row in _object_rows(payload.get('hold_attempts'), 'hold_attempts') if keep(row, 'event_time')], 'events': [project(row, 'events') for row in _object_rows(payload.get('events'), 'events') if keep(row, 'time')], 'observations': [project(row, 'observations') for row in _object_rows(rows, ROW_KEY) if keep(row, 'event_time') and (node is None or row.get('node') == node)]}
def _future_request(case: V3R2Case, releases: tuple[float, float], binary: Path) -> dict[str, Any]:
    rows = build_bag_rows(case)
    deadline = 10000.0
    rows += [{'segment_id': 'v3r2_future:external', 'task_id': 90002, 'pass_time': releases[0], 'std': deadline, 'start': 0, 'goal': 3, 'source': 'external'}, {'segment_id': 'v3r2_future:local', 'task_id': 90003, 'pass_time': releases[1], 'std': deadline, 'start': 1, 'goal': 3, 'source': 'local'}]
    return _build_profile_request(motif_profile(1.0), rows, scenario=case.scenario + '__future_probe', mode=MODE, binary=binary)[0]
def _sparse_potential(nodes: Sequence[Sequence[Any]], edges: Sequence[Sequence[Any]]) -> list[list[float]]:
    ids, size = (sorted((int(row[0]) for row in nodes)), max((int(row[0]) for row in nodes)) + 1)
    service = {int(row[0]): max(float(row[2]), 0.001) for row in nodes}
    incoming: dict[int, list[tuple[int, float]]] = {node: [] for node in ids}
    for start, end, length, speed in edges:
        incoming[int(end)].append((int(start), float(length) / float(speed)))
    unreachable = math.fsum(service.values()) + math.fsum((float(row[2]) / float(row[3]) for row in edges)) + 1.0
    matrix = [[unreachable] * size for _ in range(size)]
    for goal in ids:
        distances, queue = ({node: math.inf for node in ids}, [(0.0, goal)])
        distances[goal] = 0.0
        while queue:
            cost, node = heapq.heappop(queue)
            if cost != distances[node]:
                continue
            for predecessor, travel in incoming[node]:
                candidate = cost + travel + service[predecessor]
                if candidate < distances[predecessor]:
                    distances[predecessor] = candidate
                    heapq.heappush(queue, (candidate, predecessor))
        for source in ids:
            matrix[source][goal] = distances[source] if math.isfinite(distances[source]) else unreachable
    return matrix
def _distant_request(case: V3R2Case, binary: Path) -> dict[str, Any]:
    request = build_request(case, mode=MODE, binary=binary)[0]
    request['node_records'] += [[10, 7, 0.0, 0, 10, [11]], [11, 1, 1.0, 1, 10, [12]], [12, 2, 0.0, 2, 10, []]]
    request['edge_records'] += [[10, 11, 0.05, 1.0], [11, 12, 0.05, 1.0]]
    request['bag_records'] += [['v3r2_distant', 90001, 0.0, 10000.0, 10, 12, 'distant']]
    request['storage_source_nodes'] = [0, 10]
    request['scenario'] = case.scenario + '__distant_probe'
    request['heuristic_time'] = _sparse_potential(request['node_records'], request['edge_records'])
    assert_request_projection(request, MODE, [0, 10], request['scenario'])
    return request
def _case_fixture_evidence(result: Mapping[str, Any]) -> dict[str, Any]:
    rows, joined = (_object_rows(result.get('rows'), 'fixture rows'), _mapping(result.get('join'), 'fixture join'))
    return {'rows': rows, 'pairs': _object_rows(joined.get('pairs'), 'fixture pairs'), 'off_ordinary_hashes': ordinary_payload_hashes(_mapping(result.get('off'), 'fixture off')), 'shadow_ordinary_hashes': ordinary_payload_hashes(_mapping(result.get('shadow'), 'fixture shadow'))}
def _probe_audit(case_id: str, payload: Mapping[str, Any], request: Mapping[str, Any], bag_count: int, origins: set[str], exact_node: int | None) -> dict[str, Any]:
    rows = extract_rows(payload, case_id=case_id, request=request)
    joined = join_v3r2_outcomes(rows, build_service_episodes(case_id, payload, rows, request))
    census = _shadow_census(_mapping(payload.get('summary'), 'probe summary'), rows, payload)
    service = _service_audit(case_id, bag_count, origins, payload, request, exact_node=exact_node)
    return {'pass': joined.get('status') == JOINED and census['pass'] and service['pass'], 'row_count': len(rows), 'join_status': joined.get('status'), 'census': census, 'service': service, 'rows': rows, 'pairs': _object_rows(joined.get('pairs'), 'probe pairs'), 'off_ordinary_hashes': None, 'shadow_ordinary_hashes': ordinary_payload_hashes(payload)}
def _map2_stage0(executor: Executor, binary: Path, expected_binary_sha256: str) -> dict[str, Any]:
    off_request, hashes = map2_fixture(mode='off', binary=binary)
    shadow_request, shadow_hashes = map2_fixture(mode=MODE, binary=binary)
    off, shadow = (executor(**off_request), executor(**shadow_request))
    rows = extract_rows(shadow, case_id='v3r2_map2_sentinel', request=shadow_request, metadata={'flow_pattern': 'map2_sentinel', 'bag_count': 8, 'service_seconds': None})
    joined = join_v3r2_outcomes(rows, build_service_episodes('v3r2_map2_sentinel', shadow, rows, shadow_request))
    off_audit = _service_audit('v3r2_map2_sentinel', 8, set(), off, off_request, exact_node=None)
    shadow_audit = _service_audit('v3r2_map2_sentinel', 8, set(), shadow, shadow_request, exact_node=None)
    legacy_wait = legacy_wait_pair(off, shadow)
    census = _shadow_census(_mapping(shadow.get('summary'), 'map2 summary'), rows, shadow)
    resources = evaluate_resources([{'resources': {'off': _resource_values(off, shadow=False), 'shadow': _resource_values(shadow, shadow=True)}}])
    sequence_parity = {key: off_audit['service_sequence'][key] == shadow_audit['service_sequence'][key] for key in ('sequence_sha256', 'origin_sequence_sha256', 'maximum_consecutive_origin_run')}
    gates = [gate('map2_frozen_hashes', hashes == shadow_hashes and hashes['raw'] == MAP2_RAW_SHA256 and (hashes['profile'] == MAP2_PROFILE_SHA256) and (hashes['potential'] == MAP2_POTENTIAL_SHA256) and (hashes['rows'] == MAP2_ROWS_SHA256), hashes), gate('map2_completion_safety', off_audit['pass'] and shadow_audit['pass']), gate('map2_legacy_wait_exact', legacy_wait['pass']), gate('map2_service_sequence_exact', all(sequence_parity.values()), sequence_parity), gate('map2_exact_no_mutation', ordinary_payload_hashes(off) == ordinary_payload_hashes(shadow)), gate('map2_join_census', joined.get('status') == JOINED and census['pass'], {'row_count': len(rows)}), gate('map2_resource', resources['pass']), gate('map2_g32_binary', _loaded_binary(off)[1] == _loaded_binary(shadow)[1] == expected_binary_sha256)]
    return {'pass': all((item['pass'] for item in gates)), 'gates': gates, 'hashes': hashes, 'row_count': len(rows), 'join_status': joined.get('status'), 'census': census, 'rows_sha256': canonical_sha256(rows), 'pairs_sha256': canonical_sha256(joined.get('pairs')), 'resources': resources, 'legacy_wait_over_120': legacy_wait, 'service_sequence_parity': sequence_parity, 'off_audit': off_audit, 'shadow_audit': shadow_audit, 'rows': rows, 'pairs': _object_rows(joined.get('pairs'), 'map2 pairs'), 'off_ordinary_hashes': ordinary_payload_hashes(off), 'shadow_ordinary_hashes': ordinary_payload_hashes(shadow)}
def run_stage0(*, executor: Executor, g32_binary: Path, expected_binary_sha256: str, proof_executable: Path=NATIVE_PROOF_EXE, g31_binary: Path=G31_BINARY, worker: Worker=run_binary_worker, proof_runner: Callable[[Path, Path], Mapping[str, Any]]=run_native_proof, expected_build_head: str | None=None) -> dict[str, Any]:
    anchor = V3R2Case(1.0, 8, 'simultaneous_local_first')
    proof: Mapping[str, Any] = {'pass': False, 'gates': []}
    cross: Mapping[str, Any] = {'pass': False, 'gates': []}
    partial: dict[str, Any] = {'cases': [], 'map2': None, 'probes': {}, 'fixtures': {}}
    try:
        binary = g32_binary.resolve(strict=True)
        proof = proof_runner(proof_executable, binary)
        explicit_off = build_request(anchor, mode='off')[0]
        cross = evaluate_cross_binary_off(explicit_off, binary, g31_binary=g31_binary, worker=worker)
        direct = run_case(anchor, executor=executor, binary=binary); partial['fixtures']['direct'] = _case_fixture_evidence(direct)
        j2 = run_case(anchor, executor=executor, binary=binary, j2=True); partial['fixtures']['j2'] = _case_fixture_evidence(j2)
        controls = []
        for flow in sorted(NEGATIVE_CONTROLS):
            result = run_case(V3R2Case(1.0, 8, flow), executor=executor, binary=binary); controls.append(result); partial['fixtures'][flow] = _case_fixture_evidence(result)
        repeated_request = build_request(anchor, mode=MODE, binary=binary)[0]
        repeated_payload = executor(**repeated_request)
        repeated_rows = extract_rows(repeated_payload, case_id=anchor.case_id, request=repeated_request, metadata={'cohort': 'safety_regression', 'replica': None, 'service_seconds': anchor.service_seconds, 'bag_count': anchor.bag_count, 'flow_pattern': anchor.flow_pattern})
        partial['fixtures']['repeated_shadow'] = {'rows': repeated_rows, 'pairs': None, 'off_ordinary_hashes': ordinary_payload_hashes(direct['off']), 'shadow_ordinary_hashes': ordinary_payload_hashes(repeated_payload)}
        repeated_join = join_v3r2_outcomes(repeated_rows, build_service_episodes(anchor.case_id, repeated_payload, repeated_rows, repeated_request))
        partial['fixtures']['repeated_shadow']['pairs'] = _object_rows(repeated_join.get('pairs'), 'repeat pairs')
        summaries = []
        for fixture_case, result in [(anchor, direct), (anchor, j2), *[(V3R2Case(1.0, 8, flow), value) for flow, value in zip(sorted(NEGATIVE_CONTROLS), controls)]]:
            summaries.append(summarize_case(fixture_case, result)); partial['cases'] = summaries
        future_request_a = _future_request(anchor, (100.0, 120.0), binary); future_a = executor(**future_request_a); future_audit = [_probe_audit('v3r2_future_a', future_a, future_request_a, 10, {'external', 'local'}, 1)]; partial['fixtures']['future_a'] = future_audit[0]
        future_request_b = _future_request(anchor, (500.0, 600.0), binary); future_b = executor(**future_request_b); future_audit.append(_probe_audit('v3r2_future_b', future_b, future_request_b, 10, {'external', 'local'}, 1)); partial['fixtures']['future_b'] = future_audit[1]
        distant_request = _distant_request(anchor, binary); distant = executor(**distant_request); distant_audit = _probe_audit('v3r2_distant', distant, distant_request, 9, {'external', 'local', 'distant'}, None); partial['fixtures']['distant'] = distant_audit
        map2 = _map2_stage0(executor, binary, expected_binary_sha256); partial['map2'] = map2; partial['fixtures']['map2'] = {key: map2[key] for key in ('rows', 'pairs', 'off_ordinary_hashes', 'shadow_ordinary_hashes')}
        direct_rows, j2_rows = (direct['rows'], j2['rows'])
        future_prefixes = {'a': canonical_sha256(_prefix(future_a, 50.0)), 'b': canonical_sha256(_prefix(future_b, 50.0))}
        distant_prefixes = {'direct': canonical_sha256(_prefix(direct['shadow'], 50.0, node=1, semantic=True)), 'distant': canonical_sha256(_prefix(distant, 50.0, node=1, semantic=True))}
        probe_evidence = {'future': {'request_a_sha256': request_sha256(future_request_a), 'request_b_sha256': request_sha256(future_request_b), 'profile_a_sha256': profile_sha256(future_request_a), 'profile_b_sha256': profile_sha256(future_request_b), 'potential_a_sha256': canonical_sha256(future_request_a['heuristic_time']), 'potential_b_sha256': canonical_sha256(future_request_b['heuristic_time']), 'prefix_sha256': future_prefixes, 'audit': future_audit}, 'distant': {'request_sha256': request_sha256(distant_request), 'profile_sha256': profile_sha256(distant_request), 'potential_sha256': canonical_sha256(distant_request['heuristic_time']), 'prefix_sha256': distant_prefixes, 'audit': distant_audit}}
        partial['probes'] = probe_evidence
        build_head_pass = expected_build_head is None or proof.get('build_head') == expected_build_head
        repeat_gate = _shadow_repeat_gate(direct['shadow'], direct_rows, direct['join'], repeated_payload, repeated_rows, repeated_join)
        gates = [gate('stage0_execution', True), gate('native_proof', proof.get('pass') is True and proof.get('g32_binary_sha256') == expected_binary_sha256), gate('native_artifacts_implementation_head', build_head_pass, {'expected': expected_build_head, 'actual': proof.get('build_head')}), gate('cross_binary_exact_off', cross.get('pass') is True and set(cross.get('runs', {})) == {'g31_parent', 'g32_omitted', 'g32_explicit', 'g32_repeated'} and all(value.get('binary_sha256') == expected_binary_sha256 for key, value in cross['runs'].items() if key.startswith('g32_'))), repeat_gate, gate('direct_unique_publish', bool(direct_rows) and all((row['external_path_code'] == 1 for row in direct_rows)) and len({physical_commit_identity(row) for row in direct_rows}) == len(direct_rows)), gate('j2_unique_publish', bool(j2_rows) and all((row['external_path_code'] == 2 for row in j2_rows)) and len({physical_commit_identity(row) for row in j2_rows}) == len(j2_rows)), gate('no_direct_j2_double_publish', all((row['external_path_code'] == 2 for row in j2_rows)) and len({physical_commit_identity(row) for row in j2_rows}) == len(j2_rows)), gate('motif_controls_safety_census', all((row['hard_gate_pass'] for row in summaries)) and all((row['admitted_row_count'] == 0 for row in summaries if row['negative_control']))), gate('motif_g32_binary', all(row['loaded_cpp_binary_sha256'] == expected_binary_sha256 for row in summaries)), gate('future_probe_completion_safety_join_census', all(item['pass'] for item in future_audit), future_audit), gate('future_release_prefix_exact', future_prefixes['a'] == future_prefixes['b'], probe_evidence['future']), gate('distant_probe_completion_safety_join_census', distant_audit['pass'], distant_audit), gate('distant_L_prefix_exact', distant_prefixes['direct'] == distant_prefixes['distant'], probe_evidence['distant']), gate('map2_sentinel', map2['pass'])]
        gates.extend(proof.get('gates', []))
        gates.extend(cross.get('gates', []))
        gates.extend(map2['gates'])
        return {'pass': all((item['pass'] for item in gates)), 'status': STAGE0_PASS if all((item['pass'] for item in gates)) else STAGE0_NO_GO, 'gates': gates, 'native_proof': proof, 'cross_binary': cross, **partial, 'error': None}
    except Exception as error:
        gates = [gate('stage0_execution', False, {'type': type(error).__name__, 'error': str(error)}), *proof.get('gates', []), *cross.get('gates', [])]
        return {'pass': False, 'status': STAGE0_NO_GO, 'gates': gates, 'native_proof': proof, 'cross_binary': cross, **partial, 'error': str(error)}

def run_stage1(*, executor: Executor, g32_binary: Path, expected_binary_sha256: str, draws: int=BOOTSTRAP_DRAWS) -> dict[str, Any]:
    manifest = population_manifest()
    safety_summaries, safety_observations, safety_pairs = ([], [], [])
    for case in registered_cases():
        try:
            result = run_case(case, executor=executor, binary=g32_binary)
            case_rows = _object_rows(result.get('rows'), 'stage1 safety rows'); safety_observations.extend(case_rows)
            case_pairs = merge_joined_pairs(case_rows, _mapping(result.get('join'), 'stage1 safety join')); safety_pairs.extend(case_pairs)
            summary = summarize_case(case, result)
        except Exception as error:
            case_value = case_manifest(case)
            summary = {**{key: case_value[key] for key in ('cohort', 'replica', 'case_id', 'service_seconds', 'bag_count', 'flow_pattern', 'negative_control')}, 'admitted_row_count': None, 'join_status': 'V3R2_OUTCOME_JOIN_INVALID', 'census_partition_pass': False, 'hard_gate_pass': False, 'error_type': type(error).__name__, 'error': str(error)}
        safety_summaries.append(summary)

    identification_summaries, identification_observations, identification_pairs = ([], [], [])
    for case in identification_cases():
        try:
            result = run_identification_case(
                case, executor=executor, binary=g32_binary
            )
            case_rows = _object_rows(result.get('rows'), 'stage1 identification rows')
            identification_observations.extend(case_rows)
            case_pairs = merge_joined_pairs(
                case_rows,
                _mapping(result.get('join'), 'stage1 identification join'),
            )
            identification_pairs.extend(case_pairs)
            summary = summarize_case(case, result)
        except Exception as error:
            case_value = identification_case_manifest(case)
            summary = {**{key: case_value[key] for key in ('cohort', 'replica', 'case_id', 'service_seconds', 'bag_count', 'flow_pattern', 'negative_control')}, 'admitted_row_count': None, 'join_status': 'V3R2_OUTCOME_JOIN_INVALID', 'census_partition_pass': False, 'hard_gate_pass': False, 'error_type': type(error).__name__, 'error': str(error)}
        identification_summaries.append(summary)

    safety_evaluation = evaluate_safety_regression(safety_summaries)
    primary = evaluate_identification_primary(
        identification_pairs, identification_summaries, draws=draws
    )
    all_summaries = [*safety_summaries, *identification_summaries]
    resources = evaluate_resources(all_summaries)
    safety_expected = {case.case_id for case in registered_cases()}
    identification_expected = {case.case_id for case in identification_cases()}
    cohort_manifest = manifest['cohorts']
    execution_errors = sum('error' in row for row in all_summaries)
    identification_manifest_cases = cohort_manifest['identification']['cases']
    replica_schedules = defaultdict(list)
    for row in identification_manifest_cases:
        replica_schedules[(row['service_seconds'], row['bag_count'])].append(
            row['bag_rows_sha256']
        )
    design_pass = (
        len(identification_manifest_cases) == 24
        and all(
            len(set(row['expected_x_insert_seconds'])) == 3
            for row in identification_manifest_cases
        )
        and all(len(values) == 2 and len(set(values)) == 2 for values in replica_schedules.values())
    )
    gates = [
        gate('stage1_manifest_bound_before_execution', manifest['case_count'] == 144 and cohort_manifest['safety_regression']['case_count'] == 120 and cohort_manifest['identification']['case_count'] == 24 and _sha_text(manifest['cohorts_sha256']), manifest['cohorts_sha256']),
        gate('stage1_identification_design_non_degenerate', design_pass, {'cases': len(identification_manifest_cases), 'strata': len(replica_schedules)}),
        gate('stage1_exact_120_attempted', len(safety_summaries) == 120 and {row['case_id'] for row in safety_summaries} == safety_expected, len(safety_summaries)),
        gate('stage1_exact_24_identification_attempted', len(identification_summaries) == 24 and {row['case_id'] for row in identification_summaries} == identification_expected, len(identification_summaries)),
        gate('stage1_no_execution_errors', execution_errors == 0, execution_errors),
        gate('stage1_loaded_binary_identity', _sha_text(expected_binary_sha256) and all(row.get('loaded_cpp_binary_sha256') == expected_binary_sha256 for row in all_summaries)),
        gate('stage1_completion_overlap_duplicate_origin_pending_safety', all(row.get('hard_gate_pass') is True for row in all_summaries)),
        gate('stage1_safety_regression', safety_evaluation['pass']),
        gate('stage1_primary_relationship', primary['pass']),
        gate('stage1_resources', resources['pass']),
    ]
    passed = all((item['pass'] for item in gates))
    safety_resources = evaluate_resources(safety_summaries)
    identification_resources = evaluate_resources(identification_summaries)
    safety = {'pass': safety_evaluation['pass'] and safety_resources['pass'], 'gates': safety_evaluation['gates'], 'manifest_sha256': cohort_manifest['safety_regression']['cases_sha256'], 'cases': safety_summaries, 'resources': safety_resources, 'observation_count': len(safety_observations), 'observations_sha256': canonical_sha256(safety_observations), 'observations': safety_observations, 'pair_count': len(safety_pairs), 'pairs_sha256': canonical_sha256(safety_pairs), 'pairs': safety_pairs}
    identification = {'pass': primary['pass'] and identification_resources['pass'] and all(row.get('hard_gate_pass') is True for row in identification_summaries), 'manifest_sha256': cohort_manifest['identification']['cases_sha256'], 'cases': identification_summaries, 'primary': primary, 'resources': identification_resources, 'observation_count': len(identification_observations), 'observations_sha256': canonical_sha256(identification_observations), 'observations': identification_observations, 'pair_count': len(identification_pairs), 'pairs_sha256': canonical_sha256(identification_pairs), 'pairs': identification_pairs}
    return {'pass': passed, 'status': 'V3R11_STAGE1_PASS' if passed else 'NO_GO_V3R11_STAGE1_CONTRACT', 'gates': gates, 'manifest_sha256': manifest['cohorts_sha256'], 'safety_regression': safety, 'identification': identification, 'resources': resources}

def run_campaign(*, executor: Executor, g32_binary: Path, proof_executable: Path=NATIVE_PROOF_EXE, g31_binary: Path=G31_BINARY, worker: Worker=run_binary_worker, proof_runner: Callable[[Path, Path], Mapping[str, Any]]=run_native_proof, identity_runner: Callable[[], Mapping[str, Any]]=implementation_identity, _test_only: bool=False) -> dict[str, Any]:
    if FORMAL_EXECUTION_BLOCKED_REASON and not _test_only:
        raise RuntimeError(FORMAL_EXECUTION_BLOCKED_REASON)
    binary = g32_binary.resolve(strict=True); binary_sha = file_sha256(binary)
    manifest = population_manifest()
    source_start = source_bundle_manifest()
    implementation = identity_runner()
    if implementation.get('pass') is True:
        stage0 = run_stage0(executor=executor, g32_binary=binary, expected_binary_sha256=binary_sha, proof_executable=proof_executable, g31_binary=g31_binary, worker=worker, proof_runner=proof_runner, expected_build_head=implementation.get('head'))
        stage0['gates'] = [*implementation.get('gates', []), *stage0['gates']]
        stage0['pass'] = bool(stage0['pass'] and all((item['pass'] for item in implementation.get('gates', []))))
    else:
        stage0 = {'pass': False, 'status': STAGE0_NO_GO, 'gates': list(implementation.get('gates', [])), 'cases': [], 'native_proof': None, 'cross_binary': None, 'map2': None, 'error': 'implementation source bundle is not a clean committed HEAD'}
    source_after_stage0 = source_bundle_manifest()
    stage0_source_gate = gate('source_bundle_unchanged_through_stage0', source_after_stage0 == source_start, {'start': source_start['sha256'], 'after_stage0': source_after_stage0['sha256']})
    stage0_binary_gate = _binary_unchanged_gate('g32_binary_unchanged_through_stage0', binary, binary_sha)
    stage0['gates'].extend((stage0_source_gate, stage0_binary_gate))
    stage0['pass'] = bool(stage0['pass'] and stage0_source_gate['pass'] and stage0_binary_gate['pass'])
    stage0['status'] = STAGE0_PASS if stage0['pass'] else STAGE0_NO_GO
    stage1 = run_stage1(executor=executor, g32_binary=binary, expected_binary_sha256=binary_sha) if stage0['pass'] else None
    source_after_stage1 = source_bundle_manifest()
    if stage1 is not None:
        stage1_source_gate = gate('source_bundle_unchanged_through_stage1', source_after_stage1 == source_start, {'start': source_start['sha256'], 'after_stage1': source_after_stage1['sha256']})
        stage1_binary_gate = _binary_unchanged_gate('g32_binary_unchanged_through_stage1', binary, binary_sha)
        stage1['gates'].extend((stage1_source_gate, stage1_binary_gate))
        stage1['pass'] = bool(stage1['pass'] and stage1_source_gate['pass'] and stage1_binary_gate['pass'])
        stage1['status'] = 'V3R11_STAGE1_PASS' if stage1['pass'] else 'NO_GO_V3R11_STAGE1_CONTRACT'
    passed = bool(stage0['pass'] and stage1 and stage1['pass'])
    decision = SYNTHETIC_PASS if passed else NO_GO
    return {'schema': SCHEMA, 'synthetic_revision_id': SYNTHETIC_REVISION_ID, 'campaign_revision_id': CAMPAIGN_REVISION_ID, 'historical_control_revision_id': COMMIT_ALIGNED_ADDENDUM_ID, 'status': decision, 'decision': decision, 'synthetic_pass': passed, 'nanning_p0_status': 'PENDING_NOT_RUN_BY_SYNTHETIC_RUNNER', 'p1_review_authorized': False, 'protocol': manifest, 'source_bundle': source_start, 'source_bundle_checkpoints': {'start': source_start, 'after_stage0': source_after_stage0, 'after_stage1': source_after_stage1}, 'implementation': implementation, 'implementation_head': implementation.get('head'), 'g32_binary_sha256': binary_sha, 'issue_remediation_ledger_file': {'path': LEDGER_PATH.relative_to(ROOT).as_posix(), 'sha256': file_sha256(LEDGER_PATH)}, 'bootstrap': {'seed': BOOTSTRAP_SEED, 'draws': BOOTSTRAP_DRAWS}, 'resource_ratio_limit': RESOURCE_RATIO_LIMIT, 'stage0': stage0, 'stage1': stage1, 'issue_remediation_ledger': [{'issue': 'V3R1 hard-coded synthetic storage role', 'handling': 'V3R2 validates an explicit nonempty generic role list and the fixed map2 [52] sentinel.'}, {'issue': 'generic trace schema was mistaken for G32 schema', 'handling': 'Rows require trace_context.source_aware_destination_service_schema_id while preserving the generic schema.'}, {'issue': 'hand-authored native proof could be forged', 'handling': 'Runner launches the focused C++ executable and binds exit code, stdout assertions, executable/G32/source hashes.'}, {'issue': 'same-name extension cannot be switched in-process', 'handling': 'G31 and G32 exact-off requests execute in isolated worker subprocesses.'}, {'issue': 'zero resource denominator produced a false negative', 'handling': '0/0 is ratio 1; positive shadow over zero off remains infinite and fails.'}, {'issue': 'V3R7 Stage1 X was constant within every mixed case', 'handling': 'V3R8 keeps the original 120 safety cases unchanged and adds 24 preregistered identification cases with three distinct insertion geometries each.'}, {'issue': 'synthetic evidence cannot establish the Nanning motif', 'handling': 'A synthetic pass is explicitly Nanning-pending and never authorizes P1; the separately registered Nanning control/shadow stage must compose the sole final GO.'}]}

def evidence_skeleton() -> dict[str, Any]:
    return {'schema': SCHEMA, 'status': 'V3R11_NOT_EXECUTED', 'protocol': population_manifest(), 'stage0': None, 'stage1': None, 'decision': None, 'p1_review_authorized': False, 'native_proof_prefix': NATIVE_PROOF_PREFIX}

def render_report(result: Mapping[str, Any]) -> str:
    lines = ['# G4IRSF32 V3R11 synthetic external-commit/local-virtual evidence', '', f"Status: `{result.get('status', 'V3R11_NOT_EXECUTED')}`", '', f'Protocol: `{PROTOCOL_ID}`', '']
    for name in ('stage0', 'stage1'):
        stage = result.get(name)
        lines += [f'## {name.upper()}', '']
        if not isinstance(stage, Mapping):
            lines += ['Not run because a prior hard gate did not pass.', '']
            continue
        lines += [f"Pass: `{stage.get('pass')}`", '']
        lines += [f"- [{('x' if item.get('pass') else ' ')}] `{item.get('name')}`" for item in stage.get('gates', [])]
        lines.append('')
    lines += ['## Problems and handling', '']
    lines += [f"- {item['issue']} — {item['handling']}" for item in result.get('issue_remediation_ledger', [])]
    lines += ['', 'X/Y is a frozen predictive association, not a causal insertion effect. Synthetic passage remains Nanning-pending and cannot authorize P1.', '']
    return '\n'.join(lines)

def write_evidence(result: Mapping[str, Any], *, json_path: Path=OUTPUT_JSON, markdown_path: Path=OUTPUT_MD) -> None:
    contents = ((markdown_path, render_report(result)), (json_path, json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n'))
    staged: list[tuple[Path, Path]] = []
    try:
        existing = [destination for destination, _content in contents if destination.exists()]
        if existing:
            raise FileExistsError(
                'append-only evidence path already exists: '
                + ', '.join(str(path) for path in existing)
            )
        for destination, content in contents:
            destination.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n', delete=False, dir=destination.parent, prefix=destination.name + '.', suffix='.tmp')
            with handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((Path(handle.name), destination))
        for temporary, destination in staged:
            os.link(temporary, destination)
    finally:
        for temporary, _destination in staged:
            if temporary.exists():
                temporary.unlink()

def cpp_executor(**request: Any) -> Mapping[str, Any]:
    from czr005.cpp_backend import g4irsf11_event_runtime_from_records
    return g4irsf11_event_runtime_from_records(**request)

def _default_g32_binary() -> Path:
    candidates = sorted(G32_BINARY_GLOB.glob('czr005_cpp*.pyd'))
    if len(candidates) != 1:
        raise ValueError(f'expected one G32 Release pyd in {G32_BINARY_GLOB}, got {len(candidates)}')
    return candidates[0]

def main(argv: Sequence[str] | None=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--g32-binary', type=Path)
    parser.add_argument('--g31-binary', type=Path, default=G31_BINARY)
    parser.add_argument('--native-proof-exe', type=Path, default=NATIVE_PROOF_EXE)
    parser.add_argument('--output-json', type=Path, default=OUTPUT_JSON)
    parser.add_argument('--output-md', type=Path, default=OUTPUT_MD)
    parser.add_argument('--worker-off-json', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--worker-binary', type=Path, help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    if arguments.worker_off_json is not None:
        if arguments.worker_binary is None:
            parser.error('--worker-binary is required with --worker-off-json')
        return worker_off_json(arguments.worker_off_json, arguments.worker_binary)
    if FORMAL_EXECUTION_BLOCKED_REASON:
        raise RuntimeError(FORMAL_EXECUTION_BLOCKED_REASON)
    binary = arguments.g32_binary or _default_g32_binary()
    result = run_campaign(executor=cpp_executor, g32_binary=binary, proof_executable=arguments.native_proof_exe, g31_binary=arguments.g31_binary)
    write_evidence(result, json_path=arguments.output_json, markdown_path=arguments.output_md)
    print(result['decision'])
    return 0 if result['decision'] == SYNTHETIC_PASS else 2
if __name__ == '__main__':
    raise SystemExit(main())
