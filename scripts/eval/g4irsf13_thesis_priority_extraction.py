"""Publish the audited G4IRSF13 thesis/legacy control extraction.

The committed outputs are deterministic and are regenerated from:

* visually audited facts from the user-supplied thesis (identified by SHA-256);
* byte-identified, read-only legacy Java/arc sources;
* the protected real ``map2.json`` and ``inputdata.jsonl``.

The thesis and legacy source files are intentionally not copied into Git.  The
default validation path therefore checks their recorded provenance and validates
all graph/task facts against the committed protected inputs.  ``--verify-external``
adds a fail-closed byte/snippet audit when the original local sources are
available.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from functools import cmp_to_key
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
PHASE_DATE = "2026-07-27"

MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
THESIS_REPORT_PATH = Path(
    "outputs/reports/g4irsf13_thesis_priority_extraction.md"
)
FORMULA_TABLE_PATH = Path(
    "outputs/tables/g4irsf13_thesis_priority_formula.csv"
)
LOCAL_DESIGN_REPORT_PATH = Path(
    "outputs/reports/g4irsf13_localized_legacy_control_design.md"
)
EBS_AUDIT_TABLE_PATH = Path(
    "outputs/tables/g4irsf13_ebs_goal_lifecycle_audit.csv"
)
LITERATURE_REPORT_PATH = Path(
    "outputs/reports/g4irsf13_literature_to_design_matrix.md"
)

MAP_RAW_SHA256 = (
    "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
)
MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
TASK_RAW_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
THESIS_SHA256 = (
    "37e61b8e4d67e56c0fa14c43b230be965e200106704363f06b80a4e6a151e1aa"
)
LEGACY_SOURCE_SHA256 = {
    "src/RUN/Main.java": (
        "af7ba8f8224a480f61e4d4b010d0c6fcf5e8798cccfdf6f298d786ac053bf5af"
    ),
    "src/App/Tasks.java": (
        "dd4505e495fd3c0fa737923dca83c9d404fc3b1e3a7ce979e7dd384a57d0948b"
    ),
    "src/App/ICS_PathFinding.java": (
        "a367fd8e79aba7b3d23b71fc9b4d01f76dd67f291f008401d676ffcbcf53d52a"
    ),
    "arc.txt": (
        "1348553fc9a7f0bb6aaa3f823a151502b7fc6beac55c3f6eeb92a59a3758811c"
    ),
}

DEFAULT_THESIS_PDF = (
    ROOT / ".local_archives/g4irsf13/pdfs/thesis.pdf"
)
DEFAULT_LEGACY_ROOT = Path(
    r"C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料"
    r"\ICS项目\代码-ICSsimulation"
)

EXPECTED_SEGMENT_COUNT = 43_603
EXPECTED_BAG_COUNT = 28_506
EXPECTED_LEG_COUNTS = {
    "direct": 13_409,
    "storage_in": 15_097,
    "storage_out": 15_097,
}

FORMULA_FIELDS = (
    "record_id",
    "source_file_page",
    "printed_page",
    "source_section",
    "exact_expression",
    "source_meaning",
    "localized_runtime_use",
    "non_transferable_boundary",
)

FORMULA_ROWS: tuple[dict[str, str], ...] = (
    {
        "record_id": "equation_4_2",
        "source_file_page": "39",
        "printed_page": "25",
        "source_section": "4.3",
        "exact_expression": (
            "r_k = p1*T_disrupt_k*I_disrupt_k + "
            "p2*T_conflict_k*I_conflict_k + "
            "p3*T_departure_k + p4*T_wait_k"
        ),
        "source_meaning": (
            "Unified task-ranking score. I_disrupt and I_conflict are binary "
            "task-class indicators; the four T terms are defined by 4.3-4.5 "
            "and the preceding disruption definition."
        ),
        "localized_runtime_use": (
            "Q1 preserves the stated task-class ordering and uses only bounded "
            "current-junction observations; Q2/Q3 retain slack and age."
        ),
        "non_transferable_boundary": (
            "The thesis gives only an ordinal weight relation, not numeric "
            "weights or a scale-normalization rule; the exact scalar score is "
            "therefore extracted but not silently calibrated."
        ),
    },
    {
        "record_id": "equation_4_3",
        "source_file_page": "40",
        "printed_page": "26",
        "source_section": "4.3",
        "exact_expression": "T_conflict_k = t_conflict_k - t",
        "source_meaning": (
            "Time from the current instant to the first conflict on the bag's "
            "future route."
        ),
        "localized_runtime_use": (
            "Replace future-route inspection with current next-edge contention "
            "only, and label the result a local projection."
        ),
        "non_transferable_boundary": (
            "No future route, teacher path, full A*, or global reservation "
            "lookup may be introduced to recreate t_conflict_k."
        ),
    },
    {
        "record_id": "equation_4_4",
        "source_file_page": "40",
        "printed_page": "26",
        "source_section": "4.3",
        "exact_expression": "T_departure_k = tau_k - t",
        "source_meaning": "Remaining time before the bag's flight departure.",
        "localized_runtime_use": (
            "Use current deadline slack from the bag record and current event "
            "time; smaller slack ranks earlier."
        ),
        "non_transferable_boundary": (
            "The deadline term cannot read a future route or future schedule."
        ),
    },
    {
        "record_id": "equation_4_5",
        "source_file_page": "40",
        "printed_page": "26",
        "source_section": "4.3",
        "exact_expression": "T_wait_k = t - t_k",
        "source_meaning": "Elapsed waiting/age since the task entered the BHS.",
        "localized_runtime_use": (
            "Use nonnegative local age as an anti-starvation tie component."
        ),
        "non_transferable_boundary": (
            "Age is a priority signal, not permission to bypass the physical "
            "shield, resource calendar, or atomic P2 validation."
        ),
    },
    {
        "record_id": "weight_relation",
        "source_file_page": "40",
        "printed_page": "26",
        "source_section": "4.3",
        "exact_expression": "p1 > p3 > p2 > p4",
        "source_meaning": (
            "The paper states disruption importance above departure, conflict, "
            "and waiting importance."
        ),
        "localized_runtime_use": (
            "Preserve the stated precedence lexicographically when numeric "
            "weights are unavailable."
        ),
        "non_transferable_boundary": (
            "Do not invent numeric p values or claim an exact scalar "
            "reproduction without a declared calibration."
        ),
    },
    {
        "record_id": "stated_order_and_tie",
        "source_file_page": "40",
        "printed_page": "26",
        "source_section": "4.3",
        "exact_expression": (
            "fault-affected > nearer departure > conflict > new; "
            "first-in-first-out tie"
        ),
        "source_meaning": (
            "The prose orders disrupted tasks first, near-departure tasks "
            "second, future-conflict tasks third, new tasks last, and states "
            "first-in-first-out."
        ),
        "localized_runtime_use": (
            "Use local fault generation, deadline slack, current contention, "
            "entry order, then stable ID."
        ),
        "non_transferable_boundary": (
            "Current contention is not the thesis's full-future-route conflict "
            "test, so results must be called a bounded local projection."
        ),
    },
)

ARC_1_TO_8: tuple[tuple[int, int, int, float], ...] = (
    (1, 0, 6, 8.0),
    (2, 1, 7, 12.0),
    (3, 2, 9, 9.0),
    (4, 3, 16, 4.0),
    (5, 4, 17, 9.0),
    (6, 5, 19, 4.0),
    (7, 6, 8, 7.0),
    (8, 6, 12, 25.0),
)

THESIS_FAULT_SCENARIOS: tuple[
    tuple[str, tuple[int, ...], int, float], ...
] = (
    ("single_1", (1,), 1, 1.00),
    ("single_2", (2,), 7, 0.88),
    ("single_3", (3,), 5, 1.00),
    ("single_4", (4,), 15, 0.95),
    ("single_5", (5,), 24, 0.97),
    ("single_6", (6,), 7, 0.96),
    ("single_7", (7,), 1, 1.00),
    ("single_8", (8,), 7, 0.99),
    ("pair_1_7", (1, 7), 2, 1.00),
    ("pair_2_4", (2, 4), 22, 0.76),
    ("pair_3_5", (3, 5), 36, 0.66),
    ("pair_4_5", (4, 5), 54, 0.00),
    ("pair_5_7", (5, 7), 12, 0.48),
    ("triple_2_4_6", (2, 4, 6), 36, 0.26),
    ("triple_3_5_8", (3, 5, 8), 51, 0.05),
    ("triple_4_6_7", (4, 6, 7), 30, 0.26),
)

PRIORITY_VARIANTS: tuple[dict[str, str], ...] = (
    {
        "variant": "Q0",
        "name": "current_f2",
        "ordered_components": "frozen current F2 priority",
        "purpose": "Control; no priority change.",
        "claim_boundary": "Must remain bitwise/deterministically unchanged.",
    },
    {
        "variant": "Q1",
        "name": "thesis_exact_local_projection",
        "ordered_components": (
            "fault-affected desc; slack asc; current-contention desc; "
            "entry-sequence asc; stable-id asc"
        ),
        "purpose": (
            "Preserve the thesis's stated class order and FIFO tie rule using "
            "only current bounded observations."
        ),
        "claim_boundary": (
            "Local contention replaces future-route conflict; Q1 is not a "
            "numeric reproduction of equation 4.2."
        ),
    },
    {
        "variant": "Q2",
        "name": "thesis_type_slack_aging",
        "ordered_components": (
            "task-type desc; slack asc; age desc; current-contention desc; "
            "stable-id asc"
        ),
        "purpose": (
            "Ablate task class, deadline slack, and anti-starvation aging."
        ),
        "claim_boundary": (
            "No future route, global task list, or invented thesis weights."
        ),
    },
    {
        "variant": "Q3",
        "name": "fault_slack_age_stable_id",
        "ordered_components": (
            "fault-generation desc; slack asc; age desc; stable-id asc"
        ),
        "purpose": (
            "Smallest deterministic control rule for repair re-entry and "
            "deadline/fairness interaction."
        ),
        "claim_boundary": (
            "Stable ID is a deterministic final tie-break, not a performance "
            "feature."
        ),
    },
)

LITERATURE_FIELDS = (
    "literature_id",
    "citation",
    "identifier",
    "primary_source",
    "access_status",
    "transferable_mechanism",
    "conflicting_assumption",
    "target_module",
    "required_ab",
    "prohibited_overclaim",
)

LITERATURE_ROWS: tuple[dict[str, str], ...] = (
    {
        "literature_id": "THESIS_FENG_2021",
        "citation": (
            "Feng Ruchen, Dynamic Route Planning Method for an Airport "
            "Baggage Handling System Based on the Internet of Things"
        ),
        "identifier": f"local-pdf-sha256:{THESIS_SHA256}",
        "primary_source": "user-supplied thesis PDF",
        "access_status": "VISUALLY_AUDITED_LOCAL_PRIMARY",
        "transferable_mechanism": (
            "Task-list lifecycle; fault/new/conflict classes; slack and age; "
            "BTI/DDI separation; affected-task repair re-entry."
        ),
        "conflicting_assumption": (
            "The thesis controller performs HCA* planning and inspects saved "
            "future routes/reservations."
        ),
        "target_module": (
            "Q1-Q3 local priority, local fault overlay, affected-bag lifecycle"
        ),
        "required_ab": (
            "Q0-Q3 isolation; B2 legacy-order one-step diagnostic; fault "
            "physical-shield-only versus local DDI/BTI policy."
        ),
        "prohibited_overclaim": (
            "Do not migrate HCA*, complete future routes, global reservations, "
            "or the thesis's reported success rates as new-runtime results."
        ),
    },
    {
        "literature_id": "PIBT_IJCAI_2019",
        "citation": (
            "Okumura et al., Priority Inheritance with Backtracking for "
            "Iterative Multi-agent Path Finding, IJCAI 2019"
        ),
        "identifier": "10.24963/ijcai.2019/76",
        "primary_source": "https://www.ijcai.org/proceedings/2019/0076.pdf",
        "access_status": "FULL_TEXT_PRIMARY",
        "transferable_mechanism": (
            "Unique priorities, local priority inheritance, valid/invalid "
            "backtracking, and one-step coordination."
        ),
        "conflicting_assumption": (
            "Finite arrival requires every adjacent pair to lie on a simple "
            "cycle of length at least three; real map2 has 11 weak-projection "
            "bridges and continuous-time directed resources."
        ),
        "target_module": "bounded local P2 ownership/prepare/validate/commit",
        "required_ab": "P0/P1/P2/P3/P4 depth and matched-contention A/B.",
        "prohibited_overclaim": (
            "Call it PIBT-inspired bounded local coordination; do not claim "
            "classic PIBT completeness or deadlock freedom on map2."
        ),
    },
    {
        "literature_id": "PIBT_PREFERENCE_SOCS_2025",
        "citation": (
            "Okumura and Nagai, Lightweight and Effective Preference "
            "Construction in PIBT for Large-Scale MAPF, SoCS 2025"
        ),
        "identifier": "10.1609/socs.v18i1.35982",
        "primary_source": (
            "https://ojs.aaai.org/index.php/SOCS/article/view/35982"
        ),
        "access_status": "FULL_TEXT_PRIMARY",
        "transferable_mechanism": (
            "Local dodge tie-break and repeated-run regret as lightweight "
            "preference components."
        ),
        "conflicting_assumption": (
            "The paper studies MAPF agents and offline/repeated PIBT runs, not "
            "timed conveyor bags with one directed resource commit."
        ),
        "target_module": "bounded P2 candidate preference only",
        "required_ab": (
            "Current versus dodge versus local-regret versus combined on a "
            "matched real contention cohort."
        ),
        "prohibited_overclaim": (
            "Do not transfer reported MAPF percentage gains or add multi-step "
            "routes; any regret feature must be bounded and local."
        ),
    },
    {
        "literature_id": "ONLINE_GGO_AAAI_2025",
        "citation": (
            "Zang et al., Online Guidance Graph Optimization for Lifelong "
            "Multi-Agent Path Finding, AAAI 2025"
        ),
        "identifier": "10.1609/aaai.v39i14.33614",
        "primary_source": (
            "https://ojs.aaai.org/index.php/AAAI/article/view/33614"
        ),
        "access_status": "FULL_TEXT_PRIMARY",
        "transferable_mechanism": (
            "Combine adaptive traffic guidance with a rule-based PIBT safety/"
            "coordination layer and test distribution change."
        ),
        "conflicting_assumption": (
            "Its learned object is a guidance graph for LMAPF; this runtime "
            "forbids global guidance scans and future path storage."
        ),
        "target_module": "clipped bounded learned residual over frozen scorer",
        "required_ab": (
            "Frozen scorer versus residual under identical local observations, "
            "plus distribution-shift slices."
        ),
        "prohibited_overclaim": (
            "Do not copy a full guidance graph or claim the published LMAPF "
            "improvements on this BHS."
        ),
    },
    {
        "literature_id": "WINC_MAPF_AAAI_2025",
        "citation": (
            "Veerapaneni et al., Windowed MAPF with Completeness Guarantees, "
            "AAAI 2025"
        ),
        "identifier": "10.1609/aaai.v39i22.34499",
        "primary_source": (
            "https://ojs.aaai.org/index.php/AAAI/article/view/34499"
        ),
        "access_status": "FULL_TEXT_PRIMARY",
        "transferable_mechanism": (
            "Treat single-step myopia, deadlock, livelock, and heuristic "
            "updates as explicit diagnostic concerns."
        ),
        "conflicting_assumption": (
            "The completeness framework uses joint configurations, agent "
            "groups, and an optimal MAPF solver; SS-CBS is still CBS."
        ),
        "target_module": "offline deadlock/livelock diagnostics only",
        "required_ab": (
            "Bounded local priority/regret controls on real motifs and the size "
            "ladder, without importing CBS."
        ),
        "prohibited_overclaim": (
            "Do not run runtime CBS or claim WinC-MAPF completeness for this "
            "directed, timed, reservation-depth-one system."
        ),
    },
    {
        "literature_id": "TARAU_ROUTE_CHOICE_2009",
        "citation": (
            "Tarau, De Schutter, and Hellendoorn, Route Choice Control of "
            "Automated Baggage Handling Systems, 2009"
        ),
        "identifier": "10.3141/2106-09",
        "primary_source": (
            "https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_011.pdf"
        ),
        "access_status": "FULL_TEXT_AUTHOR_MANUSCRIPT",
        "transferable_mechanism": (
            "Junction-owned event decisions and explicit quality/computation "
            "comparison between local heuristics and prediction."
        ),
        "conflicting_assumption": (
            "DCV switches, preferred route sets, and predictive horizons do "
            "not match this fixed conveyor graph and one-next-edge contract."
        ),
        "target_module": "event-junction local observation and scorer boundary",
        "required_ab": "Q variants with resource/P2/scorer controls fixed.",
        "prohibited_overclaim": (
            "Do not call the local rule MPC-equivalent or import full predictive "
            "routes."
        ),
    },
    {
        "literature_id": "TARAU_DECENTRALIZED_2009",
        "citation": (
            "Tarau, De Schutter, and Hellendoorn, Decentralized Route Choice "
            "Control of Automated Baggage Handling Systems, IFAC 2009"
        ),
        "identifier": "10.3182/20090902-3-US-2007.0036",
        "primary_source": (
            "https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_031.pdf"
        ),
        "access_status": "FULL_TEXT_AUTHOR_MANUSCRIPT",
        "transferable_mechanism": (
            "Make local-only and bounded-neighbor information variants "
            "explicit and audit every information read."
        ),
        "conflicting_assumption": (
            "Decentralized MPC still predicts multiple bags and assumes "
            "low-level safety and DCV capacities."
        ),
        "target_module": "bounded local feature lineage and zero-global-scan audit",
        "required_ab": "Local-only versus bounded-neighbor residual.",
        "prohibited_overclaim": (
            "Do not call a neighbor summary decentralized without read-depth "
            "and scan counters."
        ),
    },
    {
        "literature_id": "TARAU_MODEL_BASED_2010",
        "citation": (
            "Tarau, De Schutter, and Hellendoorn, Model-Based Control for "
            "Route Choice in Automated Baggage Handling Systems, 2010"
        ),
        "identifier": "10.1109/TSMCC.2009.2036735",
        "primary_source": (
            "https://www.dcsc.tudelft.nl/~bdeschutter/pub/rep/09_048.pdf"
        ),
        "access_status": "FULL_TEXT_AUTHOR_MANUSCRIPT",
        "transferable_mechanism": (
            "Separate event control, physical safety, and policy; compare "
            "bounded local prediction with a cheap one-step heuristic."
        ),
        "conflicting_assumption": (
            "Enough carriers, endpoint capacity, DCV dynamics, and multi-step "
            "MPC are not this runtime's semantics."
        ),
        "target_module": "event loop, physical interlock, and local telemetry",
        "required_ab": "One-variable event/resource/policy isolation.",
        "prohibited_overclaim": (
            "Do not assume safety away or use this source to authorize global "
            "future planning."
        ),
    },
    {
        "literature_id": "JOHNSTONE_MERGE_2015",
        "citation": (
            "Johnstone, Creighton, and Nahavandi, Simulation-Based Baggage "
            "Handling System Merge Analysis, 2015"
        ),
        "identifier": "10.1016/j.simpat.2015.01.003",
        "primary_source": (
            "https://www.sciencedirect.com/science/article/pii/"
            "S1569190X15000131"
        ),
        "access_status": "PRIMARY_PUBLISHER_ABSTRACT_AND_SNIPPETS",
        "transferable_mechanism": (
            "Treat merge control and geometry separately; measure input, busy "
            "time, queue, and output near saturation."
        ),
        "conflicting_assumption": (
            "A studied merge's physical spacing/rate is not calibration for "
            "map2's 23 real directed merge nodes."
        ),
        "target_module": "merge-only credit and merge service telemetry",
        "required_ab": "C0 versus merge-only C7 on real merge motifs first.",
        "prohibited_overclaim": (
            "Do not copy physical capacity numbers or infer airport-wide "
            "capacity."
        ),
    },
    {
        "literature_id": "MAP_EXECUTION_UNCERTAINTY_SOCS_2024",
        "citation": (
            "Liu et al., Multi-Agent Path Execution with Uncertainty, SoCS "
            "2024"
        ),
        "identifier": "10.1609/socs.v17i1.31543",
        "primary_source": (
            "https://ojs.aaai.org/index.php/SOCS/article/view/31543"
        ),
        "access_status": "FULL_TEXT_PRIMARY",
        "transferable_mechanism": (
            "Validate concurrent actions online and keep execution safety "
            "separate from nominal planning."
        ),
        "conflicting_assumption": (
            "The method reasons about feasibility of remaining plans, while "
            "this final runtime stores no remaining route."
        ),
        "target_module": "P2 validate/commit and physical safety gate",
        "required_ab": "P2 atomicity/fault-between-prepare-and-commit tests.",
        "prohibited_overclaim": (
            "Do not import full-plan feasibility or call the one-step gate an "
            "implementation of the paper."
        ),
    },
    {
        "literature_id": "REALTIME_SIPP_SOCS_2024",
        "citation": (
            "Wild Thomas, Ruml, and Shimony, Real-time Safe Interval Path "
            "Planning, SoCS 2024"
        ),
        "identifier": "10.1609/socs.v17i1.31554",
        "primary_source": (
            "https://ojs.aaai.org/index.php/SOCS/article/view/31554"
        ),
        "access_status": "FULL_TEXT_PRIMARY",
        "transferable_mechanism": (
            "Bound decision time, commit the next action online, and expose "
            "time-dependent safety intervals."
        ),
        "conflicting_assumption": (
            "SIPP assumes known future obstacle trajectories and performs "
            "lookahead/search over safe-interval states."
        ),
        "target_module": "local resource-calendar feature and runtime budget audit",
        "required_ab": "Same policy with/without bounded calendar feature.",
        "prohibited_overclaim": (
            "Do not add SIPP/A* search, known future trajectories, or a "
            "complete-route commitment."
        ),
    },
)

ALLOWED_PRIMARY_HOSTS = {
    "www.ijcai.org",
    "ojs.aaai.org",
    "www.dcsc.tudelft.nl",
    "www.sciencedirect.com",
}

EBS_FIELDS = (
    "check_id",
    "status",
    "observed",
    "expected",
    "evidence",
    "control_contract",
    "claim_boundary",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_graph(root: Path = ROOT) -> dict[str, Any]:
    path = root / MAP_PATH
    if _sha256(path) != MAP_RAW_SHA256:
        raise ValueError("protected map2 raw SHA-256 mismatch")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_tasks(root: Path = ROOT) -> list[dict[str, Any]]:
    path = root / TASK_PATH
    if _sha256(path) != TASK_RAW_SHA256:
        raise ValueError("protected inputdata raw SHA-256 mismatch")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"task row {line_number} is not an object")
                rows.append(row)
    return rows


def _weak_projection_bridges(
    node_ids: Iterable[int],
    edges: Iterable[tuple[int, int]],
) -> tuple[tuple[int, int], ...]:
    adjacency = {int(node): set() for node in node_ids}
    for start, end in edges:
        adjacency[int(start)].add(int(end))
        adjacency[int(end)].add(int(start))

    timer = 0
    discovery: dict[int, int] = {}
    low: dict[int, int] = {}
    parent: dict[int, int] = {}
    bridges: set[tuple[int, int]] = set()

    def visit(node: int) -> None:
        nonlocal timer
        timer += 1
        discovery[node] = timer
        low[node] = timer
        for neighbor in sorted(adjacency[node]):
            if neighbor not in discovery:
                parent[neighbor] = node
                visit(neighbor)
                low[node] = min(low[node], low[neighbor])
                if low[neighbor] > discovery[node]:
                    bridges.add(tuple(sorted((node, neighbor))))
            elif parent.get(node) != neighbor:
                low[node] = min(low[node], discovery[neighbor])

    for node in sorted(adjacency):
        if node not in discovery:
            visit(node)
    return tuple(sorted(bridges))


def real_map_motifs(
    graph: Mapping[str, Any] | None = None,
) -> dict[str, tuple[Any, ...]]:
    """Return motif identities derived only from the protected real map2."""

    payload = dict(graph) if graph is not None else _load_graph()
    nodes = {
        int(row["location"]): row
        for row in payload["nodes"]
    }
    edges = tuple(
        (int(row["start"]), int(row["end"]))
        for row in payload["edges"]
    )
    indegree: Counter[int] = Counter(end for _, end in edges)
    outdegree: Counter[int] = Counter(start for start, _ in edges)
    return {
        "edges": edges,
        "merge_nodes": tuple(
            node for node in sorted(nodes) if indegree[node] > 1
        ),
        "split_nodes": tuple(
            node for node in sorted(nodes) if outdegree[node] > 1
        ),
        "weak_projection_bridges": _weak_projection_bridges(nodes, edges),
        "ebs_nodes": tuple(
            node
            for node in sorted(nodes)
            if node == 52 and int(nodes[node]["node_type"]) == 1
        ),
        "goal_nodes": tuple(int(node) for node in payload["end_nodes"]),
    }


def legacy_pass_time_compare(left: float, right: float) -> int:
    """Exact projection of Java ``(int)(left.pass_time-right.pass_time)``."""

    return int(float(left) - float(right))


def legacy_stable_pass_time_order(
    indexed_pass_times: Sequence[tuple[str, float]],
) -> tuple[str, ...]:
    """Apply the legacy comparator while retaining Java/Python stable ties."""

    def compare(
        left: tuple[str, float],
        right: tuple[str, float],
    ) -> int:
        return legacy_pass_time_compare(left[1], right[1])

    return tuple(
        item_id
        for item_id, _ in sorted(indexed_pass_times, key=cmp_to_key(compare))
    )


def localized_priority_key(
    variant: str,
    *,
    fault_affected: bool,
    deadline_slack_seconds: float,
    age_seconds: float,
    current_contention: bool,
    entry_sequence: int,
    stable_id: int,
    task_type_rank: int = 0,
    fault_generation: int = 0,
) -> tuple[float | int, ...]:
    """Return the documented deterministic local priority key.

    Lower tuples run first.  Q0 is deliberately excluded because its exact key
    remains owned by the frozen F2 runtime and must not be reimplemented here.
    """

    slack = float(deadline_slack_seconds)
    age = max(0.0, float(age_seconds))
    if not math.isfinite(slack) or not math.isfinite(age):
        raise ValueError("priority slack/age must be finite")
    if variant == "Q1":
        return (
            -int(bool(fault_affected)),
            slack,
            -int(bool(current_contention)),
            int(entry_sequence),
            int(stable_id),
        )
    if variant == "Q2":
        return (
            -int(task_type_rank),
            slack,
            -age,
            -int(bool(current_contention)),
            int(stable_id),
        )
    if variant == "Q3":
        return (
            -int(fault_generation),
            slack,
            -age,
            int(stable_id),
        )
    raise ValueError(f"unsupported localized priority variant {variant!r}")


def build_ebs_audit_rows(
    graph: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    nodes = {
        int(row["location"]): row
        for row in graph["nodes"]
    }
    edges = tuple(
        (int(row["start"]), int(row["end"]))
        for row in graph["edges"]
    )
    indegree: Counter[int] = Counter(end for _, end in edges)
    outdegree: Counter[int] = Counter(start for start, _ in edges)
    leg_counts = Counter(str(row["leg"]) for row in tasks)
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in tasks:
        grouped[int(row["task_id"])].append(row)

    split_groups = [
        rows
        for rows in grouped.values()
        if {str(row["leg"]) for row in rows}
        == {"storage_in", "storage_out"}
    ]
    direct_groups = [
        rows
        for rows in grouped.values()
        if {str(row["leg"]) for row in rows} == {"direct"}
    ]
    paired = all(
        len(rows) == 2
        and [str(row["leg"]) for row in rows]
        == ["storage_in", "storage_out"]
        and len({int(row["pallet_id"]) for row in rows}) == 1
        and len({float(row["original_entry_time"]) for row in rows}) == 1
        for rows in split_groups
    )
    storage_in_endpoint = all(
        int(row["goal"]) == 47
        for row in tasks
        if str(row["leg"]) == "storage_in"
    )
    storage_out_source = all(
        int(row["start"]) == 52
        for row in tasks
        if str(row["leg"]) == "storage_out"
    )
    release_exact = all(
        math.isclose(
            float(row["pass_time"]),
            float(row["std"]) - 2700.0,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        )
        for row in tasks
        if str(row["leg"]) == "storage_out"
    )
    goal_set = {int(node) for node in graph["end_nodes"]}
    terminal_goals = all(int(row["goal"]) in goal_set for row in tasks)

    def row(
        check_id: str,
        passed: bool,
        observed: Any,
        expected: Any,
        evidence: str,
        control_contract: str,
        claim_boundary: str,
    ) -> dict[str, str]:
        return {
            "check_id": check_id,
            "status": "PASS" if passed else "FAIL",
            "observed": str(observed),
            "expected": str(expected),
            "evidence": evidence,
            "control_contract": control_contract,
            "claim_boundary": claim_boundary,
        }

    return [
        row(
            "protected_map_identity",
            len(nodes) == 54 and len(edges) == 69,
            f"nodes={len(nodes)};edges={len(edges)};raw_sha256={MAP_RAW_SHA256}",
            "nodes=54;edges=69;frozen raw SHA-256",
            MAP_PATH.as_posix(),
            "All graph-dependent validation uses this real map.",
            "No generated, copied, enlarged, or hand-built graph is evidence.",
        ),
        row(
            "protected_task_identity",
            len(tasks) == EXPECTED_SEGMENT_COUNT
            and len(grouped) == EXPECTED_BAG_COUNT,
            f"segments={len(tasks)};raw_bags={len(grouped)}",
            f"segments={EXPECTED_SEGMENT_COUNT};raw_bags={EXPECTED_BAG_COUNT}",
            TASK_PATH.as_posix(),
            "Task and raw-bag denominators stay frozen.",
            "No task rewrite/resample is allowed in G4IRSF13-C.",
        ),
        row(
            "storage_split_cardinality",
            dict(leg_counts) == EXPECTED_LEG_COUNTS,
            ";".join(
                f"{name}={leg_counts[name]}"
                for name in ("direct", "storage_in", "storage_out")
            ),
            ";".join(
                f"{name}={EXPECTED_LEG_COUNTS[name]}"
                for name in ("direct", "storage_in", "storage_out")
            ),
            TASK_PATH.as_posix(),
            "A split raw bag owns exactly one storage-in and one storage-out leg.",
            "Segment count is not raw-bag count.",
        ),
        row(
            "storage_leg_pairing_and_order",
            paired
            and len(split_groups) == EXPECTED_LEG_COUNTS["storage_in"],
            f"paired_split_bags={len(split_groups)};ordered={paired}",
            "paired_split_bags=15097;storage_in_before_storage_out=True",
            TASK_PATH.as_posix(),
            "Pair by task/pallet/original-entry identity, never by position alone.",
            "Storage legs remain separate runtime segments.",
        ),
        row(
            "direct_bag_cardinality",
            len(direct_groups) == EXPECTED_LEG_COUNTS["direct"]
            and all(len(rows) == 1 for rows in direct_groups),
            f"direct_raw_bags={len(direct_groups)}",
            "direct_raw_bags=13409",
            TASK_PATH.as_posix(),
            "A direct raw bag completes when its sole segment completes.",
            "Do not synthesize an EBS leg for a direct bag.",
        ),
        row(
            "storage_in_goal_47",
            storage_in_endpoint
            and int(nodes[47]["node_type"]) == 2
            and outdegree[47] == 0,
            (
                f"all_goal47={storage_in_endpoint};node_type="
                f"{nodes[47]['node_type']};outdegree={outdegree[47]}"
            ),
            "all_goal47=True;node_type=2;outdegree=0",
            "thesis/legacy split plus real map2 node 47",
            (
                "Arrival at node 47 completes only the storage-in segment, not "
                "the raw bag."
            ),
            (
                "The discontinuity to source 52 represents the legacy EBS "
                "handoff; no hidden map edge is inferred."
            ),
        ),
        row(
            "storage_out_source_52",
            storage_out_source
            and 52 in {int(node) for node in graph["start_nodes"]}
            and int(nodes[52]["node_type"]) == 1
            and indegree[52] == 0
            and outdegree[52] == 2,
            (
                f"all_start52={storage_out_source};node_type="
                f"{nodes[52]['node_type']};indegree={indegree[52]};"
                f"outdegree={outdegree[52]}"
            ),
            "all_start52=True;node_type=1;indegree=0;outdegree=2",
            "legacy Main.ReadTaskList plus real map2 node 52",
            "Storage-out enters the ready lifecycle at real source/EBS node 52.",
            "Source 52 is not a shortcut or a fallback route.",
        ),
        row(
            "storage_out_release_std_minus_2700",
            release_exact,
            f"rows={leg_counts['storage_out']};all_exact={release_exact}",
            "rows=15097;pass_time=STD-2700 exactly",
            "legacy Main.ReadTaskList and protected task rows",
            (
                "Scheduled EBS dwell is represented once between original "
                "entry and storage-out release."
            ),
            (
                "Primary original-entry TTH includes this elapsed time once; "
                "legacy segment-sum transport THT excludes the inter-leg dwell. "
                "The two denominators must stay separately labelled."
            ),
        ),
        row(
            "goal_nodes_are_real_terminals",
            terminal_goals
            and all(outdegree[int(goal)] == 0 for goal in goal_set),
            (
                f"used_goals={sorted({int(row['goal']) for row in tasks})};"
                f"map_goals={sorted(goal_set)}"
            ),
            "every task goal is a real map end node with outdegree=0",
            MAP_PATH.as_posix(),
            "A segment emits one goal-completion transition on terminal arrival.",
            "No successor route may be stored or selected after completion.",
        ),
        row(
            "raw_bag_completion_contract",
            paired
            and len(split_groups) + len(direct_groups) == EXPECTED_BAG_COUNT,
            (
                f"direct={len(direct_groups)};split={len(split_groups)};"
                f"total={len(grouped)}"
            ),
            "direct=13409;split=15097;total=28506",
            "protected task identity/lifecycle audit",
            (
                "A raw bag is complete iff its direct segment completes or both "
                "storage legs complete; storage-in completion alone is partial."
            ),
            "Evaluation must fail closed on a missing or duplicated leg.",
        ),
    ]


def validate_formula_rows(
    rows: Sequence[Mapping[str, str]] = FORMULA_ROWS,
) -> list[str]:
    errors: list[str] = []
    ids = tuple(row.get("record_id", "") for row in rows)
    expected = (
        "equation_4_2",
        "equation_4_3",
        "equation_4_4",
        "equation_4_5",
        "weight_relation",
        "stated_order_and_tie",
    )
    if ids != expected:
        errors.append(f"formula coverage/order mismatch: {ids!r}")
    for row in rows:
        for field in FORMULA_FIELDS:
            if not str(row.get(field, "")).strip():
                errors.append(f"{row.get('record_id')}: missing {field}")
    expressions = {row["record_id"]: row["exact_expression"] for row in rows}
    if expressions.get("weight_relation") != "p1 > p3 > p2 > p4":
        errors.append("thesis weight relation mismatch")
    if "first-in-first-out" not in expressions.get(
        "stated_order_and_tie", ""
    ):
        errors.append("missing thesis FIFO tie rule")
    return errors


def validate_literature_rows(
    rows: Sequence[Mapping[str, str]] = LITERATURE_ROWS,
) -> list[str]:
    errors: list[str] = []
    ids = [row.get("literature_id", "") for row in rows]
    if len(ids) != 11 or len(set(ids)) != 11:
        errors.append("literature coverage must contain 11 unique sources")
    for row in rows:
        row_id = row.get("literature_id", "")
        for field in LITERATURE_FIELDS:
            if not str(row.get(field, "")).strip():
                errors.append(f"{row_id}: missing {field}")
        source = str(row.get("primary_source", ""))
        if source.startswith("http"):
            parsed = urlparse(source)
            if parsed.scheme != "https":
                errors.append(f"{row_id}: non-HTTPS primary source")
            if parsed.hostname not in ALLOWED_PRIMARY_HOSTS:
                errors.append(
                    f"{row_id}: unapproved primary host {parsed.hostname}"
                )
    boundary = " ".join(
        row["prohibited_overclaim"] for row in rows
    ).lower()
    for required in (
        "classic pibt completeness",
        "global future planning",
        "runtime cbs",
        "full guidance graph",
        "future trajectories",
    ):
        if required not in boundary:
            errors.append(f"missing literature boundary: {required}")
    return errors


def validate_source_model(
    graph: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors = validate_formula_rows() + validate_literature_rows()
    motifs = real_map_motifs(graph)
    edges_by_pair = {
        (int(row["start"]), int(row["end"])): float(row["length"])
        for row in graph["edges"]
    }
    for arc_id, start, end, length in ARC_1_TO_8:
        observed = edges_by_pair.get((start, end))
        if observed is None or not math.isclose(
            observed, length, rel_tol=0.0, abs_tol=1.0e-12
        ):
            errors.append(
                f"arc {arc_id}: real map mismatch for {start}->{end}"
            )
    if 8 not in motifs["merge_nodes"]:
        errors.append("real merge node 8 missing")
    if 6 not in motifs["split_nodes"] or 52 not in motifs["split_nodes"]:
        errors.append("real split node 6/52 missing")
    if (0, 6) not in motifs["weak_projection_bridges"]:
        errors.append("real weak-projection bridge (0,6) missing")
    if motifs["ebs_nodes"] != (52,):
        errors.append("real EBS/source node 52 missing")
    if len(THESIS_FAULT_SCENARIOS) != 16:
        errors.append("thesis fault table must contain 16 scenarios")
    ebs_rows = build_ebs_audit_rows(graph, tasks)
    errors.extend(
        f"{row['check_id']}: {row['observed']}"
        for row in ebs_rows
        if row["status"] != "PASS"
    )
    return errors


def verify_external_sources(
    thesis_pdf: Path,
    legacy_root: Path,
) -> list[str]:
    """Fail-closed audit of local primary files; never modifies them."""

    errors: list[str] = []
    if not thesis_pdf.is_file():
        errors.append(f"missing thesis PDF: {thesis_pdf}")
    elif _sha256(thesis_pdf) != THESIS_SHA256:
        errors.append("thesis PDF SHA-256 mismatch")

    snippets = {
        "src/RUN/Main.java": (
            "return (int) (o1.getPass_time()-o2.getPass_time());",
            "newtask.setGoal(47);",
            "newtask1.setStar(52);",
            "double passtime = newtask1.getSTD()-2700;",
        ),
        "src/App/Tasks.java": (
            "temptask.getPass_time() - epoch >= 1",
            "task_List.get(ics_pf.getMap().star.get(i).getLocation()).remove(0);",
        ),
        "src/App/ICS_PathFinding.java": (
            "ArrayList<task>repairedTasks = new ArrayList<task>();",
            "repairedTasks.add(tk);",
            "ArrayList<Node>new_path=Astar.research",
            "ICS.getUnfinishTasks().addAll(tasks.new_tasks_list);",
        ),
    }
    for relative_path, expected_hash in LEGACY_SOURCE_SHA256.items():
        path = legacy_root / relative_path
        if not path.is_file():
            errors.append(f"missing legacy source: {relative_path}")
            continue
        if _sha256(path) != expected_hash:
            errors.append(f"legacy source SHA-256 mismatch: {relative_path}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for snippet in snippets.get(relative_path, ()):
            if snippet not in text:
                errors.append(
                    f"{relative_path}: missing audited snippet {snippet!r}"
                )

    arc_path = legacy_root / "arc.txt"
    if arc_path.is_file() and _sha256(arc_path) == LEGACY_SOURCE_SHA256["arc.txt"]:
        parsed: list[tuple[int, int, int, float]] = []
        for line in arc_path.read_text(
            encoding="utf-8", errors="ignore"
        ).splitlines()[:8]:
            fields = line.split()
            if len(fields) >= 4:
                parsed.append(
                    (
                        int(fields[0]),
                        int(fields[1]),
                        int(fields[2]),
                        float(fields[3]),
                    )
                )
        if tuple(parsed) != ARC_1_TO_8:
            errors.append("legacy arc.txt first-eight mapping mismatch")
    return errors


def _csv_text(
    fields: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=fields,
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _md_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[Any]],
) -> list[str]:
    def safe(value: Any) -> str:
        return str(value).replace("|", r"\|").replace("\n", " ")

    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *[
            "| " + " | ".join(safe(value) for value in row) + " |"
            for row in rows
        ],
    ]


def build_thesis_report(
    graph: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
) -> str:
    formula_errors = validate_formula_rows()
    if formula_errors:
        raise ValueError("; ".join(formula_errors))
    motifs = real_map_motifs(graph)
    formula_table = _md_table(
        ("Record", "Exact extraction", "Meaning", "Local boundary"),
        (
            (
                row["record_id"],
                row["exact_expression"],
                row["source_meaning"],
                row["non_transferable_boundary"],
            )
            for row in FORMULA_ROWS
        ),
    )
    arc_table = _md_table(
        ("Arc ID", "Real map edge", "Length"),
        (
            (arc_id, f"{start}->{end}", f"{length:g}")
            for arc_id, start, end, length in ARC_1_TO_8
        ),
    )
    fault_table = _md_table(
        ("Scenario", "Interrupted arcs", "Affected conveyors", "Paper success"),
        (
            (
                scenario,
                ",".join(str(value) for value in arcs),
                affected,
                f"{success:.2f}",
            )
            for scenario, arcs, affected, success in THESIS_FAULT_SCENARIOS
        ),
    )
    return "\n".join(
        [
            "# G4IRSF13 Thesis Priority Extraction",
            "",
            f"Date: {PHASE_DATE}",
            "",
            "status: `SOURCE_EXTRACTION_COMPLETE`",
            "implementation_claim: `DESIGN_INPUT_NOT_RUNTIME_PROMOTION`",
            f"thesis_sha256: `{THESIS_SHA256}`",
            f"map_raw_sha256: `{MAP_RAW_SHA256}`",
            f"map_semantic_sha256: `{MAP_SEMANTIC_SHA256}`",
            f"task_raw_sha256: `{TASK_RAW_SHA256}`",
            "",
            "## Source boundary",
            "",
            (
                "The user-supplied primary PDF was visually reviewed after "
                "Poppler rendering. File pages 33, 34, 38, 39, 40, and 46 "
                "(printed pages 19, 20, 24, 25, 26, and 32) support the "
                "lifecycle, BTI/DDI, fault/repair, formula, and Table 5.5 facts "
                "below. The byte identity above prevents an unlabelled source "
                "substitution."
            ),
            "",
            (
                "The legacy Java and `arc.txt` were read-only inputs. Their "
                f"recorded hashes are: `{json.dumps(LEGACY_SOURCE_SHA256, sort_keys=True)}`."
            ),
            "",
            "## Task-list lifecycle extracted from Chapter 4",
            "",
            (
                "The thesis task tuple is `(b_k, o_k, d_k, t_k, tau_k)`: bag "
                "identity, origin, destination, BHS-entry time, and flight "
                "departure time. New tasks, tasks affected by a device "
                "interruption, and tasks whose future routes conflict are added "
                "to task list F and ranked before planning."
            ),
            "",
            (
                "A task with a conflict-free route leaves F. A task with no "
                "route remains for a later planning cycle. Affected tasks may "
                "continue on the already committed safe portion, and repair "
                "places non-complete affected tasks back into the task "
                "processing lifecycle."
            ),
            "",
            "## Equations 4.2-4.5 and stated ordering",
            "",
            *formula_table,
            "",
            (
                "The scalar expression is not fully executable from the thesis "
                "alone: numeric weights and cross-term normalization are not "
                "specified. G4IRSF13 therefore preserves the explicitly stated "
                "ordering as a deterministic local projection and reports this "
                "limitation rather than inventing p-values."
            ),
            "",
            "## BTI and DDI separation",
            "",
            (
                "- DDI is device interruption/repair information. It updates "
                "which physical conveyor resources are available and identifies "
                "tasks potentially affected by the change."
            ),
            (
                "- BTI is baggage tracking information. It supplies the actual "
                "bag/node passage state used to update execution state and to "
                "identify conflicts/affected bags."
            ),
            (
                "- Localized transfer: DDI becomes a bounded generation-tagged "
                "availability overlay; BTI anchors the bag's actual local "
                "position. The physical entry interlock remains authoritative."
            ),
            "",
            "## Fault propagation and repair re-entry",
            "",
            (
                "The thesis removes an affected conveyor set from the available "
                "graph, holds bags that cannot safely continue, and restores the "
                "set on repair. Bags stopped by the interruption are returned to "
                "the task list for priority processing."
            ),
            "",
            (
                "Only the lifecycle is transferable. The final runtime must "
                "re-enqueue at the current safe node and choose at most one next "
                "edge. It must not recreate the thesis HCA*, saved route, global "
                "reservation table, or full replan."
            ),
            "",
            "## Legacy arc IDs 1-8 mapped to protected map2",
            "",
            *arc_table,
            "",
            (
                f"All eight are real directed map2 edges. The real-map audit "
                f"also finds merge node 8, split nodes 6 and 52, and "
                f"{len(motifs['weak_projection_bridges'])} weak-projection "
                "bridges; `(0,6)` (arc 1) is one of those bridges."
            ),
            "",
            "## Thesis Table 5.5 (paper-reported only)",
            "",
            *fault_table,
            "",
            (
                "These 16 rows are extracted paper outcomes, not G4IRSF13 "
                "runtime results. Stage H may map the listed arc IDs through "
                "`arc.txt`, but promotion requires informative exposure and a "
                "matched physical-shield control."
            ),
            "",
            "## Protected input coverage",
            "",
            (
                f"The committed input contains `{len(tasks)}` segments for "
                f"`{len({int(row['task_id']) for row in tasks})}` raw bags. "
                "EBS/source/goal details are validated in "
                "`g4irsf13_ebs_goal_lifecycle_audit.csv`."
            ),
        ]
    ) + "\n"


def build_local_design_report() -> str:
    priority_table = _md_table(
        ("Variant", "Name", "Ordered local components", "Boundary"),
        (
            (
                row["variant"],
                row["name"],
                row["ordered_components"],
                row["claim_boundary"],
            )
            for row in PRIORITY_VARIANTS
        ),
    )
    return "\n".join(
        [
            "# G4IRSF13 Localized Legacy Control Design",
            "",
            f"Date: {PHASE_DATE}",
            "",
            "status: `STATIC_DESIGN_READY_FOR_CONTROLLED_AB`",
            "runtime_scope: `ONE_NEXT_EDGE_RESERVATION_DEPTH_ONE`",
            "",
            "## What the legacy Java actually does",
            "",
            (
                "`RUN/Main.java` sorts each per-source list with "
                "`(int)(o1.pass_time-o2.pass_time)`. Java truncates toward zero, "
                "so sub-second differences compare equal; `Collections.sort` "
                "then retains input order for those ties. This is a coarse "
                "pass-time comparator, not equations 4.2-4.5."
            ),
            "",
            (
                "`Tasks.generate_tasks` considers at most the head item of each "
                "real source per epoch, requires `pass_time-epoch < 1`, and does "
                "not generate from a source that already has an unfinished "
                "task. `ICS_PathFinding` appends new tasks to `unfinishTasks`, "
                "removes from the head, and appends an unplanned task back to "
                "the tail."
            ),
            "",
            (
                "Fault-affected temporary tasks are also sorted by the coarse "
                "integer pass-time comparator. On repair, a non-complete "
                "affected task is collected for processing. Legacy code then "
                "runs A* and stores a route; only the collect/re-enter lifecycle "
                "is eligible for migration."
            ),
            "",
            "## Q0-Q3 priority controls",
            "",
            *priority_table,
            "",
            (
                "All keys are deterministic and lower keys run first. Slack and "
                "age come from the current bag and event time. Current-contention "
                "means contention for a current next-edge candidate, never an "
                "inspection of a future route."
            ),
            "",
            "## B2 legacy_order_one_step_diagnostic",
            "",
            (
                "B2 reproduces only the legacy coarse pass-time order at a "
                "ready queue. It then invokes the same bounded candidate "
                "enumeration, safety shield, resource semantics, P2 mode, and "
                "single-edge commit as the event runtime. A sub-second "
                "comparator tie is resolved by preserved enqueue sequence and "
                "stable ID."
            ),
            "",
            "B2 is diagnostic-only and must report:",
            "",
            "- `reservation_depth = 1`;",
            "- one committed next edge per bag decision;",
            "- `runtime_full_astar_calls = 0`;",
            "- `future_routes_stored = 0`;",
            "- `global_reservation_scans = 0`;",
            "- identical physical interlock and atomic P2 validation.",
            "",
            (
                "A result produced by calling legacy A*, retaining "
                "`saved_routes`, or inspecting the global reservation table is "
                "not B2 and must fail closed."
            ),
            "",
            "## Repair re-entry contract",
            "",
            "1. DDI applies a monotone fault/repair generation to the local overlay.",
            "2. BTI anchors the affected bag at its actual current safe node.",
            "3. Unconsumed credit and uncommitted P2 proposals touching the fault are invalidated.",
            "4. A repaired, non-complete bag is re-enqueued once with its original identity and age.",
            "5. Q1/Q2/Q3 may prioritize it; the physical shield and P2 validation remain authoritative.",
            "6. The decision selects at most one available next edge or holds.",
            "",
            "## EBS/source 52 and goal-completion contract",
            "",
            (
                "An early raw bag is two runtime segments: storage-in ends at "
                "real terminal node 47; storage-out later enters at real source "
                "52 at `STD-2700`. Storage-in completion is not raw-bag "
                "completion. The raw bag completes only after storage-out reaches "
                "its final goal. A direct raw bag completes after its single "
                "segment."
            ),
            "",
            (
                "Primary G4IRSF13 TTH uses final raw-bag completion relative to "
                "original entry, so EBS dwell appears once. Any legacy "
                "segment-sum transport metric that excludes inter-leg dwell must "
                "remain separately named."
            ),
            "",
            "## Required experiment order",
            "",
            (
                "Run deterministic unit checks, real-map merge/split/bridge/EBS "
                "motifs, then 144, 512, 2048, 8192, and at most four top full "
                "cases. Q0 remains the control. Priority changes cannot be "
                "credited when lower source wait is offset by a larger network "
                "time or a p95/p99 regression."
            ),
        ]
    ) + "\n"


def _source_link(row: Mapping[str, str]) -> str:
    source = row["primary_source"]
    if source.startswith("https://"):
        return f"[primary source]({source})"
    return f"`{source}`"


def build_literature_report() -> str:
    errors = validate_literature_rows()
    if errors:
        raise ValueError("; ".join(errors))
    coverage = _md_table(
        ("ID", "Identifier", "Access", "Target"),
        (
            (
                row["literature_id"],
                row["identifier"],
                row["access_status"],
                row["target_module"],
            )
            for row in LITERATURE_ROWS
        ),
    )
    lines = [
        "# G4IRSF13 Literature-to-Design Matrix",
        "",
        f"Date: {PHASE_DATE}",
        "",
        "coverage: `11/11 COMPLETE`",
        "source_policy: `PRIMARY_OR_OFFICIAL_ONLY`",
        "claim: `DESIGN_JUSTIFICATION_NOT_PROMOTION_EVIDENCE`",
        "",
        "## Executive boundary",
        "",
        (
            "The sources justify bounded mechanisms and controlled A/B tests. "
            "They do not authorize HCA*/A*/SIPP/CBS in the final runtime, a "
            "full guidance graph, a complete future route, a global reservation "
            "scan, or a completeness/throughput theorem on protected map2."
        ),
        "",
        *coverage,
        "",
        "## Source-by-source transfer contract",
        "",
    ]
    for index, row in enumerate(LITERATURE_ROWS, start=1):
        lines.extend(
            [
                f"### {index}. {row['literature_id']}",
                "",
                (
                    f"**Citation:** {row['citation']}. Identifier: "
                    f"`{row['identifier']}`. {_source_link(row)}."
                ),
                "",
                f"**Access:** `{row['access_status']}`.",
                "",
                f"**Transferable mechanism:** {row['transferable_mechanism']}",
                "",
                f"**Conflicting assumption:** {row['conflicting_assumption']}",
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
                "The approved transfer is a one-step, reservation-depth-one, "
                "bounded-local controller with an always-on physical interlock. "
                "Every imported idea remains behind its own matched A/B and "
                "must pass completion, safety, tail, and no-future-information "
                "gates before promotion."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def render_outputs(root: Path = ROOT) -> dict[Path, str]:
    graph = _load_graph(root)
    tasks = _load_tasks(root)
    errors = validate_source_model(graph, tasks)
    if errors:
        raise ValueError("; ".join(errors))
    ebs_rows = build_ebs_audit_rows(graph, tasks)
    return {
        THESIS_REPORT_PATH: build_thesis_report(graph, tasks),
        FORMULA_TABLE_PATH: _csv_text(FORMULA_FIELDS, FORMULA_ROWS),
        LOCAL_DESIGN_REPORT_PATH: build_local_design_report(),
        EBS_AUDIT_TABLE_PATH: _csv_text(EBS_FIELDS, ebs_rows),
        LITERATURE_REPORT_PATH: build_literature_report(),
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
        if not path.is_file():
            errors.append(f"missing {relative_path.as_posix()}")
        elif path.read_text(encoding="utf-8") != expected:
            errors.append(f"stale {relative_path.as_posix()}")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verify-external", action="store_true")
    parser.add_argument("--thesis-pdf", type=Path, default=DEFAULT_THESIS_PDF)
    parser.add_argument(
        "--legacy-root",
        type=Path,
        default=DEFAULT_LEGACY_ROOT,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.verify_external:
        source_errors = verify_external_sources(
            args.thesis_pdf,
            args.legacy_root,
        )
        if source_errors:
            raise ValueError("; ".join(source_errors))
    outputs = render_outputs()
    if args.write:
        write_outputs(ROOT, outputs)
        action = "published"
    else:
        output_errors = check_outputs(ROOT, outputs)
        if output_errors:
            raise ValueError("; ".join(output_errors))
        action = "validated"
    print(
        f"{action}: outputs={len(outputs)} formulas={len(FORMULA_ROWS)} "
        f"literature={len(LITERATURE_ROWS)} external="
        f"{'verified' if args.verify_external else 'recorded'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
