package App;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;

/**
 * Deterministic 0.2 s position simulator.  Every tick is evaluated from one
 * frozen snapshot, conflicts are resolved locally, and mutations are committed
 * only after all move/entry proposals have been formed.
 */
public final class FengDhSimulator {
    /*
     * The paper does not disclose this duration.  It is frozen, unavailable
     * to the CLI, and supported only by the historical single-bag OD lower
     * envelope.  It is a fixed physical handoff delay, not a capacity server
     * or a route-score term.
     */
    static final double RECONSTRUCTED_TRANSFER_DURATION_SECONDS = 2.0d;

    public static final class RunConfig {
        public final long horizonTick;
        public final int traceSampleModulo;
        public final long deadlockIdleTicks;

        public RunConfig(long horizonTick, int traceSampleModulo, long deadlockIdleTicks) {
            if (horizonTick < 0L || traceSampleModulo < 0 || deadlockIdleTicks <= 0L) {
                throw new IllegalArgumentException("invalid simulator run configuration");
            }
            this.horizonTick = horizonTick;
            this.traceSampleModulo = traceSampleModulo;
            this.deadlockIdleTicks = deadlockIdleTicks;
        }

        public static RunConfig untilComplete(int traceSampleModulo) {
            return new RunConfig(Long.MAX_VALUE, traceSampleModulo, 50_000L);
        }
    }

    public static final class RunResult {
        public final String status;
        public final long startTick;
        public final long endTick;
        public final int segmentPopulation;
        public final int completedSegments;
        public final int rawBagPopulation;
        public final int completedRawBags;
        public final long releasedSegments;
        public final long enteredSegments;
        public final long moveCommits;
        public final long stoppedTicks;
        public final long holds;
        public final long entryStoppedHolds;
        public final long entryMovingHolds;
        public final long mergeConflictHolds;
        public final long followingHolds;
        public final long junctionThroughBusyHolds;
        public final long noPathHolds;
        public final long decisions;
        public final long tiedDecisions;
        public final long unreachableDecisions;
        public final int peakActiveSegments;
        public final int peakEdgeOccupancy;

        RunResult(
                String status,
                long startTick,
                long endTick,
                int segmentPopulation,
                int completedSegments,
                int rawBagPopulation,
                int completedRawBags,
                long releasedSegments,
                long enteredSegments,
                long moveCommits,
                long stoppedTicks,
                long holds,
                long entryStoppedHolds,
                long entryMovingHolds,
                long mergeConflictHolds,
                long followingHolds,
                long junctionThroughBusyHolds,
                long noPathHolds,
                long decisions,
                long tiedDecisions,
                long unreachableDecisions,
                int peakActiveSegments,
                int peakEdgeOccupancy) {
            this.status = status;
            this.startTick = startTick;
            this.endTick = endTick;
            this.segmentPopulation = segmentPopulation;
            this.completedSegments = completedSegments;
            this.rawBagPopulation = rawBagPopulation;
            this.completedRawBags = completedRawBags;
            this.releasedSegments = releasedSegments;
            this.enteredSegments = enteredSegments;
            this.moveCommits = moveCommits;
            this.stoppedTicks = stoppedTicks;
            this.holds = holds;
            this.entryStoppedHolds = entryStoppedHolds;
            this.entryMovingHolds = entryMovingHolds;
            this.mergeConflictHolds = mergeConflictHolds;
            this.followingHolds = followingHolds;
            this.junctionThroughBusyHolds = junctionThroughBusyHolds;
            this.noPathHolds = noPathHolds;
            this.decisions = decisions;
            this.tiedDecisions = tiedDecisions;
            this.unreachableDecisions = unreachableDecisions;
            this.peakActiveSegments = peakActiveSegments;
            this.peakEdgeOccupancy = peakEdgeOccupancy;
        }
    }

    private static final class EntryProposal {
        final FengDhBagState bag;
        final int upstreamEdgeId;
        final int downstreamNode;
        final FengDhPolicy.Decision decision;

        EntryProposal(
                FengDhBagState bag,
                int upstreamEdgeId,
                int downstreamNode,
                FengDhPolicy.Decision decision) {
            this.bag = bag;
            this.upstreamEdgeId = upstreamEdgeId;
            this.downstreamNode = downstreamNode;
            this.decision = decision;
        }
    }

    private static final class NodeServiceProposal {
        final FengDhBagState bag;
        final int upstreamEdgeId;
        final int node;
        FengDhBagState blockingBag;

        NodeServiceProposal(FengDhBagState bag, int upstreamEdgeId, int node) {
            this.bag = bag;
            this.upstreamEdgeId = upstreamEdgeId;
            this.node = node;
        }
    }

    private final FengDhEdgeLattice lattice;
    private final FengDhPolicy policy;
    private final ArrayList<FengDhBagState> allSegments;
    private final LinkedHashMap<Long, FengDhBagState> active;
    private final HashMap<Long, FengDhBagState> completedByTask;
    private final HashMap<Integer, FengDhBagState> nodeThroughOccupants;
    private final int rawBagPopulation;
    private int nextReleaseIndex;
    private long tick;
    private long releasedSegments;
    private long enteredSegments;
    private long moveCommits;
    private long stoppedTicks;
    private long holds;
    private long entryStoppedHolds;
    private long entryMovingHolds;
    private long mergeConflictHolds;
    private long followingHolds;
    private long junctionThroughBusyHolds;
    private long noPathHolds;
    private int peakActiveSegments;
    private int peakEdgeOccupancy;

    public FengDhSimulator(
            FengDhEdgeLattice lattice,
            FengDhPolicy policy,
            List<FengDhBagState> segments) {
        this.lattice = lattice;
        this.policy = policy;
        this.allSegments = new ArrayList<FengDhBagState>(segments);
        Collections.sort(this.allSegments, new Comparator<FengDhBagState>() {
            @Override
            public int compare(FengDhBagState left, FengDhBagState right) {
                int byRelease = Long.compare(left.releaseTick, right.releaseTick);
                if (byRelease != 0) {
                    return byRelease;
                }
                int byRaw = Long.compare(left.rawBagId, right.rawBagId);
                if (byRaw != 0) {
                    return byRaw;
                }
                return Integer.compare(left.segmentId, right.segmentId);
            }
        });
        this.active = new LinkedHashMap<Long, FengDhBagState>();
        this.completedByTask = new HashMap<Long, FengDhBagState>();
        this.nodeThroughOccupants = new HashMap<Integer, FengDhBagState>();
        HashMap<Long, Boolean> rawIds = new HashMap<Long, Boolean>();
        HashMap<Long, Boolean> taskIds = new HashMap<Long, Boolean>();
        for (FengDhBagState bag : allSegments) {
            if (taskIds.put(Long.valueOf(bag.taskId), Boolean.TRUE) != null) {
                throw new IllegalArgumentException("duplicate task leg id " + bag.taskId);
            }
            rawIds.put(Long.valueOf(bag.rawBagId), Boolean.TRUE);
        }
        this.rawBagPopulation = rawIds.size();
        this.tick = allSegments.isEmpty() ? 0L : allSegments.get(0).releaseTick;
    }

    public FengDhEdgeLattice getLattice() {
        return lattice;
    }

    public FengDhPolicy getPolicy() {
        return policy;
    }

    public List<FengDhBagState> getAllSegments() {
        return Collections.unmodifiableList(allSegments);
    }

    public long getTick() {
        return tick;
    }

    public RunResult run(RunConfig config) {
        long startTick = tick;
        long idleTicks = 0L;
        String status = "COMPLETE";
        while (completedByTask.size() < allSegments.size()) {
            if (tick >= config.horizonTick) {
                status = "HORIZON_REACHED";
                break;
            }
            if (active.isEmpty() && nextReleaseIndex < allSegments.size()) {
                long nextTick = allSegments.get(nextReleaseIndex).releaseTick;
                if (nextTick > tick) {
                    tick = Math.min(nextTick, config.horizonTick);
                    if (tick >= config.horizonTick) {
                        status = "HORIZON_REACHED";
                        break;
                    }
                }
            }
            long progress = step(config.traceSampleModulo);
            if (progress == 0L) {
                idleTicks++;
                if (idleTicks >= config.deadlockIdleTicks) {
                    status = "DEADLOCK";
                    break;
                }
            } else {
                idleTicks = 0L;
            }
        }
        return new RunResult(
                status,
                startTick,
                tick,
                allSegments.size(),
                completedByTask.size(),
                rawBagPopulation,
                completedRawBagCount(),
                releasedSegments,
                enteredSegments,
                moveCommits,
                stoppedTicks,
                holds,
                entryStoppedHolds,
                entryMovingHolds,
                mergeConflictHolds,
                followingHolds,
                junctionThroughBusyHolds,
                noPathHolds,
                policy.getDecisions(),
                policy.getTiedDecisions(),
                policy.getUnreachableDecisions(),
                peakActiveSegments,
                peakEdgeOccupancy);
    }

    /** Execute one synchronous snapshot-plan-resolve-commit tick. */
    public long step(int traceSampleModulo) {
        long commitTick = tick + 1L;
        long progress = 0L;
        progress += releaseEligible(traceSampleModulo);
        FengDhEdgeLattice.Snapshot snapshot = lattice.snapshot();

        ArrayList<FengDhBagState> edgeCompletions = new ArrayList<FengDhBagState>();
        ArrayList<FengDhBagState> nodeCompletions = new ArrayList<FengDhBagState>();
        ArrayList<FengDhBagState> servicesFinishing = new ArrayList<FengDhBagState>();
        ArrayList<FengDhBagState> throughServicesFinishing =
                new ArrayList<FengDhBagState>();
        ArrayList<FengDhBagState> nodeThroughWaiting = new ArrayList<FengDhBagState>();
        ArrayList<FengDhBagState> internalMoves = new ArrayList<FengDhBagState>();
        ArrayList<FengDhBagState> internalStops = new ArrayList<FengDhBagState>();
        HashMap<Long, Integer> plannedPositions = new HashMap<Long, Integer>();
        HashSet<Long> guaranteedDepartures = new HashSet<Long>();
        HashMap<Integer, ArrayList<EntryProposal>> entriesByEdge =
                new HashMap<Integer, ArrayList<EntryProposal>>();
        HashMap<Integer, ArrayList<NodeServiceProposal>> servicesByNode =
                new HashMap<Integer, ArrayList<NodeServiceProposal>>();

        // Existing edge occupants propose from the frozen beginning-of-tick
        // lattice.  Positive node-through time is physical execution, not a
        // route-score term: a bag first requests the downstream local server.
        for (FengDhEdgeLattice.EdgeData edge : lattice.edges()) {
            for (FengDhBagState bag : lattice.occupantsDownstreamFirst(edge.id)) {
                if (bag.getPositionCell() < edge.cellCount - 1) {
                    continue;
                }
                // The reconstructed transfer is an induction/handoff stage,
                // so reaching the requested destination completes directly:
                // no transfer or map through-time is charged at the goal.
                if (edge.to == bag.goalNode) {
                    edgeCompletions.add(bag);
                    guaranteedDepartures.add(Long.valueOf(bag.taskId));
                    continue;
                }
                FengDhBagState throughOccupant = nodeThroughOccupants.get(
                        Integer.valueOf(edge.to));
                if (throughOccupant == bag) {
                    if (!bag.isNodeServiceReadyAt(commitTick)) {
                        nodeThroughWaiting.add(bag);
                        // A finite, already-started service advances with this
                        // tick even though its retained footprint is stationary.
                        progress++;
                        continue;
                    }
                    throughServicesFinishing.add(bag);
                    guaranteedDepartures.add(Long.valueOf(bag.taskId));
                    continue;
                }
                addNodeService(servicesByNode,
                        new NodeServiceProposal(bag, edge.id, edge.to));
            }
        }

        // Resolve node service admissions before target-edge entries so a
        // zero-time winner supplies the same simultaneous-vacate guarantee as
        // an already-finishing positive service or a goal arrival.
        HashSet<Integer> nodeThroughDepartures = new HashSet<Integer>();
        for (FengDhBagState bag : throughServicesFinishing) {
            nodeThroughDepartures.add(Integer.valueOf(bag.getCurrentNode()));
        }

        LinkedHashMap<Long, NodeServiceProposal> approvedNodeServices =
                new LinkedHashMap<Long, NodeServiceProposal>();
        ArrayList<NodeServiceProposal> blockedNodeServices =
                new ArrayList<NodeServiceProposal>();
        for (Integer nodeValue : sortedNodeIds(servicesByNode)) {
            ArrayList<NodeServiceProposal> proposals = servicesByNode.get(nodeValue);
            Collections.sort(proposals, nodeServiceOrder());
            FengDhBagState occupant = nodeThroughOccupants.get(nodeValue);
            boolean available = occupant == null || nodeThroughDepartures.contains(nodeValue);
            int firstBlocked = 0;
            if (available) {
                NodeServiceProposal winner = proposals.get(0);
                approvedNodeServices.put(Long.valueOf(winner.bag.taskId), winner);
                if (mapThroughTicks(winner.node) == 0L) {
                    guaranteedDepartures.add(Long.valueOf(winner.bag.taskId));
                }
                firstBlocked = 1;
            }
            for (int index = firstBlocked; index < proposals.size(); index++) {
                NodeServiceProposal proposal = proposals.get(index);
                proposal.blockingBag = available ? proposals.get(0).bag : occupant;
                blockedNodeServices.add(proposal);
            }
        }

        // First movement pass supplies post-plan entrance positions.  A second
        // pass below adds every transfer/node admission that conflict
        // resolution proves will vacate its upstream edge in this commit.
        planInternalMovement(
                guaranteedDepartures, plannedPositions, internalMoves, internalStops);

        // Released source bags and completed per-bag transfer timers choose an
        // exit.  Only the map-defined through stage retains the upstream
        // footprint; the fixed transfer delay itself adds no capacity server.
        ArrayList<FengDhBagState> activeSnapshot = new ArrayList<FengDhBagState>(active.values());
        for (FengDhBagState bag : activeSnapshot) {
            if (bag.getStatus() != FengDhBagState.Status.AT_LOADING_OR_JUNCTION) {
                continue;
            }
            if (bag.getCurrentNode() == bag.goalNode) {
                if (bag.isNodeServiceReadyAt(commitTick)) {
                    servicesFinishing.add(bag);
                    nodeCompletions.add(bag);
                } else if (bag.hasNodeServiceStarted()) {
                    progress++;
                }
                continue;
            }
            if (!bag.isNodeServiceReadyAt(commitTick)) {
                if (bag.hasNodeServiceStarted()) {
                    // Count only the finite timer countdown, never repeated
                    // route requests or an already-finished service.
                    progress++;
                }
                continue;
            }
            servicesFinishing.add(bag);
            FengDhPolicy.Decision decision = policy.choose(
                    bag.getCurrentNode(), bag.goalNode, snapshot);
            if (decision == null) {
                holdNodeNoPath(bag, commitTick, traceSampleModulo);
                continue;
            }
            boolean recordTrace = shouldTrace(bag, traceSampleModulo);
            bag.selectEdge(tick, decision.selectedEdgeId,
                    recordTrace ? decision.traceDetail() : "", recordTrace);
            addEntry(entriesByEdge,
                    new EntryProposal(
                            bag, -1, bag.getCurrentNode(), decision));
        }

        // Resolve target-edge entry conflicts using frozen local FIFO keys.
        LinkedHashMap<Long, EntryProposal> approvedEntries =
                new LinkedHashMap<Long, EntryProposal>();
        for (FengDhEdgeLattice.EdgeData target : lattice.edges()) {
            ArrayList<EntryProposal> proposals = entriesByEdge.get(Integer.valueOf(target.id));
            if (proposals == null || proposals.isEmpty()) {
                continue;
            }
            Collections.sort(proposals, entryOrder());
            FengDhEdgeLattice.EntryBlocker blocker = lattice.entryBlockerAfterPlan(
                    target.id, plannedPositions, guaranteedDepartures);
            if (blocker != null) {
                for (EntryProposal proposal : proposals) {
                    holdForBlocker(proposal, blocker, commitTick, traceSampleModulo);
                }
                continue;
            }
            EntryProposal winner = proposals.get(0);
            approvedEntries.put(Long.valueOf(winner.bag.taskId), winner);
            for (int index = 1; index < proposals.size(); index++) {
                holdForMergeConflict(proposals.get(index), winner, commitTick, traceSampleModulo);
            }
        }
        // Any accepted direct edge-transfer proposal vacates its upstream edge.
        for (EntryProposal proposal : approvedEntries.values()) {
            if (proposal.upstreamEdgeId >= 0) {
                guaranteedDepartures.add(Long.valueOf(proposal.bag.taskId));
            }
        }

        // Re-plan followers after every accepted upstream departure is known.
        // This is the simultaneous-vacate rule at edge/node boundaries.
        plannedPositions.clear();
        internalMoves.clear();
        internalStops.clear();
        planInternalMovement(
                guaranteedDepartures, plannedPositions, internalMoves, internalStops);

        // Zero through-time completes in this commit and immediately starts
        // the existing per-bag transfer timer.  Remove its upstream footprint
        // before follower mutations, including a one-cell carrier moving into
        // the exact vacated cell.  Arbitration still uses the frozen snapshot.
        for (NodeServiceProposal proposal : approvedNodeServices.values()) {
            if (mapThroughTicks(proposal.node) != 0L) {
                continue;
            }
            FengDhBagState bag = proposal.bag;
            bag.beginBoundaryService(
                    commitTick,
                    proposal.node,
                    commitTick,
                    "ZERO_MAP_THROUGH_TIME;basis=LEGACY_NODE_CONSTRAINT;"
                            + "upstream_edge=" + proposal.upstreamEdgeId,
                    shouldTrace(bag, traceSampleModulo));
            lattice.remove(proposal.upstreamEdgeId, bag);
            bag.beginNodeService(
                    commitTick,
                    proposal.node,
                    commitTick + reconstructedTransferTicks(),
                    "INTERMEDIATE_FIXED_TRANSFER_DELAY;reconstructed_transfer_seconds="
                            + RECONSTRUCTED_TRANSFER_DURATION_SECONDS
                            + ";basis=HISTORICAL_OD_LOWER_ENVELOPE;upstream_edge="
                            + proposal.upstreamEdgeId,
                    shouldTrace(bag, traceSampleModulo));
            progress++;
        }

        // The same simultaneous-vacate rule also applies to goal arrivals
        // and finishing positive through services.  Keep their state/trace
        // commits below, but release lattice cells before follower moves.
        for (FengDhBagState bag : edgeCompletions) {
            lattice.remove(bag.getCurrentEdgeId(), bag);
        }
        for (FengDhBagState bag : throughServicesFinishing) {
            lattice.remove(bag.getCurrentEdgeId(), bag);
        }

        // Commit internal edge motion.  Snapshot-based following never reads an
        // earlier mutation in this loop, so container order cannot create motion.
        for (FengDhBagState bag : internalMoves) {
            int edgeId = bag.getCurrentEdgeId();
            FengDhEdgeLattice.EdgeData edge = lattice.edge(edgeId);
            int nextPosition = bag.getPositionCell() + 1;
            lattice.move(edgeId, bag, nextPosition);
            bag.moveOnEdge(commitTick, nextPosition, shouldTrace(bag, traceSampleModulo));
            if (nextPosition == edge.cellCount - 1) {
                bag.markDownstreamArrival(commitTick, edge.to);
            }
            moveCommits++;
            progress++;
        }
        for (FengDhBagState bag : internalStops) {
            bag.stopOnEdge(
                    commitTick,
                    "FOLLOWING_FOOTPRINT_BLOCKED",
                    -1,
                    -1,
                    null,
                    shouldTrace(bag, traceSampleModulo));
            stoppedTicks++;
            holds++;
            followingHolds++;
        }
        for (FengDhBagState bag : nodeThroughWaiting) {
            stopPhysicalHandoff(
                    bag, commitTick, "MAP_JUNCTION_THROUGH_SERVICE", traceSampleModulo);
        }
        for (NodeServiceProposal proposal : blockedNodeServices) {
            holdForJunctionThrough(proposal, commitTick, traceSampleModulo);
        }

        // A service whose ready boundary is this commit finishes before its
        // accepted edge entry, or remains at the node when the edge is blocked.
        for (FengDhBagState bag : servicesFinishing) {
            bag.finishNodeService(commitTick, shouldTrace(bag, traceSampleModulo));
        }
        for (FengDhBagState bag : throughServicesFinishing) {
            int node = bag.getCurrentNode();
            int upstreamEdgeId = bag.getCurrentEdgeId();
            bag.finishNodeService(commitTick, shouldTrace(bag, traceSampleModulo));
            FengDhBagState removed = nodeThroughOccupants.remove(Integer.valueOf(node));
            if (removed != bag) {
                throw new IllegalStateException("junction through occupant mismatch at " + node);
            }
            bag.beginNodeService(
                    commitTick,
                    node,
                    commitTick + reconstructedTransferTicks(),
                    "INTERMEDIATE_FIXED_TRANSFER_DELAY;reconstructed_transfer_seconds="
                            + RECONSTRUCTED_TRANSFER_DURATION_SECONDS
                            + ";basis=HISTORICAL_OD_LOWER_ENVELOPE;upstream_edge="
                            + upstreamEdgeId,
                    shouldTrace(bag, traceSampleModulo));
            progress++;
        }

        // Completion and accepted transfers remove upstream occupation first.
        for (FengDhBagState bag : edgeCompletions) {
            bag.complete(commitTick, bag.goalNode, shouldTrace(bag, traceSampleModulo));
            completedByTask.put(Long.valueOf(bag.taskId), bag);
            active.remove(Long.valueOf(bag.taskId));
            progress++;
        }
        for (FengDhBagState bag : nodeCompletions) {
            bag.complete(commitTick, bag.goalNode, shouldTrace(bag, traceSampleModulo));
            completedByTask.put(Long.valueOf(bag.taskId), bag);
            active.remove(Long.valueOf(bag.taskId));
            progress++;
        }
        for (EntryProposal proposal : approvedEntries.values()) {
            FengDhBagState bag = proposal.bag;
            int targetEdgeId = proposal.decision.selectedEdgeId;
            boolean recordTrace = shouldTrace(bag, traceSampleModulo);
            if (proposal.upstreamEdgeId >= 0) {
                lattice.remove(proposal.upstreamEdgeId, bag);
                lattice.enter(targetEdgeId, bag);
                bag.transferEdge(
                        commitTick,
                        proposal.downstreamNode,
                        targetEdgeId,
                        recordTrace ? proposal.decision.traceDetail() : "",
                        recordTrace);
            } else {
                lattice.enter(targetEdgeId, bag);
                boolean firstAdmission = bag.getFirstAdmissionTick() < 0L;
                bag.enterEdge(
                        commitTick,
                        targetEdgeId,
                        firstAdmission,
                        recordTrace ? proposal.decision.traceDetail() : "",
                        recordTrace);
                if (firstAdmission) {
                    enteredSegments++;
                }
            }
            if (lattice.edge(targetEdgeId).cellCount == 1) {
                bag.markDownstreamArrival(commitTick, lattice.edge(targetEdgeId).to);
            }
            moveCommits++;
            progress++;
        }
        for (NodeServiceProposal proposal : approvedNodeServices.values()) {
            FengDhBagState bag = proposal.bag;
            long throughTicks = mapThroughTicks(proposal.node);
            if (throughTicks == 0L) {
                continue; // Completed and released before follower commits.
            }
            double mapThroughSeconds = lattice.nodes().get(
                    Integer.valueOf(proposal.node)).throughTimeSeconds;
            if (throughTicks > 0L) {
                bag.beginBoundaryService(
                        commitTick,
                        proposal.node,
                        commitTick + throughTicks,
                        "MAP_JUNCTION_THROUGH_EXCLUSIVE;map_through_seconds="
                                + mapThroughSeconds
                                + ";basis=LEGACY_NODE_CONSTRAINT;upstream_edge="
                                + proposal.upstreamEdgeId,
                        shouldTrace(bag, traceSampleModulo));
                stopPhysicalHandoff(
                        bag, commitTick, "MAP_JUNCTION_THROUGH_SERVICE", traceSampleModulo);
                FengDhBagState old = nodeThroughOccupants.put(
                        Integer.valueOf(proposal.node), bag);
                if (old != null) {
                    throw new IllegalStateException(
                            "duplicate junction through occupant at " + proposal.node);
                }
            }
            progress++;
        }

        lattice.assertIntegrity();
        peakActiveSegments = Math.max(peakActiveSegments, active.size());
        peakEdgeOccupancy = Math.max(peakEdgeOccupancy, lattice.activeOnEdges());
        tick = commitTick;
        return progress;
    }

    private void planInternalMovement(
            HashSet<Long> guaranteedDepartures,
            HashMap<Long, Integer> plannedPositions,
            ArrayList<FengDhBagState> internalMoves,
            ArrayList<FengDhBagState> internalStops) {
        for (FengDhEdgeLattice.EdgeData edge : lattice.edges()) {
            Integer leaderFinalPosition = null;
            for (FengDhBagState bag : lattice.occupantsDownstreamFirst(edge.id)) {
                int position = bag.getPositionCell();
                if (guaranteedDepartures.contains(Long.valueOf(bag.taskId))) {
                    continue;
                }
                if (position >= edge.cellCount - 1) {
                    plannedPositions.put(Long.valueOf(bag.taskId), Integer.valueOf(position));
                    leaderFinalPosition = Integer.valueOf(position);
                    continue;
                }
                int proposed = position + 1;
                boolean canMove = leaderFinalPosition == null
                        || proposed <= leaderFinalPosition.intValue() - lattice.getFootprintCells();
                int finalPosition = canMove ? proposed : position;
                plannedPositions.put(Long.valueOf(bag.taskId), Integer.valueOf(finalPosition));
                if (canMove) {
                    internalMoves.add(bag);
                } else {
                    internalStops.add(bag);
                }
                leaderFinalPosition = Integer.valueOf(
                        bag.getStatus() == FengDhBagState.Status.STOPPED_ON_EDGE
                                ? position : finalPosition);
            }
        }
    }

    private void stopPhysicalHandoff(
            FengDhBagState bag, long commitTick, String reason, int traceSampleModulo) {
        bag.stopOnEdge(
                commitTick,
                reason,
                -1,
                -1,
                null,
                shouldTrace(bag, traceSampleModulo));
        stoppedTicks++;
        holds++;
    }

    private long mapThroughTicks(int node) {
        FengDhEdgeLattice.NodeData data = lattice.nodes().get(Integer.valueOf(node));
        if (data == null) {
            throw new IllegalArgumentException("unknown service node " + node);
        }
        if (data.throughTimeSeconds < 0.0d) {
            throw new IllegalStateException("negative node service time at " + node);
        }
        return secondsToTicks(data.throughTimeSeconds);
    }

    private static long sourceTransferTicks() {
        return reconstructedTransferTicks();
    }

    private static long reconstructedTransferTicks() {
        return secondsToTicks(RECONSTRUCTED_TRANSFER_DURATION_SECONDS);
    }

    private static long secondsToTicks(double seconds) {
        return (long) Math.ceil(
                seconds / FengDhEdgeLattice.TICK_SECONDS - 1.0e-12d);
    }

    private static ArrayList<Integer> sortedNodeIds(
            HashMap<Integer, ArrayList<NodeServiceProposal>> servicesByNode) {
        ArrayList<Integer> result = new ArrayList<Integer>(servicesByNode.keySet());
        Collections.sort(result);
        return result;
    }

    private long releaseEligible(int traceSampleModulo) {
        long released = 0L;
        while (nextReleaseIndex < allSegments.size()
                && allSegments.get(nextReleaseIndex).releaseTick <= tick) {
            FengDhBagState bag = allSegments.get(nextReleaseIndex++);
            if (bag.getStatus() != FengDhBagState.Status.NOT_RELEASED) {
                if (bag.isCompleted()) {
                    completedByTask.put(Long.valueOf(bag.taskId), bag);
                } else {
                    active.put(Long.valueOf(bag.taskId), bag);
                }
                continue;
            }
            bag.release(tick, shouldTrace(bag, traceSampleModulo));
            bag.beginNodeService(
                    tick,
                    bag.startNode,
                    tick + sourceTransferTicks(),
                    "SOURCE_FIXED_TRANSFER;reconstructed_transfer_seconds="
                            + RECONSTRUCTED_TRANSFER_DURATION_SECONDS
                            + ";basis=HISTORICAL_OD_LOWER_ENVELOPE",
                    shouldTrace(bag, traceSampleModulo));
            active.put(Long.valueOf(bag.taskId), bag);
            releasedSegments++;
            released++;
        }
        return released;
    }

    private int completedRawBagCount() {
        HashMap<Long, Integer> counts = new HashMap<Long, Integer>();
        for (FengDhBagState bag : allSegments) {
            if (bag.isCompleted()) {
                Integer old = counts.get(Long.valueOf(bag.rawBagId));
                counts.put(Long.valueOf(bag.rawBagId), Integer.valueOf(old == null ? 1 : old + 1));
            }
        }
        int complete = 0;
        for (FengDhBagState bag : allSegments) {
            if (bag.segmentId == 0) {
                Integer count = counts.get(Long.valueOf(bag.rawBagId));
                if (count != null && count.intValue() == bag.segmentCount) {
                    complete++;
                }
            }
        }
        return complete;
    }

    private void stopNoPath(
            FengDhBagState bag, long commitTick, int node, int traceSampleModulo) {
        bag.stopOnEdge(
                commitTick,
                "NO_REACHABLE_CONTINUATION_AT_NODE_" + node,
                -1,
                -1,
                null,
                shouldTrace(bag, traceSampleModulo));
        stoppedTicks++;
        holds++;
        noPathHolds++;
    }

    private void holdNodeNoPath(
            FengDhBagState bag, long commitTick, int traceSampleModulo) {
        bag.holdAtNode(
                commitTick,
                "NO_REACHABLE_CONTINUATION",
                -1,
                -1,
                null,
                shouldTrace(bag, traceSampleModulo));
        holds++;
        noPathHolds++;
    }

    private void holdForBlocker(
            EntryProposal proposal,
            FengDhEdgeLattice.EntryBlocker blocker,
            long commitTick,
            int traceSampleModulo) {
        FengDhBagState.Status state = blocker.bag.getStatus();
        String reason;
        if (state == FengDhBagState.Status.STOPPED_ON_EDGE) {
            reason = "ENTRY_STOPPED_OCCUPANT";
            entryStoppedHolds++;
        } else {
            reason = "ENTRY_MOVING_OCCUPANT_SNAPSHOT_GAP";
            entryMovingHolds++;
        }
        hold(proposal, commitTick, reason, (int) blocker.bag.taskId, state, traceSampleModulo);
    }

    private void holdForMergeConflict(
            EntryProposal loser,
            EntryProposal winner,
            long commitTick,
            int traceSampleModulo) {
        mergeConflictHolds++;
        hold(loser, commitTick, "LOCAL_FIFO_ENTRY_CONFLICT", (int) winner.bag.taskId,
                winner.bag.getStatus(), traceSampleModulo);
    }

    private void holdForJunctionThrough(
            NodeServiceProposal proposal, long commitTick, int traceSampleModulo) {
        FengDhBagState blocker = proposal.blockingBag;
        proposal.bag.stopOnEdge(
                commitTick,
                "JUNCTION_THROUGH_BUSY",
                -1,
                blocker == null ? -1 : (int) blocker.taskId,
                blocker == null ? null : blocker.getStatus(),
                shouldTrace(proposal.bag, traceSampleModulo));
        stoppedTicks++;
        holds++;
        junctionThroughBusyHolds++;
    }

    private void hold(
            EntryProposal proposal,
            long commitTick,
            String reason,
            int occupant,
            FengDhBagState.Status occupantStatus,
            int traceSampleModulo) {
        FengDhBagState bag = proposal.bag;
        if (proposal.upstreamEdgeId >= 0) {
            bag.stopOnEdge(
                    commitTick,
                    reason,
                    proposal.decision.selectedEdgeId,
                    occupant,
                    occupantStatus,
                    shouldTrace(bag, traceSampleModulo));
            stoppedTicks++;
        } else {
            bag.holdAtNode(
                    commitTick,
                    reason,
                    proposal.decision.selectedEdgeId,
                    occupant,
                    occupantStatus,
                    shouldTrace(bag, traceSampleModulo));
        }
        holds++;
    }

    private static void addEntry(
            HashMap<Integer, ArrayList<EntryProposal>> entriesByEdge,
            EntryProposal proposal) {
        Integer key = Integer.valueOf(proposal.decision.selectedEdgeId);
        ArrayList<EntryProposal> values = entriesByEdge.get(key);
        if (values == null) {
            values = new ArrayList<EntryProposal>();
            entriesByEdge.put(key, values);
        }
        values.add(proposal);
    }

    private static void addNodeService(
            HashMap<Integer, ArrayList<NodeServiceProposal>> servicesByNode,
            NodeServiceProposal proposal) {
        Integer key = Integer.valueOf(proposal.node);
        ArrayList<NodeServiceProposal> values = servicesByNode.get(key);
        if (values == null) {
            values = new ArrayList<NodeServiceProposal>();
            servicesByNode.put(key, values);
        }
        values.add(proposal);
    }

    private static Comparator<EntryProposal> entryOrder() {
        return new Comparator<EntryProposal>() {
            @Override
            public int compare(EntryProposal left, EntryProposal right) {
                int byArrival = Long.compare(
                        left.bag.getNodeArrivalTick(), right.bag.getNodeArrivalTick());
                if (byArrival != 0) {
                    return byArrival;
                }
                int byRelease = Long.compare(left.bag.releaseTick, right.bag.releaseTick);
                if (byRelease != 0) {
                    return byRelease;
                }
                int byTask = Long.compare(left.bag.taskId, right.bag.taskId);
                if (byTask != 0) {
                    return byTask;
                }
                return Integer.compare(left.upstreamEdgeId, right.upstreamEdgeId);
            }
        };
    }

    private static Comparator<NodeServiceProposal> nodeServiceOrder() {
        return new Comparator<NodeServiceProposal>() {
            @Override
            public int compare(NodeServiceProposal left, NodeServiceProposal right) {
                int byArrival = Long.compare(
                        left.bag.getNodeArrivalTick(), right.bag.getNodeArrivalTick());
                if (byArrival != 0) {
                    return byArrival;
                }
                int byRelease = Long.compare(left.bag.releaseTick, right.bag.releaseTick);
                if (byRelease != 0) {
                    return byRelease;
                }
                int byTask = Long.compare(left.bag.taskId, right.bag.taskId);
                if (byTask != 0) {
                    return byTask;
                }
                return Integer.compare(left.upstreamEdgeId, right.upstreamEdgeId);
            }
        };
    }

    private static boolean shouldTrace(FengDhBagState bag, int traceSampleModulo) {
        return traceSampleModulo > 0
                && Math.floorMod(bag.rawBagId, (long) traceSampleModulo) == 0L;
    }
}
