"""Derive finite upstream body-clearance V5; no formal experiment is launched."""
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
NAME = "feng_cie_dh_boundary_clearance_v5"
METHOD = "FENG_DH_BOUNDARY_CLEARANCE_V5"
OUTPUT = ROOT / "outputs/runtime/feng_dh_semantics_reaudit_20260905/boundary_clearance_fixtures"


def replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"parent contract differs; expected one occurrence: {old[:100]}")
    return text.replace(old, new, 1)


def bag_state(text: str) -> str:
    text = replace(text, "    private boolean nodeServiceFinished;", "    private boolean nodeServiceFinished;\n    private long boundaryClearanceReadyTick = -1L;")
    text = replace(text, "    private void clearNodeService() {", '''    public boolean isBoundaryClearance() {
        return boundaryClearanceReadyTick >= 0L;
    }

    public long getBoundaryClearanceReadyTick() {
        return boundaryClearanceReadyTick;
    }

    void beginBoundaryClearance(long tick, long clearanceReadyTick, long transferReadyTick,
            String detail, boolean recordTrace) {
        require(status == Status.MOVING_ON_EDGE || status == Status.STOPPED_ON_EDGE,
                "clearance requires physical edge ownership");
        require(hasNodeServiceStarted() && nodeServiceFinished && !isBoundaryClearance(),
                "clearance must start once after through completion");
        require(clearanceReadyTick > tick && clearanceReadyTick < transferReadyTick,
                "V5 requires positive body clearance strictly inside the existing transfer");
        boundaryClearanceReadyTick = clearanceReadyTick;
        nodeServiceStartTick = tick;
        nodeServiceReadyTick = transferReadyTick;
        nodeServiceFinished = false;
        if (recordTrace) {
            addTrace(tick, "NODE_SERVICE_START", currentNode, currentEdgeId, positionCell,
                    "arrival_tick=" + nodeArrivalTick + ";ready_tick=" + transferReadyTick
                            + ";clearance_ready_tick=" + clearanceReadyTick + ";" + detail);
        }
    }

    void leaveBoundaryAfterClearance(long tick, boolean recordTrace) {
        require(isBoundaryClearance() && tick >= boundaryClearanceReadyTick,
                "boundary cannot clear before its physical clearance timer");
        require(status == Status.MOVING_ON_EDGE || status == Status.STOPPED_ON_EDGE,
                "clearance completion requires physical edge ownership");
        previousStatus = status;
        status = Status.AT_LOADING_OR_JUNCTION;
        currentEdgeId = -1;
        positionCell = -1;
        boundaryClearanceReadyTick = -1L;
        lastHoldReason = "";
        retryTick = -1L;
        if (recordTrace) {
            addTrace(tick, "BOUNDARY_CLEARANCE_FINISH", currentNode, -1, -1,
                    "transfer_ready_tick_unchanged=" + nodeServiceReadyTick);
        }
    }

    private void clearNodeService() {
        boundaryClearanceReadyTick = -1L;''')
    return text


def simulator(text: str) -> str:
    text = replace(text, "        ArrayList<FengDhBagState> nodeThroughWaiting = new ArrayList<FengDhBagState>();", """        ArrayList<FengDhBagState> nodeThroughWaiting = new ArrayList<FengDhBagState>();
        ArrayList<FengDhBagState> clearanceFinishing = new ArrayList<FengDhBagState>();
        ArrayList<FengDhBagState> clearanceWaiting = new ArrayList<FengDhBagState>();""")
    text = replace(text, "                FengDhBagState throughOccupant = nodeThroughOccupants.get(", """                if (bag.isBoundaryClearance()) {
                    if (commitTick >= bag.getBoundaryClearanceReadyTick()) {
                        clearanceFinishing.add(bag);
                        guaranteedDepartures.add(Long.valueOf(bag.taskId));
                    } else {
                        clearanceWaiting.add(bag);
                        progress++;
                    }
                    continue;
                }
                FengDhBagState throughOccupant = nodeThroughOccupants.get(""")
    text = replace(text, "                    throughServicesFinishing.add(bag);\n                    guaranteedDepartures.add(Long.valueOf(bag.taskId));", "                    throughServicesFinishing.add(bag);")
    text = replace(text, """                if (mapThroughTicks(winner.node) == 0L) {
                    guaranteedDepartures.add(Long.valueOf(winner.bag.taskId));
                }
""", "")
    text = replace(text, """        // Zero through-time completes in this commit and immediately starts
        // the existing per-bag transfer timer.  Remove its upstream footprint
        // before follower mutations, including a one-cell carrier moving into
        // the exact vacated cell.  Arbitration still uses the frozen snapshot.""", """        // Zero through completes once; total transfer ready time is unchanged.
        // Retain only the map-derived body-clearance interval on the upstream.""")
    text = replace(text, """            lattice.remove(proposal.upstreamEdgeId, bag);
            bag.beginNodeService(
                    commitTick,
                    proposal.node,
                    commitTick + reconstructedTransferTicks(),""", """            bag.beginBoundaryClearance(
                    commitTick,
                    commitTick + boundaryClearanceTicks(proposal.upstreamEdgeId),
                    commitTick + reconstructedTransferTicks(),""")
    old = """                            + proposal.upstreamEdgeId,
                    shouldTrace(bag, traceSampleModulo));
            progress++;
        }

        // The same simultaneous-vacate rule also applies to goal arrivals"""
    new = """                            + proposal.upstreamEdgeId,
                    shouldTrace(bag, traceSampleModulo));
            stopPhysicalHandoff(bag, commitTick, "BOUNDARY_BODY_CLEARANCE", traceSampleModulo);
            progress++;
        }

        // The same simultaneous-vacate rule also applies to goal arrivals"""
    text = replace(text, old, new)
    text = replace(text, """        // The same simultaneous-vacate rule also applies to goal arrivals
        // and finishing positive through services.  Keep their state/trace
        // commits below, but release lattice cells before follower moves.""", """        // Clear physical cells only at goals or completed body clearance,
        // before followers commit. Through completion alone retains the cell.""")
    text = replace(text, """        for (FengDhBagState bag : throughServicesFinishing) {
            lattice.remove(bag.getCurrentEdgeId(), bag);
        }""", """        for (FengDhBagState bag : clearanceFinishing) {
            lattice.remove(bag.getCurrentEdgeId(), bag);
            bag.leaveBoundaryAfterClearance(commitTick, shouldTrace(bag, traceSampleModulo));
            progress++;
        }""")
    text = replace(text, """        for (NodeServiceProposal proposal : blockedNodeServices) {
            holdForJunctionThrough(proposal, commitTick, traceSampleModulo);
        }""", """        for (FengDhBagState bag : clearanceWaiting) {
            stopPhysicalHandoff(bag, commitTick, "BOUNDARY_BODY_CLEARANCE", traceSampleModulo);
        }
        for (NodeServiceProposal proposal : blockedNodeServices) {
            holdForJunctionThrough(proposal, commitTick, traceSampleModulo);
        }""")
    text = replace(text, """            bag.beginNodeService(
                    commitTick,
                    node,
                    commitTick + reconstructedTransferTicks(),""", """            bag.beginBoundaryClearance(
                    commitTick,
                    commitTick + boundaryClearanceTicks(upstreamEdgeId),
                    commitTick + reconstructedTransferTicks(),""")
    text = replace(text, """                            + upstreamEdgeId,
                    shouldTrace(bag, traceSampleModulo));
            progress++;
        }""", """                            + upstreamEdgeId,
                    shouldTrace(bag, traceSampleModulo));
            stopPhysicalHandoff(bag, commitTick, "BOUNDARY_BODY_CLEARANCE", traceSampleModulo);
            progress++;
        }""")
    text = replace(text, """        // Released source bags and completed per-bag transfer timers choose an
        // exit.  Only the map-defined through stage retains the upstream
        // footprint; the fixed transfer delay itself adds no capacity server.""", """        // Released sources and off-edge transfer timers choose an exit.
        // The initial body-clearance part retains the upstream footprint;
        // its remainder keeps the original total ready timestamp.""")
    text = replace(text, "continue; // Completed and released before follower commits.", "continue; // Through completed; body clearance was started above.")
    text = replace(text, "    private long mapThroughTicks(int node) {", """    private long boundaryClearanceTicks(int upstreamEdgeId) {
        double seconds = (lattice.getAgvLengthMeters() + lattice.getSafeLengthMeters())
                / lattice.edge(upstreamEdgeId).speedMetersPerSecond;
        long ticks = secondsToTicks(seconds);
        if (ticks <= 0L || ticks >= reconstructedTransferTicks()) {
            throw new IllegalArgumentException(
                    "V5 supports positive body clearance strictly shorter than existing transfer");
        }
        return ticks;
    }

    private long mapThroughTicks(int node) {""")
    return text


def verify(target: Path) -> dict:
    build = ROOT / "build/feng_dh_boundary_clearance_v5"
    audit = ROOT / "build/feng_dh_boundary_clearance_v5_audit"
    build.mkdir(parents=True, exist_ok=True)
    audit.mkdir(parents=True, exist_ok=True)
    command = [shutil.which("javac") or "javac", "--release", "8", "-Xlint:all", "-encoding", "UTF-8",
               "-d", str(build), *map(str, sorted((target / "App").glob("*.java")))]
    subprocess.run(command, check=True, capture_output=True, timeout=60)
    test = ROOT / "tests/java/App/BoundaryClearanceAudit.java"
    subprocess.run([command[0], "--release", "8", "-Xlint:all", "-encoding", "UTF-8", "-cp", str(build),
                    "-d", str(audit), str(test)], check=True, capture_output=True, timeout=60)
    run = [shutil.which("java") or "java", "-cp", str(build) + os.pathsep + str(audit),
           "App.BoundaryClearanceAudit", str(OUTPUT)]
    result = subprocess.run(run, check=True, capture_output=True, timeout=60)
    (OUTPUT / "results.jsonl").write_bytes(result.stdout)
    (OUTPUT / "stderr.txt").write_bytes(result.stderr)
    checks = [json.loads(line) for line in result.stdout.decode("utf-8").splitlines()]
    if len(checks) != 9 or not all(row["pass"] for row in checks):
        raise RuntimeError("bounded fixture failure")
    return {"compile_command": command, "command": run, "checks": checks,
            "class_aggregate_sha256": aggregate(build, "*.class"),
            "test_source": files_identity(test.parent, test.name),
            "outputs": {p: h for p, h in files_identity(OUTPUT, "*").items()
                        if p != "derivation_and_fixtures.json"}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    parent = ROOT / "benchmarks/java/feng_cie_dh"
    target = ROOT / "benchmarks/java" / NAME
    before = files_identity(parent, "*.java")
    if len(before) != 5:
        raise RuntimeError("expected five parent sources")
    payloads = {}
    for path in sorted((parent / "App").glob("*.java")):
        raw = path.read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        if path.name == "FengDhSimulator.java": text = simulator(text)
        elif path.name == "FengDhBagState.java": text = bag_state(text)
        elif path.name == "FengDhBenchmark.java":
            text, count = re.subn(r'private static final String METHOD = "[A-Z0-9_]+";',
                                 f'private static final String METHOD = "{METHOD}";', text)
            if count != 1: raise RuntimeError("expected one METHOD")
            text = text.replace("STATIC_FREE_FLOW_FENG_EXECUTOR", "STATIC_FREE_FLOW_BOUNDARY_CLEARANCE_V5")
        payload = text.replace("\n", "\r\n").encode("utf-8")
        if path.name in ("FengDhPolicy.java", "FengDhEdgeLattice.java") and payload != raw:
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
    verification = verify(target) if args.verify else None
    if files_identity(parent, "*.java") != before: raise RuntimeError("parent changed")
    manifest = {"schema": "feng.dh.boundary_clearance_derivation.v1", "method": METHOD,
                "parent_files": before, "target_files": files_identity(target, "*.java"),
                "parent_source_aggregate_sha256": aggregate(parent, "*.java"),
                "source_aggregate_sha256": aggregate(target, "*.java"),
                "verification": verification, "formal_experiments_started": 0}
    (OUTPUT / "derivation_and_fixtures.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("method", "source_aggregate_sha256")}, indent=2))


if __name__ == "__main__": main()
