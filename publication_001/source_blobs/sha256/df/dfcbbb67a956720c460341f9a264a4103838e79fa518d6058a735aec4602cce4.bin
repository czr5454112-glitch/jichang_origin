"""Source-only next diagnostic design; no executable runtime binding.

This file is deliberately data only. It does not import, clone, mutate, time or
install the accepted runtime. The next implementation requires separate source
review, focused synthetic verification and a separately authorized campaign.
"""

DESIGN = {
    'schema': 'g31.constructor_prelude.cost_design.v1',
    'status': 'source_design_not_implemented_or_executed',
    'reference_source': 'scripts/experiments/g31_ics_circulation/single_capture_static_inventory_runtime.py',
    'reference_sha256': '9ec4089e19232c4671ee76175ea9b6b068dc57f1e042bf2a398f1a03655b8c60',
    'reference_callable': 'ConstructorTimer.__call__',
    'question': 'How much of the charged constructor call-site wall precedes its existing started_ns?',
    'minimum_new_boundary_set': [
        {
            'name': 'program_boundary_check',
            'start': 'Immediately before the existing if self.boundary is not None statement.',
            'end': 'Immediately after that whole if statement, including the unchanged boundary.check() call.',
            'work': 'Exact original _ProgramBoundary.check; no cached success, elision, source scan or alternative guard.',
        },
        {
            'name': 'root_fields_row_and_append',
            'start': 'The same timestamp ending program_boundary_check.',
            'end': 'Immediately after the original row dictionary construction and self.rows.append(row).',
            'work': 'Original len, _root_fields(root), dictionary allocation and append, with their original order.',
        },
    ],
    'existing_boundary_retained': {
        'name': 'exact_constructor',
        'start': "Original row['started_ns'] = self.clock() statement, unchanged.",
        'end': "Original row['finished_ns'] = self.clock() statements on both original paths, unchanged.",
        'scope': 'Actual reviewed exact class constructor including its dynamic and static-use checks; wall, not CPU.',
    },
    'integer_conservation': {
        'no_sum_of_medians': True,
        'adjacent_prelude_phases': True,
        'new_clock_gap': 'Keep metadata_end to original constructor started_ns as explicit timing/bookkeeping gap.',
        'post_call_tail': 'Exact-return-type validation and diagnostic export remain in complete root, not silently charged to constructor.',
        'residual_debit': 'Subtract only the union of new intervals outside native/refresh/RPC/existing-constructor intervals.',
        'unknown': 'Any missing/ill-ordered/overlapping/error clock is unknown, never synthesized as zero.',
    },
    'proposed_binding': {
        'new_files_only': True,
        'original_class_not_mutated': True,
        'transformation': 'Private copy of original __call__ with only passive timestamp assignments and a final sidecar hook inserted.',
        'inverse_AST': 'Removing exactly the inserted clock assignments and final diagnostic hook must recover the complete original function AST.',
        'full_globals': 'Original defining globals/defaults/kwdefaults/closure retained; only explicitly named new diagnostic hooks added privately.',
        'class_identity': 'ActualAdvanceChain returned instance remains the existing exact reviewed class, not a proxy or subclass.',
        'cold_boundary': 'New callable/hook code, defaults, closure, MRO dependencies and full defining globals get a new explicit cold boundary.',
        'failure': 'Preserve original exception identity. Diagnostic sink failure is separately retained and disqualifies the new campaign; do not mask the original exception.',
        'evidence': 'Append scalar sidecar records in memory; no root/client/session/observation/ACK object references retained.',
        'persistence': 'Use existing provider setup/close/failure saves; add no per-root disk write.',
    },
    'unchanged_obligations': [
        'Original 18 branches, all unknowns, full RPC/native/physical/saved checks.',
        'ActualAdvanceChain exact-type/drain/MRO/classcell and all dynamic authority checks.',
        '60ms selection cutoff and complete 100ms root boundary.',
        'Original background cadence, activate IDs, endpoint calls, policy decisions and clocks.',
        'C loader/module/spec/DLL and all existing entry/exit file checks; fallback count remains unknown.',
        'Cold bind, additional instrumentation, export and cleanup charged in whole campaign/root as applicable.',
    ],
    'focused_synthetic_before_installation': [
        'Complete inverse AST and full-global/default/closure identity comparison.',
        'Boundary raises: same original exception and zero metadata/constructor calls.',
        'Metadata/append raises: no constructor call, incomplete diagnostic retained.',
        'Constructor raises or returns wrong exact type: original error path unchanged.',
        'Scalar clock sequence proves adjacent prelude, existing constructor and explicit gap conservation.',
        'Source/global/descriptor/MRO mutations rejected by the new cold boundary.',
        'Sidecar cannot preserve runtime object references; failure cannot be certified.',
    ],
    'limits': [
        'The measured 8–12ms constructor excludes these two prelude intervals; their cost is currently unknown.',
        'No claim that these once-per-root calls explain the 2626.4559ms closed-root prefinal residual.',
        'Do not attribute event-to-event intervals to a function or reuse the old unmeasured constructor as a control.',
        'If prelude is small, a separate next diagnostic may bracket the frequent root observation/gate and record calls; it is outside this minimum change.',
        'Diagnostic wall measurements include scheduler/GC interference; no CPU or hard-real-time claim.',
    ],
}
