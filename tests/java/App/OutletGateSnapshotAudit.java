package App;

import java.util.Arrays;

/** Two consecutive zero-through junctions must use the same frozen status. */
public final class OutletGateSnapshotAudit {
    private static FengDhBagState bag(long id, int start, int goal) {
        return new FengDhBagState(id, id, 0, 1, 0, 0, 0, 99999, start, goal, false, "");
    }

    private static void seed(FengDhEdgeLattice graph, FengDhBagState bag,
            int edgeId, int position) {
        bag.release(0, false);
        bag.enterEdge(0, edgeId, true, "", false);
        graph.enter(edgeId, bag);
        if (position > 0) {
            graph.move(edgeId, bag, position);
            bag.moveOnEdge(0, position, false);
        }
        bag.markDownstreamArrival(0, graph.edge(edgeId).to);
    }

    private static void check(boolean okay, String why) {
        if (!okay) throw new AssertionError(why);
    }

    private static boolean firstStep(boolean downstreamFirst, boolean frozen) {
        int upstream = downstreamFirst ? 20 : 10;
        int downstream = downstreamFirst ? 10 : 20;
        FengDhEdgeLattice graph = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(upstream, 1, 0, 0, 0)
                .addNode(downstream, 1, 0, 0, 0)
                .addNode(30, 1, 4, 0, 0).addNode(40, 2)
                .addEdge(0, upstream, 2).addEdge(upstream, downstream, 0.5)
                .addEdge(downstream, 30, 0.5).addEdge(30, 40, 2).build();
        FengDhBagState first = bag(1, 0, 40);
        FengDhBagState middle = bag(2, upstream, 40);
        FengDhBagState blocker = bag(3, downstream, 40);
        seed(graph, first, 0, 3);
        seed(graph, middle, 1, 0);
        seed(graph, blocker, 2, 0);
        blocker.stopOnEdge(0, "seed_stopped", -1, -1, null, false);
        FengDhSimulator simulator = new FengDhSimulator(graph,
                new FengDhPolicy(graph, 0.4, 0.8), Arrays.asList(first, middle, blocker));
        simulator.step(0);
        graph.assertIntegrity();
        check(middle.getCurrentEdgeId() == 1
                && middle.getStatus() == FengDhBagState.Status.STOPPED_ON_EDGE,
                "downstream zero node did not HOLD on its frozen stopped outlet");
        boolean released = first.getCurrentEdgeId() == -1;
        check(released == (frozen || !downstreamFirst),
                "upstream gate did not exhibit the expected frozen/live contrast");
        if (released) {
            check(first.getNodeServiceReadyTick() == 11,
                    "frozen check changed the existing transfer timer");
        }
        System.out.println("{\"case\":\"zero_chain_node_order\",\"downstream_first\":"
                + downstreamFirst + ",\"frozen\":" + frozen
                + ",\"upstream_released\":" + released + ",\"pass\":true}");
        return released;
    }

    public static void main(String[] args) {
        boolean frozen = args.length > 0 && args[0].equals("frozen");
        boolean lowFirst = firstStep(false, frozen);
        boolean highFirst = firstStep(true, frozen);
        check(frozen ? lowFirst == highFirst : lowFirst != highFirst,
                "node ID permutation did not verify the intended order property");
    }
}
