import App.Astar;
import App.Edge;
import App.Node;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;

public class LegacyAstarBenchmark {
    private static final class CaseRow {
        final int start;
        final int goal;

        CaseRow(int start, int goal) {
            this.start = start;
            this.goal = goal;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 5) {
            throw new IllegalArgumentException(
                "usage: LegacyAstarBenchmark <mapPath> <casesCsv> <repeats> <warmupRepeats> <pathCsv>"
            );
        }
        System.setProperty("java.awt.headless", "true");
        String mapPath = args[0];
        String casesCsv = args[1];
        int repeats = Integer.parseInt(args[2]);
        int warmupRepeats = Integer.parseInt(args[3]);
        String pathCsv = args[4];

        App.Map map = new App.Map();
        map.read(map, mapPath);
        ArrayList<CaseRow> cases = readCases(casesCsv);
        HashMap<Integer, ArrayList<ArrayList<Double>>> emptyConstraints = new HashMap<>();
        ArrayList<Edge> emptyFaultEdges = new ArrayList<>();

        int warmupChecksum = runPlans(map, cases, warmupRepeats, emptyConstraints, emptyFaultEdges);
        long startNs = System.nanoTime();
        int checksum = runPlans(map, cases, repeats, emptyConstraints, emptyFaultEdges);
        long elapsedNs = System.nanoTime() - startNs;

        writePaths(pathCsv, map, cases, emptyConstraints, emptyFaultEdges);

        double elapsedSeconds = elapsedNs / 1_000_000_000.0;
        int totalPlans = repeats * cases.size();
        double plansPerSecond = elapsedSeconds > 0.0 ? totalPlans / elapsedSeconds : 0.0;
        System.out.println("case_count=" + cases.size());
        System.out.println("repeats=" + repeats);
        System.out.println("warmup_repeats=" + warmupRepeats);
        System.out.println("warmup_checksum=" + warmupChecksum);
        System.out.println("total_plans=" + totalPlans);
        System.out.println("elapsed_seconds=" + elapsedSeconds);
        System.out.println("plans_per_second=" + plansPerSecond);
        System.out.println("checksum=" + checksum);
    }

    private static ArrayList<CaseRow> readCases(String path) throws IOException {
        ArrayList<CaseRow> rows = new ArrayList<>();
        try (BufferedReader reader = new BufferedReader(new FileReader(path))) {
            String line = reader.readLine();
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty()) {
                    continue;
                }
                String[] parts = line.split(",");
                rows.add(new CaseRow(Integer.parseInt(parts[0]), Integer.parseInt(parts[1])));
            }
        }
        return rows;
    }

    private static int runPlans(
        App.Map map,
        ArrayList<CaseRow> cases,
        int repeats,
        HashMap<Integer, ArrayList<ArrayList<Double>>> constraints,
        ArrayList<Edge> faultEdges
    ) {
        int checksum = 0;
        for (int repeat = 0; repeat < repeats; repeat++) {
            for (CaseRow row : cases) {
                checksum += plan(map, row.start, row.goal, constraints, faultEdges).size();
            }
        }
        return checksum;
    }

    private static ArrayList<Node> plan(
        App.Map map,
        int start,
        int goal,
        HashMap<Integer, ArrayList<ArrayList<Double>>> constraints,
        ArrayList<Edge> faultEdges
    ) {
        Node startNode = new Node();
        startNode.setLocation(start);
        startNode.setT1(0.0);
        Node goalNode = new Node();
        goalNode.setLocation(goal);
        return Astar.research(startNode, goalNode, map, constraints, faultEdges);
    }

    private static void writePaths(
        String path,
        App.Map map,
        ArrayList<CaseRow> cases,
        HashMap<Integer, ArrayList<ArrayList<Double>>> constraints,
        ArrayList<Edge> faultEdges
    ) throws IOException {
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(path))) {
            writer.write("start,goal,path");
            writer.newLine();
            for (CaseRow row : cases) {
                ArrayList<Node> route = plan(map, row.start, row.goal, constraints, faultEdges);
                writer.write(row.start + "," + row.goal + ",");
                for (int index = 0; index < route.size(); index++) {
                    if (index > 0) {
                        writer.write(";");
                    }
                    writer.write(Integer.toString(route.get(index).getLocation()));
                }
                writer.newLine();
            }
        }
    }
}
