# G4IRSF32 evidence-gap closure record

Status: `BOUNDARY_CLOSED_WITH_EXPLICIT_NON_EXACT_AND_NOT_SUPPORTED_RESULTS`

Date: 2026-08-27 (Asia/Shanghai)

Provenance correction: 2026-08-29 (Asia/Shanghai)

This record closes the four evidence side branches named by the independent
G4IRSF32 action plan. “Closed” means that the available provenance has been
exhausted and a reproducible terminal classification has been recorded. It
does not turn missing source material into a positive experimental result.

## Table 5.3

Terminal classification:

`TABLE_5_3_ARCHIVE_UNAVAILABLE_NON_EXACT_RECONSTRUCTION`

Available source and archived output:

- local archived thesis PDF:
  `C:/PROGRAMING/czr005/.local_archives/g4irsf13/pdfs/thesis.pdf`;
- audited PDF pages 43–45 (printed pages 29–31) contain the reported Table 5.3
  values `3.56/4.43/8.62` and `3.13/3.96/5.98`;
- two copies of the original project workbook
  `仿真结果数据整理（与分散启发式方法对比）.xlsx` remain under the archived
  graduation-project and ICS-project folders;
- `分散启发式算法!A2:J43604` retains 43,603 segment-level records,
  `原始数据!A2:D28507` retains 28,506 bag inputs and release times, and
  `分散启发式算法!L20:O23` retains the two methods' summary values and
  improvement formulas.

Missing exact-replay material:

- the executable source or binary for the distributed/MPC baseline;
- the complete route-choice, conflict-resolution and scheduling rules needed
  to implement that baseline uniquely;
- its parameters, random stream and repeat definition;
- a run contract binding the preserved workbook to a build and map revision.

The workbook is archived exact output/context, not an executable exact replay.
The available process diagram is only a high-level flow and does not close the
missing decision rules. No current result may therefore be labelled an exact
reproduction or a victory over an exact replay. The terminal name above means
that the archive required for executable replay is unavailable; it no longer
means that the historical row-level results are absent.

## Table 5.4

Terminal classification:

`NO_MATCHED_HCA_SEAM_TABLE_5_4_REMAINS_DESCRIPTIVE`

The paper describes dynamic/static observation-bias comparisons, but the
available repository history does not contain two runnable arms with the same
perturbation seam and random stream:

- `git log -S update_route_and_constrain_dynamic` reaches only the historical
  introduction at `8254a7a`;
- the local same-name Java archives are content-equivalent apart from line
  endings;
- the active path uses static update with `bias_time=0`;
- the dynamic call and main replanning segment are commented, and the remaining
  fragment uses an unfrozen `3*Math.random()` rather than the reported 4x3
  matched matrix.

No disturbance is moved to a different semantic location and no random stream
is fabricated. Existing Table 5.4 reconstructions remain descriptive and
cannot generate a cross-algorithm verdict.

## map2 `pair_5_7`

Terminal classification:

`ARCHIVED_ONLY_SOURCE_PROTOCOL_UNRESOLVED_NOT_MEASURED`

The source history contains incompatible meanings for line IDs 5 and 7:

- the paper reports only `5,7`, without directed endpoints;
- the old `arc.txt` literal line order gives `4->17,6->8`;
- the G26 reconstruction gives `14->46,33->44`;
- the fault workbook sheet is labelled `33->44,46->36`.

The Java runner consumes directed endpoints and has no line-ID registry that
could select among them. The cached workbook value is 13,939, but the workbook
does not retain task IDs, fault events, the complete configuration, or a
provenance record that selects one definition.

The two principal reconstructed definitions were preserved and probed. Each
fresh probe completed 8,013 rather than reproducing 13,939. More performance
probes cannot recover the missing identity, so neither is promoted as the
“correct” or more favourable definition. Both 1x and 2x `pair_5_7` cells
remain `NOT_MEASURED` until original fault-event provenance is recovered.

## Real Nanning EBS semantics

Terminal classification:

`REAL_NANNING_EBS_DEPLOYMENT_NOT_SUPPORTED`

The frozen Nanning profile explicitly records:

- EBS status `NOT_IDENTIFIED_IN_SOURCE_WORKBOOKS`;
- node 53/type 7 as an empty-pallet storage proxy (`IDK1`), not a verified EBS;
- node 49/type 1 as a local loader/source;
- the timetable as a deterministic projection from the historical workload,
  not real Nanning operational task data.

Accordingly, `53->49` experiments test a declared storage proxy and a real
topological mixed-source motif. They do not establish real-airport EBS
deployment, production OD semantics, or airport operational validation. This
gap can be reopened only by an authoritative airport/business source that
identifies the EBS roles and supplies compatible operational data; it cannot
be repaired by relabelling a node in code.

## Reporting boundary

These four terminal classifications are evidence, not omissions to be hidden.
They remain visible beside every later G32 capacity, timing, resource, or
held-out conclusion. None of them may be replaced by a survivor-only metric,
an inferred disturbance seam, a favourable fault definition, or an invented
business role.
