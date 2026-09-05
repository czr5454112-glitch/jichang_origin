package App;

import java.io.File;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.HashSet;

/** Service-reuse observation timing, distinct from per-bag service duration. */
public final class NextTickServiceAudit {
    private static boolean nextTick;
    private static File output;

    public static void main(String[] args) throws Exception {
        nextTick = args[0].equals("next");
        output = new File(args[1]);
        if (!output.isDirectory() && !output.mkdirs()) throw new IllegalStateException("output");
        compete(true);
        compete(false);
        single(0.0d, 28);
        single(1.0d, 33);
    }

    private static FengDhBagState bag(long id, int start, int goal) {
        return new FengDhBagState(id * 2, id, 0, 1, 0, 0, 0, 9999, start, goal, false, "");
    }

    private static void seed(FengDhEdgeLattice lattice, FengDhBagState bag, int edge, int pos) {
        bag.release(0, true);
        bag.enterEdge(0, edge, true, "seed", true);
        lattice.enter(edge, bag);
        lattice.move(edge, bag, pos);
        bag.moveOnEdge(0, pos, true);
        if (pos == lattice.edge(edge).cellCount - 1) bag.markDownstreamArrival(0, lattice.edge(edge).to);
    }

    private static void check(boolean pass, String message) {
        if (!pass) throw new AssertionError(message);
    }

    private static void finish(FengDhEdgeLattice lattice, FengDhBagState... bags) {
        FengDhSimulator simulator = new FengDhSimulator(lattice, new FengDhPolicy(lattice, .4d, .8d), Arrays.asList(bags));
        while (simulator.getTick() < 200) {
            boolean complete = true;
            for (FengDhBagState bag : bags) complete &= bag.isCompleted();
            if (complete) {
                check(lattice.activeOnEdges() == 0, "completed occupancy");
                return;
            }
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
            }
        }
        throw new AssertionError("finite fixture failed completion");
    }

    private static long service(FengDhBagState bag) {
        for (FengDhBagState.TraceEvent event : bag.getTrace()) {
            if (event.event.equals("NODE_SERVICE_START") && event.detail.contains("MAP_JUNCTION_THROUGH_EXCLUSIVE")) return event.tick;
        }
        throw new AssertionError("missing through service");
    }

    private static void compete(boolean twoPorts) throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().addNode(0, 1).addNode(1, 1)
                .addNode(2, 1, 1.0d, 0, 0).addNode(3, 2)
                .addEdge(0, 2, 2).addEdge(1, 2, 2).addEdge(2, 3, 3).build();
        FengDhBagState a = bag(1, 0, 3), b = bag(2, twoPorts ? 1 : 0, 3);
        seed(lattice, a, 0, 3);
        seed(lattice, b, twoPorts ? 1 : 0, twoPorts ? 3 : 1);
        finish(lattice, a, b);
        long expected = twoPorts ? (nextTick ? 7 : 6) : 8;
        check(service(a) == 1 && service(b) == expected, "incorrect service reuse observation");
        write(twoPorts ? "NS1_two_incoming_ports" : "NS2_same_incoming_port", "\"service_start_ticks\":[1," + expected + "]", a, b);
    }

    private static void single(double through, long completion) throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().addNode(0, 1).addNode(1, 1, through, 0, 0)
                .addNode(2, 2).addEdge(0, 1, 2).addEdge(1, 2, 2).build();
        FengDhBagState bag = bag(1, 0, 2);
        finish(lattice, bag);
        check(bag.getCompletionTick() == completion && bag.getFirstAdmissionTick() == 10,
                "uncontended free-flow dwell changed");
        write(through == 0 ? "NS3_zero_single" : "NS4_positive_single", "\"completion_tick\":" + completion, bag);
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
        System.out.println("{\"case_id\":\"" + id + "\",\"pass\":true,\"next_tick_service_reuse\":"
                + nextTick + ",\"all_complete\":true," + detail + "}");
    }
}
