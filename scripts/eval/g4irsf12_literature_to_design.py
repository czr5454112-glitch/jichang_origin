"""Publish the audited G4IRSF12 literature-to-design mapping.

Only primary papers, author-hosted manuscripts, publisher pages, or official
institutional guidance are used.  Access limitations are explicit and no
secondary-source detail is substituted for an inaccessible primary text.
"""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
PHASE_DATE = "2026-07-23"
REPORT_PATH = Path("outputs/reports/g4irsf12_literature_to_design.md")
TABLE_PATH = Path("outputs/tables/g4irsf12_literature_to_design.csv")

EXPECTED_IDS = (
    "PIBT_IJCAI_2019",
    "WINPIBT_ARXIV_2019",
    "TARAU_ROUTE_CHOICE_2009",
    "TARAU_MODEL_BASED_2010",
    "TARAU_DECENTRALIZED_2009",
    "JOHNSTONE_MERGE_2015",
    "TASSIULAS_EPHREMIDES_1992",
    "VARAIYA_MAX_PRESSURE_2013",
    "SORENSEN_DRL_BHS_2020",
    "ZANG_ONLINE_GGO_2025",
    "IATA_ADRM_12",
    "ACRP_REPORT_82",
    "ACRP_REPORT_163",
)

EXPECTED_IDENTIFIERS = {
    "PIBT_IJCAI_2019": "10.24963/ijcai.2019/76",
    "WINPIBT_ARXIV_2019": "arXiv:1905.10149",
    "TARAU_ROUTE_CHOICE_2009": "10.3141/2106-09",
    "TARAU_MODEL_BASED_2010": "10.1109/TSMCC.2009.2036735",
    "TARAU_DECENTRALIZED_2009": "10.3182/20090902-3-US-2007.0036",
    "JOHNSTONE_MERGE_2015": "10.1016/j.simpat.2015.01.003",
    "TASSIULAS_EPHREMIDES_1992": "10.1109/9.182479",
    "VARAIYA_MAX_PRESSURE_2013": "10.1016/j.trc.2013.08.014",
    "SORENSEN_DRL_BHS_2020": "10.3233/ICA-190613",
    "ZANG_ONLINE_GGO_2025": "10.1609/aaai.v39i14.33614",
    "IATA_ADRM_12": "IATA_ADRM_12TH_EDITION",
    "ACRP_REPORT_82": "10.17226/22646",
    "ACRP_REPORT_163": "10.17226/23692",
}

ALLOWED_PRIMARY_HOSTS = {
    "www.ijcai.org",
    "arxiv.org",
    "www.dcsc.tudelft.nl",
    "www.sciencedirect.com",
    "drum.lib.umd.edu",
    "journals.sagepub.com",
    "ojs.aaai.org",
    "www.iata.org",
    "www.nationalacademies.org",
    "nap.nationalacademies.org",
}

FIELDS = (
    "order",
    "literature_id",
    "citation",
    "year",
    "identifier",
    "primary_source_url",
    "access_status",
    "primary_evidence",
    "applicable_problem",
    "transferable_mechanism",
    "conflicting_assumptions",
    "target_module",
    "required_ab",
    "prohibited_overclaim",
)


LITERATURE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "order": 1,
        "literature_id": "PIBT_IJCAI_2019",
        "citation": (
            "Okumura, Machida, Défago, and Tamura, Priority Inheritance with "
            "Backtracking for Iterative Multi-agent Path Finding, IJCAI 2019"
        ),
        "year": 2019,
        "identifier": "10.24963/ijcai.2019/76",
        "primary_source_url": (
            "https://www.ijcai.org/proceedings/2019/0076.pdf"
        ),
        "access_status": "FULL_TEXT_PRIMARY",
        "primary_evidence": (
            "The paper gives every agent a unique time-varying priority, lets a "
            "blocker inherit priority, and returns valid/invalid outcomes by "
            "backtracking. Its finite-arrival theorem requires every adjacent "
            "node pair to lie on a simple cycle of length at least three."
        ),
        "applicable_problem": (
            "Several simultaneously ready bags locally block one another at a "
            "junction, merge, or next-node resource."
        ),
        "transferable_mechanism": (
            "Unique deterministic priority; recursive priority inheritance to "
            "the actual local owner; visiting/cycle guard; valid/invalid "
            "backtracking; two-phase atomic one-step commit."
        ),
        "conflicting_assumptions": (
            "The protected airport graph is directed, has 31 directed SCCs and "
            "11 weak-projection bridges, so it does not satisfy the paper's "
            "classic simple-cycle/biconnected completeness premise. The runtime "
            "also models timed physical resources rather than unit synchronous "
            "vertex moves."
        ),
        "target_module": (
            "cpp/ics_core/runtime/bounded_local_pibt.hpp and the ready-set "
            "arbitration/atomic-commit boundary"
        ),
        "required_ab": (
            "Stage F P0/P1/P2/P3/P4 depth ablation; framework B5 versus B6 "
            "with scorer, resource semantics, pressure, and admission fixed."
        ),
        "prohibited_overclaim": (
            "Call the implementation PIBT-inspired bounded local coordination. "
            "Do not claim classic PIBT completeness, deadlock freedom, finite "
            "arrival, or throughput optimality on this graph."
        ),
    },
    {
        "order": 2,
        "literature_id": "WINPIBT_ARXIV_2019",
        "citation": (
            "Okumura, Tamura, and Défago, winPIBT: Extended Prioritized "
            "Algorithm for Iterative Multi-agent Path Finding, arXiv 2019"
        ),
        "year": 2019,
        "identifier": "arXiv:1905.10149",
        "primary_source_url": "https://arxiv.org/abs/1905.10149",
        "access_status": "FULL_TEXT_PRIMARY_PREPRINT",
        "primary_evidence": (
            "winPIBT generalizes one-step PIBT with configurable multi-step "
            "time-node reservations. The paper reports that useful window size "
            "depends on map structure and that extra reservation can itself "
            "produce awkward paths."
        ),
        "applicable_problem": (
            "Diagnosing whether one-step shortsightedness causes livelock or "
            "avoidable detours in narrow passages."
        ),
        "transferable_mechanism": (
            "Use window size as an explicit sensitivity variable and preserve "
            "the paper's warning that longer lookahead is not uniformly better."
        ),
        "conflicting_assumptions": (
            "The required final runtime has reservation_depth=1, stores no "
            "complete future path, and forbids multi-step global reservation. "
            "The graph also lacks the completeness topology premise."
        ),
        "target_module": (
            "Offline diagnostic design only; no import into the final "
            "reservation-depth-one runtime"
        ),
        "required_ab": (
            "Any window >1 experiment must be separately labelled research-only "
            "and compared with P1 under identical maps/tasks; it cannot replace "
            "the mandated P0-P4 recursion-depth ablation."
        ),
        "prohibited_overclaim": (
            "Do not call the one-step implementation winPIBT, silently retain "
            "future reservations, or infer that a larger window improves this "
            "airport map."
        ),
    },
    {
        "order": 3,
        "literature_id": "TARAU_ROUTE_CHOICE_2009",
        "citation": (
            "Tarău, De Schutter, and Hellendoorn, Route Choice Control of "
            "Automated Baggage Handling Systems, Transportation Research Record "
            "2106, 2009"
        ),
        "year": 2009,
        "identifier": "10.3141/2106-09",
        "primary_source_url": (
            "https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_011.pdf"
        ),
        "access_status": "FULL_TEXT_AUTHOR_TECHNICAL_REPORT",
        "primary_evidence": (
            "The author manuscript compares centralized MPC, decentralized MPC, "
            "and a fast decentralized heuristic. A junction owns local switch-in "
            "and switch-out control; centralized MPC becomes computationally "
            "intractable at larger streams, while local methods trade optimality "
            "for computation."
        ),
        "applicable_problem": (
            "Selecting routes at BHS junctions under dynamic demand, timing "
            "priorities, and a strict online computation budget."
        ),
        "transferable_mechanism": (
            "Treat the junction as the local decision boundary; expose static "
            "and dynamic bag priority; measure quality-versus-computation rather "
            "than assuming centralized lookahead is deployable."
        ),
        "conflicting_assumptions": (
            "The paper studies DCVs, switch controllers, preferred route sets, "
            "and predictive horizons. This project uses a fixed directed "
            "conveyor graph, one-next-edge decisions, no full future route, and "
            "different collision/resource semantics."
        ),
        "target_module": (
            "Event junction candidate ranking, local scorer adapter, and bounded "
            "decision telemetry"
        ),
        "required_ab": (
            "B3/B5 with one variable changed; E S0-S4 scorer isolation with "
            "resource semantics, PIBT, pressure, and admission fixed."
        ),
        "prohibited_overclaim": (
            "Do not import the paper's benchmark performance, call the local "
            "heuristic optimal, or claim equivalence between its DCV switches "
            "and this conveyor resource model."
        ),
    },
    {
        "order": 4,
        "literature_id": "TARAU_MODEL_BASED_2010",
        "citation": (
            "Tarău, De Schutter, and Hellendoorn, Model-Based Control for Route "
            "Choice in Automated Baggage Handling Systems, IEEE TSMC-C 2010"
        ),
        "year": 2010,
        "identifier": "10.1109/TSMCC.2009.2036735",
        "primary_source_url": (
            "https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_048.pdf"
        ),
        "access_status": "FULL_TEXT_AUTHOR_TECHNICAL_REPORT",
        "primary_evidence": (
            "The author manuscript develops an event-driven DCV model and "
            "centralized, decentralized, and distributed predictive controllers "
            "plus low-cost heuristics. It explicitly assumes low-level safety "
            "controllers, enough empty DCVs, and junctions with at most two "
            "incoming and two outgoing links."
        ),
        "applicable_problem": (
            "Separating fast event simulation, local route choice, and physical "
            "safety while exposing the cost of prediction horizon."
        ),
        "transferable_mechanism": (
            "Keep safety interlocks below route policy; trigger decisions at "
            "events; compare bounded local predictive information with a one-step "
            "heuristic under the same physical model."
        ),
        "conflicting_assumptions": (
            "Enough empty carriers, no source starvation, assumed low-level "
            "collision control, DCV dynamics, fixed route sets, and multi-step "
            "MPC do not match source queues, timed reservations, faults, or the "
            "no-future-route constraint here."
        ),
        "target_module": (
            "Event loop, physical fault shield, resource-semantics layer, and "
            "local scorer/telemetry boundary"
        ),
        "required_ab": (
            "B2/B3 for event-loop and reservation-horizon isolation; C R0-R4 "
            "resource semantics before changing policy."
        ),
        "prohibited_overclaim": (
            "Do not call this runtime MPC/model-equivalent, assume low-level "
            "safety away, or use the paper to authorize global future planning."
        ),
    },
    {
        "order": 5,
        "literature_id": "TARAU_DECENTRALIZED_2009",
        "citation": (
            "Tarău, De Schutter, and Hellendoorn, Decentralized Route Choice "
            "Control of Automated Baggage Handling Systems, IFAC 2009"
        ),
        "year": 2009,
        "identifier": "10.3182/20090902-3-US-2007.0036",
        "primary_source_url": (
            "https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_031.pdf"
        ),
        "access_status": "FULL_TEXT_AUTHOR_TECHNICAL_REPORT",
        "primary_evidence": (
            "The author manuscript uses an event-based DCV model and compares "
            "decentralized MPC with one-step local heuristics. The heuristics use "
            "local incoming/outgoing flow, optionally neighboring-junction flow; "
            "larger MPC horizon generally costs more computation."
        ),
        "applicable_problem": (
            "Designing a genuinely local junction controller and auditing exactly "
            "which neighbor state crosses its information boundary."
        ),
        "transferable_mechanism": (
            "Make local-only and local-plus-neighbor variants explicit; log every "
            "read; bound neighbor depth; compare latency and outcomes."
        ),
        "conflicting_assumptions": (
            "The paper assumes low-level collision avoidance, sufficient DCVs, "
            "large endpoint capacity, and a DCV/switch topology. Its decentralized "
            "MPC still predicts multiple bags and is not reservation-depth one."
        ),
        "target_module": (
            "Bounded local observation builder, scorer feature lineage, and "
            "zero-global-scan counters"
        ),
        "required_ab": (
            "E local S1 versus S2 ID removal; G C0/C2/C3 bounded-neighbor "
            "pressure variants; hold resource and PIBT modes fixed."
        ),
        "prohibited_overclaim": (
            "Do not call a bounded neighbor summary fully decentralized without "
            "read auditing, or transfer the paper's suboptimality/performance "
            "results to this topology."
        ),
    },
    {
        "order": 6,
        "literature_id": "JOHNSTONE_MERGE_2015",
        "citation": (
            "Johnstone, Creighton, and Nahavandi, Simulation-Based Baggage "
            "Handling System Merge Analysis, Simulation Modelling Practice and "
            "Theory 53, 2015"
        ),
        "year": 2015,
        "identifier": "10.1016/j.simpat.2015.01.003",
        "primary_source_url": (
            "https://www.sciencedirect.com/science/article/pii/"
            "S1569190X15000131"
        ),
        "access_status": "PRIMARY_PUBLISHER_ABSTRACT_AND_SECTION_SNIPPETS",
        "primary_evidence": (
            "The publisher abstract and visible sections isolate a conveyor merge "
            "as a bottleneck and study both its control algorithm and physical "
            "layout using simulation and bag throughput. Full subscription text "
            "was not relied on."
        ),
        "applicable_problem": (
            "Calibrating merge service calendars and explaining congestion where "
            "two directed inflows compete for one collector resource."
        ),
        "transferable_mechanism": (
            "Represent merge control and merge geometry as separate variables; "
            "measure offered input, merge busy time, queue formation, and output "
            "throughput near saturation."
        ),
        "conflicting_assumptions": (
            "The studied single-merge conveyor geometry, bag spacing, controllers, "
            "and rates are not the protected map's 23 inferred merges. This "
            "project has no authoritative physical headway/buffer calibration."
        ),
        "target_module": (
            "R4 merge service calendar, merge inventory, utilization telemetry, "
            "and backlog-drain reporting"
        ),
        "required_ab": (
            "C R2 versus R4 with identical direction/headway and policy; vary "
            "only merge calendar semantics, first on real-map motifs then the "
            "size ladder."
        ),
        "prohibited_overclaim": (
            "Do not copy numerical headway, spacing, layout, or capacity values; "
            "do not claim physical calibration or airport-wide capacity from a "
            "single-merge mechanism."
        ),
    },
    {
        "order": 7,
        "literature_id": "TASSIULAS_EPHREMIDES_1992",
        "citation": (
            "Tassiulas and Ephremides, Stability Properties of Constrained "
            "Queueing Systems and Scheduling Policies for Maximum Throughput in "
            "Multihop Radio Networks, IEEE TAC 1992"
        ),
        "year": 1992,
        "identifier": "10.1109/9.182479",
        "primary_source_url": (
            "https://drum.lib.umd.edu/items/"
            "571fda52-aefb-4497-9a2d-69d8c7c907b9"
        ),
        "access_status": "FULL_TEXT_INSTITUTIONAL_REPOSITORY",
        "primary_evidence": (
            "The paper defines stability regions for constrained queues with "
            "interdependent servers and selects feasible simultaneous server "
            "activations from global queue state. Its maximum-throughput result "
            "uses centralized decisions, slotted time, and infinite buffers."
        ),
        "applicable_problem": (
            "Understanding why a queue differential can inform local routing and "
            "why stability must be measured under sustained arrivals."
        ),
        "transferable_mechanism": (
            "Use upstream-minus-downstream queue pressure as a diagnostic/control "
            "component; define feasible resource activations; evaluate queue "
            "stability region empirically via injection, backlog, and drain."
        ),
        "conflicting_assumptions": (
            "This runtime has continuous event time, directed travel resources, "
            "finite/unknown buffers, deadlines, faults, local bounded state, "
            "credit admission, and no centralized maximum-weight activation over "
            "the whole network."
        ),
        "target_module": (
            "Goal-conditioned differential pressure, expiring-credit admission, "
            "and stability/backlog telemetry"
        ),
        "required_ab": (
            "Stage G C0-C6 with pressure, credit, and PIBT introduced separately; "
            "measure arrival/departure rates, source/network backlog, and drain."
        ),
        "prohibited_overclaim": (
            "A bounded local differential term is not the paper's "
            "throughput-optimal policy. Do not claim a maximal stability region "
            "without matching its model, feasible schedules, and proof."
        ),
    },
    {
        "order": 8,
        "literature_id": "VARAIYA_MAX_PRESSURE_2013",
        "citation": (
            "Varaiya, Max Pressure Control of a Network of Signalized "
            "Intersections, Transportation Research Part C 36, 2013"
        ),
        "year": 2013,
        "identifier": "10.1016/j.trc.2013.08.014",
        "primary_source_url": (
            "https://www.sciencedirect.com/science/article/pii/"
            "S0968090X13001782"
        ),
        "access_status": "PRIMARY_PUBLISHER_ABSTRACT_ONLY",
        "primary_evidence": (
            "The publisher abstract models separate turn queues as infinite point "
            "queues in a store-and-forward network with iid arrivals, fixed turn "
            "ratios, iid saturation rates, and selectable compatible stages. "
            "Under those assumptions, adjacent-queue max pressure stabilizes "
            "interior feasible demand."
        ),
        "applicable_problem": (
            "Choosing among competing local movements at a junction using "
            "destination/turn-conditioned upstream and downstream congestion."
        ),
        "transferable_mechanism": (
            "Condition queues by movement/goal; subtract downstream scheduled "
            "incoming work; combine with service rate; choose only among "
            "physically compatible local actions."
        ),
        "conflicting_assumptions": (
            "Bags do not follow fixed stochastic turn ratios; queues are not "
            "infinite point queues; service is timed and faultable; deadlines and "
            "source admission matter; the controller does not select the paper's "
            "traffic-signal stage set."
        ),
        "target_module": (
            "Q(node, goal), age, scheduled incoming, local service-rate estimate, "
            "and differential-pressure scorer term"
        ),
        "required_ab": (
            "G C0/C1/C2/C3 first, then C4/C5/C6; compare destination-conditioned "
            "differential against absolute queue penalty under identical loads."
        ),
        "prohibited_overclaim": (
            "Local differential pressure is not automatically max-pressure or "
            "throughput-optimal. Do not transfer the theorem without iid/turn/"
            "service/storage/stage assumptions and a proof."
        ),
    },
    {
        "order": 9,
        "literature_id": "SORENSEN_DRL_BHS_2020",
        "citation": (
            "Sørensen, Nielsen, and Karstoft, Routing in Congested Baggage "
            "Handling Systems Using Deep Reinforcement Learning, Integrated "
            "Computer-Aided Engineering 27(2), 2020"
        ),
        "year": 2020,
        "identifier": "10.3233/ICA-190613",
        "primary_source_url": (
            "https://journals.sagepub.com/doi/10.3233/ICA-190613"
        ),
        "access_status": "PRIMARY_PUBLISHER_ABSTRACT_ONLY",
        "primary_evidence": (
            "The publisher abstract reports a single global Dueling-DQN agent "
            "with prioritized replay and multi-action output, trained/tested in "
            "three simple but functionally realistic cyclic BHS simulations over "
            "a broad load distribution."
        ),
        "applicable_problem": (
            "Testing whether a learned policy can rank congestion-aware routes "
            "better than static or dynamic shortest-path rules."
        ),
        "transferable_mechanism": (
            "Train across a load distribution, compare with strong rule baselines, "
            "and evaluate closed-loop deadlocks, throughput, and delivery time "
            "rather than offline accuracy alone."
        ),
        "conflicting_assumptions": (
            "The paper's controller is a single global multi-action DQN, whereas "
            "this project requires lightweight one-step local decisions, bounded "
            "state, zero global scan, an independent safety shield, and the fixed "
            "real map. Its simulated environments do not establish airport scope."
        ),
        "target_module": (
            "Stage-I candidate ranking training/evaluation protocol only; not the "
            "physical shield or PIBT coordinator"
        ),
        "required_ab": (
            "After all I gates, compare v3 linear/tiny-MLP candidates with S0/S3/"
            "S4 in a closed loop at 144/512/2048/8192 before full 1x."
        ),
        "prohibited_overclaim": (
            "Do not authorize PPO/MAPPO/full RL, claim real-airport transfer, "
            "claim deadlock elimination, or equate global DQN evidence with a "
            "legal local scorer."
        ),
    },
    {
        "order": 10,
        "literature_id": "ZANG_ONLINE_GGO_2025",
        "citation": (
            "Zang et al., Online Guidance Graph Optimization for Lifelong "
            "Multi-Agent Path Finding, AAAI 2025"
        ),
        "year": 2025,
        "identifier": "10.1609/aaai.v39i14.33614",
        "primary_source_url": (
            "https://ojs.aaai.org/index.php/AAAI/article/download/33614/35769"
        ),
        "access_status": "FULL_TEXT_PRIMARY",
        "primary_evidence": (
            "The paper learns an online policy that updates directed guidance "
            "edge/action costs from real-time traffic and integrates it with PIBT "
            "or Guided-PIBT. LMAPF throughput is goals reached per timestep; "
            "benefit varies by map and dynamic task distribution."
        ),
        "applicable_problem": (
            "Adapting local route preference when congestion locations move with "
            "time-varying task banks."
        ),
        "transferable_mechanism": (
            "Separate learned edge ranking/guidance from collision coordination; "
            "condition evaluation on dynamic demand; measure closed-loop "
            "throughput and compute overhead."
        ),
        "conflicting_assumptions": (
            "The paper updates a map-wide guidance graph and may use guide paths/"
            "LNS, while this runtime forbids global scans and future paths and "
            "limits the learned model to legal bounded local features. Its maps, "
            "tasks, agent dynamics, and throughput denominator differ."
        ),
        "target_module": (
            "Stage-I lightweight local scorer feature/ranking research; PIBT and "
            "physical shield remain separate owners"
        ),
        "required_ab": (
            "Only after I gates: static local scorer versus bounded online local "
            "features, identical PIBT/resource/admission; dynamic-bank held-out "
            "closed-loop tests."
        ),
        "prohibited_overclaim": (
            "Do not claim the reported throughput improvements on map2, import a "
            "global guidance graph/LNS into the final runtime, or treat learned "
            "guidance as collision safety."
        ),
    },
    {
        "order": 11,
        "literature_id": "IATA_ADRM_12",
        "citation": (
            "International Air Transport Association, Airport Development "
            "Reference Manual, 12th edition"
        ),
        "year": 2022,
        "identifier": "IATA_ADRM_12TH_EDITION",
        "primary_source_url": (
            "https://www.iata.org/en/publications/manuals/"
            "airport-development-reference-manual/"
        ),
        "access_status": "OFFICIAL_SCOPE_PAGE_ONLY",
        "primary_evidence": (
            "IATA's official scope page states that ADRM covers airport planning "
            "and capacity-demand balance, with expanded sections on peak "
            "forecasting, design-day flight schedules, demand-capacity "
            "calculations, and a BHS section. The paid manual text was not used."
        ),
        "applicable_problem": (
            "Defining the represented airport/terminal/BHS subsystem and selecting "
            "design demand before any capacity claim."
        ),
        "transferable_mechanism": (
            "Make peak/design-day and subsystem demand-capacity analysis explicit; "
            "tie any scale factor to represented-system checked bags, not an "
            "arbitrary agent multiplier."
        ),
        "conflicting_assumptions": (
            "The fixed case's airport, terminal, local/transfer scope, parallel "
            "BHS share, and day type are unknown. The public scope page supplies "
            "no case-specific numbers."
        ),
        "target_module": (
            "G4IRSF12-K airport-scope/demand-calibration protocol and Phase-L "
            "capacity frontier"
        ),
        "required_ab": (
            "No algorithm A/B. Compare immutable 1.0 historical-day descriptor "
            "with a future case-specific calibrated design-day profile only after "
            "all scope inputs and J gates pass."
        ),
        "prohibited_overclaim": (
            "Do not claim an ADRM-prescribed 1.1/1.25/1.5 multiplier, infer the "
            "airport scope, or treat whole-airport annual passengers as "
            "represented BHS design-day bags."
        ),
    },
    {
        "order": 12,
        "literature_id": "ACRP_REPORT_82",
        "citation": (
            "National Academies / ACRP Report 82, Preparing Peak Period and "
            "Operational Profiles—Guidebook, 2013"
        ),
        "year": 2013,
        "identifier": "10.17226/22646",
        "primary_source_url": (
            "https://www.nationalacademies.org/publications/22646"
        ),
        "access_status": "OFFICIAL_REPORT_SUMMARY_AND_TOOLBOX_DESCRIPTION",
        "primary_evidence": (
            "The official report page describes converting annual forecasts to "
            "daily/hourly peak profiles with separate operations and passenger "
            "modules, using user-defined design-day parameters. It supports "
            "lead/lag factors and scenario analysis; defaults are not evidence "
            "for this airport."
        ),
        "applicable_problem": (
            "Turning a defensible annual/design-day forecast into hourly and "
            "peak-period demand without flattening flight banks."
        ),
        "transferable_mechanism": (
            "Publish clock-hour and rolling-window profiles, define design-day "
            "parameters before scaling, retain lead/lag or baggage dwell "
            "distributions, and run uncertainty scenarios."
        ),
        "conflicting_assumptions": (
            "The current input has one historical schedule day but lacks airport "
            "identity, annual case-period activity, design-day definition, "
            "passenger-to-bag conversion, and terminal/subsystem allocation."
        ),
        "target_module": (
            "Demand calibration inputs, uncertainty envelope, temporal-shape "
            "audit, and future workload manifest validation"
        ),
        "required_ab": (
            "Future workload audit must compare baseline versus candidate hourly/"
            "5/15/60-minute shares and lead/dwell distributions before runtime; "
            "then Phase L advances one scale at a time."
        ),
        "prohibited_overclaim": (
            "Do not use toolbox examples/defaults as airport facts, call 1.25 a "
            "design-day factor, or treat an annual average as peak demand."
        ),
    },
    {
        "order": 13,
        "literature_id": "ACRP_REPORT_163",
        "citation": (
            "National Academies / ACRP Research Report 163, Guidebook for "
            "Preparing and Using Airport Design Day Flight Schedules, 2016"
        ),
        "year": 2016,
        "identifier": "10.17226/23692",
        "primary_source_url": (
            "https://nap.nationalacademies.org/read/23692/chapter/9"
        ),
        "access_status": "FULL_TEXT_OFFICIAL_CHAPTER",
        "primary_evidence": (
            "The official chapter applies flight-by-flight DDFS data to "
            "time-of-day/facility-specific profiles. Activity-level adjustment is "
            "appropriate only when profile shape is expected to remain stable. "
            "Departure-facility peaks require airport-specific show-up lead "
            "distributions, typically obtained from passenger surveys."
        ),
        "applicable_problem": (
            "Building a traceable design-day baggage profile by terminal/facility "
            "and relating schedule time to actual early-arrival/EBS demand."
        ),
        "transferable_mechanism": (
            "Preserve flight-bank shape; keep facility scope explicit; audit "
            "lead/dwell distributions; derive baggage make-up demand from a "
            "case-specific DDFS rather than uniform time compression."
        ),
        "conflicting_assumptions": (
            "The raw input lacks flight IDs, named terminal/facility allocation, "
            "passenger survey show-up curves, and proof that scaled activity "
            "preserves profile shape. Airport scope remains unknown."
        ),
        "target_module": (
            "G4IRSF12-K design-day numerator and shape protocol; future "
            "original_rule_replay_scaled_input drift audit"
        ),
        "required_ab": (
            "Before any Phase-L run, compare candidate versus 1.0 flight-bank/"
            "hourly shape and deadline/EBS dwell; reject shape drift before "
            "measuring capacity."
        ),
        "prohibited_overclaim": (
            "Do not call a resampled task stream a DDFS, infer airport-specific "
            "show-up distributions, or declare a finite realistic scale envelope "
            "while airport/terminal/subsystem inputs are missing."
        ),
    },
)


def validate_rows(rows: Sequence[Mapping[str, Any]] = LITERATURE_ROWS) -> list[str]:
    errors: list[str] = []
    ids = tuple(str(row.get("literature_id", "")) for row in rows)
    if ids != EXPECTED_IDS:
        errors.append(f"literature order/coverage mismatch: {ids!r}")
    if len(set(ids)) != len(ids):
        errors.append("duplicate literature_id")

    for expected_order, row in enumerate(rows, start=1):
        row_id = str(row.get("literature_id", ""))
        if row.get("order") != expected_order:
            errors.append(f"{row_id}: order mismatch")
        for field in FIELDS:
            value = row.get(field)
            if value is None or str(value).strip() == "":
                errors.append(f"{row_id}: missing {field}")
        if row.get("identifier") != EXPECTED_IDENTIFIERS.get(row_id):
            errors.append(f"{row_id}: identifier mismatch")
        parsed = urlparse(str(row.get("primary_source_url", "")))
        if parsed.scheme != "https":
            errors.append(f"{row_id}: primary source must use https")
        if parsed.hostname not in ALLOWED_PRIMARY_HOSTS:
            errors.append(f"{row_id}: non-primary/unapproved host {parsed.hostname}")
        access = str(row.get("access_status", ""))
        if not (
            access.startswith("FULL_TEXT")
            or access.startswith("PRIMARY_")
            or access.startswith("OFFICIAL_")
            or access == "METADATA_ONLY"
        ):
            errors.append(f"{row_id}: invalid access status {access}")

    combined_boundary = " ".join(
        str(row.get("prohibited_overclaim", "")) for row in rows
    ).lower()
    if "classic pibt completeness" not in combined_boundary:
        errors.append("missing classic PIBT completeness boundary")
    if "throughput-optimal" not in combined_boundary:
        errors.append("missing local differential throughput-optimality boundary")
    if "airport" not in combined_boundary or "scope" not in combined_boundary:
        errors.append("missing airport-scope boundary")
    return errors


def _csv_text(rows: Sequence[Mapping[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _markdown_link(row: Mapping[str, Any]) -> str:
    return f"[primary source]({row['primary_source_url']})"


def build_report(rows: Sequence[Mapping[str, Any]] = LITERATURE_ROWS) -> str:
    errors = validate_rows(rows)
    if errors:
        raise ValueError("; ".join(errors))

    summary_rows = [
        (
            row["order"],
            row["literature_id"],
            _markdown_link(row),
            row["access_status"],
            row["target_module"],
        )
        for row in rows
    ]
    summary = [
        "| # | ID | Primary source | Access | Project mapping |",
        "| --- | --- | --- | --- | --- |",
        *[
            "| " + " | ".join(str(value) for value in values) + " |"
            for values in summary_rows
        ],
    ]

    lines = [
        "# G4IRSF12 Literature-to-Design Audit",
        "",
        f"Date: {PHASE_DATE}",
        "",
        "coverage: `13/13 COMPLETE`",
        "source_policy: `PRIMARY_OR_OFFICIAL_ONLY`",
        "implementation_claim: `DESIGN_INPUT_NOT_ALGORITHM_PASS`",
        "",
        "## Executive boundaries",
        "",
        (
            "- The protected map is directed and its audit reports 31 directed "
            "SCCs plus 11 weak-projection bridges. It does not satisfy the "
            "classic PIBT adjacent-edge simple-cycle/biconnected premise. The "
            "implemented mechanism remains **PIBT-inspired bounded local "
            "coordination**, without a completeness/deadlock-freedom claim."
        ),
        (
            "- Tassiulas–Ephremides and Varaiya prove stability/maximum-throughput "
            "results under specific queue, arrival, service, storage, feasible-"
            "schedule, and information assumptions. A bounded local "
            "destination-conditioned differential term in this runtime is **not "
            "throughput-optimal** by citation."
        ),
        (
            "- IATA/ACRP prescribe scoped peak/design-day analysis, not a universal "
            "multiplier. This case's airport, terminal, local/transfer scope, "
            "parallel BHS share, and day type remain unknown; no finite realistic "
            "scale envelope follows from these sources."
        ),
        (
            "- Publisher pages with only an original abstract or visible section "
            "snippets are labelled as such. No inaccessible detail was filled "
            "from reviews, aggregators, or secondary summaries."
        ),
        "",
        "## Coverage",
        "",
        *summary,
        "",
        "## Item-by-item transfer contract",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"### {row['order']}. {row['literature_id']}",
                "",
                f"**Citation:** {row['citation']}. Identifier: "
                f"`{row['identifier']}`. {_markdown_link(row)}.",
                "",
                f"**Access:** `{row['access_status']}`.",
                "",
                f"**Primary evidence:** {row['primary_evidence']}",
                "",
                f"**Applicable problem:** {row['applicable_problem']}",
                "",
                f"**Transferable mechanism:** {row['transferable_mechanism']}",
                "",
                f"**Conflicting assumptions:** {row['conflicting_assumptions']}",
                "",
                f"**Target module:** `{row['target_module']}`.",
                "",
                f"**Required A/B:** {row['required_ab']}",
                "",
                f"**Prohibited overclaim:** {row['prohibited_overclaim']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Decision",
            "",
            (
                "These sources justify controlled mechanisms and measurement "
                "contracts, not promotion. Runtime promotion still requires the "
                "predeclared real-map A/B gates, full original-scale completion, "
                "tail/backlog/fault evidence, and the independent airport-demand "
                "calibration gate."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def render_outputs(
    rows: Sequence[Mapping[str, Any]] = LITERATURE_ROWS,
) -> dict[Path, str]:
    errors = validate_rows(rows)
    if errors:
        raise ValueError("; ".join(errors))
    return {
        TABLE_PATH: _csv_text(rows),
        REPORT_PATH: build_report(rows),
    }


def write_outputs(root: Path, outputs: Mapping[Path, str]) -> None:
    for relative_path, content in outputs.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def check_outputs(root: Path, outputs: Mapping[Path, str]) -> list[str]:
    errors: list[str] = []
    for relative_path, expected in outputs.items():
        path = root / relative_path
        if not path.exists():
            errors.append(f"missing {relative_path.as_posix()}")
            continue
        if path.read_text(encoding="utf-8") != expected:
            errors.append(f"stale {relative_path.as_posix()}")
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    outputs = render_outputs()
    if args.write:
        write_outputs(ROOT, outputs)
        action = "published"
    else:
        errors = check_outputs(ROOT, outputs)
        if errors:
            raise ValueError("; ".join(errors))
        action = "validated"
    print(
        f"{action}: literature_rows={len(LITERATURE_ROWS)} "
        "coverage=13/13 source_policy=PRIMARY_OR_OFFICIAL_ONLY"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
