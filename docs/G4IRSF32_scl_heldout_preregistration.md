# G4IRSF32 SCL held-out map preregistration

Status: `PREREGISTERED_CANDIDATE_ONLY_NOT_IMPORTED_NOT_RUN`

Frozen on 2026-08-27 (Asia/Shanghai), before any SCL import or outcome run.
This document selects a factual, subsystem-level abstraction of the Santiago
International Airport baggage handling system (SCL) for the G4IRSF32 held-out
map gate. It does not contain an SCL result, implement an importer, or authorize
copying a source figure.

The scientific selection verdict under
`G4IRSF32_cross_map_next_stage_action_plan.md` section 12.4 is
`GO_REAL_PROVENANCE_ABSTRACTED_TOPOLOGY`. Import and execution remain blocked
until the final G32 algorithm and candidate parameters are frozen. A later bad
result may not be used to tune the scorer, guard, proxy, topology, service rule,
or to replace SCL with another map.

## 1. Source identity and provenance

Primary source:

- Juan Pablo Cavada, Cristian E. Cortes, and Pablo A. Rey, "A simulation
  approach to modelling baggage handling systems at an international airport,"
  *Simulation Modelling Practice and Theory* 75 (2017), 146-164.
- DOI: <https://doi.org/10.1016/j.simpat.2017.01.006>.
- Universidad de Chile repository record:
  <https://repositorio.uchile.cl/handle/2250/160191>.
- Repository PDF:
  <https://repositorio.uchile.cl/bitstream/handle/2250/160191/A-simulation-approach.pdf?sequence=1&isAllowed=y>.
- Audited PDF size: `2582270` bytes.
- Audited PDF SHA-256:
  `EF9C031FE41264E7416F8F7D627942B2E2844F5950A0490505632DB2CE11F843`.

Evidence anchors in the journal pagination are:

| Page | Evidence used here |
|---:|---|
| 146 | The model is applied to Santiago International Airport, Chile; the PDF carries the Elsevier copyright notice. |
| 148, Fig. 1 | The source labels the figure as the SCL BHS conveyor network and shows T1-T4, N2, M1-M9, normal flow, and irregular-bag flow. |
| 148-149 | Four T subsystems feed N2 and two loading carousels each; a common conveyor collects suspicious bags; irregular bags reach N3/M9; cleared M9 bags return to M1-M8 by cart or go directly to the aircraft when closing. |
| 155 | M1-M8 and M9 repeat a carousel circuit when the relevant handler or flight state is unavailable. This is the factual basis for directed recirculation, not an inferred compass direction. |
| 156, Table 2 | The paper reports a generic baggage-handler average of 30 seconds per bag. |
| 157-159 | The paper reports manufacturer, ideal-simulation, observed, and operational capacity scales; these corroborate an operational SCL model but are not converted into per-edge measurements here. |
| 163 | The authors thank Andes Airport Services for the real problem and the data used to develop and test the platform. |

The source is therefore evidence of a real named airport and a real operational
subsystem. This preregistration is not a claim that the abstraction is a
conveyor-level CAD reconstruction.

## 2. Abstraction boundary and roles

Abstraction label: `FACTUAL_ABSTRACTION_SUBSYSTEM_LOGICAL_V1`.

Only relationships stated by the article text or shown by its labelled
schematic are retained. Belt-section geometry, compass direction, distances,
unlabelled diverters, proprietary controls, and individual aircraft identities
are outside scope. The newly authored identifiers and ordering below do not
reproduce the source figure's graphic expression.

| Nodes | Frozen role | Meaning |
|---|---|---|
| `T1`-`T4` | `SOURCE` | Aggregate check-in/collector subsystems. |
| `N2_1`-`N2_4` | `SECURITY_CHECKPOINT` | First-level security associated with each T subsystem. |
| `IRREG_MERGE` | `MERGE` | Factual abstraction of the common conveyor collecting irregular/suspicious bags from all four T subsystems. |
| `N3_AGG` | `SECURITY_ESCALATION_AGGREGATE` | Aggregate higher-security path; detailed high-security equipment is deliberately collapsed. |
| `M1_CHECK`-`M8_CHECK` | `DESTINATION_SERVICE` | Handler decision/service point on the eight loading carousels. |
| `M1_RECIRC`-`M8_RECIRC` | `RECIRCULATION` | One full additional carousel circuit before returning to the same check point. |
| `M9_CHECK` | `REWORK_SERVICE` | Irregular-bag handler decision/service point. |
| `M9_RECIRC` | `REWORK_RECIRCULATION` | One full additional M9 circuit. |
| `LOADED_SINK_M1`-`LOADED_SINK_M8` | `SINK` | Abstract successful departure from the corresponding loading carousel toward an aircraft. |
| `DIRECT_AIRCRAFT_SINK` | `SINK` | Abstract direct departure from M9 for a closing flight. |

No source-backed EBS or storage facility is identified in the selected
subsystem. Therefore `storage_nodes=[]` and
`ebs_status=NOT_IDENTIFIED_OUT_OF_SCOPE`. A later importer must fail closed
rather than relabel a carousel, T subsystem, or arbitrary node as EBS/storage.

## 3. Frozen directed edge set

The following is the complete edge set of the declared abstraction. It is not
a claim that unlisted physical conveyor sections do not exist.

```text
# Aggregate check-in flow to first-level security
T1 -> N2_1                           [CONVEYOR_LOGICAL]
T2 -> N2_2                           [CONVEYOR_LOGICAL]
T3 -> N2_3                           [CONVEYOR_LOGICAL]
T4 -> N2_4                           [CONVEYOR_LOGICAL]

# Security-cleared destination alternatives
N2_1 -> M1_CHECK                     [CONVEYOR_LOGICAL]
N2_1 -> M2_CHECK                     [CONVEYOR_LOGICAL]
N2_2 -> M3_CHECK                     [CONVEYOR_LOGICAL]
N2_2 -> M4_CHECK                     [CONVEYOR_LOGICAL]
N2_3 -> M5_CHECK                     [CONVEYOR_LOGICAL]
N2_3 -> M6_CHECK                     [CONVEYOR_LOGICAL]
N2_4 -> M7_CHECK                     [CONVEYOR_LOGICAL]
N2_4 -> M8_CHECK                     [CONVEYOR_LOGICAL]

# Four-to-one irregular-bag merge and its two documented dispositions
N2_1 -> IRREG_MERGE                  [CONVEYOR_LOGICAL]
N2_2 -> IRREG_MERGE                  [CONVEYOR_LOGICAL]
N2_3 -> IRREG_MERGE                  [CONVEYOR_LOGICAL]
N2_4 -> IRREG_MERGE                  [CONVEYOR_LOGICAL]
IRREG_MERGE -> M9_CHECK              [CONVEYOR_LOGICAL_TRACKING_ERROR]
IRREG_MERGE -> N3_AGG                [CONVEYOR_LOGICAL_SECURITY]
N3_AGG -> M9_CHECK                   [CONVEYOR_LOGICAL_SECURITY_CLEAR]

# Operational carousel cycles; arrows mean process succession, not geography
M1_CHECK -> M1_RECIRC                [CAROUSEL_PROCESS]
M1_RECIRC -> M1_CHECK                [CAROUSEL_PROCESS]
M2_CHECK -> M2_RECIRC                [CAROUSEL_PROCESS]
M2_RECIRC -> M2_CHECK                [CAROUSEL_PROCESS]
M3_CHECK -> M3_RECIRC                [CAROUSEL_PROCESS]
M3_RECIRC -> M3_CHECK                [CAROUSEL_PROCESS]
M4_CHECK -> M4_RECIRC                [CAROUSEL_PROCESS]
M4_RECIRC -> M4_CHECK                [CAROUSEL_PROCESS]
M5_CHECK -> M5_RECIRC                [CAROUSEL_PROCESS]
M5_RECIRC -> M5_CHECK                [CAROUSEL_PROCESS]
M6_CHECK -> M6_RECIRC                [CAROUSEL_PROCESS]
M6_RECIRC -> M6_CHECK                [CAROUSEL_PROCESS]
M7_CHECK -> M7_RECIRC                [CAROUSEL_PROCESS]
M7_RECIRC -> M7_CHECK                [CAROUSEL_PROCESS]
M8_CHECK -> M8_RECIRC                [CAROUSEL_PROCESS]
M8_RECIRC -> M8_CHECK                [CAROUSEL_PROCESS]
M9_CHECK -> M9_RECIRC                [CAROUSEL_PROCESS]
M9_RECIRC -> M9_CHECK                [CAROUSEL_PROCESS]

# Successful loading exits
M1_CHECK -> LOADED_SINK_M1           [MANUAL_LOAD]
M2_CHECK -> LOADED_SINK_M2           [MANUAL_LOAD]
M3_CHECK -> LOADED_SINK_M3           [MANUAL_LOAD]
M4_CHECK -> LOADED_SINK_M4           [MANUAL_LOAD]
M5_CHECK -> LOADED_SINK_M5           [MANUAL_LOAD]
M6_CHECK -> LOADED_SINK_M6           [MANUAL_LOAD]
M7_CHECK -> LOADED_SINK_M7           [MANUAL_LOAD]
M8_CHECK -> LOADED_SINK_M8           [MANUAL_LOAD]

# Cleared M9 return by cart, or direct loading for a closing flight
M9_CHECK -> M1_CHECK                 [MANUAL_CART]
M9_CHECK -> M2_CHECK                 [MANUAL_CART]
M9_CHECK -> M3_CHECK                 [MANUAL_CART]
M9_CHECK -> M4_CHECK                 [MANUAL_CART]
M9_CHECK -> M5_CHECK                 [MANUAL_CART]
M9_CHECK -> M6_CHECK                 [MANUAL_CART]
M9_CHECK -> M7_CHECK                 [MANUAL_CART]
M9_CHECK -> M8_CHECK                 [MANUAL_CART]
M9_CHECK -> DIRECT_AIRCRAFT_SINK     [MANUAL_LOAD]
```

The two-node carousel template is deliberately minimal:
`M*_CHECK -> M*_RECIRC -> M*_CHECK`. The article explicitly describes a bag
going around the carousel again, so the directed cycle is factual at the
process level. The template does not infer the physical clockwise or
counter-clockwise direction of a belt.

## 4. Frozen service-time rule

The only source-backed service rule selected here is:

```text
service_time(M1_CHECK ... M8_CHECK, M9_CHECK) = 30.0 seconds per bag
service_time(all other abstraction nodes) = 0.0 seconds
```

The 30-second value is a generic handler average reported by the paper, not a
claim of a device-level SCL measurement. It is tagged
`SOURCE_REPORTED_GENERIC_PRIOR` and must not be fitted after observing G32
outcomes. If a future runtime applies its already-frozen global positive
minimum to zero-service connector nodes, that is computational semantics and
must not be reported as measured SCL service.

This creates a deliberately different service scale from the existing map2
profile (`0` or `1` second) and Nanning profile (`0`, `1`, `1.5`, `2`, or `3`
seconds), without outcome-dependent scaling. The reported 1000/800/500/625
bags-per-hour figures are retained as provenance context only; this document
does not silently turn any of them into a scanner or belt service time.

## 5. Section 12.4 lock and remaining pre-run work

The selected topology differs structurally through four parallel source
subsystems, a shared four-to-one irregular-flow merge, normal two-way
destination branching, nine explicit recirculation cycles, and manual return
edges from M9. Sources and sinks are explicit. Storage/EBS is explicitly
absent rather than imputed.

The following remain `NOT_DONE` and are not made true by this preregistration:

- no SCL graph/profile file has been generated or loaded;
- no SCL workload or fault scenario has been imported;
- per-edge distance, belt speed, and travel time are not published at the
  selected abstraction level and have not been invented;
- the arbitrary-ID remapper, role-schema validation, fail-closed storage/EBS,
  generic workload/fault import, and automatic profile validation must pass
  their own gates before a run;
- no SCL baseline, candidate, safety, capacity, or performance run has occurred;
- no `UNSEEN_MAP_PASS`, `UNSEEN_MAP_MIXED`, or `UNSEEN_MAP_FAIL` verdict exists.

Only after the final algorithm and candidate parameters are frozen may a thin
generic importer materialize this exact abstraction. Before the first run it
must freeze the materialized node/edge/profile/workload/fault hashes and one
outcome-independent rule for any still-required travel parameter. Missing
parameters must fail closed; they may not be chosen from held-out results.

## 6. Copyright and redistribution boundary

The Universidad de Chile repository record displays a
CC BY-NC-ND 3.0 Chile notice, while the deposited article PDF states
`(c) 2017 Elsevier B.V. All rights reserved.` The scope of the repository
notice relative to the publisher PDF and its figures is not sufficiently clear
to treat the figures as openly adaptable.

Consequently:

- this project must not copy, crop, bundle, trace, redraw, or visually imitate
  Fig. 1 or Fig. 7;
- this document records only factual relationships in a new naming, ordering,
  role schema, and textual edge-list expression, with attribution;
- the source PDF remains an external cited object and is not a project artifact;
- this is a research provenance assessment, not legal advice;
- public redistribution of a derived graph asset remains
  `RIGHTS_CLEARANCE_REQUIRED` until written permission or legal review confirms
  that the factual edge list may be distributed as planned.

The rights boundary does not negate the section 12.4 scientific selection for
an internal preregistered run. It does block any claim that the source figures
or a derivative graphical rendering are openly licensed.
