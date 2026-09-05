package App;

import java.io.File;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.HashSet;

/** Contradictory arrival/task-id order at actual simulated contention points. */
public final class IdOrderProbeAudit {
    private static boolean idOrder;
    private static File output;

    public static void main(String[] args) throws Exception {
        idOrder = args[0].equals("id");
        output = new File(args[1]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create fixture output");
        }
        nodeServicePriority();
        edgeEntryPriority();
    }

    private static FengDhBagState bag(long rawId, int start, int goal) {
        return new FengDhBagState(rawId * 2, rawId, 0, 1, 0, 0, 0, 99999, start, goal, false, "");
    }

    private static void seed(FengDhEdgeLattice lattice, FengDhBagState bag, int edge, int pos) {
        bag.release(0, true);
        bag.enterEdge(0, edge, true, "seed", true);
        lattice.enter(edge, bag);
        if (pos > 0) {
            lattice.move(edge, bag, pos);
            bag.moveOnEdge(0, pos, true);
        }
        if (pos == lattice.edge(edge).cellCount - 1) {
            bag.markDownstreamArrival(0, lattice.edge(edge).to);
        }
    }

    private static FengDhSimulator sim(FengDhEdgeLattice lattice, FengDhBagState... bags) {
        return new FengDhSimulator(lattice, new FengDhPolicy(lattice, 0.4d, 0.8d), Arrays.asList(bags));
    }

    private static void check(boolean pass, String message) {
        if (!pass) {
            throw new AssertionError(message);
        }
    }

    private static void step(FengDhSimulator simulator, FengDhEdgeLattice lattice, FengDhBagState... bags) {
        simulator.step(1);
        lattice.assertIntegrity();
        HashSet<Long> occupants = new HashSet<Long>();
        for (FengDhEdgeLattice.EdgeData edge : lattice.edges()) {
            for (FengDhBagState bag : lattice.occupantsDownstreamFirst(edge.id)) {
                check(occupants.add(Long.valueOf(bag.taskId)), "duplicate edge identity");
            }
        }
        for (FengDhBagState bag : bags) {
            check(occupants.contains(Long.valueOf(bag.taskId)) == (bag.getCurrentEdgeId() >= 0),
                    "physical bag/lattice ownership mismatch");
        }
    }

    private static void finish(FengDhSimulator simulator, FengDhEdgeLattice lattice, FengDhBagState... bags) {
        while (simulator.getTick() < 200) {
            boolean complete = true;
            for (FengDhBagState bag : bags) {
                complete &= bag.isCompleted();
            }
            if (complete) {
                check(lattice.activeOnEdges() == 0, "completed bags retain occupancy");
                return;
            }
            step(simulator, lattice, bags);
        }
        throw new AssertionError("finite contention failed eventual completion");
    }

    private static long serviceStart(FengDhBagState bag, int node) {
        for (FengDhBagState.TraceEvent event : bag.getTrace()) {
            if (event.event.equals("NODE_SERVICE_START") && event.node == node
                    && event.detail.contains("MAP_JUNCTION_THROUGH_EXCLUSIVE")) {
                return event.tick;
            }
        }
        throw new AssertionError("missing node service start");
    }

    private static long edgeEntry(FengDhBagState bag, int edge) {
        for (FengDhBagState.TraceEvent event : bag.getTrace()) {
            if ((event.event.equals("ENTER_EDGE") || event.event.equals("TRANSFER"))
                    && event.edgeId == edge) {
                return event.tick;
            }
        }
        throw new AssertionError("missing edge entry");
    }

    private static void nodeServicePriority() throws Exception {
        // Two contenders arrive through separate ports while a third bag is
        // already using the common one-second service; no artificial timestamps.
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1).addNode(2, 1)
                .addNode(3, 1, 1.0d, 0, 0).addNode(4, 2)
                .addEdge(0, 3, 3).addEdge(1, 3, 3).addEdge(2, 3, 3)
                .addEdge(3, 4, 3).build();
        FengDhBagState holder = bag(0, 0, 4), early = bag(10, 1, 4), late = bag(1, 2, 4);
        seed(lattice, holder, 0, 5);
        seed(lattice, early, 1, 4);
        seed(lattice, late, 2, 3);
        FengDhSimulator simulator = sim(lattice, late, early, holder);
        for (int tick = 1; tick <= 5; tick++) {
            step(simulator, lattice, holder, early, late);
        }
        check(early.getNodeArrivalTick() == 1 && late.getNodeArrivalTick() == 2,
                "fixture lacks opposing physical-arrival and task-id orders");
        finish(simulator, lattice, holder, early, late);
        long earlyStart = serviceStart(early, 3), lateStart = serviceStart(late, 3);
        check(serviceStart(holder, 3) == 1, "holder did not stage contention");
        check(idOrder ? lateStart < earlyStart : earlyStart < lateStart,
                "node-service grant used the wrong priority");
        write("IO1_node_service_conflict", earlyStart, lateStart, holder, early, late);
    }

    private static void edgeEntryPriority() throws Exception {
        // Both contenders complete zero-through/transfer before a blocked
        // outlet becomes free, isolating entry arbitration from service order.
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1).addNode(2, 1)
                .addNode(3, 1, 4.0d, 0, 0).addNode(4, 2)
                .addEdge(0, 2, 3).addEdge(1, 2, 3).addEdge(2, 3, 0.5d)
                .addEdge(3, 4, 3).build();
        FengDhBagState early = bag(10, 0, 4), late = bag(1, 1, 4), blocker = bag(0, 2, 4);
        seed(lattice, early, 0, 5);
        seed(lattice, late, 1, 4);
        seed(lattice, blocker, 2, 0);
        FengDhSimulator simulator = sim(lattice, late, blocker, early);
        for (int tick = 1; tick <= 3; tick++) {
            step(simulator, lattice, early, late, blocker);
        }
        check(early.getNodeArrivalTick() == 0 && late.getNodeArrivalTick() == 1,
                "fixture lacks opposing physical-arrival and task-id orders");
        finish(simulator, lattice, early, late, blocker);
        long earlyEntry = edgeEntry(early, 2), lateEntry = edgeEntry(late, 2);
        check(Math.min(earlyEntry, lateEntry) > 12, "outlet opened before both transfers were ready");
        check(idOrder ? lateEntry < earlyEntry : earlyEntry < lateEntry,
                "edge-entry grant used the wrong priority");
        write("IO2_edge_entry_conflict", earlyEntry, lateEntry, early, late, blocker);
    }

    private static void write(String id, long early, long late, FengDhBagState... bags) throws Exception {
        PrintWriter writer = new PrintWriter(new File(output, id + ".tsv"), "UTF-8");
        try {
            writer.println("task_id\ttick\tevent\tnode\tedge\tposition\tdetail");
            for (FengDhBagState bag : bags) {
                for (FengDhBagState.TraceEvent event : bag.getTrace()) {
                    writer.println(bag.taskId + "\t" + event.tick + "\t" + event.event + "\t" + event.node
                            + "\t" + event.edgeId + "\t" + event.positionCell + "\t" + event.detail);
                }
            }
        } finally {
            writer.close();
        }
        System.out.println("{\"case_id\":\"" + id + "\",\"pass\":true,\"order\":\""
                + (idOrder ? "task_id" : "physical_arrival_fifo")
                + "\",\"early_high_id_tick\":" + early + ",\"late_low_id_tick\":" + late
                + ",\"all_complete\":true}");
    }
}
