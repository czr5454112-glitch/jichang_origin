package App;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;

/** Small real-App-class checks; no workload generation or simulation loop. */
public final class HcaTimeLabelAudit {
    private static boolean repaired;
    private static int checks;

    private static void require(boolean value, String detail) {
        if (!value) throw new AssertionError(detail);
    }

    private static void check(boolean value, String name) {
        require(value, name);
        checks++;
    }

    private static Map graph(boolean reservationCase) {
        Map map = new Map();
        map.D = reservationCase ? 6 : 5;
        map.hcost = new double[map.D][map.D];
        for (int i = 0; i < map.D; i++) {
            Vertex node = new Vertex();
            node.location = i;
            node.t = reservationCase && i == 3 ? 1.0 : 0.0;
            map.V.add(node);
            map.N.put(i, new ArrayList<Integer>());
        }
        edge(map, 0, 1, 1.0);
        edge(map, 0, 2, 2.0);
        edge(map, 1, 3, 10.0);
        edge(map, 2, 3, 1.0);
        edge(map, 3, 4, 1.0);
        if (reservationCase) edge(map, 5, 3, 1.0);
        return map;
    }

    private static void edge(Map map, int from, int to, double seconds) {
        Edge edge = new Edge();
        edge.Star = from; edge.End = to; edge.length = seconds; edge.v = 1.0;
        map.E.add(edge); map.N.get(from).add(to);
    }

    private static HashMap<Integer, ArrayList<ArrayList<Double>>> empty(Map map) {
        HashMap<Integer, ArrayList<ArrayList<Double>>> result = new HashMap<>();
        for (int i = 0; i < map.D; i++) result.put(i, new ArrayList<ArrayList<Double>>());
        return result;
    }

    private static ArrayList<Node> search(Map map, int from, int to, double start,
            HashMap<Integer, ArrayList<ArrayList<Double>>> constraints) {
        Node source = new Node(); source.location = from; source.t1 = start;
        Node goal = new Node(); goal.location = to;
        return Astar.research(source, goal, map, constraints, new ArrayList<Edge>());
    }

    private static int mismatches(Map map, ArrayList<Node> route) {
        int count = 0;
        for (int i = 0; i < route.size(); i++) {
            Node node = route.get(i);
            double through = map.V.get(node.location).t;
            if (Math.abs(node.t2 - node.t1 - through) > 1e-7) count++;
            if (i == 0) continue;
            Node parent = route.get(i - 1);
            Edge selected = null;
            for (Edge edge : map.E) if (edge.Star == parent.location && edge.End == node.location) selected = edge;
            require(selected != null, "returned route has missing edge");
            if (Math.abs(node.t1 - parent.t2 - selected.length / selected.v) > 1e-7) count++;
        }
        return count;
    }

    private static String path(ArrayList<Node> route) {
        StringBuilder value = new StringBuilder("[");
        for (Node node : route) {
            if (value.length() > 1) value.append(',');
            value.append("{\"node\":").append(node.location)
                    .append(",\"t1\":").append(node.t1).append(",\"t2\":").append(node.t2).append('}');
        }
        return value.append(']').toString();
    }

    private static void fixtureResult(String name, int mismatchCount, ArrayList<Node> route) {
        System.out.println("{\"case\":\"" + name + "\",\"status\":\"PASS\",\"formula_valid\":"
                + (mismatchCount == 0) + ",\"mismatch_count\":" + mismatchCount + ",\"path\":" + path(route) + "}");
    }

    private static void originalCounterexample() {
        Map map = graph(false);
        ArrayList<Node> route = search(map, 0, 4, 0.0, empty(map));
        int mismatch = mismatches(map, route);
        check(route.size() == 4 && route.get(1).location == 2
                && (repaired ? mismatch == 0 : mismatch > 0)
                && Math.abs(route.get(3).t2 - (repaired ? 4.0 : 12.0)) < 1e-9,
                "five_node_old_failure_new_recurrence");
        fixtureResult("five_node", mismatch, route);
    }

    private static void realMap(String name, String file, int from, int to, double start, boolean oldFailure)
            throws Exception {
        Map map = new Map(); map.read(map, file);
        ArrayList<Node> route = search(map, from, to, start, empty(map));
        require(!route.isEmpty(), "real map OD missing");
        int mismatch = mismatches(map, route);
        check(repaired || !oldFailure ? mismatch == 0 : mismatch > 0, name + "_recurrence");
        fixtureResult(name, mismatch, route);
    }

    private static void reservationChecks() throws Exception {
        Map map = graph(true);
        HashMap<Integer, ArrayList<ArrayList<Double>>> constraints = empty(map);
        constraints.get(3).add(new ArrayList<Double>(Arrays.asList(900.0, 4.5, 10.5)));
        ArrayList<Node> route = search(map, 0, 4, 0.0, constraints);
        Method update = ICS_PathFinding.class.getDeclaredMethod("update_constrain", int.class, ArrayList.class, HashMap.class);
        update.setAccessible(true);
        update.invoke(new ICS_PathFinding(), 100, route, constraints);
        ArrayList<Double> reservation = null;
        for (ArrayList<Double> item : constraints.get(3)) if (item.get(0).intValue() == 100) reservation = item;
        require(reservation != null, "native reservation missing");
        check(constraints.get(3).size() == 2
                && Math.abs(reservation.get(1) - (repaired ? 3.0 : 11.0)) < 1e-9
                && Math.abs(reservation.get(2) - (repaired ? 4.0 : 12.0)) < 1e-9,
                "native_reservation_uses_updated_labels");
        ArrayList<Node> conflicting = search(map, 5, 4, 2.0, constraints);
        check(repaired ? conflicting.isEmpty() : !conflicting.isEmpty(), "new_time_window_conflict_is_blocked");
        ArrayList<Node> late = search(map, 5, 4, 10.1, constraints);
        check(repaired ? !late.isEmpty() : late.isEmpty(), "old_stale_window_is_not_reserved");
        System.out.println("{\"case\":\"native_reservations\",\"status\":\"PASS\",\"reservation\":" + reservation
                + ",\"conflicting_request_blocked\":" + conflicting.isEmpty()
                + ",\"old_window_request_allowed\":" + !late.isEmpty() + "}");
        HashMap<Integer, ArrayList<ArrayList<Double>>> rejection = empty(map);
        rejection.get(3).add(new ArrayList<Double>(Arrays.asList(901.0, 3.0, 4.0)));
        ArrayList<Node> safe = search(map, 0, 4, 0.0, rejection);
        check(safe.size() == 4 && safe.get(1).location == 1 && mismatches(map, safe) == 0
                && Math.abs(safe.get(2).t1 - 11.0) < 1e-9,
                "candidate_conflict_check_still_precedes_relaxation");
        fixtureResult("rejected_earlier_candidate", mismatches(map, safe), safe);
    }

    public static void main(String[] args) throws Exception {
        require(args.length == 3, "mode map2 nanning arguments required");
        repaired = args[0].equals("repaired");
        require(repaired || args[0].equals("original"), "invalid mode");
        originalCounterexample();
        realMap("nanning_24_to_53", args[2], 24, 53, 8866.0, true);
        realMap("map2_5_to_47_control", args[1], 5, 47, 12471.0, false);
        reservationChecks();
        System.out.println("{\"status\":\"PASS\",\"mode\":\"" + args[0] + "\",\"asserted_checks\":" + checks
                + ",\"full_simulation_executed\":false}");
    }
}
