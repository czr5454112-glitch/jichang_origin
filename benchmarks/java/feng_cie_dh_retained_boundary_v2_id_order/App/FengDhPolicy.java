package App;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.PriorityQueue;

/**
 * CIE-DH local route choice: free-flow continuation plus penalties for bags
 * physically moving or stopped on the candidate continuation at tick start.
 */
public final class FengDhPolicy {
    public static final class Path {
        public final List<Integer> nodeIds;
        public final List<Integer> edgeIds;
        public final double freeFlowSeconds;

        Path(List<Integer> nodeIds, List<Integer> edgeIds, double freeFlowSeconds) {
            this.nodeIds = Collections.unmodifiableList(new ArrayList<Integer>(nodeIds));
            this.edgeIds = Collections.unmodifiableList(new ArrayList<Integer>(edgeIds));
            this.freeFlowSeconds = freeFlowSeconds;
        }
    }

    public static final class Decision {
        public final int selectedEdgeId;
        public final Path continuation;
        public final int movingBags;
        public final int stoppedBags;
        public final double etaSeconds;
        public final int equalScoreCandidateCount;

        Decision(
                int selectedEdgeId,
                Path continuation,
                int movingBags,
                int stoppedBags,
                double etaSeconds,
                int equalScoreCandidateCount) {
            this.selectedEdgeId = selectedEdgeId;
            this.continuation = continuation;
            this.movingBags = movingBags;
            this.stoppedBags = stoppedBags;
            this.etaSeconds = etaSeconds;
            this.equalScoreCandidateCount = equalScoreCandidateCount;
        }

        public String traceDetail() {
            return "free_flow_seconds=" + continuation.freeFlowSeconds
                    + ";moving=" + movingBags
                    + ";stopped=" + stoppedBags
                    + ";eta_seconds=" + etaSeconds
                    + ";equal_score_candidates=" + equalScoreCandidateCount
                    + ";nodes=" + join(continuation.nodeIds);
        }
    }

    private static final class Label {
        final int node;
        final double distance;
        final ArrayList<Integer> nodes;
        final ArrayList<Integer> edges;

        Label(int node, double distance, ArrayList<Integer> nodes, ArrayList<Integer> edges) {
            this.node = node;
            this.distance = distance;
            this.nodes = nodes;
            this.edges = edges;
        }
    }

    private static final double EPSILON = 1.0e-9d;
    private final FengDhEdgeLattice lattice;
    private final double alphaMoveSeconds;
    private final double betaStopSeconds;
    private final HashMap<Long, Path> shortestPathCache;
    private final HashMap<Long, List<Path>> candidatePathCache;
    private final HashMap<Long, Decision> snapshotDecisionCache;
    private FengDhEdgeLattice.Snapshot cachedSnapshot;
    private long decisions;
    private long unreachableDecisions;
    private long tiedDecisions;

    public FengDhPolicy(
            FengDhEdgeLattice lattice,
            double alphaMoveSeconds,
            double betaStopSeconds) {
        if (alphaMoveSeconds < 0.0d) {
            throw new IllegalArgumentException("moving penalty must be nonnegative");
        }
        boolean staticFreeFlowControl = alphaMoveSeconds == 0.0d
                && betaStopSeconds == 0.0d;
        if (!staticFreeFlowControl && !(betaStopSeconds > alphaMoveSeconds)) {
            throw new IllegalArgumentException(
                    "stopped penalty must exceed moving penalty except in the exact 0/0 static control");
        }
        this.lattice = lattice;
        this.alphaMoveSeconds = alphaMoveSeconds;
        this.betaStopSeconds = betaStopSeconds;
        this.shortestPathCache = new HashMap<Long, Path>();
        this.candidatePathCache = new HashMap<Long, List<Path>>();
        this.snapshotDecisionCache = new HashMap<Long, Decision>();
    }

    public double getAlphaMoveSeconds() {
        return alphaMoveSeconds;
    }

    public double getBetaStopSeconds() {
        return betaStopSeconds;
    }

    public long getDecisions() {
        return decisions;
    }

    public long getUnreachableDecisions() {
        return unreachableDecisions;
    }

    public long getTiedDecisions() {
        return tiedDecisions;
    }

    public Decision choose(
            int currentNode,
            int goalNode,
            FengDhEdgeLattice.Snapshot snapshot) {
        decisions++;
        if (currentNode == goalNode) {
            return null;
        }
        // Scores depend only on this immutable tick-start snapshot and the OD.
        // Keep logical request/tie/unreachable counters on every cache hit.
        if (snapshot != cachedSnapshot) {
            snapshotDecisionCache.clear();
            cachedSnapshot = snapshot;
        }
        Long key = Long.valueOf(pairKey(currentNode, goalNode));
        if (snapshotDecisionCache.containsKey(key)) {
            Decision cached = snapshotDecisionCache.get(key);
            if (cached == null) {
                unreachableDecisions++;
            } else if (cached.equalScoreCandidateCount > 1) {
                tiedDecisions++;
            }
            return cached;
        }
        ArrayList<Decision> candidates = new ArrayList<Decision>();
        for (Path continuation : candidatePaths(currentNode, goalNode)) {
            int moving = 0;
            int stopped = 0;
            for (Integer edgeId : continuation.edgeIds) {
                moving += snapshot.movingCount(edgeId.intValue());
                stopped += snapshot.stoppedCount(edgeId.intValue());
            }
            double eta = continuation.freeFlowSeconds
                    + alphaMoveSeconds * moving
                    + betaStopSeconds * stopped;
            candidates.add(new Decision(continuation.edgeIds.get(0).intValue(),
                    continuation, moving, stopped, eta, 1));
        }
        if (candidates.isEmpty()) {
            unreachableDecisions++;
            snapshotDecisionCache.put(key, null);
            return null;
        }
        Collections.sort(candidates, new Comparator<Decision>() {
            @Override
            public int compare(Decision left, Decision right) {
                int byScore = compareDouble(left.etaSeconds, right.etaSeconds);
                if (byScore != 0) {
                    return byScore;
                }
                int byPath = compareIntegerLists(
                        left.continuation.nodeIds, right.continuation.nodeIds);
                if (byPath != 0) {
                    return byPath;
                }
                return Integer.compare(left.selectedEdgeId, right.selectedEdgeId);
            }
        });
        Decision best = candidates.get(0);
        int equal = 0;
        for (Decision candidate : candidates) {
            if (Math.abs(candidate.etaSeconds - best.etaSeconds) <= EPSILON) {
                equal++;
            }
        }
        if (equal > 1) {
            tiedDecisions++;
        }
        Decision selected = new Decision(
                best.selectedEdgeId,
                best.continuation,
                best.movingBags,
                best.stoppedBags,
                best.etaSeconds,
                equal);
        snapshotDecisionCache.put(key, selected);
        return selected;
    }

    /** Static topology paths keep the original outgoing-edge iteration order. */
    private List<Path> candidatePaths(int currentNode, int goalNode) {
        Long key = Long.valueOf(pairKey(currentNode, goalNode));
        List<Path> cached = candidatePathCache.get(key);
        if (cached != null) {
            return cached;
        }
        ArrayList<Path> paths = new ArrayList<Path>();
        for (FengDhEdgeLattice.EdgeData first : lattice.outgoing(currentNode)) {
            Path suffix = shortestPath(first.to, goalNode);
            if (suffix == null) {
                continue;
            }
            ArrayList<Integer> nodes = new ArrayList<Integer>();
            nodes.add(Integer.valueOf(currentNode));
            nodes.addAll(suffix.nodeIds);
            ArrayList<Integer> edges = new ArrayList<Integer>();
            edges.add(Integer.valueOf(first.id));
            edges.addAll(suffix.edgeIds);
            paths.add(new Path(nodes, edges,
                    first.freeFlowSeconds() + suffix.freeFlowSeconds));
        }
        List<Path> frozen = Collections.unmodifiableList(paths);
        candidatePathCache.put(key, frozen);
        return frozen;
    }

    /** Free-flow shortest continuation with lexicographic full-node tie breaking. */
    public Path shortestPath(int start, int goal) {
        if (start == goal) {
            ArrayList<Integer> nodes = new ArrayList<Integer>();
            nodes.add(Integer.valueOf(start));
            return new Path(nodes, Collections.<Integer>emptyList(), 0.0d);
        }
        long key = pairKey(start, goal);
        if (shortestPathCache.containsKey(Long.valueOf(key))) {
            return shortestPathCache.get(Long.valueOf(key));
        }
        Comparator<Label> ordering = new Comparator<Label>() {
            @Override
            public int compare(Label left, Label right) {
                int byDistance = compareDouble(left.distance, right.distance);
                if (byDistance != 0) {
                    return byDistance;
                }
                return compareIntegerLists(left.nodes, right.nodes);
            }
        };
        PriorityQueue<Label> queue = new PriorityQueue<Label>(ordering);
        HashMap<Integer, Label> best = new HashMap<Integer, Label>();
        ArrayList<Integer> initialNodes = new ArrayList<Integer>();
        initialNodes.add(Integer.valueOf(start));
        Label initial = new Label(start, 0.0d, initialNodes, new ArrayList<Integer>());
        queue.add(initial);
        best.put(Integer.valueOf(start), initial);
        Path answer = null;
        while (!queue.isEmpty()) {
            Label current = queue.poll();
            if (best.get(Integer.valueOf(current.node)) != current) {
                continue;
            }
            if (current.node == goal) {
                answer = new Path(current.nodes, current.edges, current.distance);
                break;
            }
            for (FengDhEdgeLattice.EdgeData edge : lattice.outgoing(current.node)) {
                double distance = current.distance + edge.freeFlowSeconds();
                ArrayList<Integer> nodes = new ArrayList<Integer>(current.nodes);
                nodes.add(Integer.valueOf(edge.to));
                ArrayList<Integer> edges = new ArrayList<Integer>(current.edges);
                edges.add(Integer.valueOf(edge.id));
                Label proposal = new Label(edge.to, distance, nodes, edges);
                Label old = best.get(Integer.valueOf(edge.to));
                if (old == null || ordering.compare(proposal, old) < 0) {
                    best.put(Integer.valueOf(edge.to), proposal);
                    queue.add(proposal);
                }
            }
        }
        shortestPathCache.put(Long.valueOf(key), answer);
        return answer;
    }

    private static int compareDouble(double left, double right) {
        if (Math.abs(left - right) <= EPSILON) {
            return 0;
        }
        return left < right ? -1 : 1;
    }

    private static int compareIntegerLists(List<Integer> left, List<Integer> right) {
        int count = Math.min(left.size(), right.size());
        for (int i = 0; i < count; i++) {
            int value = Integer.compare(left.get(i).intValue(), right.get(i).intValue());
            if (value != 0) {
                return value;
            }
        }
        return Integer.compare(left.size(), right.size());
    }

    private static String join(List<Integer> values) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < values.size(); i++) {
            if (i > 0) {
                result.append('>');
            }
            result.append(values.get(i).intValue());
        }
        return result.toString();
    }

    private static long pairKey(int start, int goal) {
        return (((long) start) << 32) ^ (goal & 0xffffffffL);
    }
}
