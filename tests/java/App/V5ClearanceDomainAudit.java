package App;

import java.io.File;
import java.lang.reflect.Method;
import java.util.Collections;

/** Checks the actual V5 clearance method on every map edge, without changing production classes. */
public final class V5ClearanceDomainAudit {
    public static void main(String[] args) throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.readLegacyMap(new File(args[0]));
        FengDhSimulator simulator = new FengDhSimulator(lattice,
                new FengDhPolicy(lattice, 0.4, 0.8), Collections.<FengDhBagState>emptyList());
        Method method = FengDhSimulator.class.getDeclaredMethod("boundaryClearanceTicks", Integer.TYPE);
        method.setAccessible(true);
        long min = Long.MAX_VALUE, max = Long.MIN_VALUE;
        for (FengDhEdgeLattice.EdgeData edge : lattice.edges()) {
            long ticks = ((Long) method.invoke(simulator, edge.id)).longValue();
            if (ticks <= 0 || ticks >= 10) throw new AssertionError("unsupported edge " + edge.id);
            min = Math.min(min, ticks);
            max = Math.max(max, ticks);
        }
        System.out.println("{\"edge_count\":" + lattice.edges().size()
                + ",\"min_clearance_ticks\":" + min + ",\"max_clearance_ticks\":" + max
                + ",\"agv_length_meters\":" + lattice.getAgvLengthMeters()
                + ",\"safe_length_meters\":" + lattice.getSafeLengthMeters()
                + ",\"status\":\"PASS\"}");
    }
}
