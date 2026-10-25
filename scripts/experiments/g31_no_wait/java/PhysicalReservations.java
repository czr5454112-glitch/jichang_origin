package App;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;

/** Per-controller persistent reservations for the separately labelled uniform physical HCA. */
public final class PhysicalReservations {
    public static final long TICKS_PER_SECOND = 1000000L;
    public static final long EDGE_ENTRY_HEADWAY_TICKS = 2000000L;
    private final HashMap<Integer, ArrayList<long[]>> nodes = new HashMap<>();
    private final HashMap<Long, ArrayList<long[]>> edges = new HashMap<>();

    public static long ticks(double seconds) {
        if (!Double.isFinite(seconds) || Math.abs(seconds) > 9.0e12)
            throw new IllegalArgumentException("invalid physical time");
        return Math.round(seconds * TICKS_PER_SECOND);
    }
    public static double seconds(long ticks) { return ticks / (double)TICKS_PER_SECOND; }
    /** Sum individually quantized durations rather than accumulating floating point times. */
    public static double add(double time, double duration) {
        return seconds(Math.addExact(ticks(time),ticks(duration)));
    }
    private static long edgeKey(int from, int to) { return ((long)from << 32) ^ (to & 0xffffffffL); }
    private static boolean free(List<long[]> windows, long start, long end) {
        if (end < start) throw new IllegalArgumentException("negative interval");
        if (start == end || windows == null) return true;
        for (long[] old : windows)
            if (Math.max(start,old[0]) < Math.min(end,old[1])) return false;
        return true;
    }
    public boolean nodeFree(int node, double start, double end) { return free(nodes.get(node),ticks(start),ticks(end)); }
    public boolean edgeFree(int from, int to, double departure) {
        long start=ticks(departure);
        return free(edges.get(edgeKey(from,to)),start,start+EDGE_ENTRY_HEADWAY_TICKS);
    }
    /** Validate first, then register atomically; no resource is freed on business completion. */
    public void commit(List<Node> path) {
        for (int i=0;i<path.size();i++) {
            Node node=path.get(i);
            if (!nodeFree(node.getLocation(),node.getT1(),node.getT2())) throw new IllegalStateException("node commit conflict");
            if (i+1<path.size() && !edgeFree(node.getLocation(),path.get(i+1).getLocation(),node.getT2()))
                throw new IllegalStateException("edge-entry commit conflict");
        }
        for (int i=0;i<path.size();i++) {
            Node node=path.get(i);long start=ticks(node.getT1()),end=ticks(node.getT2());
            if (start<end) nodes.computeIfAbsent(node.getLocation(),k->new ArrayList<>()).add(new long[]{start,end});
            if (i+1<path.size()) {
                long entry=ticks(node.getT2());
                edges.computeIfAbsent(edgeKey(node.getLocation(),path.get(i+1).getLocation()),k->new ArrayList<>())
                    .add(new long[]{entry,entry+EDGE_ENTRY_HEADWAY_TICKS});
            }
        }
    }
    private static <K> void pruneTable(HashMap<K,ArrayList<long[]>> table,long now) {
        Iterator<ArrayList<long[]>> it=table.values().iterator();
        while (it.hasNext()) {
            ArrayList<long[]> windows=it.next();windows.removeIf(w->w[1]<=now);
            if (windows.isEmpty()) it.remove();
        }
    }
    public void prune(double now) { long time=ticks(now);pruneTable(nodes,time);pruneTable(edges,time); }
}
