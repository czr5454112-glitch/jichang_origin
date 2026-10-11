"""Explicit runtime boundary for a complete, source-authenticated projection.

This adapter re-reads the original raw/canonical/parent inputs. It never creates
a BusinessWorkload with substituted destinations. The returned arrival tape
and environment provenance are private; only ``initial`` is policy-visible.
SHA bindings identify caller-declared inputs, not an authorization signature.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .business_inputs import (BusinessWorkload, load_business_workload,
                              _keys, _require, _text)
from .business_projection import (BusinessProjection, parse_projection_contract,
                                  validate_business_projection)
from .business_runtime import (BusinessGeneratorFactory, RuntimeProxyContract,
                               build_business_runtime, parse_runtime_proxy_contract)
from .model import Bag
from .storage_contracts import StorageSnapshot


RUN_POLICIES = {
    "schema": "ics_business_projection_runtime_v1",
    "evidence_status": "proxy_research",
    "source_validation": "reload_complete_raw_canonical_parent_normalized_and_compare",
    "adaptation_policy": "verified_projection_changes_only_private_bag_destination",
    "future_policy": "private_environment_tape_reveal_only_on_observation",
    "denominator_policy": "complete_source_before_any_explicit_external_window",
}
SOURCE_PATH_FIELDS = frozenset(("normalized", "normalization_manifest", "raw", "canonical",
                                "source_timetable", "source_manifest", "graph_profile"))
BINDING_FIELDS = frozenset(("source_workload_sha256", "input_contract_sha256",
    "projection_sha256", "projection_contract_sha256", "runtime_contract_sha256", "graph_sha256"))


@dataclass(frozen=True)
class ProjectionRunContract:
    run_id: str
    title: str
    source_workload_sha256: str
    input_contract_sha256: str
    projection_sha256: str
    projection_contract_sha256: str
    runtime_contract_sha256: str
    graph_sha256: str
    assumption_id: str
    source_ref: str
    canonical_json: str
    canonical_sha256: str


@dataclass(frozen=True)
class ProjectionEnvironmentProvenance:
    """Full source and old/new destination ledger, never a policy argument."""
    original: BusinessWorkload
    projection: BusinessProjection
    run_contract: ProjectionRunContract


@dataclass(frozen=True)
class ProjectedBusinessRuntime:
    initial: StorageSnapshot
    future_bags: tuple[Bag, ...]  # Environment-private arrival tape.
    generator_factory: BusinessGeneratorFactory
    contract: RuntimeProxyContract
    source_business_count: int
    source_segment_count: int
    input_binding_sha256: tuple[tuple[str, str], ...]
    edge_travel_seconds: tuple[tuple[str, str], ...]
    closed_edge_ids: tuple[str, ...]
    environment_projection: ProjectionEnvironmentProvenance
    qualification: str = "Source-authenticated static destination research proxy; no joint capacity or real assignment claim"

    def simulation_kwargs(self) -> dict[str, Any]:
        """Only public constructor settings; provenance/future remain external."""
        c = self.contract
        return dict(generator_factory=self.generator_factory, route_mode=c.route_mode,
            search_horizon=c.search_horizon, candidate_count=c.candidate_count,
            reactive_empty_dispatch=c.reactive_empty_dispatch, coordination_order=c.coordination_order)


def parse_projection_run_contract(value: Mapping[str, Any], original: BusinessWorkload,
                                  projection: BusinessProjection,
                                  runtime: RuntimeProxyContract) -> ProjectionRunContract:
    obj = _keys(value, set(RUN_POLICIES) | set(BINDING_FIELDS) |
                {"run_id", "title", "assumption_id", "source_ref"}, "projection run contract")
    for key, policy in RUN_POLICIES.items():
        _require(obj[key] == policy, f"unsupported projection run {key}")
    for key in ("run_id", "title", "assumption_id", "source_ref"):
        _text(obj[key], "projection run " + key)
    _require("proxy" in obj["title"].lower(), "projection run title must identify proxy")
    expected = dict(source_workload_sha256=original.content_sha256,
        input_contract_sha256=original.contract.canonical_sha256,
        projection_sha256=projection.content_sha256,
        projection_contract_sha256=projection.contract.canonical_sha256,
        runtime_contract_sha256=runtime.canonical_sha256, graph_sha256=original.contract.graph_sha256)
    for key, digest in expected.items():
        _require(isinstance(obj[key], str) and len(obj[key]) == 64 and
                 all(c in "0123456789abcdef" for c in obj[key]), f"projection run {key}: SHA256 required")
        _require(obj[key] == digest, f"projection run {key} binding mismatch")
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return ProjectionRunContract(obj["run_id"], obj["title"], **expected,
        assumption_id=obj["assumption_id"], source_ref=obj["source_ref"],
        canonical_json=canonical, canonical_sha256=sha256(canonical.encode()).hexdigest())


def build_projected_business_runtime(original: BusinessWorkload, projection: BusinessProjection, *,
        source_inputs: Mapping[str, Any], projection_declaration: Mapping[str, Any],
        runtime_contract: Mapping[str, Any], run_contract: Mapping[str, Any],
        profile_path: str | Path) -> ProjectedBusinessRuntime:
    """Authenticate the full source, recheck whole-family domains, then adapt.

    ``source_inputs`` contains all eight original loader arguments, including
    the explicit operation contract. Callers freeze the external declarations
    before calling. Replacing every artifact and every declaration is a new
    research input, not a valid signature over the previously audited source.
    This function does no physics and makes no automatic window selection.
    """
    _require(type(original) is BusinessWorkload, "original BusinessWorkload required")
    _require(type(projection) is BusinessProjection, "explicit BusinessProjection required")
    _require(isinstance(source_inputs, Mapping), "complete source_inputs mapping required")
    source = _keys(dict(source_inputs), set(SOURCE_PATH_FIELDS) | {"contract"}, "source_inputs")
    for key in SOURCE_PATH_FIELDS:
        _require(isinstance(source[key], (str, Path)), f"source_inputs {key}: file path required")
    source = {key: Path(source[key]) for key in SOURCE_PATH_FIELDS} | {"contract": deepcopy(source["contract"])}
    declaration = deepcopy(projection_declaration)
    runtime_declaration = deepcopy(runtime_contract)
    run_declaration = deepcopy(run_contract)

    runtime = parse_runtime_proxy_contract(runtime_declaration, original)
    run = parse_projection_run_contract(run_declaration, original, projection, runtime)
    parsed_projection = parse_projection_contract(declaration, original)
    _require(parsed_projection == projection.contract, "external projection declaration differs from bound projection")
    _require(runtime.unload_seconds == parsed_projection.unload_seconds,
             "projection/runtime exact unload seconds mismatch")

    rebuilt = load_business_workload(**source)
    _require(rebuilt == original, "original workload differs from complete reloaded source")
    # Recompute all records, full parent-family membership, directed positive
    # role-constrained return domains, exact seconds and per-edge tick bounds.
    validate_business_projection(projection, rebuilt, profile_path)
    base = build_business_runtime(rebuilt, profile_path, runtime_declaration)
    _require(base.contract == runtime, "runtime contract changed during adaptation")
    _require(len(base.future_bags) == len(projection.records) == rebuilt.raw_business_count,
             "complete source denominator required")
    future = []
    for bag, record, task in zip(base.future_bags, projection.records, rebuilt.tasks):
        _require(record.original == task and bag.bag_id == task.business_bag_id,
                 "source/projection runtime identity mismatch")
        _require(bag.destination == record.original_destination == task.final_destination,
                 "original destination provenance mismatch")
        # dataclasses.replace preserves StorageBag and its immutable published
        # waypoint, release, deadline and protected flag; only final changes.
        future.append(replace(bag, destination=record.projected_destination))
    _require(not base.initial.bags and not base.initial.storage_progress,
             "future bags or milestones leaked into initial public snapshot")
    # Source files can be large: the loader itself checks its initial reads;
    # rehash at this boundary as well, after the domain/runtime work finishes.
    for name, digest in rebuilt.input_sha256:
        _require(sha256(Path(name).read_bytes()).hexdigest() == digest,
                 f"source changed during projection adaptation: {name}")
    _require(sha256(Path(profile_path).read_bytes()).hexdigest() == run.graph_sha256,
             "runtime profile changed during projection adaptation")
    return ProjectedBusinessRuntime(base.initial, tuple(future), base.generator_factory, base.contract,
        base.source_business_count, base.source_segment_count, base.input_binding_sha256,
        base.edge_travel_seconds, base.closed_edge_ids, ProjectionEnvironmentProvenance(rebuilt, projection, run))
