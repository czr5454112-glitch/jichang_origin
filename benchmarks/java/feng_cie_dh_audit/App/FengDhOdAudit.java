package App;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;

/** Independent, one-bag-per-OD audit; no benchmark or simulator semantics are changed. */
public final class FengDhOdAudit {
    private static String quote(String value) {
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\"";
    }

    public static void main(String[] args) throws Exception {
        File map = new File(args[0]);
        List<String> rows = Files.readAllLines(new File(args[1]).toPath(), StandardCharsets.UTF_8);
        PrintWriter output = new PrintWriter(new OutputStreamWriter(
                new FileOutputStream(args[2]), StandardCharsets.UTF_8));
        int passed = 0, failed = 0, unreachable = 0;
        try {
            for (int i = 1; i < rows.size(); i++) {
                if (rows.get(i).trim().isEmpty()) continue;
                String[] row = rows.get(i).split("\t", -1);
                int start = Integer.parseInt(row[0]), goal = Integer.parseInt(row[1]);
                FengDhEdgeLattice lattice = FengDhEdgeLattice.readLegacyMap(map);
                FengDhPolicy policy = new FengDhPolicy(lattice, 0.4, 0.8);
                FengDhPolicy.Path path = policy.shortestPath(start, goal);
                if (path == null) {
                    unreachable++;
                    output.println("{\"start\":" + start + ",\"goal\":" + goal
                            + ",\"reachable\":false,\"status\":\"UNREACHABLE\"}");
                    continue;
                }
                ArrayList<Integer> zeroIntermediate = new ArrayList<Integer>();
                for (int n = 1; n < path.nodeIds.size() - 1; n++) {
                    int node = path.nodeIds.get(n).intValue();
                    if (lattice.nodes().get(Integer.valueOf(node)).throughTimeSeconds == 0.0)
                        zeroIntermediate.add(Integer.valueOf(node));
                }
                FengDhBagState bag = new FengDhBagState(1, 1, 0, 1,
                        0, 0, 0, 99999, start, goal, false, row[5]);
                FengDhSimulator simulator = new FengDhSimulator(lattice, policy, Arrays.asList(bag));
                long horizon = Math.max(5000L, (long)Math.ceil(path.freeFlowSeconds * 10)
                        + lattice.nodes().size() * 100L);
                String firstInvalid = "null";
                long staleServiceStarts = 0L, lastServiceStart = -1L;
                int lastServiceEdge = -2;
                while (!bag.isCompleted() && simulator.getTick() < horizon) {
                    simulator.step(1);
                    long serviceStart = bag.getNodeServiceStartTick();
                    int edge = bag.getCurrentEdgeId();
                    if (edge >= 0 && bag.getCurrentNode() != goal
                            && lattice.nodes().get(Integer.valueOf(bag.getCurrentNode()))
                                    .throughTimeSeconds == 0.0
                            && serviceStart == simulator.getTick()
                            && bag.getNodeServiceReadyTick() == serviceStart) {
                        if (firstInvalid.equals("null")) {
                            firstInvalid = "{\"tick\":" + simulator.getTick()
                                    + ",\"node\":" + bag.getCurrentNode()
                                    + ",\"edge\":" + edge
                                    + ",\"position_cell\":" + bag.getPositionCell()
                                    + ",\"state\":" + quote(bag.getStatus().name())
                                    + ",\"ready_tick\":" + bag.getNodeServiceReadyTick()
                                    + ",\"problem\":\"instant_service_finished_but_upstream_retained\"}";
                        }
                        if (lastServiceEdge == edge && lastServiceStart >= 0L)
                            staleServiceStarts++;
                        lastServiceStart = serviceStart;
                        lastServiceEdge = edge;
                    }
                    // Two consecutive invalid service starts suffice to reproduce the defect.
                    if (staleServiceStarts > 0L) break;
                }
                lattice.assertIntegrity();
                boolean complete = bag.isCompleted();
                if (complete) passed++; else failed++;
                StringBuilder events = new StringBuilder("[");
                for (FengDhBagState.TraceEvent event : bag.getTrace()) {
                    if (!event.event.startsWith("NODE_SERVICE") && !event.event.equals("COMPLETE"))
                        continue;
                    if (events.length() > 1) events.append(',');
                    events.append("{\"tick\":").append(event.tick)
                            .append(",\"event\":").append(quote(event.event))
                            .append(",\"node\":").append(event.node)
                            .append(",\"edge\":").append(event.edgeId)
                            .append(",\"position_cell\":").append(event.positionCell)
                            .append(",\"detail\":").append(quote(event.detail)).append('}');
                }
                events.append(']');
                output.println("{\"start\":" + start + ",\"goal\":" + goal
                        + ",\"reachable\":true,\"status\":" + quote(complete ? "COMPLETE" : "FAILED")
                        + ",\"end_tick\":" + simulator.getTick()
                        + ",\"completion_tick\":" + bag.getCompletionTick()
                        + ",\"shortest_path\":" + path.nodeIds
                        + ",\"zero_intermediate_nodes\":" + zeroIntermediate
                        + ",\"zero_goal\":" + (lattice.nodes().get(Integer.valueOf(goal)).throughTimeSeconds == 0.0)
                        + ",\"first_invalid_state\":" + firstInvalid
                        + ",\"repeated_zero_service_starts\":" + staleServiceStarts
                        + ",\"sample_raw_bag_id\":" + quote(row[2])
                        + ",\"sample_segment_id\":" + quote(row[3])
                        + ",\"sample_input_path\":" + quote(row[4])
                        + ",\"sample_raw_row\":" + quote(row[5])
                        + ",\"service_events\":" + events + "}");
            }
        } finally { output.close(); }
        System.out.println("completed=" + passed + " failed=" + failed + " unreachable=" + unreachable);
        if (args.length > 3 && args[3].equals("require-pass") && failed > 0)
            throw new AssertionError("reachable formal workload ODs did not complete: " + failed);
    }
}
