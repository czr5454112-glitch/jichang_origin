"""Explicit public support of *new external* business arrivals for joint runs.

This contract cannot be inferred from an observed empty queue or a missing B1
node. It is an independently preloaded experiment contract, bound to the fixed
business projection and the source of the time-only synthetic parent generator.
The offline input audit is referenced by digest; actors never inspect its jobs.
"""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path

from . import foundation_airport_feasible_domain as domain
from . import foundation_airport_joint_parents as parents
from .foundation_airport_batch_patch import digest

SCHEMA = "g31.foundation.airport_external_arrival_support.v1"
RECEIPT_SCHEMA = "g31.foundation.airport_arrival_support_receipt.v1"
GENERATOR_MODULE = "scripts.experiments.g31_ics_circulation.foundation_airport_joint_parents"


def require(value, reason):
    if not value:
        raise ValueError("airport_arrival_support:" + reason)


def _sha(value):
    return type(value) is str and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def generator_source_sha256():
    return hashlib.sha256(Path(parents.__file__).read_bytes()).hexdigest()


def build_arrival_support_contract(*, parent, input_origin_support_audit_sha256):
    """Register public support after a separately recorded offline input audit.

    The audit producer must check every physical input job.origin belongs to
    ACTIVE_LOADERS and that the registered generator changed only allowed time
    coordinates. This factory receives neither private jobs nor their counts.
    """
    registered = parents.validate_public_parent(parent)
    require(_sha(input_origin_support_audit_sha256), "offline_audit_digest_required")
    value = {"schema": SCHEMA, "version": "feasible_external_arrival_support_joint_time_only_v1",
        "business_contract_version": domain.VERSION, "business_semantic_sha256": domain.BUSINESS_SHA,
        "external_arrival_nodes": list(domain.ACTIVE_LOADERS),
        "parent": registered, "parent_generator_module": GENERATOR_MODULE,
        "parent_generator_source_sha256": generator_source_sha256(),
        "input_origin_support_audit_sha256": input_origin_support_audit_sha256,
        "available_at_physical_seconds": 0.,
        "semantics": "new_external_business_origin_support_only",
        "structural_zero_outside_support": True,
        "existing_waiting_jobs_or_inventory_inferred_zero": False,
        "internal_transfer_or_loaded_release_demand_excluded_from_structural_zero_claim": True,
        "runtime_future_jobs_read": False, "same_contract_for_all_policy_variants": True,
        "native_execution_authority": False}
    value["sha256"] = digest(value)
    validate_contract(value)
    return value


def validate_contract(contract):
    require(type(contract) is dict and contract.get("schema") == SCHEMA
            and contract.get("sha256") == digest({key: value for key, value in contract.items() if key != "sha256"}),
            "contract_identity")
    require(contract.get("business_contract_version") == domain.VERSION
            and contract.get("business_semantic_sha256") == domain.BUSINESS_SHA
            and contract.get("external_arrival_nodes") == list(domain.ACTIVE_LOADERS), "fixed_business_arrival_support")
    require(contract.get("parent_generator_module") == GENERATOR_MODULE
            and contract.get("parent_generator_source_sha256") == generator_source_sha256(),
            "time_only_generator_source_identity")
    require(contract.get("parent") == parents.validate_public_parent(contract["parent"]), "registered_joint_parent")
    require(_sha(contract.get("input_origin_support_audit_sha256")), "offline_audit_digest_required")
    require(contract.get("available_at_physical_seconds") == 0.
            and contract.get("semantics") == "new_external_business_origin_support_only"
            and contract.get("structural_zero_outside_support") is True
            and contract.get("existing_waiting_jobs_or_inventory_inferred_zero") is False
            and contract.get("internal_transfer_or_loaded_release_demand_excluded_from_structural_zero_claim") is True
            and contract.get("runtime_future_jobs_read") is False
            and contract.get("same_contract_for_all_policy_variants") is True
            and contract.get("native_execution_authority") is False, "narrow_public_contract_boundary")
    return tuple(contract["external_arrival_nodes"])


def record_controller_preload(contract, session, *, owners):
    """Record a real caller's startup session clock; creates no native session."""
    validate_contract(contract)
    require(session.physical_time == 0., "actual_startup_clock_required")
    owners = list(owners)
    require(owners and len(set(owners)) == len(owners) and all(type(owner) is str and owner for owner in owners),
            "unique_actual_preload_owners")
    records = {}
    for owner in owners:
        record = {"schema": RECEIPT_SCHEMA, "receipt_kind": "actual_controller_startup_preload",
            "owner_id": owner, "contract_sha256": contract["sha256"],
            "parent_group": contract["parent"]["parent_group"], "received_at_physical_seconds": 0.,
            "native_message_receipt_claimed": False,
            "scope": "explicit shared experiment public-support preload before controller callbacks"}
        record["receipt_sha256"] = digest(record)
        records[owner] = record
    return records


def validate_arrival_support(contract, receipt, *, now, owner, parent=None):
    support = validate_contract(contract)
    require(type(now) in (int, float) and math.isfinite(now) and now >= 0., "current_physical_clock")
    require(type(receipt) is dict and receipt.get("schema") == RECEIPT_SCHEMA
            and receipt.get("receipt_sha256") == digest({key: value for key, value in receipt.items()
                                                        if key != "receipt_sha256"}), "actual_receipt_identity")
    require(receipt.get("receipt_kind") == "actual_controller_startup_preload"
            and receipt.get("owner_id") == owner and receipt.get("contract_sha256") == contract["sha256"]
            and receipt.get("parent_group") == contract["parent"]["parent_group"]
            and receipt.get("native_message_receipt_claimed") is False, "receipt_owner_parent_contract")
    received = receipt.get("received_at_physical_seconds")
    require(type(received) in (int, float) and math.isfinite(received)
            and received == contract["available_at_physical_seconds"] == 0. <= now,
            "support_actually_available_at_current_clock")
    if parent is not None:
        require(parents.validate_public_parent(parent) == contract["parent"], "current_parent_binding")
    return support
