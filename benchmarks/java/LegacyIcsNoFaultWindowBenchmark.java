import App.ICS_PathFinding;
import App.Edge;
import App.Node;
import App.Tasks;
import App.Vertex;
import App.task;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;

public class LegacyIcsNoFaultWindowBenchmark {
    private static final class PlannedRoute {
        final int ordinal;
        final int taskId;
        final int start;
        final int goal;
        final double epoch;
        final double finishTime;
        final ArrayList<Integer> path;

        PlannedRoute(
            int ordinal,
            int taskId,
            int start,
            int goal,
            double epoch,
            double finishTime,
            ArrayList<Integer> path
        ) {
            this.ordinal = ordinal;
            this.taskId = taskId;
            this.start = start;
            this.goal = goal;
            this.epoch = epoch;
            this.finishTime = finishTime;
            this.path = path;
        }
    }

    private static final class RunResult {
        int startEpoch;
        int maxEpochs;
        int maxNewTasks;
        int epochsRun;
        int generatedCount;
        int plannedCount;
        int completedCount;
        int faultEventCount;
        int repairEventCount;
        int activeFaultCount;
        int activeRouteCount;
        int unfinishedCount;
        long routeSizeChecksum;
        long routeLocationChecksum;
        double lastEpoch;
        ArrayList<PlannedRoute> plannedRoutes = new ArrayList<>();
    }

    private static final class ScheduleEvent {
        final int epoch;
        final int start;
        final int end;
        final boolean repair;

        ScheduleEvent(int epoch, int start, int end, boolean repair) {
            this.epoch = epoch;
            this.start = start;
            this.end = end;
            this.repair = repair;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 9) {
            throw new IllegalArgumentException(
                "usage: LegacyIcsNoFaultWindowBenchmark <mapPath> <inputdataPath> <startEpoch> "
                + "<maxEpochs> <maxNewTasks> <repeats> <warmupRepeats> <routeCsv> <summaryCsv> [faultSchedule]"
            );
        }
        System.setProperty("java.awt.headless", "true");
        String mapPath = args[0];
        String inputdataPath = args[1];
        int startEpoch = Integer.parseInt(args[2]);
        int maxEpochs = Integer.parseInt(args[3]);
        int maxNewTasks = Integer.parseInt(args[4]);
        int repeats = Integer.parseInt(args[5]);
        int warmupRepeats = Integer.parseInt(args[6]);
        String routeCsv = args[7];
        String summaryCsv = args[8];
        ArrayList<ScheduleEvent> schedule = args.length > 9 ? parseSchedule(args[9]) : new ArrayList<ScheduleEvent>();

        for (int repeat = 0; repeat < warmupRepeats; repeat++) {
            runOnce(mapPath, inputdataPath, startEpoch, maxEpochs, maxNewTasks, schedule);
        }

        ArrayList<RunResult> runs = new ArrayList<>();
        long startNs = System.nanoTime();
        for (int repeat = 0; repeat < repeats; repeat++) {
            runs.add(runOnce(mapPath, inputdataPath, startEpoch, maxEpochs, maxNewTasks, schedule));
        }
        long elapsedNs = System.nanoTime() - startNs;
        if (runs.isEmpty()) {
            throw new IllegalArgumentException("repeats must be positive");
        }

        writeRoutes(routeCsv, runs.get(0).plannedRoutes);
        writeSummary(summaryCsv, runs);

        RunResult first = runs.get(0);
        double elapsedSeconds = elapsedNs / 1_000_000_000.0;
        double windowsPerSecond = elapsedSeconds > 0.0 ? repeats / elapsedSeconds : 0.0;
        double plansPerSecond = elapsedSeconds > 0.0 ? (double) (first.plannedCount * repeats) / elapsedSeconds : 0.0;
        System.out.println("repeats=" + repeats);
        System.out.println("warmup_repeats=" + warmupRepeats);
        System.out.println("elapsed_seconds=" + elapsedSeconds);
        System.out.println("windows_per_second=" + windowsPerSecond);
        System.out.println("plans_per_second=" + plansPerSecond);
        System.out.println("start_epoch=" + first.startEpoch);
        System.out.println("max_epochs=" + first.maxEpochs);
        System.out.println("max_new_tasks=" + first.maxNewTasks);
        System.out.println("epochs_run=" + first.epochsRun);
        System.out.println("generated_count=" + first.generatedCount);
        System.out.println("planned_count=" + first.plannedCount);
        System.out.println("completed_count=" + first.completedCount);
        System.out.println("fault_event_count=" + first.faultEventCount);
        System.out.println("repair_event_count=" + first.repairEventCount);
        System.out.println("active_fault_count=" + first.activeFaultCount);
        System.out.println("active_route_count=" + first.activeRouteCount);
        System.out.println("unfinished_count=" + first.unfinishedCount);
        System.out.println("route_size_checksum=" + first.routeSizeChecksum);
        System.out.println("route_location_checksum=" + first.routeLocationChecksum);
        System.out.println("last_epoch=" + first.lastEpoch);
    }

    private static RunResult runOnce(
        String mapPath,
        String inputdataPath,
        int startEpoch,
        int maxEpochs,
        int maxNewTasks,
        ArrayList<ScheduleEvent> schedule
    ) throws IOException {
        prepareWorkingFiles();
        RunResult result = new RunResult();
        result.startEpoch = startEpoch;
        result.maxEpochs = maxEpochs;
        result.maxNewTasks = maxNewTasks;

        ICS_PathFinding ics = new ICS_PathFinding();
        ics.getMap().read(ics.getMap(), mapPath);
        HashMap<Integer, ArrayList<task>> taskList = new HashMap<>();
        for (Vertex vertex : ics.getMap().getStar()) {
            taskList.put(vertex.getLocation(), new ArrayList<task>());
        }
        readTaskList(inputdataPath, taskList, 4800.0);
        for (int start : taskList.keySet()) {
            sortTasks(taskList.get(start));
        }

        for (int epochIndex = 0; epochIndex < maxEpochs; epochIndex++) {
            double epoch = startEpoch + epochIndex;
            result.lastEpoch = epoch;
            result.epochsRun = epochIndex + 1;
            applyScheduleEvents(schedule, startEpoch + epochIndex, ics, result);
            Tasks newTasks = new Tasks();
            newTasks.generate_tasks(taskList, newTasks, epoch, ics, 0.0, 0.0, 0.0);
            result.generatedCount += newTasks.getNew_tasks_list().size();
            HashSet<Integer> beforeKeys = new HashSet<>(ics.getSaved_routes().keySet());
            ics.ICS_path_finding(newTasks, ics.getMap(), epoch, ics);
            recordNewRoutes(result, beforeKeys, ics, epoch);
            if (maxNewTasks > 0 && result.generatedCount >= maxNewTasks) {
                break;
            }
        }

        result.completedCount = countLines(new File("output.txt"));
        result.plannedCount = result.plannedRoutes.size();
        result.activeRouteCount = ics.getSaved_routes().size();
        result.unfinishedCount = ics.getUnfinishTasks().size();
        result.activeFaultCount = ics.getFault_edges().size();
        return result;
    }

    private static void applyScheduleEvents(
        ArrayList<ScheduleEvent> schedule,
        int epoch,
        ICS_PathFinding ics,
        RunResult result
    ) {
        for (ScheduleEvent event : schedule) {
            if (event.epoch != epoch) {
                continue;
            }
            Edge edge = findEdge(event.start, event.end, ics);
            if (edge == null) {
                throw new IllegalArgumentException("unknown scheduled edge: " + event.start + "->" + event.end);
            }
            edge.setFault(!event.repair);
            if (event.repair) {
                result.repairEventCount++;
            } else {
                result.faultEventCount++;
            }
        }
    }

    private static Edge findEdge(int start, int end, ICS_PathFinding ics) {
        for (Edge edge : ics.getMap().getE()) {
            if (edge.getStar() == start && edge.getEnd() == end) {
                return edge;
            }
        }
        return null;
    }

    private static void recordNewRoutes(
        RunResult result,
        HashSet<Integer> beforeKeys,
        ICS_PathFinding ics,
        double epoch
    ) {
        ArrayList<Integer> keys = new ArrayList<>(ics.getSaved_routes().keySet());
        Collections.sort(keys);
        for (int key : keys) {
            if (beforeKeys.contains(key)) {
                continue;
            }
            ArrayList<Node> route = ics.getSaved_routes().get(key);
            if (route == null || route.isEmpty()) {
                continue;
            }
            ArrayList<Integer> path = new ArrayList<>();
            for (Node node : route) {
                path.add(node.getLocation());
            }
            PlannedRoute planned = new PlannedRoute(
                result.plannedRoutes.size() + 1,
                key,
                route.get(0).getLocation(),
                route.get(route.size() - 1).getLocation(),
                epoch,
                route.get(route.size() - 1).getT2(),
                path
            );
            result.plannedRoutes.add(planned);
            result.routeSizeChecksum += route.size();
            for (int index = 0; index < route.size(); index++) {
                result.routeLocationChecksum += (long) (index + 1) * (long) (route.get(index).getLocation() + 1);
            }
        }
    }

    private static void prepareWorkingFiles() {
        deleteRecursively(new File("task"));
        new File("task").mkdirs();
        new File("output.txt").delete();
        new File("outputstarttime.txt").delete();
    }

    private static void deleteRecursively(File file) {
        if (!file.exists()) {
            return;
        }
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children != null) {
                for (File child : children) {
                    deleteRecursively(child);
                }
            }
        }
        file.delete();
    }

    private static int countLines(File file) throws IOException {
        if (!file.exists()) {
            return 0;
        }
        int count = 0;
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            while (reader.readLine() != null) {
                count++;
            }
        }
        return count;
    }

    private static void sortTasks(ArrayList<task> tasks) {
        Collections.sort(tasks, new Comparator<task>() {
            @Override
            public int compare(task left, task right) {
                return (int) (left.getPass_time() - right.getPass_time());
            }
        });
    }

    private static void readTaskList(
        String path,
        HashMap<Integer, ArrayList<task>> taskList,
        double earlyBagThreshold
    ) throws IOException {
        BufferedReader reader = new BufferedReader(new FileReader(path));
        reader.readLine();
        String line;
        while ((line = reader.readLine()) != null) {
            if (line.trim().isEmpty()) {
                continue;
            }
            String[] order = line.split(" ");
            task newTask = new task();
            newTask.setTask_ID(Integer.valueOf(order[0]));
            newTask.setPallet_ID(Integer.valueOf(order[0]));
            newTask.setPass_time(Double.valueOf(order[1]));
            newTask.setSTD(Double.valueOf(order[2]));
            newTask.setStar(Integer.valueOf(order[3]));

            if (newTask.getSTD() - newTask.getPass_time() < earlyBagThreshold) {
                newTask.setGoal(Integer.valueOf(order[4]));
                taskList.get(newTask.getStar()).add(newTask);
            } else {
                newTask.setGoal(47);
                taskList.get(newTask.getStar()).add(newTask);

                task storageOut = new task();
                storageOut.setTask_ID(Integer.valueOf(order[0]));
                storageOut.setPallet_ID(Integer.valueOf(order[0]));
                storageOut.setSTD(Double.valueOf(order[2]));
                storageOut.setPass_time(storageOut.getSTD() - 2700);
                storageOut.setStar(52);
                storageOut.setGoal(Integer.valueOf(order[4]));
                taskList.get(storageOut.getStar()).add(storageOut);
            }
        }
        reader.close();
    }

    private static ArrayList<ScheduleEvent> parseSchedule(String spec) {
        ArrayList<ScheduleEvent> events = new ArrayList<>();
        if (spec == null || spec.trim().isEmpty() || spec.equalsIgnoreCase("none")) {
            return events;
        }
        String[] chunks = spec.split(";");
        for (String chunk : chunks) {
            if (chunk.trim().isEmpty()) {
                continue;
            }
            String[] parts = chunk.split(":");
            if (parts.length != 4) {
                throw new IllegalArgumentException("invalid schedule event: " + chunk);
            }
            String action = parts[3].trim().toLowerCase();
            boolean repair;
            if (action.equals("repair") || action.equals("repaired")) {
                repair = true;
            } else if (action.equals("fault") || action.equals("fail")) {
                repair = false;
            } else {
                throw new IllegalArgumentException("invalid schedule action: " + parts[3]);
            }
            events.add(
                new ScheduleEvent(
                    Integer.parseInt(parts[0].trim()),
                    Integer.parseInt(parts[1].trim()),
                    Integer.parseInt(parts[2].trim()),
                    repair
                )
            );
        }
        return events;
    }

    private static String pathText(List<Integer> path) {
        StringBuilder builder = new StringBuilder();
        for (int index = 0; index < path.size(); index++) {
            if (index > 0) {
                builder.append(';');
            }
            builder.append(path.get(index));
        }
        return builder.toString();
    }

    private static void writeRoutes(String path, ArrayList<PlannedRoute> routes) throws IOException {
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(path))) {
            writer.write("ordinal,task_id,start,goal,epoch,finish_time,path");
            writer.newLine();
            for (PlannedRoute route : routes) {
                writer.write(
                    route.ordinal + "," + route.taskId + "," + route.start + "," + route.goal + ","
                        + route.epoch + "," + route.finishTime + "," + pathText(route.path)
                );
                writer.newLine();
            }
        }
    }

    private static void writeSummary(String path, ArrayList<RunResult> runs) throws IOException {
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(path))) {
            writer.write(
                "repeat,start_epoch,max_epochs,max_new_tasks,epochs_run,generated_count,planned_count,"
                    + "completed_count,fault_event_count,repair_event_count,active_fault_count,"
                    + "active_route_count,unfinished_count,route_size_checksum,"
                    + "route_location_checksum,last_epoch"
            );
            writer.newLine();
            for (int index = 0; index < runs.size(); index++) {
                RunResult run = runs.get(index);
                writer.write(
                    (index + 1) + "," + run.startEpoch + "," + run.maxEpochs + "," + run.maxNewTasks + ","
                        + run.epochsRun + "," + run.generatedCount + "," + run.plannedCount + ","
                        + run.completedCount + "," + run.faultEventCount + "," + run.repairEventCount + ","
                        + run.activeFaultCount + "," + run.activeRouteCount + "," + run.unfinishedCount + ","
                        + run.routeSizeChecksum + "," + run.routeLocationChecksum + "," + run.lastEpoch
                );
                writer.newLine();
            }
        }
    }
}
