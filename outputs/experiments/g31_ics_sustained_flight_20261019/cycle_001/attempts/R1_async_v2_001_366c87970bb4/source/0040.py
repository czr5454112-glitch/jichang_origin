"""Immutable, process-local compilation of explicitly registered static cases.

No observation, receipt, future event, forecast, candidate result or guard outcome
is cached here. Importing this module does not compile or change any domain.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time

SCHEMA = 'g31.foundation.repeated_static_registry.v1'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def immutable(value):
    """Own a scalar/tuple-only copy; never retain mutable registry declarations."""
    if type(value) is dict:
        require(all(type(key) is str for key in value), 'static_registry_string_declaration_keys')
        return tuple((key, immutable(item)) for key, item in sorted(value.items()))
    if type(value) in (list, tuple):
        return tuple(immutable(item) for item in value)
    require(type(value) in (str, int, float, bool, type(None))
        and (type(value) is not float or math.isfinite(value)), 'static_registry_finite_scalar_declaration')
    return value


def declaration(cases, reuse_counts, hold_cases, contract_fields):
    return immutable((SCHEMA, cases, reuse_counts, hold_cases, tuple(contract_fields)))


@dataclass(frozen=True, slots=True)
class CompiledRegistry:
    physical_canonical: str
    declaration: tuple
    fields: tuple[str, ...]
    # Each case keeps sorted original business identities and every original
    # contract field, in order. Tuple comparisons preserve old scalar equality.
    cases: tuple
    compilation_wall_ns: int

    def identify(self, physical_canonical, jobs, *, declaration, contract_fields):
        require(declaration == self.declaration and tuple(contract_fields) == self.fields,
            'repeated_static_registry_declaration_changed')
        require(physical_canonical == self.physical_canonical, 'repeated_fixed_physical_contract_changed')
        matches = []
        for case, identities, values in self.cases:
            if set(jobs) == set(identities) and all(
                    all(jobs[key][field] == expected for field, expected in zip(self.fields, row, strict=True))
                    for key, row in zip(identities, values, strict=True)):
                matches.append(case)
        require(len(matches) == 1, 'repeated_business_contract_not_registered')
        return matches[0]

    def audit(self):
        return {'schema': SCHEMA, 'case_count': len(self.cases), 'contract_field_count': len(self.fields),
            'compilation_wall_ns': self.compilation_wall_ns, 'dynamic_state_cached': False,
            'compilation_included_in_current_request': False}


def compile_registry(*, physical_canonical, registry_declaration, contract_fields, case_names, build_jobs, clock=time.perf_counter_ns):
    """Call before the episode/worker ready; build_jobs is evaluated once/case."""
    start = clock(); fields = tuple(contract_fields); names = tuple(case_names)
    require(type(physical_canonical) is str and bool(physical_canonical), 'static_registry_physical_canonical')
    require(fields and len(set(fields)) == len(fields) and all(type(field) is str for field in fields),
        'static_registry_unique_contract_fields')
    require(names and len(set(names)) == len(names) and all(type(case) is str for case in names),
        'static_registry_unique_case_names')
    rows = []
    for case in names:
        jobs = build_jobs(case)
        require(type(jobs) is dict and jobs and all(type(key) is str for key in jobs), 'static_registry_complete_job_map')
        identities = tuple(sorted(jobs))
        values = tuple(tuple(immutable(jobs[key][field]) for field in fields) for key in identities)
        require(all(type(value) in (str, int, float, bool, type(None)) for row in values for value in row),
            'static_registry_scalar_contract_fields')
        rows.append((case, identities, values))
    return CompiledRegistry(physical_canonical, immutable(registry_declaration), fields, tuple(rows), clock()-start)
