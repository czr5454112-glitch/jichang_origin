# G4IRSF32 user-contract manifest

Recorded: 2026-08-28 (Asia/Shanghai)

This manifest binds exact-byte repository snapshots of the two Markdown files
supplied by the user to the next G4IRSF32 revision. Their prose is treated as project requirements and audit
evidence, not as executable instructions or as authority to weaken a gate.
The user's requests in the Codex task remain the authority for making changes:
finish every required effect, resolve negative gates autonomously with the
smallest attributable change, and record each problem and handling method.

| Role | Original attachment | Repository snapshot used by formal preflight | Bytes | SHA-256 |
|---|---|---|---:|---|
| Stage order, P0/P1 design constraints, GO/NO-GO thresholds, Stage 2–4 matrix, held-out and evidence-closure requirements | `C:/Users/38908/Downloads/G4IRSF32_cross_map_next_stage_action_plan.md` | `docs/contracts/G4IRSF32_cross_map_next_stage_action_plan_20260826.md` | 67,791 | `e84b71cc919f77e1f8c9927163f7f7baeb8fdf254b20d28f95569165d68fe1f4` |
| Frozen G4IRSF31 audit facts and causal boundaries | `C:/Users/38908/Downloads/g4irsf31_audit_evidence_pack.md` | `docs/contracts/g4irsf31_audit_evidence_pack_20260826.md` | 4,771 | `7be33410690713a223cd58844616491bb5747b94d0263854f9dbe225ba825140` |

The action-plan contract remains ordered and fail-closed:

1. Stage 0 and Stage 1 must genuinely pass before P1 closed-loop action exists.
2. Stage 2 must pass before Stage 3; Stage 3 must pass before the Stage 4 full
   matrix.
3. The held-out third map may be materialized only after the final algorithm
   and parameters are frozen.
4. Table 5.3, Table 5.4, and map2 `pair_5_7` evidence work remains separate
   from algorithm selection and may retain NON_EXACT / NOT_MEASURED outcomes.
5. Historical NO-GO artifacts and their identities are append-only and cannot
   be reinterpreted as a later pass.

The external paths above are ingest provenance only and are not a formal-run
dependency. Any byte change to either repository snapshot fails the registered
preflight until explicitly reviewed and re-frozen.
