# G4IRSF12 Literature-to-Design Audit

Date: 2026-07-23

coverage: `13/13 COMPLETE`
source_policy: `PRIMARY_OR_OFFICIAL_ONLY`
implementation_claim: `DESIGN_INPUT_NOT_ALGORITHM_PASS`

## Executive boundaries

- The protected map is directed and its audit reports 31 directed SCCs plus 11 weak-projection bridges. It does not satisfy the classic PIBT adjacent-edge simple-cycle/biconnected premise. The implemented mechanism remains **PIBT-inspired bounded local coordination**, without a completeness/deadlock-freedom claim.
- Tassiulas–Ephremides and Varaiya prove stability/maximum-throughput results under specific queue, arrival, service, storage, feasible-schedule, and information assumptions. A bounded local destination-conditioned differential term in this runtime is **not throughput-optimal** by citation.
- IATA/ACRP prescribe scoped peak/design-day analysis, not a universal multiplier. This case's airport, terminal, local/transfer scope, parallel BHS share, and day type remain unknown; no finite realistic scale envelope follows from these sources.
- Publisher pages with only an original abstract or visible section snippets are labelled as such. No inaccessible detail was filled from reviews, aggregators, or secondary summaries.

## Coverage

| # | ID | Primary source | Access | Project mapping |
| --- | --- | --- | --- | --- |
| 1 | PIBT_IJCAI_2019 | [primary source](https://www.ijcai.org/proceedings/2019/0076.pdf) | FULL_TEXT_PRIMARY | cpp/ics_core/runtime/bounded_local_pibt.hpp and the ready-set arbitration/atomic-commit boundary |
| 2 | WINPIBT_ARXIV_2019 | [primary source](https://arxiv.org/abs/1905.10149) | FULL_TEXT_PRIMARY_PREPRINT | Offline diagnostic design only; no import into the final reservation-depth-one runtime |
| 3 | TARAU_ROUTE_CHOICE_2009 | [primary source](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_011.pdf) | FULL_TEXT_AUTHOR_TECHNICAL_REPORT | Event junction candidate ranking, local scorer adapter, and bounded decision telemetry |
| 4 | TARAU_MODEL_BASED_2010 | [primary source](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_048.pdf) | FULL_TEXT_AUTHOR_TECHNICAL_REPORT | Event loop, physical fault shield, resource-semantics layer, and local scorer/telemetry boundary |
| 5 | TARAU_DECENTRALIZED_2009 | [primary source](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_031.pdf) | FULL_TEXT_AUTHOR_TECHNICAL_REPORT | Bounded local observation builder, scorer feature lineage, and zero-global-scan counters |
| 6 | JOHNSTONE_MERGE_2015 | [primary source](https://www.sciencedirect.com/science/article/pii/S1569190X15000131) | PRIMARY_PUBLISHER_ABSTRACT_AND_SECTION_SNIPPETS | R4 merge service calendar, merge inventory, utilization telemetry, and backlog-drain reporting |
| 7 | TASSIULAS_EPHREMIDES_1992 | [primary source](https://drum.lib.umd.edu/items/571fda52-aefb-4497-9a2d-69d8c7c907b9) | FULL_TEXT_INSTITUTIONAL_REPOSITORY | Goal-conditioned differential pressure, expiring-credit admission, and stability/backlog telemetry |
| 8 | VARAIYA_MAX_PRESSURE_2013 | [primary source](https://www.sciencedirect.com/science/article/pii/S0968090X13001782) | PRIMARY_PUBLISHER_ABSTRACT_ONLY | Q(node, goal), age, scheduled incoming, local service-rate estimate, and differential-pressure scorer term |
| 9 | SORENSEN_DRL_BHS_2020 | [primary source](https://journals.sagepub.com/doi/10.3233/ICA-190613) | PRIMARY_PUBLISHER_ABSTRACT_ONLY | Stage-I candidate ranking training/evaluation protocol only; not the physical shield or PIBT coordinator |
| 10 | ZANG_ONLINE_GGO_2025 | [primary source](https://ojs.aaai.org/index.php/AAAI/article/download/33614/35769) | FULL_TEXT_PRIMARY | Stage-I lightweight local scorer feature/ranking research; PIBT and physical shield remain separate owners |
| 11 | IATA_ADRM_12 | [primary source](https://www.iata.org/en/publications/manuals/airport-development-reference-manual/) | OFFICIAL_SCOPE_PAGE_ONLY | G4IRSF12-K airport-scope/demand-calibration protocol and Phase-L capacity frontier |
| 12 | ACRP_REPORT_82 | [primary source](https://www.nationalacademies.org/publications/22646) | OFFICIAL_REPORT_SUMMARY_AND_TOOLBOX_DESCRIPTION | Demand calibration inputs, uncertainty envelope, temporal-shape audit, and future workload manifest validation |
| 13 | ACRP_REPORT_163 | [primary source](https://nap.nationalacademies.org/read/23692/chapter/9) | FULL_TEXT_OFFICIAL_CHAPTER | G4IRSF12-K design-day numerator and shape protocol; future original_rule_replay_scaled_input drift audit |

## Item-by-item transfer contract

### 1. PIBT_IJCAI_2019

**Citation:** Okumura, Machida, Défago, and Tamura, Priority Inheritance with Backtracking for Iterative Multi-agent Path Finding, IJCAI 2019. Identifier: `10.24963/ijcai.2019/76`. [primary source](https://www.ijcai.org/proceedings/2019/0076.pdf).

**Access:** `FULL_TEXT_PRIMARY`.

**Primary evidence:** The paper gives every agent a unique time-varying priority, lets a blocker inherit priority, and returns valid/invalid outcomes by backtracking. Its finite-arrival theorem requires every adjacent node pair to lie on a simple cycle of length at least three.

**Applicable problem:** Several simultaneously ready bags locally block one another at a junction, merge, or next-node resource.

**Transferable mechanism:** Unique deterministic priority; recursive priority inheritance to the actual local owner; visiting/cycle guard; valid/invalid backtracking; two-phase atomic one-step commit.

**Conflicting assumptions:** The protected airport graph is directed, has 31 directed SCCs and 11 weak-projection bridges, so it does not satisfy the paper's classic simple-cycle/biconnected completeness premise. The runtime also models timed physical resources rather than unit synchronous vertex moves.

**Target module:** `cpp/ics_core/runtime/bounded_local_pibt.hpp and the ready-set arbitration/atomic-commit boundary`.

**Required A/B:** Stage F P0/P1/P2/P3/P4 depth ablation; framework B5 versus B6 with scorer, resource semantics, pressure, and admission fixed.

**Prohibited overclaim:** Call the implementation PIBT-inspired bounded local coordination. Do not claim classic PIBT completeness, deadlock freedom, finite arrival, or throughput optimality on this graph.

### 2. WINPIBT_ARXIV_2019

**Citation:** Okumura, Tamura, and Défago, winPIBT: Extended Prioritized Algorithm for Iterative Multi-agent Path Finding, arXiv 2019. Identifier: `arXiv:1905.10149`. [primary source](https://arxiv.org/abs/1905.10149).

**Access:** `FULL_TEXT_PRIMARY_PREPRINT`.

**Primary evidence:** winPIBT generalizes one-step PIBT with configurable multi-step time-node reservations. The paper reports that useful window size depends on map structure and that extra reservation can itself produce awkward paths.

**Applicable problem:** Diagnosing whether one-step shortsightedness causes livelock or avoidable detours in narrow passages.

**Transferable mechanism:** Use window size as an explicit sensitivity variable and preserve the paper's warning that longer lookahead is not uniformly better.

**Conflicting assumptions:** The required final runtime has reservation_depth=1, stores no complete future path, and forbids multi-step global reservation. The graph also lacks the completeness topology premise.

**Target module:** `Offline diagnostic design only; no import into the final reservation-depth-one runtime`.

**Required A/B:** Any window >1 experiment must be separately labelled research-only and compared with P1 under identical maps/tasks; it cannot replace the mandated P0-P4 recursion-depth ablation.

**Prohibited overclaim:** Do not call the one-step implementation winPIBT, silently retain future reservations, or infer that a larger window improves this airport map.

### 3. TARAU_ROUTE_CHOICE_2009

**Citation:** Tarău, De Schutter, and Hellendoorn, Route Choice Control of Automated Baggage Handling Systems, Transportation Research Record 2106, 2009. Identifier: `10.3141/2106-09`. [primary source](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_011.pdf).

**Access:** `FULL_TEXT_AUTHOR_TECHNICAL_REPORT`.

**Primary evidence:** The author manuscript compares centralized MPC, decentralized MPC, and a fast decentralized heuristic. A junction owns local switch-in and switch-out control; centralized MPC becomes computationally intractable at larger streams, while local methods trade optimality for computation.

**Applicable problem:** Selecting routes at BHS junctions under dynamic demand, timing priorities, and a strict online computation budget.

**Transferable mechanism:** Treat the junction as the local decision boundary; expose static and dynamic bag priority; measure quality-versus-computation rather than assuming centralized lookahead is deployable.

**Conflicting assumptions:** The paper studies DCVs, switch controllers, preferred route sets, and predictive horizons. This project uses a fixed directed conveyor graph, one-next-edge decisions, no full future route, and different collision/resource semantics.

**Target module:** `Event junction candidate ranking, local scorer adapter, and bounded decision telemetry`.

**Required A/B:** B3/B5 with one variable changed; E S0-S4 scorer isolation with resource semantics, PIBT, pressure, and admission fixed.

**Prohibited overclaim:** Do not import the paper's benchmark performance, call the local heuristic optimal, or claim equivalence between its DCV switches and this conveyor resource model.

### 4. TARAU_MODEL_BASED_2010

**Citation:** Tarău, De Schutter, and Hellendoorn, Model-Based Control for Route Choice in Automated Baggage Handling Systems, IEEE TSMC-C 2010. Identifier: `10.1109/TSMCC.2009.2036735`. [primary source](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_048.pdf).

**Access:** `FULL_TEXT_AUTHOR_TECHNICAL_REPORT`.

**Primary evidence:** The author manuscript develops an event-driven DCV model and centralized, decentralized, and distributed predictive controllers plus low-cost heuristics. It explicitly assumes low-level safety controllers, enough empty DCVs, and junctions with at most two incoming and two outgoing links.

**Applicable problem:** Separating fast event simulation, local route choice, and physical safety while exposing the cost of prediction horizon.

**Transferable mechanism:** Keep safety interlocks below route policy; trigger decisions at events; compare bounded local predictive information with a one-step heuristic under the same physical model.

**Conflicting assumptions:** Enough empty carriers, no source starvation, assumed low-level collision control, DCV dynamics, fixed route sets, and multi-step MPC do not match source queues, timed reservations, faults, or the no-future-route constraint here.

**Target module:** `Event loop, physical fault shield, resource-semantics layer, and local scorer/telemetry boundary`.

**Required A/B:** B2/B3 for event-loop and reservation-horizon isolation; C R0-R4 resource semantics before changing policy.

**Prohibited overclaim:** Do not call this runtime MPC/model-equivalent, assume low-level safety away, or use the paper to authorize global future planning.

### 5. TARAU_DECENTRALIZED_2009

**Citation:** Tarău, De Schutter, and Hellendoorn, Decentralized Route Choice Control of Automated Baggage Handling Systems, IFAC 2009. Identifier: `10.3182/20090902-3-US-2007.0036`. [primary source](https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_031.pdf).

**Access:** `FULL_TEXT_AUTHOR_TECHNICAL_REPORT`.

**Primary evidence:** The author manuscript uses an event-based DCV model and compares decentralized MPC with one-step local heuristics. The heuristics use local incoming/outgoing flow, optionally neighboring-junction flow; larger MPC horizon generally costs more computation.

**Applicable problem:** Designing a genuinely local junction controller and auditing exactly which neighbor state crosses its information boundary.

**Transferable mechanism:** Make local-only and local-plus-neighbor variants explicit; log every read; bound neighbor depth; compare latency and outcomes.

**Conflicting assumptions:** The paper assumes low-level collision avoidance, sufficient DCVs, large endpoint capacity, and a DCV/switch topology. Its decentralized MPC still predicts multiple bags and is not reservation-depth one.

**Target module:** `Bounded local observation builder, scorer feature lineage, and zero-global-scan counters`.

**Required A/B:** E local S1 versus S2 ID removal; G C0/C2/C3 bounded-neighbor pressure variants; hold resource and PIBT modes fixed.

**Prohibited overclaim:** Do not call a bounded neighbor summary fully decentralized without read auditing, or transfer the paper's suboptimality/performance results to this topology.

### 6. JOHNSTONE_MERGE_2015

**Citation:** Johnstone, Creighton, and Nahavandi, Simulation-Based Baggage Handling System Merge Analysis, Simulation Modelling Practice and Theory 53, 2015. Identifier: `10.1016/j.simpat.2015.01.003`. [primary source](https://www.sciencedirect.com/science/article/pii/S1569190X15000131).

**Access:** `PRIMARY_PUBLISHER_ABSTRACT_AND_SECTION_SNIPPETS`.

**Primary evidence:** The publisher abstract and visible sections isolate a conveyor merge as a bottleneck and study both its control algorithm and physical layout using simulation and bag throughput. Full subscription text was not relied on.

**Applicable problem:** Calibrating merge service calendars and explaining congestion where two directed inflows compete for one collector resource.

**Transferable mechanism:** Represent merge control and merge geometry as separate variables; measure offered input, merge busy time, queue formation, and output throughput near saturation.

**Conflicting assumptions:** The studied single-merge conveyor geometry, bag spacing, controllers, and rates are not the protected map's 23 inferred merges. This project has no authoritative physical headway/buffer calibration.

**Target module:** `R4 merge service calendar, merge inventory, utilization telemetry, and backlog-drain reporting`.

**Required A/B:** C R2 versus R4 with identical direction/headway and policy; vary only merge calendar semantics, first on real-map motifs then the size ladder.

**Prohibited overclaim:** Do not copy numerical headway, spacing, layout, or capacity values; do not claim physical calibration or airport-wide capacity from a single-merge mechanism.

### 7. TASSIULAS_EPHREMIDES_1992

**Citation:** Tassiulas and Ephremides, Stability Properties of Constrained Queueing Systems and Scheduling Policies for Maximum Throughput in Multihop Radio Networks, IEEE TAC 1992. Identifier: `10.1109/9.182479`. [primary source](https://drum.lib.umd.edu/items/571fda52-aefb-4497-9a2d-69d8c7c907b9).

**Access:** `FULL_TEXT_INSTITUTIONAL_REPOSITORY`.

**Primary evidence:** The paper defines stability regions for constrained queues with interdependent servers and selects feasible simultaneous server activations from global queue state. Its maximum-throughput result uses centralized decisions, slotted time, and infinite buffers.

**Applicable problem:** Understanding why a queue differential can inform local routing and why stability must be measured under sustained arrivals.

**Transferable mechanism:** Use upstream-minus-downstream queue pressure as a diagnostic/control component; define feasible resource activations; evaluate queue stability region empirically via injection, backlog, and drain.

**Conflicting assumptions:** This runtime has continuous event time, directed travel resources, finite/unknown buffers, deadlines, faults, local bounded state, credit admission, and no centralized maximum-weight activation over the whole network.

**Target module:** `Goal-conditioned differential pressure, expiring-credit admission, and stability/backlog telemetry`.

**Required A/B:** Stage G C0-C6 with pressure, credit, and PIBT introduced separately; measure arrival/departure rates, source/network backlog, and drain.

**Prohibited overclaim:** A bounded local differential term is not the paper's throughput-optimal policy. Do not claim a maximal stability region without matching its model, feasible schedules, and proof.

### 8. VARAIYA_MAX_PRESSURE_2013

**Citation:** Varaiya, Max Pressure Control of a Network of Signalized Intersections, Transportation Research Part C 36, 2013. Identifier: `10.1016/j.trc.2013.08.014`. [primary source](https://www.sciencedirect.com/science/article/pii/S0968090X13001782).

**Access:** `PRIMARY_PUBLISHER_ABSTRACT_ONLY`.

**Primary evidence:** The publisher abstract models separate turn queues as infinite point queues in a store-and-forward network with iid arrivals, fixed turn ratios, iid saturation rates, and selectable compatible stages. Under those assumptions, adjacent-queue max pressure stabilizes interior feasible demand.

**Applicable problem:** Choosing among competing local movements at a junction using destination/turn-conditioned upstream and downstream congestion.

**Transferable mechanism:** Condition queues by movement/goal; subtract downstream scheduled incoming work; combine with service rate; choose only among physically compatible local actions.

**Conflicting assumptions:** Bags do not follow fixed stochastic turn ratios; queues are not infinite point queues; service is timed and faultable; deadlines and source admission matter; the controller does not select the paper's traffic-signal stage set.

**Target module:** `Q(node, goal), age, scheduled incoming, local service-rate estimate, and differential-pressure scorer term`.

**Required A/B:** G C0/C1/C2/C3 first, then C4/C5/C6; compare destination-conditioned differential against absolute queue penalty under identical loads.

**Prohibited overclaim:** Local differential pressure is not automatically max-pressure or throughput-optimal. Do not transfer the theorem without iid/turn/service/storage/stage assumptions and a proof.

### 9. SORENSEN_DRL_BHS_2020

**Citation:** Sørensen, Nielsen, and Karstoft, Routing in Congested Baggage Handling Systems Using Deep Reinforcement Learning, Integrated Computer-Aided Engineering 27(2), 2020. Identifier: `10.3233/ICA-190613`. [primary source](https://journals.sagepub.com/doi/10.3233/ICA-190613).

**Access:** `PRIMARY_PUBLISHER_ABSTRACT_ONLY`.

**Primary evidence:** The publisher abstract reports a single global Dueling-DQN agent with prioritized replay and multi-action output, trained/tested in three simple but functionally realistic cyclic BHS simulations over a broad load distribution.

**Applicable problem:** Testing whether a learned policy can rank congestion-aware routes better than static or dynamic shortest-path rules.

**Transferable mechanism:** Train across a load distribution, compare with strong rule baselines, and evaluate closed-loop deadlocks, throughput, and delivery time rather than offline accuracy alone.

**Conflicting assumptions:** The paper's controller is a single global multi-action DQN, whereas this project requires lightweight one-step local decisions, bounded state, zero global scan, an independent safety shield, and the fixed real map. Its simulated environments do not establish airport scope.

**Target module:** `Stage-I candidate ranking training/evaluation protocol only; not the physical shield or PIBT coordinator`.

**Required A/B:** After all I gates, compare v3 linear/tiny-MLP candidates with S0/S3/S4 in a closed loop at 144/512/2048/8192 before full 1x.

**Prohibited overclaim:** Do not authorize PPO/MAPPO/full RL, claim real-airport transfer, claim deadlock elimination, or equate global DQN evidence with a legal local scorer.

### 10. ZANG_ONLINE_GGO_2025

**Citation:** Zang et al., Online Guidance Graph Optimization for Lifelong Multi-Agent Path Finding, AAAI 2025. Identifier: `10.1609/aaai.v39i14.33614`. [primary source](https://ojs.aaai.org/index.php/AAAI/article/download/33614/35769).

**Access:** `FULL_TEXT_PRIMARY`.

**Primary evidence:** The paper learns an online policy that updates directed guidance edge/action costs from real-time traffic and integrates it with PIBT or Guided-PIBT. LMAPF throughput is goals reached per timestep; benefit varies by map and dynamic task distribution.

**Applicable problem:** Adapting local route preference when congestion locations move with time-varying task banks.

**Transferable mechanism:** Separate learned edge ranking/guidance from collision coordination; condition evaluation on dynamic demand; measure closed-loop throughput and compute overhead.

**Conflicting assumptions:** The paper updates a map-wide guidance graph and may use guide paths/LNS, while this runtime forbids global scans and future paths and limits the learned model to legal bounded local features. Its maps, tasks, agent dynamics, and throughput denominator differ.

**Target module:** `Stage-I lightweight local scorer feature/ranking research; PIBT and physical shield remain separate owners`.

**Required A/B:** Only after I gates: static local scorer versus bounded online local features, identical PIBT/resource/admission; dynamic-bank held-out closed-loop tests.

**Prohibited overclaim:** Do not claim the reported throughput improvements on map2, import a global guidance graph/LNS into the final runtime, or treat learned guidance as collision safety.

### 11. IATA_ADRM_12

**Citation:** International Air Transport Association, Airport Development Reference Manual, 12th edition. Identifier: `IATA_ADRM_12TH_EDITION`. [primary source](https://www.iata.org/en/publications/manuals/airport-development-reference-manual/).

**Access:** `OFFICIAL_SCOPE_PAGE_ONLY`.

**Primary evidence:** IATA's official scope page states that ADRM covers airport planning and capacity-demand balance, with expanded sections on peak forecasting, design-day flight schedules, demand-capacity calculations, and a BHS section. The paid manual text was not used.

**Applicable problem:** Defining the represented airport/terminal/BHS subsystem and selecting design demand before any capacity claim.

**Transferable mechanism:** Make peak/design-day and subsystem demand-capacity analysis explicit; tie any scale factor to represented-system checked bags, not an arbitrary agent multiplier.

**Conflicting assumptions:** The fixed case's airport, terminal, local/transfer scope, parallel BHS share, and day type are unknown. The public scope page supplies no case-specific numbers.

**Target module:** `G4IRSF12-K airport-scope/demand-calibration protocol and Phase-L capacity frontier`.

**Required A/B:** No algorithm A/B. Compare immutable 1.0 historical-day descriptor with a future case-specific calibrated design-day profile only after all scope inputs and J gates pass.

**Prohibited overclaim:** Do not claim an ADRM-prescribed 1.1/1.25/1.5 multiplier, infer the airport scope, or treat whole-airport annual passengers as represented BHS design-day bags.

### 12. ACRP_REPORT_82

**Citation:** National Academies / ACRP Report 82, Preparing Peak Period and Operational Profiles—Guidebook, 2013. Identifier: `10.17226/22646`. [primary source](https://www.nationalacademies.org/publications/22646).

**Access:** `OFFICIAL_REPORT_SUMMARY_AND_TOOLBOX_DESCRIPTION`.

**Primary evidence:** The official report page describes converting annual forecasts to daily/hourly peak profiles with separate operations and passenger modules, using user-defined design-day parameters. It supports lead/lag factors and scenario analysis; defaults are not evidence for this airport.

**Applicable problem:** Turning a defensible annual/design-day forecast into hourly and peak-period demand without flattening flight banks.

**Transferable mechanism:** Publish clock-hour and rolling-window profiles, define design-day parameters before scaling, retain lead/lag or baggage dwell distributions, and run uncertainty scenarios.

**Conflicting assumptions:** The current input has one historical schedule day but lacks airport identity, annual case-period activity, design-day definition, passenger-to-bag conversion, and terminal/subsystem allocation.

**Target module:** `Demand calibration inputs, uncertainty envelope, temporal-shape audit, and future workload manifest validation`.

**Required A/B:** Future workload audit must compare baseline versus candidate hourly/5/15/60-minute shares and lead/dwell distributions before runtime; then Phase L advances one scale at a time.

**Prohibited overclaim:** Do not use toolbox examples/defaults as airport facts, call 1.25 a design-day factor, or treat an annual average as peak demand.

### 13. ACRP_REPORT_163

**Citation:** National Academies / ACRP Research Report 163, Guidebook for Preparing and Using Airport Design Day Flight Schedules, 2016. Identifier: `10.17226/23692`. [primary source](https://nap.nationalacademies.org/read/23692/chapter/9).

**Access:** `FULL_TEXT_OFFICIAL_CHAPTER`.

**Primary evidence:** The official chapter applies flight-by-flight DDFS data to time-of-day/facility-specific profiles. Activity-level adjustment is appropriate only when profile shape is expected to remain stable. Departure-facility peaks require airport-specific show-up lead distributions, typically obtained from passenger surveys.

**Applicable problem:** Building a traceable design-day baggage profile by terminal/facility and relating schedule time to actual early-arrival/EBS demand.

**Transferable mechanism:** Preserve flight-bank shape; keep facility scope explicit; audit lead/dwell distributions; derive baggage make-up demand from a case-specific DDFS rather than uniform time compression.

**Conflicting assumptions:** The raw input lacks flight IDs, named terminal/facility allocation, passenger survey show-up curves, and proof that scaled activity preserves profile shape. Airport scope remains unknown.

**Target module:** `G4IRSF12-K design-day numerator and shape protocol; future original_rule_replay_scaled_input drift audit`.

**Required A/B:** Before any Phase-L run, compare candidate versus 1.0 flight-bank/hourly shape and deadline/EBS dwell; reject shape drift before measuring capacity.

**Prohibited overclaim:** Do not call a resampled task stream a DDFS, infer airport-specific show-up distributions, or declare a finite realistic scale envelope while airport/terminal/subsystem inputs are missing.

## Decision

These sources justify controlled mechanisms and measurement contracts, not promotion. Runtime promotion still requires the predeclared real-map A/B gates, full original-scale completion, tail/backlog/fault evidence, and the independent airport-demand calibration gate.
