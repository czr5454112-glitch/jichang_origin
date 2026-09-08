package App;

import java.util.ArrayList;
import java.util.HashMap;

/** Bounded probe of the unchanged native Handling_faults implementation. */
public final class HcaFaultCapabilityAudit {
    private static Edge edge(Map map, int from, int to, double distance) {
        Edge value = new Edge(); value.Star = from; value.End = to; value.length = distance; value.v = 1;
        map.E.add(value); map.N.get(from).add(to); return value;
    }
    private static Map map() {
        Map map = new Map(); map.D = 5; map.fault_threshold = 1000; map.hcost = new double[5][5];
        for (int i = 0; i < 5; i++) {
            Vertex node = new Vertex(); node.location = i; node.t = 1;
            map.V.add(node); map.N.put(i, new ArrayList<Integer>());
        }
        edge(map, 0, 1, 10); edge(map, 1, 2, 10); edge(map, 2, 3, 10);
        edge(map, 1, 4, 12); edge(map, 4, 3, 12);
        return map;
    }
    private static ArrayList<Node> initial(Map map) {
        Node source = new Node(); source.location = 0; source.t1 = 100;
        Node goal = new Node(); goal.location = 3;
        HashMap<Integer, ArrayList<ArrayList<Double>>> constraints = new HashMap<>();
        for (int i = 0; i < 5; i++) constraints.put(i, new ArrayList<ArrayList<Double>>());
        return Astar.research(source, goal, map, constraints, new ArrayList<Edge>());
    }
    private static String path(ArrayList<Node> value) {
        StringBuilder out = new StringBuilder("[");
        for (Node node : value) {
            if (out.length() > 1) out.append(',');
            out.append("{\"node\":").append(node.location).append(",\"t1\":").append(node.t1)
                .append(",\"t2\":").append(node.t2).append('}');
        }
        return out.append(']').toString();
    }
    private static ICS_PathFinding prepared(Map map) {
        ICS_PathFinding ics = new ICS_PathFinding(); ics.setMap(map); ics.getSaved_routes().put(7, initial(map)); return ics;
    }
    private static void fail(ICS_PathFinding ics, int from, int to, double epoch) throws Exception {
        Tasks report = new Tasks(); report.cur_time = epoch;
        for (Edge edge : ics.getMap().E) if (edge.Star == from && edge.End == to) {
            edge.fault = true; report.fault_edges.add(edge);
        }
        ics.ICS_path_finding(report, ics.getMap(), epoch, ics);
    }
    public static void main(String[] args) throws Exception {
        System.setProperty("java.awt.headless", "true");
        Map map = map(); ICS_PathFinding ics = prepared(map);
        String before = path(ics.getSaved_routes().get(7));
        fail(ics, 2, 3, 101);
        ArrayList<Node> after = ics.getSaved_routes().get(7);
        if (after == null || after.size() != 3 || after.get(1).location != 4) throw new AssertionError("future fault did not invoke alternate route");
        System.out.println("{\"case\":\"future_edge_real_native_replan\",\"status\":\"PASS\",\"before\":" + before + ",\"after\":" + path(after) + "}");
        map = map(); ics = prepared(map); fail(ics, 0, 1, 101);
        if (ics.getSaved_routes().containsKey(7) || !ics.getFault_routes().containsKey(7)
                || !ics.getFault_task_id_List().contains(7)) throw new AssertionError("on-edge fault state was not retained");
        System.out.println("{\"case\":\"current_edge_native_fault_population\",\"status\":\"PASS\",\"saved_routes\":0,\"fault_routes\":1,\"fault_ids\":1}");
        // A previously failed alternate edge is omitted from the subsequent E1 search.
        map = map(); ics = prepared(map);
        for (Edge edge : map.E) if (edge.Star == 1 && edge.End == 4) { edge.fault = true; ics.getFault_edges().add(edge); }
        fail(ics, 2, 3, 101);
        after = ics.getSaved_routes().get(7);
        boolean usesExistingFailure = after != null && after.size() >= 2 && after.get(0).location == 1 && after.get(1).location == 4;
        if (!usesExistingFailure) throw new AssertionError("fixture no longer reproduces native E1-only defect; reevaluate scope");
        System.out.println("{\"case\":\"native_replan_uses_preexisting_failed_edge\",\"expected_defect_reproduced\":true,\"after\":" + path(after) + "}");
    }
}
