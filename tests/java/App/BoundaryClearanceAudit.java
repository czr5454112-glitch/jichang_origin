package App;

import java.io.File;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.HashSet;

/** V5 finite body clearance without extending the original transfer timer. */
public final class BoundaryClearanceAudit {
    private static File output;

    public static void main(String[] args) throws Exception {
        output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) throw new IllegalStateException("output");
        single(0.0d, 28);
        single(1.0d, 33);
        clearance(1.0d, 1.0d, 2, "BC3_positive_clearance");
        clearance(0.0d, 1.0d, 2, "BC4_zero_one_shot_clearance");
        clearance(1.0d, 1.5d, 3, "BC5_map_derived_clearance");
        compete(false);
        compete(true);
        finiteCountdown();
        blockedOutlet();
    }

    private static FengDhBagState bag(long id, int start, int goal) {
        return new FengDhBagState(id * 2, id, 0, 1, 0, 0, 0, 9999, start, goal, false, "");
    }

    private static FengDhSimulator sim(FengDhEdgeLattice lattice, FengDhBagState... bags) {
        return new FengDhSimulator(lattice, new FengDhPolicy(lattice, .4d, .8d), Arrays.asList(bags));
    }

    private static void seed(FengDhEdgeLattice lattice, FengDhBagState bag, int edge, int pos) {
        bag.release(0, true);
        bag.enterEdge(0, edge, true, "seed", true);
        lattice.enter(edge, bag);
        if (pos > 0) {
            lattice.move(edge, bag, pos);
            bag.moveOnEdge(0, pos, true);
        }
        if (pos == lattice.edge(edge).cellCount - 1) bag.markDownstreamArrival(0, lattice.edge(edge).to);
    }

    private static void check(boolean pass, String message) {
        if (!pass) throw new AssertionError(message);
    }

    private static void step(FengDhSimulator simulator, FengDhEdgeLattice lattice, FengDhBagState... bags) {
        simulator.step(1);
        lattice.assertIntegrity();
        HashSet<Long> occupants = new HashSet<Long>();
        for (FengDhEdgeLattice.EdgeData edge : lattice.edges()) {
            for (FengDhBagState bag : lattice.occupantsDownstreamFirst(edge.id)) {
                check(occupants.add(Long.valueOf(bag.taskId)), "duplicate physical identity");
            }
        }
        for (FengDhBagState bag : bags) {
            check(occupants.contains(Long.valueOf(bag.taskId)) == (bag.getCurrentEdgeId() >= 0), "ownership mismatch");
            if (bag.isBoundaryClearance()) {
                check(bag.getCurrentEdgeId() >= 0 && bag.getStatus() == FengDhBagState.Status.STOPPED_ON_EDGE,
                        "clearance lost physical stopped footprint");
            }
        }
    }

    private static void finish(FengDhSimulator simulator, FengDhEdgeLattice lattice, FengDhBagState... bags) {
        while (simulator.getTick() < 250) {
            boolean complete = true;
            for (FengDhBagState bag : bags) complete &= bag.isCompleted();
            if (complete) {
                check(lattice.activeOnEdges() == 0, "completed occupancy");
                return;
            }
            step(simulator, lattice, bags);
        }
        throw new AssertionError("finite fixture failed completion");
    }

    private static long service(FengDhBagState bag) {
        for (FengDhBagState.TraceEvent event : bag.getTrace()) {
            if (event.event.equals("NODE_SERVICE_START") && event.detail.contains("MAP_JUNCTION_THROUGH_EXCLUSIVE")) return event.tick;
        }
        throw new AssertionError("missing through service");
    }

    private static int count(FengDhBagState bag, String eventName, String detail) {
        int count = 0;
        for (FengDhBagState.TraceEvent event : bag.getTrace()) {
            if (event.event.equals(eventName) && event.detail.contains(detail)) count++;
        }
        return count;
    }

    private static void single(double through, long completion) throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().addNode(0, 1).addNode(1, 1, through, 0, 0)
                .addNode(2, 2).addEdge(0, 1, 2).addEdge(1, 2, 2).build();
        FengDhBagState bag = bag(1, 0, 2);
        finish(sim(lattice, bag), lattice, bag);
        check(bag.getCompletionTick() == completion && bag.getFirstAdmissionTick() == 10,
                "uncontended free-flow dwell changed");
        write(through == 0 ? "BC1_zero_single" : "BC2_positive_single", "\"completion_tick\":" + completion, bag);
    }

    private static void clearance(double through, double body, int clearTicks, String id) throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().physicalDimensions(body, 0)
                .addNode(0, 1).addNode(1, 1, through, 0, 0).addNode(2, 2)
                .addEdge(0, 1, 2).addEdge(1, 2, 2).build();
        FengDhBagState bag = bag(1, 0, 2);
        seed(lattice, bag, 0, 3);
        FengDhSimulator simulator = sim(lattice, bag);
        long transferStart = through == 0 ? 1 : 6;
        long clearReady = transferStart + clearTicks, transferReady = transferStart + 10;
        for (int tick = 1; tick < transferReady; tick++) {
            step(simulator, lattice, bag);
            if (tick >= transferStart) {
                check(bag.getNodeServiceStartTick() == transferStart && bag.getNodeServiceReadyTick() == transferReady,
                        "total transfer timer was extended or restarted");
                if (tick < clearReady) {
                    check(bag.isBoundaryClearance() && bag.getCurrentEdgeId() == 0,
                            "footprint removed before clearance");
                } else {
                    check(!bag.isBoundaryClearance() && bag.getCurrentEdgeId() == -1,
                            "footprint retained beyond derived clearance");
                }
            }
            if (tick == transferStart) {
                boolean rejected = false;
                try { bag.beginBoundaryClearance(tick, clearReady, transferReady, "duplicate", false); }
                catch (IllegalStateException expected) { rejected = true; }
                check(rejected, "repeated clearance start accepted");
            }
        }
        step(simulator, lattice, bag);
        check(bag.getCurrentEdgeId() == 1, "original transfer-ready admission changed");
        finish(simulator, lattice, bag);
        check(count(bag, "NODE_SERVICE_START", "INTERMEDIATE_FIXED_TRANSFER_DELAY") == 1
                && count(bag, "BOUNDARY_CLEARANCE_FINISH", "") == 1, "transfer/clearance repeated");
        if (through == 0) check(count(bag, "NODE_SERVICE_START", "ZERO_MAP_THROUGH_TIME") == 1, "zero service repeated");
        write(id, "\"clearance_ready_tick\":" + clearReady + ",\"transfer_ready_tick\":" + transferReady, bag);
    }

    private static void compete(boolean twoPorts) throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().addNode(0, 1).addNode(1, 1)
                .addNode(2, 1, 1.0d, 0, 0).addNode(3, 2)
                .addEdge(0, 2, 2).addEdge(1, 2, 2).addEdge(2, 3, 3).build();
        FengDhBagState a = bag(1, 0, 3), b = bag(2, twoPorts ? 1 : 0, 3);
        seed(lattice, a, 0, 3);
        seed(lattice, b, twoPorts ? 1 : 0, twoPorts ? 3 : 1);
        finish(sim(lattice, a, b), lattice, a, b);
        long expected = twoPorts ? 6 : 10;
        check(service(a) == 1 && service(b) == expected, "incorrect finite-clearance headway");
        write(twoPorts ? "BC7_two_incoming_ports" : "BC6_same_incoming_port",
                "\"service_start_ticks\":[1," + expected + "]", a, b);
    }

    private static void finiteCountdown() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().addNode(0, 1).addNode(1, 1, 20.0d, 0, 0)
                .addNode(2, 2).addEdge(0, 1, 2).addEdge(1, 2, 2).build();
        FengDhBagState bag = bag(1, 0, 2);
        FengDhSimulator.RunResult result = sim(lattice, bag).run(new FengDhSimulator.RunConfig(200, 1, 2));
        check(result.status.equals("COMPLETE") && result.endTick == 128, "finite clearance mistaken for deadlock");
        lattice.assertIntegrity();
        write("BC8_finite_countdowns", "\"completion_tick\":128", bag);
    }

    private static void blockedOutlet() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().addNode(0, 1).addNode(1, 1)
                .addNode(2, 1, 4.0d, 0, 0).addNode(3, 2)
                .addEdge(0, 1, 2).addEdge(1, 2, .5d).addEdge(2, 3, 2).build();
        FengDhBagState waiting = bag(1, 0, 3), blocker = bag(2, 1, 3);
        seed(lattice, waiting, 0, 3);
        seed(lattice, blocker, 1, 0);
        FengDhSimulator simulator = sim(lattice, waiting, blocker);
        for (int tick = 1; tick <= 22; tick++) {
            step(simulator, lattice, waiting, blocker);
            if (tick >= 3) {
                check(waiting.getCurrentEdgeId() == -1 && waiting.getNodeServiceReadyTick() == 11,
                        "finite-clearance probe silently became full outlet retention");
            }
        }
        finish(simulator, lattice, waiting, blocker);
        write("BC9_blocked_outlet_scope", "\"upstream_clear_tick\":3,\"unchanged_transfer_ready_tick\":11", waiting, blocker);
    }

    private static void write(String id, String detail, FengDhBagState... bags) throws Exception {
        PrintWriter writer = new PrintWriter(new File(output, id + ".tsv"), "UTF-8");
        try {
            writer.println("task_id\ttick\tevent\tnode\tedge\tposition\tdetail");
            for (FengDhBagState bag : bags) {
                for (FengDhBagState.TraceEvent event : bag.getTrace()) {
                    writer.println(bag.taskId + "\t" + event.tick + "\t" + event.event + "\t" + event.node
                            + "\t" + event.edgeId + "\t" + event.positionCell + "\t" + event.detail);
                }
            }
        } finally { writer.close(); }
        System.out.println("{\"case_id\":\"" + id + "\",\"pass\":true,\"all_complete\":true," + detail + "}");
    }
}
