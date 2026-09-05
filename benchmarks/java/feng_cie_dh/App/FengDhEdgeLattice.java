package App;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/**
 * Directed Feng map plus position-level edge occupation.  A bag position is
 * the leading reference point on a 0.5 m lattice.  The historical carrier
 * length plus safety distance is enforced as a minimum spacing between those
 * reference points.
 */
public final class FengDhEdgeLattice {
    public static final double TICK_SECONDS = 0.2d;
    public static final double DEFAULT_SPEED_METERS_PER_SECOND = 2.5d;
    public static final double CELL_METERS = TICK_SECONDS * DEFAULT_SPEED_METERS_PER_SECOND;

    public static final class NodeData {
        public final int id;
        public final int type;
        public final double throughTimeSeconds;
        public final int y;
        public final int x;

        public NodeData(int id, int type, double throughTimeSeconds, int y, int x) {
            this.id = id;
            this.type = type;
            this.throughTimeSeconds = throughTimeSeconds;
            this.y = y;
            this.x = x;
        }
    }

    public static final class EdgeData {
        public final int id;
        public final int from;
        public final int to;
        public final double lengthMeters;
        public final double speedMetersPerSecond;
        public final int cellCount;

        EdgeData(
                int id,
                int from,
                int to,
                double lengthMeters,
                double speedMetersPerSecond) {
            if (lengthMeters <= 0.0d || speedMetersPerSecond <= 0.0d) {
                throw new IllegalArgumentException("edge length and speed must be positive");
            }
            this.id = id;
            this.from = from;
            this.to = to;
            this.lengthMeters = lengthMeters;
            this.speedMetersPerSecond = speedMetersPerSecond;
            this.cellCount = Math.max(1, (int) Math.ceil(lengthMeters / CELL_METERS - 1.0e-12d));
        }

        public double freeFlowSeconds() {
            return lengthMeters / speedMetersPerSecond;
        }
    }

    public static final class OccupantSnapshot {
        public final long taskId;
        public final int positionCell;
        public final FengDhBagState.Status status;

        OccupantSnapshot(long taskId, int positionCell, FengDhBagState.Status status) {
            this.taskId = taskId;
            this.positionCell = positionCell;
            this.status = status;
        }
    }

    public static final class EntryBlocker {
        public final FengDhBagState bag;
        public final int positionCell;

        EntryBlocker(FengDhBagState bag, int positionCell) {
            this.bag = bag;
            this.positionCell = positionCell;
        }
    }

    public static final class Snapshot {
        private final Map<Integer, List<OccupantSnapshot>> byEdge;
        private final int[] movingByEdge;
        private final int[] stoppedByEdge;

        Snapshot(
                Map<Integer, List<OccupantSnapshot>> byEdge,
                int[] movingByEdge,
                int[] stoppedByEdge) {
            this.byEdge = byEdge;
            this.movingByEdge = movingByEdge;
            this.stoppedByEdge = stoppedByEdge;
        }

        public List<OccupantSnapshot> occupants(int edgeId) {
            List<OccupantSnapshot> values = byEdge.get(Integer.valueOf(edgeId));
            return values == null ? Collections.<OccupantSnapshot>emptyList() : values;
        }

        public int movingCount(int edgeId) {
            return edgeId >= 0 && edgeId < movingByEdge.length ? movingByEdge[edgeId] : 0;
        }

        public int stoppedCount(int edgeId) {
            return edgeId >= 0 && edgeId < stoppedByEdge.length ? stoppedByEdge[edgeId] : 0;
        }
    }

    /** Builder used by deterministic mechanism tests; formal runs use readLegacyMap. */
    public static final class Builder {
        private final LinkedHashMap<Integer, NodeData> nodes = new LinkedHashMap<Integer, NodeData>();
        private final ArrayList<EdgeData> edges = new ArrayList<EdgeData>();
        private double agvLengthMeters = 1.0d;
        private double safeLengthMeters = 0.0d;
        private double faultThreshold = 0.0d;

        public Builder physicalDimensions(double agvLengthMeters, double safeLengthMeters) {
            this.agvLengthMeters = agvLengthMeters;
            this.safeLengthMeters = safeLengthMeters;
            return this;
        }

        public Builder addNode(int id, int type) {
            return addNode(id, type, 0.0d, 0, 0);
        }

        public Builder addNode(int id, int type, double throughTimeSeconds, int y, int x) {
            if (nodes.put(Integer.valueOf(id),
                    new NodeData(id, type, throughTimeSeconds, y, x)) != null) {
                throw new IllegalArgumentException("duplicate node " + id);
            }
            return this;
        }

        public Builder addEdge(int from, int to, double lengthMeters) {
            edges.add(new EdgeData(edges.size(), from, to, lengthMeters,
                    DEFAULT_SPEED_METERS_PER_SECOND));
            return this;
        }

        public FengDhEdgeLattice build() {
            return new FengDhEdgeLattice(nodes, edges, agvLengthMeters, safeLengthMeters,
                    faultThreshold);
        }
    }

    private final Map<Integer, NodeData> nodes;
    private final List<EdgeData> edges;
    private final Map<Integer, List<EdgeData>> outgoing;
    private final Map<Long, EdgeData> edgeByEndpoints;
    private final Map<Integer, TreeMap<Integer, FengDhBagState>> occupancy;
    private final double agvLengthMeters;
    private final double safeLengthMeters;
    private final double faultThreshold;
    private final int footprintCells;

    private FengDhEdgeLattice(
            Map<Integer, NodeData> sourceNodes,
            List<EdgeData> sourceEdges,
            double agvLengthMeters,
            double safeLengthMeters,
            double faultThreshold) {
        if (sourceNodes.isEmpty()) {
            throw new IllegalArgumentException("network has no nodes");
        }
        if (agvLengthMeters < 0.0d || safeLengthMeters < 0.0d) {
            throw new IllegalArgumentException("physical dimensions cannot be negative");
        }
        this.nodes = Collections.unmodifiableMap(
                new LinkedHashMap<Integer, NodeData>(sourceNodes));
        this.edges = Collections.unmodifiableList(new ArrayList<EdgeData>(sourceEdges));
        this.agvLengthMeters = agvLengthMeters;
        this.safeLengthMeters = safeLengthMeters;
        this.faultThreshold = faultThreshold;
        this.footprintCells = Math.max(1,
                (int) Math.ceil((agvLengthMeters + safeLengthMeters) / CELL_METERS - 1.0e-12d));
        this.outgoing = new HashMap<Integer, List<EdgeData>>();
        this.edgeByEndpoints = new HashMap<Long, EdgeData>();
        this.occupancy = new HashMap<Integer, TreeMap<Integer, FengDhBagState>>();
        for (Integer node : nodes.keySet()) {
            outgoing.put(node, new ArrayList<EdgeData>());
        }
        for (EdgeData edge : edges) {
            if (!nodes.containsKey(Integer.valueOf(edge.from))
                    || !nodes.containsKey(Integer.valueOf(edge.to))) {
                throw new IllegalArgumentException("edge endpoint is not a node: "
                        + edge.from + "->" + edge.to);
            }
            long key = endpointKey(edge.from, edge.to);
            if (edgeByEndpoints.put(Long.valueOf(key), edge) != null) {
                throw new IllegalArgumentException("parallel legacy edge is ambiguous: "
                        + edge.from + "->" + edge.to);
            }
            outgoing.get(Integer.valueOf(edge.from)).add(edge);
            occupancy.put(Integer.valueOf(edge.id), new TreeMap<Integer, FengDhBagState>());
        }
        Comparator<EdgeData> edgeOrder = new Comparator<EdgeData>() {
            @Override
            public int compare(EdgeData left, EdgeData right) {
                int byTo = Integer.compare(left.to, right.to);
                return byTo != 0 ? byTo : Integer.compare(left.id, right.id);
            }
        };
        for (Map.Entry<Integer, List<EdgeData>> entry : outgoing.entrySet()) {
            Collections.sort(entry.getValue(), edgeOrder);
            entry.setValue(Collections.unmodifiableList(entry.getValue()));
        }
    }

    public static Builder builder() {
        return new Builder();
    }

    /** Parse the exact layout consumed by the original App.Map.read method. */
    public static FengDhEdgeLattice readLegacyMap(File path) throws IOException {
        BufferedReader reader = new BufferedReader(new FileReader(path));
        try {
            String first = requireLine(reader, "map header");
            String[] header = split(first);
            if (header.length < 4) {
                throw new IOException("legacy map header has fewer than four fields");
            }
            int nodeCount = parseInt(header[0], "node count");
            double agvLength = parseDouble(header[1], "AGV length");
            double safeLength = parseDouble(header[2], "safe length");
            double faultThreshold = parseDouble(header[3], "fault threshold");
            LinkedHashMap<Integer, NodeData> nodes = new LinkedHashMap<Integer, NodeData>();
            Map<Integer, List<Integer>> declaredOutgoing = new HashMap<Integer, List<Integer>>();
            for (int i = 0; i < nodeCount; i++) {
                String[] fields = split(requireLine(reader, "node " + i));
                if (fields.length < 5) {
                    throw new IOException("node row has fewer than five fields at index " + i);
                }
                int id = parseInt(fields[0], "node id");
                NodeData node = new NodeData(
                        id,
                        parseInt(fields[1], "node type"),
                        parseDouble(fields[2], "node through time"),
                        parseInt(fields[3], "node y"),
                        parseInt(fields[4], "node x"));
                if (nodes.put(Integer.valueOf(id), node) != null) {
                    throw new IOException("duplicate node " + id);
                }
                ArrayList<Integer> neighbors = new ArrayList<Integer>();
                for (int j = 5; j < fields.length; j++) {
                    neighbors.add(Integer.valueOf(parseInt(fields[j], "neighbor")));
                }
                declaredOutgoing.put(Integer.valueOf(id), neighbors);
            }
            // The original parser loads, but does not route with, the D x D hcost block.
            for (int i = 0; i < nodeCount; i++) {
                String[] fields = split(requireLine(reader, "heuristic row " + i));
                if (fields.length != nodeCount) {
                    throw new IOException("heuristic row " + i + " has " + fields.length
                            + " fields; expected " + nodeCount);
                }
                for (String field : fields) {
                    parseDouble(field, "heuristic value");
                }
            }
            ArrayList<EdgeData> edges = new ArrayList<EdgeData>();
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty()) {
                    continue;
                }
                String[] fields = split(line);
                if (fields.length < 3) {
                    throw new IOException("edge row has fewer than three fields: " + line);
                }
                double speed = fields.length >= 4
                        ? parseDouble(fields[3], "edge speed")
                        : DEFAULT_SPEED_METERS_PER_SECOND;
                edges.add(new EdgeData(
                        edges.size(),
                        parseInt(fields[0], "edge start"),
                        parseInt(fields[1], "edge end"),
                        parseDouble(fields[2], "edge length"),
                        speed));
            }
            FengDhEdgeLattice lattice = new FengDhEdgeLattice(
                    nodes, edges, agvLength, safeLength, faultThreshold);
            lattice.validateDeclaredAdjacency(declaredOutgoing);
            return lattice;
        } finally {
            reader.close();
        }
    }

    public Map<Integer, NodeData> nodes() {
        return nodes;
    }

    public List<EdgeData> edges() {
        return edges;
    }

    public List<EdgeData> outgoing(int node) {
        List<EdgeData> result = outgoing.get(Integer.valueOf(node));
        return result == null ? Collections.<EdgeData>emptyList() : result;
    }

    public EdgeData edge(int edgeId) {
        if (edgeId < 0 || edgeId >= edges.size()) {
            throw new IllegalArgumentException("unknown edge id " + edgeId);
        }
        return edges.get(edgeId);
    }

    public EdgeData edge(int from, int to) {
        return edgeByEndpoints.get(Long.valueOf(endpointKey(from, to)));
    }

    public double getAgvLengthMeters() {
        return agvLengthMeters;
    }

    public double getSafeLengthMeters() {
        return safeLengthMeters;
    }

    public double getFaultThreshold() {
        return faultThreshold;
    }

    public int getFootprintCells() {
        return footprintCells;
    }

    public double headwaySeconds() {
        return (agvLengthMeters + safeLengthMeters) / DEFAULT_SPEED_METERS_PER_SECOND;
    }

    public Snapshot snapshot() {
        HashMap<Integer, List<OccupantSnapshot>> result =
                new HashMap<Integer, List<OccupantSnapshot>>();
        int[] movingByEdge = new int[edges.size()];
        int[] stoppedByEdge = new int[edges.size()];
        for (EdgeData edge : edges) {
            ArrayList<OccupantSnapshot> values = new ArrayList<OccupantSnapshot>();
            for (Map.Entry<Integer, FengDhBagState> entry
                    : occupancy.get(Integer.valueOf(edge.id)).entrySet()) {
                FengDhBagState.Status status = entry.getValue().getStatus();
                values.add(new OccupantSnapshot(
                        entry.getValue().taskId,
                        entry.getKey().intValue(),
                        status));
                if (status == FengDhBagState.Status.MOVING_ON_EDGE) {
                    movingByEdge[edge.id]++;
                } else if (status == FengDhBagState.Status.STOPPED_ON_EDGE) {
                    stoppedByEdge[edge.id]++;
                }
            }
            result.put(Integer.valueOf(edge.id), Collections.unmodifiableList(values));
        }
        return new Snapshot(Collections.unmodifiableMap(result), movingByEdge, stoppedByEdge);
    }

    public List<FengDhBagState> occupantsDownstreamFirst(int edgeId) {
        ArrayList<FengDhBagState> result = new ArrayList<FengDhBagState>(
                occupancy.get(Integer.valueOf(edgeId)).descendingMap().values());
        return result;
    }

    public EntryBlocker entryBlocker(int edgeId) {
        TreeMap<Integer, FengDhBagState> occupied = occupancy.get(Integer.valueOf(edgeId));
        if (occupied.isEmpty()) {
            return null;
        }
        Map.Entry<Integer, FengDhBagState> nearest = occupied.firstEntry();
        if (nearest.getKey().intValue() < footprintCells) {
            return new EntryBlocker(nearest.getValue(), nearest.getKey().intValue());
        }
        return null;
    }

    /**
     * Entry check against the simultaneous commit positions.  This is what
     * permits a following bag to enter when a moving entrance occupant really
     * advances far enough in the same tick, while a stopped occupant remains a
     * blocker.  Guaranteed departures (goal completions) are omitted.
     */
    public EntryBlocker entryBlockerAfterPlan(
            int edgeId,
            Map<Long, Integer> plannedPositions,
            Set<Long> guaranteedDepartures) {
        TreeMap<Integer, FengDhBagState> occupied = occupancy.get(Integer.valueOf(edgeId));
        FengDhBagState nearestBag = null;
        int nearestPosition = Integer.MAX_VALUE;
        for (Map.Entry<Integer, FengDhBagState> entry : occupied.entrySet()) {
            FengDhBagState bag = entry.getValue();
            if (guaranteedDepartures.contains(Long.valueOf(bag.taskId))) {
                continue;
            }
            if (bag.getStatus() == FengDhBagState.Status.STOPPED_ON_EDGE
                    && entry.getKey().intValue() < footprintCells) {
                return new EntryBlocker(bag, entry.getKey().intValue());
            }
            Integer planned = plannedPositions.get(Long.valueOf(bag.taskId));
            int position = planned == null ? entry.getKey().intValue() : planned.intValue();
            if (position < nearestPosition) {
                nearestPosition = position;
                nearestBag = bag;
            }
        }
        if (nearestBag != null && nearestPosition < footprintCells) {
            return new EntryBlocker(nearestBag, nearestPosition);
        }
        return null;
    }

    public void enter(int edgeId, FengDhBagState bag) {
        if (entryBlocker(edgeId) != null) {
            throw new IllegalStateException("edge entry is not available for " + edgeId);
        }
        TreeMap<Integer, FengDhBagState> occupied = occupancy.get(Integer.valueOf(edgeId));
        if (occupied.put(Integer.valueOf(0), bag) != null) {
            throw new IllegalStateException("edge entry position collision on " + edgeId);
        }
    }

    public void move(int edgeId, FengDhBagState bag, int newPosition) {
        TreeMap<Integer, FengDhBagState> occupied = occupancy.get(Integer.valueOf(edgeId));
        FengDhBagState removed = occupied.remove(Integer.valueOf(bag.getPositionCell()));
        if (removed != bag) {
            throw new IllegalStateException("moving bag is not at its recorded lattice position");
        }
        if (occupied.put(Integer.valueOf(newPosition), bag) != null) {
            throw new IllegalStateException("lattice position collision on edge " + edgeId);
        }
    }

    public void remove(int edgeId, FengDhBagState bag) {
        TreeMap<Integer, FengDhBagState> occupied = occupancy.get(Integer.valueOf(edgeId));
        FengDhBagState removed = occupied.remove(Integer.valueOf(bag.getPositionCell()));
        if (removed != bag) {
            throw new IllegalStateException("removing bag is not at its recorded lattice position");
        }
    }

    public int activeOnEdges() {
        int total = 0;
        for (TreeMap<Integer, FengDhBagState> occupied : occupancy.values()) {
            total += occupied.size();
        }
        return total;
    }

    /** Fail closed on overlap, wrong edge ownership, or illegal state. */
    public void assertIntegrity() {
        HashMap<Long, Integer> seen = new HashMap<Long, Integer>();
        for (EdgeData edge : edges) {
            Integer priorPosition = null;
            for (Map.Entry<Integer, FengDhBagState> entry
                    : occupancy.get(Integer.valueOf(edge.id)).entrySet()) {
                int position = entry.getKey().intValue();
                FengDhBagState bag = entry.getValue();
                if (position < 0 || position >= edge.cellCount) {
                    throw new IllegalStateException("bag position outside edge lattice");
                }
                if (priorPosition != null && position - priorPosition.intValue() < footprintCells) {
                    throw new IllegalStateException("carrier/safety footprint overlap on edge " + edge.id);
                }
                if (bag.getCurrentEdgeId() != edge.id
                        || (bag.getStatus() != FengDhBagState.Status.MOVING_ON_EDGE
                        && bag.getStatus() != FengDhBagState.Status.STOPPED_ON_EDGE)) {
                    throw new IllegalStateException("edge occupancy and bag state disagree");
                }
                if (seen.put(Long.valueOf(bag.taskId), Integer.valueOf(edge.id)) != null) {
                    throw new IllegalStateException("bag occupies more than one edge");
                }
                priorPosition = Integer.valueOf(position);
            }
        }
    }

    private void validateDeclaredAdjacency(Map<Integer, List<Integer>> declared) throws IOException {
        for (Map.Entry<Integer, List<Integer>> entry : declared.entrySet()) {
            ArrayList<Integer> parsed = new ArrayList<Integer>();
            for (EdgeData edge : outgoing(entry.getKey().intValue())) {
                parsed.add(Integer.valueOf(edge.to));
            }
            ArrayList<Integer> expected = new ArrayList<Integer>(entry.getValue());
            Collections.sort(parsed);
            Collections.sort(expected);
            if (!parsed.equals(expected)) {
                throw new IOException("node adjacency and edge rows disagree at node " + entry.getKey()
                        + ": declared=" + expected + ", parsed=" + parsed);
            }
        }
    }

    private static String requireLine(BufferedReader reader, String label) throws IOException {
        String line = reader.readLine();
        if (line == null) {
            throw new IOException("unexpected end of file while reading " + label);
        }
        return line;
    }

    private static String[] split(String line) {
        String trimmed = line.trim();
        return trimmed.isEmpty() ? new String[0] : trimmed.split("\\s+");
    }

    private static int parseInt(String value, String label) throws IOException {
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException error) {
            throw new IOException("invalid " + label + ": " + value, error);
        }
    }

    private static double parseDouble(String value, String label) throws IOException {
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException error) {
            throw new IOException("invalid " + label + ": " + value, error);
        }
    }

    private static long endpointKey(int from, int to) {
        return (((long) from) << 32) ^ (to & 0xffffffffL);
    }
}
