"""Derive control-only V6 post-movement scoring; run only bounded fixtures."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from derive_feng_dh_id_order_probes import aggregate, files_identity

ROOT = Path(__file__).resolve().parents[2]
NAME = "feng_cie_dh_post_movement_scoring_v6"
METHOD = "FENG_DH_POST_MOVEMENT_SCORING_V6"
OUTPUT = ROOT / "outputs/runtime/feng_dh_semantics_reaudit_20260905/post_movement_scoring_fixtures"


def once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"expected one control anchor: {old[:80]}")
    return text.replace(old, new, 1)


def lattice(text: str) -> str:
    return once(text, "    public List<FengDhBagState> occupantsDownstreamFirst(int edgeId) {", '''    /** Independent immutable score view; never changes occupancy or bag status. */
    public Snapshot scoringSnapshotAfterMovement(
            Map<Long, Integer> plannedPositions, Set<Long> guaranteedDepartures) {
        HashMap<Integer, List<OccupantSnapshot>> result =
                new HashMap<Integer, List<OccupantSnapshot>>();
        int[] movingByEdge = new int[edges.size()];
        int[] stoppedByEdge = new int[edges.size()];
        for (EdgeData edge : edges) {
            ArrayList<OccupantSnapshot> values = new ArrayList<OccupantSnapshot>();
            for (Map.Entry<Integer, FengDhBagState> entry
                    : occupancy.get(Integer.valueOf(edge.id)).entrySet()) {
                FengDhBagState bag = entry.getValue();
                if (guaranteedDepartures.contains(Long.valueOf(bag.taskId))) {
                    continue;
                }
                Integer planned = plannedPositions.get(Long.valueOf(bag.taskId));
                int oldPosition = entry.getKey().intValue();
                if (planned == null || planned.intValue() < oldPosition
                        || planned.intValue() > oldPosition + 1) {
                    throw new IllegalStateException("incomplete or invalid score movement plan");
                }
                boolean advances = planned.intValue() > oldPosition;
                FengDhBagState.Status status = advances
                        ? FengDhBagState.Status.MOVING_ON_EDGE : FengDhBagState.Status.STOPPED_ON_EDGE;
                values.add(new OccupantSnapshot(bag.taskId, planned.intValue(), status));
                if (advances) movingByEdge[edge.id]++;
                else stoppedByEdge[edge.id]++;
            }
            result.put(Integer.valueOf(edge.id), Collections.unmodifiableList(values));
        }
        return new Snapshot(Collections.unmodifiableMap(result), movingByEdge, stoppedByEdge);
    }

    public List<FengDhBagState> occupantsDownstreamFirst(int edgeId) {''')


def simulator(text: str) -> str:
    text = once(text, """        // Released source bags and completed per-bag transfer timers choose an""", """        // V6 changes the score observation only. The physical plan and original
        // bag statuses remain unchanged for all conflict/admission decisions.
        HashSet<Long> scoringDepartures = new HashSet<Long>(guaranteedDepartures);
        HashMap<Long, Integer> scoringPlan = new HashMap<Long, Integer>(plannedPositions);
        FengDhEdgeLattice.Snapshot scoringSnapshot = lattice.scoringSnapshotAfterMovement(
                scoringPlan, scoringDepartures);

        // Released source bags and completed per-bag transfer timers choose an""")
    text = once(text, "                    bag.getCurrentNode(), bag.goalNode, snapshot);",
                "                    bag.getCurrentNode(), bag.goalNode, scoringSnapshot);")
    text = once(text, """            if (proposal.upstreamEdgeId >= 0) {
                guaranteedDepartures.add(Long.valueOf(proposal.bag.taskId));
            }""", """            if (proposal.upstreamEdgeId >= 0) {
                throw new IllegalStateException("V6 proof is restricted to off-edge control entries");
            }""")
    text = once(text, """        // Zero through-time completes in this commit and immediately starts""", """        if (!guaranteedDepartures.equals(scoringDepartures)
                || !plannedPositions.equals(scoringPlan)) {
            throw new IllegalStateException("score-dependent departure or movement feedback in V6");
        }

        // Zero through-time completes in this commit and immediately starts""")
    return text


def verify(name: str, post: bool) -> dict:
    source = ROOT / "benchmarks/java" / name / "App"
    classes = ROOT / "build/feng_dh_post_movement_scoring_probe" / name / "classes"
    audit = classes.parent / "audit"
    classes.mkdir(parents=True, exist_ok=True)
    audit.mkdir(parents=True, exist_ok=True)
    command = [shutil.which("javac") or "javac", "--release", "8", "-Xlint:all", "-encoding", "UTF-8",
               "-d", str(classes), *map(str, sorted(source.glob("*.java")))]
    subprocess.run(command, check=True, capture_output=True, timeout=60)
    test = ROOT / "tests/java/App/PostMovementScoringAudit.java"
    test_sources = [test]
    if post: test_sources.append(test.parent / "PostMovementSnapshotAudit.java")
    subprocess.run([command[0], "--release", "8", "-Xlint:all", "-encoding", "UTF-8", "-cp", str(classes),
                    "-d", str(audit), *map(str, test_sources)], check=True, capture_output=True, timeout=60)
    output = OUTPUT / name
    output.mkdir(parents=True, exist_ok=True)
    run = [shutil.which("java") or "java", "-cp", str(classes) + os.pathsep + str(audit),
           "App.PostMovementScoringAudit", "post" if post else "parent", str(output)]
    result = subprocess.run(run, check=True, capture_output=True, timeout=60)
    (output / "results.jsonl").write_bytes(result.stdout)
    (output / "stderr.txt").write_bytes(result.stderr)
    checks = [json.loads(line) for line in result.stdout.decode("utf-8").splitlines()]
    if len(checks) != 9 or not all(row["pass"] for row in checks):
        raise RuntimeError("bounded fixture failure")
    if post:
        frozen = subprocess.run([run[0], "-cp", run[2], "App.PostMovementSnapshotAudit"],
                                check=True, capture_output=True, timeout=60)
        (output / "frozen_projection.jsonl").write_bytes(frozen.stdout)
        extra = json.loads(frozen.stdout.decode("utf-8"))
        if not extra["pass"]: raise RuntimeError("immutable snapshot fixture failure")
        checks.append(extra)
    return {"name": name, "compile_command": command, "command": run, "checks": checks,
            "class_aggregate_sha256": aggregate(classes, "*.class"),
            "test_source": {p.name: files_identity(p.parent, p.name)[p.name] for p in test_sources},
            "outputs": files_identity(output, "*")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    parent = ROOT / "benchmarks/java/feng_cie_dh"
    target = ROOT / "benchmarks/java" / NAME
    before = files_identity(parent, "*.java")
    if len(before) != 5: raise RuntimeError("expected five control sources")
    payloads = {}
    for path in sorted((parent / "App").glob("*.java")):
        raw = path.read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        if path.name == "FengDhSimulator.java": text = simulator(text)
        elif path.name == "FengDhEdgeLattice.java": text = lattice(text)
        elif path.name == "FengDhBenchmark.java":
            text, count = re.subn(r'private static final String METHOD = "[A-Z0-9_]+";',
                                 f'private static final String METHOD = "{METHOD}";', text)
            if count != 1: raise RuntimeError("expected one METHOD")
            text = text.replace("STATIC_FREE_FLOW_FENG_EXECUTOR", "STATIC_FREE_FLOW_POST_MOVEMENT_SCORING_V6")
        payload = text.replace("\n", "\r\n").encode("utf-8")
        if path.name in ("FengDhPolicy.java", "FengDhBagState.java") and payload != raw:
            raise RuntimeError("unchanged sources must be canonical CRLF")
        payloads[path.name] = payload
    (target / "App").mkdir(parents=True, exist_ok=True)
    if {p.name for p in (target / "App").glob("*.java")} - set(payloads): raise RuntimeError("extra target Java")
    for name, payload in payloads.items():
        path = target / "App" / name
        if path.exists() and path.read_bytes() != payload: raise RuntimeError("differing probe source exists")
    for name, payload in payloads.items():
        path = target / "App" / name
        if not path.exists(): path.write_bytes(payload)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    verification = [verify("feng_cie_dh", False), verify(NAME, True)] if args.verify else []
    if files_identity(parent, "*.java") != before: raise RuntimeError("parent changed")
    manifest = {"schema": "feng.dh.post_movement_scoring_derivation.v1", "method": METHOD,
                "parent_files": before, "target_files": files_identity(target, "*.java"),
                "parent_source_aggregate_sha256": aggregate(parent, "*.java"),
                "source_aggregate_sha256": aggregate(target, "*.java"),
                "verification": verification, "formal_experiments_started": 0}
    (OUTPUT / "derivation_and_fixtures.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("method", "source_aggregate_sha256")}, indent=2))


if __name__ == "__main__": main()
