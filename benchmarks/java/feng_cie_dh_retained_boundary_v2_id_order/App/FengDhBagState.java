package App;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Mutable state for one historical task leg in the Feng paper-environment
 * reconstruction.  A raw bag can have one direct leg, or two EBS legs.  The
 * simulator owns every mutation; identifiers and business times are immutable.
 */
public final class FengDhBagState {
    public enum Status {
        NOT_RELEASED,
        AT_LOADING_OR_JUNCTION,
        MOVING_ON_EDGE,
        STOPPED_ON_EDGE,
        COMPLETED
    }

    public static final class TraceEvent {
        public final long tick;
        public final String event;
        public final int node;
        public final int edgeId;
        public final int positionCell;
        public final String detail;

        TraceEvent(long tick, String event, int node, int edgeId, int positionCell, String detail) {
            this.tick = tick;
            this.event = event;
            this.node = node;
            this.edgeId = edgeId;
            this.positionCell = positionCell;
            this.detail = detail == null ? "" : detail;
        }
    }

    public final long taskId;
    public final long rawBagId;
    public final int segmentId;
    public final int segmentCount;
    public final double rawEntrySeconds;
    public final double releaseSeconds;
    public final long releaseTick;
    public final double deadlineSeconds;
    public final int startNode;
    public final int goalNode;
    public final boolean ebsSegment;
    public final String sourceRow;

    private Status status;
    private Status previousStatus;
    private int currentNode;
    private int currentEdgeId;
    private int positionCell;
    private int chosenOutgoingEdgeId;
    private long nodeArrivalTick;
    private long edgeEntryTick;
    private long firstAdmissionTick;
    private long completionTick;
    private long nodeServiceStartTick;
    private long nodeServiceReadyTick;
    private boolean nodeServiceFinished;
    private boolean retainedBoundaryTransfer;
    private long movingTicks;
    private long stoppedTicks;
    private long holdCount;
    private String lastHoldReason;
    private int lastEntryOccupant;
    private Status lastEntryOccupantStatus;
    private long retryTick;
    private final ArrayList<TraceEvent> trace;

    public FengDhBagState(
            long taskId,
            long rawBagId,
            int segmentId,
            int segmentCount,
            double rawEntrySeconds,
            double releaseSeconds,
            long releaseTick,
            double deadlineSeconds,
            int startNode,
            int goalNode,
            boolean ebsSegment,
            String sourceRow) {
        if (segmentId < 0 || segmentId >= segmentCount) {
            throw new IllegalArgumentException("segmentId must be in [0, segmentCount)");
        }
        this.taskId = taskId;
        this.rawBagId = rawBagId;
        this.segmentId = segmentId;
        this.segmentCount = segmentCount;
        this.rawEntrySeconds = rawEntrySeconds;
        this.releaseSeconds = releaseSeconds;
        this.releaseTick = releaseTick;
        this.deadlineSeconds = deadlineSeconds;
        this.startNode = startNode;
        this.goalNode = goalNode;
        this.ebsSegment = ebsSegment;
        this.sourceRow = sourceRow == null ? "" : sourceRow;
        this.status = Status.NOT_RELEASED;
        this.previousStatus = Status.NOT_RELEASED;
        this.currentNode = startNode;
        this.currentEdgeId = -1;
        this.positionCell = -1;
        this.chosenOutgoingEdgeId = -1;
        this.nodeArrivalTick = releaseTick;
        this.edgeEntryTick = -1L;
        this.firstAdmissionTick = -1L;
        this.completionTick = -1L;
        this.nodeServiceStartTick = -1L;
        this.nodeServiceReadyTick = -1L;
        this.nodeServiceFinished = false;
        this.lastHoldReason = "";
        this.lastEntryOccupant = -1;
        this.lastEntryOccupantStatus = null;
        this.retryTick = -1L;
        this.trace = new ArrayList<TraceEvent>();
    }

    public Status getStatus() {
        return status;
    }

    public Status getPreviousStatus() {
        return previousStatus;
    }

    public int getCurrentNode() {
        return currentNode;
    }

    public int getCurrentEdgeId() {
        return currentEdgeId;
    }

    public int getPositionCell() {
        return positionCell;
    }

    public int getChosenOutgoingEdgeId() {
        return chosenOutgoingEdgeId;
    }

    public long getNodeArrivalTick() {
        return nodeArrivalTick;
    }

    public long getEdgeEntryTick() {
        return edgeEntryTick;
    }

    public long getFirstAdmissionTick() {
        return firstAdmissionTick;
    }

    public long getCompletionTick() {
        return completionTick;
    }

    public long getNodeServiceStartTick() {
        return nodeServiceStartTick;
    }

    public long getNodeServiceReadyTick() {
        return nodeServiceReadyTick;
    }

    public boolean hasNodeServiceStarted() {
        return nodeServiceStartTick >= 0L;
    }

    public boolean isRetainedBoundaryTransfer() {
        return retainedBoundaryTransfer;
    }

    public boolean isNodeServiceReadyAt(long tick) {
        return nodeServiceStartTick >= 0L && tick >= nodeServiceReadyTick;
    }

    public long getMovingTicks() {
        return movingTicks;
    }

    public long getStoppedTicks() {
        return stoppedTicks;
    }

    public long getHoldCount() {
        return holdCount;
    }

    public String getLastHoldReason() {
        return lastHoldReason;
    }

    public int getLastEntryOccupant() {
        return lastEntryOccupant;
    }

    public Status getLastEntryOccupantStatus() {
        return lastEntryOccupantStatus;
    }

    public long getRetryTick() {
        return retryTick;
    }

    public boolean isCompleted() {
        return status == Status.COMPLETED;
    }

    public List<TraceEvent> getTrace() {
        return Collections.unmodifiableList(trace);
    }

    void release(long tick, boolean recordTrace) {
        require(status == Status.NOT_RELEASED, "release requires NOT_RELEASED");
        previousStatus = status;
        status = Status.AT_LOADING_OR_JUNCTION;
        currentNode = startNode;
        nodeArrivalTick = tick;
        if (recordTrace) {
            addTrace(tick, "RELEASE", currentNode, -1, -1, "release_seconds=" + releaseSeconds);
        }
    }

    void selectEdge(long tick, int edgeId, String detail, boolean recordTrace) {
        chosenOutgoingEdgeId = edgeId;
        if (recordTrace) {
            addTrace(tick, "SELECT", currentNode, edgeId, positionCell, detail);
        }
    }

    void enterEdge(long tick, int edgeId, boolean firstAdmission, String detail, boolean recordTrace) {
        previousStatus = status;
        status = Status.MOVING_ON_EDGE;
        currentEdgeId = edgeId;
        positionCell = 0;
        edgeEntryTick = tick;
        movingTicks++;
        lastHoldReason = "";
        retryTick = -1L;
        clearNodeService();
        if (firstAdmission && firstAdmissionTick < 0L) {
            firstAdmissionTick = tick;
        }
        if (recordTrace) {
            addTrace(tick, "ENTER_EDGE", currentNode, edgeId, 0, detail);
        }
    }

    void moveOnEdge(long tick, int newPositionCell, boolean recordTrace) {
        require(status == Status.MOVING_ON_EDGE || status == Status.STOPPED_ON_EDGE,
                "edge move requires an edge state");
        require(newPositionCell > positionCell, "edge move must advance");
        previousStatus = status;
        status = Status.MOVING_ON_EDGE;
        positionCell = newPositionCell;
        movingTicks++;
        lastHoldReason = "";
        retryTick = -1L;
        if (recordTrace) {
            addTrace(tick, "MOVE", currentNode, currentEdgeId, positionCell, "");
        }
    }

    void markDownstreamArrival(long tick, int downstreamNode) {
        nodeArrivalTick = tick;
        currentNode = downstreamNode;
    }

    void stopOnEdge(
            long tick,
            String reason,
            int selectedEdge,
            int entryOccupant,
            Status entryOccupantStatus,
            boolean recordTrace) {
        require(status == Status.MOVING_ON_EDGE || status == Status.STOPPED_ON_EDGE,
                "edge stop requires an edge state");
        previousStatus = status;
        status = Status.STOPPED_ON_EDGE;
        stoppedTicks++;
        holdCount++;
        lastHoldReason = reason == null ? "BLOCKED" : reason;
        chosenOutgoingEdgeId = selectedEdge;
        lastEntryOccupant = entryOccupant;
        lastEntryOccupantStatus = entryOccupantStatus;
        retryTick = tick + 1L;
        if (recordTrace) {
            addTrace(tick, "HOLD", currentNode, selectedEdge, positionCell,
                    holdDetail(lastHoldReason, entryOccupant, entryOccupantStatus, retryTick));
        }
    }

    void holdAtNode(
            long tick,
            String reason,
            int selectedEdge,
            int entryOccupant,
            Status entryOccupantStatus,
            boolean recordTrace) {
        require(status == Status.AT_LOADING_OR_JUNCTION,
                "node hold requires AT_LOADING_OR_JUNCTION");
        previousStatus = status;
        status = Status.AT_LOADING_OR_JUNCTION;
        holdCount++;
        lastHoldReason = reason == null ? "BLOCKED" : reason;
        chosenOutgoingEdgeId = selectedEdge;
        lastEntryOccupant = entryOccupant;
        lastEntryOccupantStatus = entryOccupantStatus;
        retryTick = tick + 1L;
        if (recordTrace) {
            addTrace(tick, "HOLD", currentNode, selectedEdge, -1,
                    holdDetail(lastHoldReason, entryOccupant, entryOccupantStatus, retryTick));
        }
    }

    void transferEdge(long tick, int downstreamNode, int nextEdgeId, String detail, boolean recordTrace) {
        require(status == Status.MOVING_ON_EDGE || status == Status.STOPPED_ON_EDGE,
                "edge transfer requires an edge state");
        previousStatus = status;
        status = Status.MOVING_ON_EDGE;
        currentNode = downstreamNode;
        currentEdgeId = nextEdgeId;
        chosenOutgoingEdgeId = nextEdgeId;
        positionCell = 0;
        edgeEntryTick = tick;
        movingTicks++;
        lastHoldReason = "";
        retryTick = -1L;
        clearNodeService();
        if (recordTrace) {
            addTrace(tick, "TRANSFER", downstreamNode, nextEdgeId, 0, detail);
        }
    }

    void complete(long tick, int goal, boolean recordTrace) {
        require(goal == goalNode, "completion node must be the goal");
        previousStatus = status;
        status = Status.COMPLETED;
        currentNode = goal;
        currentEdgeId = -1;
        positionCell = -1;
        completionTick = tick;
        clearNodeService();
        if (firstAdmissionTick < 0L) {
            firstAdmissionTick = tick;
        }
        if (recordTrace) {
            addTrace(tick, "COMPLETE", goal, -1, -1, "");
        }
    }

    void beginNodeService(
            long tick,
            int node,
            long readyTick,
            String detail,
            boolean recordTrace) {
        require(status == Status.AT_LOADING_OR_JUNCTION
                        || status == Status.MOVING_ON_EDGE
                        || status == Status.STOPPED_ON_EDGE,
                "node service admission requires a node or edge state");
        require(readyTick >= tick, "node service cannot finish before it starts");
        previousStatus = status;
        status = Status.AT_LOADING_OR_JUNCTION;
        currentNode = node;
        currentEdgeId = -1;
        positionCell = -1;
        chosenOutgoingEdgeId = -1;
        nodeServiceStartTick = tick;
        nodeServiceReadyTick = readyTick;
        nodeServiceFinished = readyTick == tick;
        lastHoldReason = "";
        retryTick = -1L;
        if (recordTrace) {
            addTrace(tick, "NODE_SERVICE_START", node, -1, -1,
                    "arrival_tick=" + nodeArrivalTick + ";ready_tick=" + readyTick
                            + (detail == null || detail.isEmpty() ? "" : ";" + detail));
            if (nodeServiceFinished) {
                addTrace(tick, "NODE_SERVICE_FINISH", node, -1, -1, "");
            }
        }
    }

    /** Start a physical handoff stage without removing the bag's edge footprint. */
    void beginBoundaryService(
            long tick,
            int node,
            long readyTick,
            String detail,
            boolean recordTrace) {
        require(status == Status.MOVING_ON_EDGE || status == Status.STOPPED_ON_EDGE,
                "boundary service admission requires an edge state");
        require(readyTick >= tick, "boundary service cannot finish before it starts");
        require(!hasNodeServiceStarted(),
                "duplicate boundary service for task " + taskId + " at node " + node
                        + "; existing_start=" + nodeServiceStartTick
                        + "; existing_ready=" + nodeServiceReadyTick);
        previousStatus = status;
        currentNode = node;
        chosenOutgoingEdgeId = -1;
        nodeServiceStartTick = tick;
        nodeServiceReadyTick = readyTick;
        nodeServiceFinished = readyTick == tick;
        lastHoldReason = "";
        retryTick = -1L;
        if (recordTrace) {
            addTrace(tick, "NODE_SERVICE_START", node, currentEdgeId, positionCell,
                    "arrival_tick=" + nodeArrivalTick + ";ready_tick=" + readyTick
                            + (detail == null || detail.isEmpty() ? "" : ";" + detail));
            if (nodeServiceFinished) {
                addTrace(tick, "NODE_SERVICE_FINISH", node, currentEdgeId, positionCell, "");
            }
        }
    }

    void finishNodeService(long tick, boolean recordTrace) {
        require(status == Status.AT_LOADING_OR_JUNCTION
                        || status == Status.MOVING_ON_EDGE
                        || status == Status.STOPPED_ON_EDGE,
                "node service completion requires a node or boundary state");
        require(nodeServiceStartTick >= 0L && tick >= nodeServiceReadyTick,
                "node service completion precedes ready tick");
        if (!nodeServiceFinished) {
            nodeServiceFinished = true;
            if (recordTrace) {
                addTrace(tick, "NODE_SERVICE_FINISH", currentNode,
                        currentEdgeId, positionCell, "");
            }
        }
    }

    /** A per-bag transfer stage keeps its incoming-edge footprint until entry. */
    void beginRetainedBoundaryTransfer(long tick, long readyTick, String detail, boolean recordTrace) {
        require(status == Status.MOVING_ON_EDGE || status == Status.STOPPED_ON_EDGE,
                "retained transfer requires an edge state");
        require(hasNodeServiceStarted() && nodeServiceFinished && !retainedBoundaryTransfer,
                "retained transfer requires one completed through stage and cannot restart");
        require(readyTick >= tick, "retained transfer cannot finish before it starts");
        retainedBoundaryTransfer = true;
        nodeServiceStartTick = tick;
        nodeServiceReadyTick = readyTick;
        nodeServiceFinished = readyTick == tick;
        chosenOutgoingEdgeId = -1;
        if (recordTrace) {
            addTrace(tick, "NODE_SERVICE_START", currentNode, currentEdgeId, positionCell,
                    "arrival_tick=" + nodeArrivalTick + ";ready_tick=" + readyTick + ";" + detail);
        }
    }

    private void clearNodeService() {
        nodeServiceStartTick = -1L;
        nodeServiceReadyTick = -1L;
        nodeServiceFinished = false;
        retainedBoundaryTransfer = false;
    }

    private void addTrace(long tick, String event, int node, int edgeId, int position, String detail) {
        trace.add(new TraceEvent(tick, event, node, edgeId, position, detail));
    }

    private static String holdDetail(
            String reason, int entryOccupant, Status entryOccupantStatus, long retryTick) {
        return "reason=" + reason
                + ";entry_occupant=" + entryOccupant
                + ";entry_occupant_state="
                + (entryOccupantStatus == null ? "NONE" : entryOccupantStatus.name())
                + ";retry_tick=" + retryTick;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
