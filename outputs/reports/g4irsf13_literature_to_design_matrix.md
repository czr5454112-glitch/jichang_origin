# G4IRSF13 Literature-to-Design Matrix

Date: 2026-07-27

coverage: `11/11 COMPLETE`
source_policy: `PRIMARY_OR_OFFICIAL_ONLY`
claim: `DESIGN_JUSTIFICATION_NOT_PROMOTION_EVIDENCE`

## Executive boundary

The sources justify bounded mechanisms and controlled A/B tests. They do not authorize HCA*/A*/SIPP/CBS in the final runtime, a full guidance graph, a complete future route, a global reservation scan, or a completeness/throughput theorem on protected map2.

| ID | Identifier | Access | Target |
| --- | --- | --- | --- |
| THESIS_FENG_2021 | local-pdf-sha256:37e61b8e4d67e56c0fa14c43b230be965e200106704363f06b80a4e6a151e1aa | VISUALLY_AUDITED_LOCAL_PRIMARY | Q1-Q3 local priority, local fault overlay, affected-bag lifecycle |
| PIBT_IJCAI_2019 | 10.24963/ijcai.2019/76 | FULL_TEXT_PRIMARY | bounded local P2 ownership/prepare/validate/commit |
| PIBT_PREFERENCE_SOCS_2025 | 10.1609/socs.v18i1.35982 | FULL_TEXT_PRIMARY | bounded P2 candidate preference only |
| ONLINE_GGO_AAAI_2025 | 10.1609/aaai.v39i14.33614 | FULL_TEXT_PRIMARY | clipped bounded learned residual over frozen scorer |
| WINC_MAPF_AAAI_2025 | 10.1609/aaai.v39i22.34499 | FULL_TEXT_PRIMARY | offline deadlock/livelock diagnostics only |
| TARAU_ROUTE_CHOICE_2009 | 10.3141/2106-09 | FULL_TEXT_AUTHOR_MANUSCRIPT | event-junction local observation and scorer boundary |
| TARAU_DECENTRALIZED_2009 | 10.3182/20090902-3-US-2007.0036 | FULL_TEXT_AUTHOR_MANUSCRIPT | bounded local feature lineage and zero-global-scan audit |
| TARAU_MODEL_BASED_2010 | 10.1109/TSMCC.2009.2036735 | FULL_TEXT_AUTHOR_MANUSCRIPT | event loop, physical interlock, and local telemetry |
| JOHNSTONE_MERGE_2015 | 10.1016/j.simpat.2015.01.003 | PRIMARY_PUBLISHER_ABSTRACT_AND_SNIPPETS | merge-only credit and merge service telemetry |
| MAP_EXECUTION_UNCERTAINTY_SOCS_2024 | 10.1609/socs.v17i1.31543 | FULL_TEXT_PRIMARY | P2 validate/commit and physical safety gate |
| REALTIME_SIPP_SOCS_2024 | 10.1609/socs.v17i1.31554 | FULL_TEXT_PRIMARY | local resource-calendar feature and runtime budget audit |

## Source-by-source transfer contract

### 1. THESIS_FENG_2021

**Citation:** Feng Ruchen, Dynamic Route Planning Method for an Airport Baggage Handling System Based on the Internet of Things. Identifier: `local-pdf-sha256:37e61b8e4d67e56c0fa14c43b230be965e200106704363f06b80a4e6a151e1aa`. `user-supplied thesis PDF`.

**Access:** `VISUALLY_AUDITED_LOCAL_PRIMARY`.

**Transferable mechanism:** Task-list lifecycle; fault/new/conflict classes; slack and age; BTI/DDI separation; affected-task repair re-entry.

**Conflicting assumption:** The thesis controller performs HCA* planning and inspects saved future routes/reservations.

**Target module:** `Q1-Q3 local priority, local fault overlay, affected-bag lifecycle`.

**Required A/B:** Q0-Q3 isolation; B2 legacy-order one-step diagnostic; fault physical-shield-only versus local DDI/BTI policy.

**Prohibited overclaim:** Do not migrate HCA*, complete future routes, global reservations, or the thesis's reported success rates as new-runtime results.

### 2. PIBT_IJCAI_2019

**Citation:** Okumura et al., Priority Inheritance with Backtracking for Iterative Multi-agent Path Finding, IJCAI 2019. Identifier: `10.24963/ijcai.2019/76`. [primary source](https://www.ijcai.org/proceedings/2019/0076.pdf).

**Access:** `FULL_TEXT_PRIMARY`.

**Transferable mechanism:** Unique priorities, local priority inheritance, valid/invalid backtracking, and one-step coordination.

**Conflicting assumption:** Finite arrival requires every adjacent pair to lie on a simple cycle of length at least three; real map2 has 11 weak-projection bridges and continuous-time directed resources.

**Target module:** `bounded local P2 ownership/prepare/validate/commit`.

**Required A/B:** P0/P1/P2/P3/P4 depth and matched-contention A/B.

**Prohibited overclaim:** Call it PIBT-inspired bounded local coordination; do not claim classic PIBT completeness or deadlock freedom on map2.

### 3. PIBT_PREFERENCE_SOCS_2025

**Citation:** Okumura and Nagai, Lightweight and Effective Preference Construction in PIBT for Large-Scale MAPF, SoCS 2025. Identifier: `10.1609/socs.v18i1.35982`. [primary source](https://ojs.aaai.org/index.php/SOCS/article/view/35982).

**Access:** `FULL_TEXT_PRIMARY`.

**Transferable mechanism:** Local dodge tie-break and repeated-run regret as lightweight preference components.

**Conflicting assumption:** The paper studies MAPF agents and offline/repeated PIBT runs, not timed conveyor bags with one directed resource commit.

**Target module:** `bounded P2 candidate preference only`.

**Required A/B:** Current versus dodge versus local-regret versus combined on a matched real contention cohort.

**Prohibited overclaim:** Do not transfer reported MAPF percentage gains or add multi-step routes; any regret feature must be bounded and local.

### 4. ONLINE_GGO_AAAI_2025

**Citation:** Zang et al., Online Guidance Graph Optimization for Lifelong Multi-Agent Path Finding, AAAI 2025. Identifier: `10.1609/aaai.v39i14.33614`. [primary source](https://ojs.aaai.org/index.php/AAAI/article/view/33614).

**Access:** `FULL_TEXT_PRIMARY`.

**Transferable mechanism:** Combine adaptive traffic guidance with a rule-based PIBT safety/coordination layer and test distribution change.

**Conflicting assumption:** Its learned object is a guidance graph for LMAPF; this runtime forbids global guidance scans and future path storage.

**Target module:** `clipped bounded learned residual over frozen scorer`.

**Required A/B:** Frozen scorer versus residual under identical local observations, plus distribution-shift slices.

**Prohibited overclaim:** Do not copy a full guidance graph or claim the published LMAPF improvements on this BHS.

### 5. WINC_MAPF_AAAI_2025

**Citation:** Veerapaneni et al., Windowed MAPF with Completeness Guarantees, AAAI 2025. Identifier: `10.1609/aaai.v39i22.34499`. [primary source](https://ojs.aaai.org/index.php/AAAI/article/view/34499).

**Access:** `FULL_TEXT_PRIMARY`.

**Transferable mechanism:** Treat single-step myopia, deadlock, livelock, and heuristic updates as explicit diagnostic concerns.

**Conflicting assumption:** The completeness framework uses joint configurations, agent groups, and an optimal MAPF solver; SS-CBS is still CBS.

**Target module:** `offline deadlock/livelock diagnostics only`.

**Required A/B:** Bounded local priority/regret controls on real motifs and the size ladder, without importing CBS.

**Prohibited overclaim:** Do not run runtime CBS or claim WinC-MAPF completeness for this directed, timed, reservation-depth-one system.

### 6. TARAU_ROUTE_CHOICE_2009

**Citation:** Tarau, De Schutter, and Hellendoorn, Route Choice Control of Automated Baggage Handling Systems, 2009. Identifier: `10.3141/2106-09`. [primary source](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_011.pdf).

**Access:** `FULL_TEXT_AUTHOR_MANUSCRIPT`.

**Transferable mechanism:** Junction-owned event decisions and explicit quality/computation comparison between local heuristics and prediction.

**Conflicting assumption:** DCV switches, preferred route sets, and predictive horizons do not match this fixed conveyor graph and one-next-edge contract.

**Target module:** `event-junction local observation and scorer boundary`.

**Required A/B:** Q variants with resource/P2/scorer controls fixed.

**Prohibited overclaim:** Do not call the local rule MPC-equivalent or import full predictive routes.

### 7. TARAU_DECENTRALIZED_2009

**Citation:** Tarau, De Schutter, and Hellendoorn, Decentralized Route Choice Control of Automated Baggage Handling Systems, IFAC 2009. Identifier: `10.3182/20090902-3-US-2007.0036`. [primary source](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_031.pdf).

**Access:** `FULL_TEXT_AUTHOR_MANUSCRIPT`.

**Transferable mechanism:** Make local-only and bounded-neighbor information variants explicit and audit every information read.

**Conflicting assumption:** Decentralized MPC still predicts multiple bags and assumes low-level safety and DCV capacities.

**Target module:** `bounded local feature lineage and zero-global-scan audit`.

**Required A/B:** Local-only versus bounded-neighbor residual.

**Prohibited overclaim:** Do not call a neighbor summary decentralized without read-depth and scan counters.

### 8. TARAU_MODEL_BASED_2010

**Citation:** Tarau, De Schutter, and Hellendoorn, Model-Based Control for Route Choice in Automated Baggage Handling Systems, 2010. Identifier: `10.1109/TSMCC.2009.2036735`. [primary source](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_048.pdf).

**Access:** `FULL_TEXT_AUTHOR_MANUSCRIPT`.

**Transferable mechanism:** Separate event control, physical safety, and policy; compare bounded local prediction with a cheap one-step heuristic.

**Conflicting assumption:** Enough carriers, endpoint capacity, DCV dynamics, and multi-step MPC are not this runtime's semantics.

**Target module:** `event loop, physical interlock, and local telemetry`.

**Required A/B:** One-variable event/resource/policy isolation.

**Prohibited overclaim:** Do not assume safety away or use this source to authorize global future planning.

### 9. JOHNSTONE_MERGE_2015

**Citation:** Johnstone, Creighton, and Nahavandi, Simulation-Based Baggage Handling System Merge Analysis, 2015. Identifier: `10.1016/j.simpat.2015.01.003`. [primary source](https://www.sciencedirect.com/science/article/pii/S1569190X15000131).

**Access:** `PRIMARY_PUBLISHER_ABSTRACT_AND_SNIPPETS`.

**Transferable mechanism:** Treat merge control and geometry separately; measure input, busy time, queue, and output near saturation.

**Conflicting assumption:** A studied merge's physical spacing/rate is not calibration for map2's 23 real directed merge nodes.

**Target module:** `merge-only credit and merge service telemetry`.

**Required A/B:** C0 versus merge-only C7 on real merge motifs first.

**Prohibited overclaim:** Do not copy physical capacity numbers or infer airport-wide capacity.

### 10. MAP_EXECUTION_UNCERTAINTY_SOCS_2024

**Citation:** Liu et al., Multi-Agent Path Execution with Uncertainty, SoCS 2024. Identifier: `10.1609/socs.v17i1.31543`. [primary source](https://ojs.aaai.org/index.php/SOCS/article/view/31543).

**Access:** `FULL_TEXT_PRIMARY`.

**Transferable mechanism:** Validate concurrent actions online and keep execution safety separate from nominal planning.

**Conflicting assumption:** The method reasons about feasibility of remaining plans, while this final runtime stores no remaining route.

**Target module:** `P2 validate/commit and physical safety gate`.

**Required A/B:** P2 atomicity/fault-between-prepare-and-commit tests.

**Prohibited overclaim:** Do not import full-plan feasibility or call the one-step gate an implementation of the paper.

### 11. REALTIME_SIPP_SOCS_2024

**Citation:** Wild Thomas, Ruml, and Shimony, Real-time Safe Interval Path Planning, SoCS 2024. Identifier: `10.1609/socs.v17i1.31554`. [primary source](https://ojs.aaai.org/index.php/SOCS/article/view/31554).

**Access:** `FULL_TEXT_PRIMARY`.

**Transferable mechanism:** Bound decision time, commit the next action online, and expose time-dependent safety intervals.

**Conflicting assumption:** SIPP assumes known future obstacle trajectories and performs lookahead/search over safe-interval states.

**Target module:** `local resource-calendar feature and runtime budget audit`.

**Required A/B:** Same policy with/without bounded calendar feature.

**Prohibited overclaim:** Do not add SIPP/A* search, known future trajectories, or a complete-route commitment.

## Decision

The approved transfer is a one-step, reservation-depth-one, bounded-local controller with an always-on physical interlock. Every imported idea remains behind its own matched A/B and must pass completion, safety, tail, and no-future-information gates before promotion.
