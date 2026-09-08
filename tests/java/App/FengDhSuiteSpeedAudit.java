package App;

import java.io.File;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Collections;

/** Physical distance/time and safety assertions independent of route cost. */
public final class FengDhSuiteSpeedAudit {
    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        for (double speed : new double[]{1.5, 2.5, 3.0}) {
            FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().uniformSpeed(speed)
                    .addNode(0, 0).addNode(1, 2).addEdge(0, 1, 12).build();
            FengDhBagState a = new FengDhBagState(0, 0, 0, 1, 0, 0, 0, 9999, 0, 1, false, "");
            FengDhBagState b = new FengDhBagState(2, 1, 0, 1, 0, 0, 0, 9999, 0, 1, false, "");
            FengDhSimulator simulator = new FengDhSimulator(lattice,
                    new FengDhPolicy(lattice, lattice.headwaySeconds(), 2*lattice.headwaySeconds()),
                    Arrays.asList(a, b));
            while (!b.isCompleted() && simulator.getTick() < 1000) {
                simulator.step(1);
                lattice.assertIntegrity();
            }
            long physicalTicks = (long)Math.ceil(12 / speed / .2 - 1e-12);
            require(a.isCompleted() && b.isCompleted(), "two bags complete");
            require(a.getCompletionTick() == 10 + physicalTicks, "actual single-edge travel time");
            require(a.getCurrentNode() == 1 && b.getCurrentNode() == 1, "correct target");
            require(b.getFirstAdmissionTick() - a.getFirstAdmissionTick() >= lattice.getFootprintCells(),
                    "entry spacing smaller than physical carrier footprint");
            require(lattice.getFootprintCells() * speed * .2 >= 1 - 1e-12, "carrier footprint");
            System.out.println("{\"test\":\"physical_speed_and_spacing\",\"speed\":"+speed
                    +",\"actual_edge_seconds\":"+(a.getCompletionTick()-a.getFirstAdmissionTick())*.2
                    +",\"cell_meters\":"+lattice.getCellMeters()+",\"pass\":true}");
            for (String mapPath : args) {
                FengDhEdgeLattice map = FengDhEdgeLattice.readLegacyMap(new File(mapPath), speed);
                FengDhSimulator empty = new FengDhSimulator(map,
                        new FengDhPolicy(map, map.headwaySeconds(), 2*map.headwaySeconds()),
                        Collections.<FengDhBagState>emptyList());
                Method clearance = FengDhSimulator.class.getDeclaredMethod("boundaryClearanceTicks", Integer.TYPE);
                clearance.setAccessible(true);
                for (FengDhEdgeLattice.EdgeData edge : map.edges()) {
                    long ticks = ((Long)clearance.invoke(empty, edge.id)).longValue();
                    require(ticks > 0 && ticks < 10, "unsupported clearance domain");
                    require(edge.cellCount * speed * .2 >= edge.lengthMeters - 1e-9, "edge shorter than length");
                    require(edge.cellCount * speed * .2 < edge.lengthMeters + speed * .2 + 1e-9,
                            "travel rounding exceeds one tick");
                }
                System.out.println("{\"test\":\"map_domain\",\"speed\":"+speed
                        +",\"nodes\":"+map.nodes().size()+",\"edges\":"+map.edges().size()+",\"pass\":true}");
            }
        }
    }
}
