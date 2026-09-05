package App;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Random;

/** Command-line entry point for the independent Feng-environment reconstruction. */
public final class FengDhBenchmark {
    private static final String METHOD = "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION";
    private static final String REPRODUCTION_LEVEL =
            "SEMANTICALLY_PARTIAL_RECONSTRUCTION";
    private static final double EARLY_BAG_THRESHOLD_SECONDS = 4_800.0d;
    private static final double EBS_RELEASE_LEAD_SECONDS = 2_700.0d;
    private static final int DEFAULT_STORAGE_IN_GOAL = 47;
    private static final int DEFAULT_STORAGE_OUT_START = 52;

    private static final class ScheduleRow {
        final long rawBagId;
        final int segmentId;
        final int start;
        final int goal;
        final double scheduledReleaseSeconds;

        ScheduleRow(
                long rawBagId,
                int segmentId,
                int start,
                int goal,
                double scheduledReleaseSeconds) {
            this.rawBagId = rawBagId;
            this.segmentId = segmentId;
            this.start = start;
            this.goal = goal;
            this.scheduledReleaseSeconds = scheduledReleaseSeconds;
        }
    }

    private static final class ScheduleData {
        final File path;
        final LinkedHashMap<String, ScheduleRow> rows;

        ScheduleData(File path, LinkedHashMap<String, ScheduleRow> rows) {
            this.path = path;
            this.rows = rows;
        }
    }

    private static final class RawInput {
        final long sourceRawId;
        final double entrySeconds;
        final double deadlineSeconds;
        final int start;
        final int goal;
        final String unloader;
        final String loader;
        final String sourceRow;

        RawInput(
                long sourceRawId,
                double entrySeconds,
                double deadlineSeconds,
                int start,
                int goal,
                String unloader,
                String loader,
                String sourceRow) {
            this.sourceRawId = sourceRawId;
            this.entrySeconds = entrySeconds;
            this.deadlineSeconds = deadlineSeconds;
            this.start = start;
            this.goal = goal;
            this.unloader = unloader;
            this.loader = loader;
            this.sourceRow = sourceRow;
        }
    }

    private static final class RawResult {
        final long rawBagId;
        final long sourceRawBagId;
        final int segmentCount;
        final boolean complete;
        final double rawEntrySeconds;
        final double deadlineSeconds;
        final double finalCompletionSeconds;
        final double rawEntryToFinalSeconds;
        final double table53ScheduledIntervalSeconds;
        final double diagnosticFirstAdmissionToCompletionSeconds;

        RawResult(
                long rawBagId,
                long sourceRawBagId,
                int segmentCount,
                boolean complete,
                double rawEntrySeconds,
                double deadlineSeconds,
                double finalCompletionSeconds,
                double rawEntryToFinalSeconds,
                double table53ScheduledIntervalSeconds,
                double diagnosticFirstAdmissionToCompletionSeconds) {
            this.rawBagId = rawBagId;
            this.sourceRawBagId = sourceRawBagId;
            this.segmentCount = segmentCount;
            this.complete = complete;
            this.rawEntrySeconds = rawEntrySeconds;
            this.deadlineSeconds = deadlineSeconds;
            this.finalCompletionSeconds = finalCompletionSeconds;
            this.rawEntryToFinalSeconds = rawEntryToFinalSeconds;
            this.table53ScheduledIntervalSeconds = table53ScheduledIntervalSeconds;
            this.diagnosticFirstAdmissionToCompletionSeconds =
                    diagnosticFirstAdmissionToCompletionSeconds;
        }
    }

    private static final class SummaryStats {
        final int count;
        final double minimum;
        final double mean;
        final double p95;
        final double p99;
        final double maximum;

        SummaryStats(List<Double> source) {
            ArrayList<Double> values = new ArrayList<Double>(source);
            Collections.sort(values);
            this.count = values.size();
            if (values.isEmpty()) {
                this.minimum = Double.NaN;
                this.mean = Double.NaN;
                this.p95 = Double.NaN;
                this.p99 = Double.NaN;
                this.maximum = Double.NaN;
            } else {
                double total = 0.0d;
                for (Double value : values) {
                    total += value.doubleValue();
                }
                this.minimum = values.get(0).doubleValue();
                this.mean = total / values.size();
                this.p95 = percentile(values, 0.95d);
                this.p99 = percentile(values, 0.99d);
                this.maximum = values.get(values.size() - 1).doubleValue();
            }
        }
    }

    private static final class MicroResult {
        final String caseId;
        final String inputJson;
        final String expectedJson;
        final String actualJson;
        final String expectedTickTrace;
        final String actualTickTrace;
        final boolean passed;

        MicroResult(
                String caseId,
                String inputJson,
                String expectedJson,
                String actualJson,
                String expectedTickTrace,
                String actualTickTrace,
                boolean passed) {
            this.caseId = caseId;
            this.inputJson = inputJson;
            this.expectedJson = expectedJson;
            this.actualJson = actualJson;
            this.expectedTickTrace = expectedTickTrace;
            this.actualTickTrace = actualTickTrace;
            this.passed = passed;
        }

        String toJsonLine() {
            return "{\"case_id\":\"" + json(caseId)
                    + "\",\"input\":" + inputJson
                    + ",\"expected\":" + expectedJson
                    + ",\"actual\":" + actualJson
                    + ",\"expected_tick_trace\":\"" + json(expectedTickTrace)
                    + "\",\"actual_tick_trace\":\"" + json(actualTickTrace)
                    + "\",\"tick_trace\":\"" + json(actualTickTrace)
                    + "\",\"pass\":" + passed + "}";
        }
    }

    private FengDhBenchmark() {
    }

    public static void main(String[] args) throws Exception {
        Locale.setDefault(Locale.ROOT);
        if (args.length == 0) {
            usage();
            System.exit(2);
        }
        if ("microtests".equals(args[0])) {
            int failures = runMicrotests(parseOptions(args, 1));
            if (failures != 0) {
                System.exit(1);
            }
            return;
        }
        if ("run".equals(args[0])) {
            runFormal(parseOptions(args, 1));
            return;
        }
        if ("static-bridge".equals(args[0])) {
            runStaticBridge(parseOptions(args, 1));
            return;
        }
        usage();
        throw new IllegalArgumentException("unknown command: " + args[0]);
    }

    /**
     * Execute one otherwise-empty-network bag for every reachable ordered OD.
     * This is a diagnostic control, not a DH coefficient cell: the exact 0/0
     * penalties make route selection purely free-flow while retaining the
     * Feng executor's 0.2 s edge lattice and goal-arrival mechanics.
     */
    private static void runStaticBridge(HashMap<String, String> options) throws Exception {
        File mapPath = new File(required(options, "--map"));
        File outputPath = new File(required(options, "--csv-out"));
        File parent = outputPath.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new IOException("cannot create bridge output directory " + parent);
        }
        FengDhEdgeLattice lattice = FengDhEdgeLattice.readLegacyMap(mapPath);
        FengDhPolicy policy = new FengDhPolicy(lattice, 0.0d, 0.0d);
        ArrayList<Integer> nodes = new ArrayList<Integer>(lattice.nodes().keySet());
        Collections.sort(nodes);
        BufferedWriter writer = Files.newBufferedWriter(
                outputPath.toPath(), StandardCharsets.UTF_8);
        int reachable = 0;
        try {
            writer.write(csvRow(values(
                    "start_node", "goal_node", "node_path", "edge_path",
                    "edge_count", "origin_equal_score_candidates",
                    "ideal_free_flow_seconds", "edge_quantized_seconds",
                    "legacy_path_node_service_seconds",
                    "post_admission_node_service_seconds",
                    "edge_plus_post_admission_node_service_quantized_seconds",
                    "observed_single_bag_seconds", "quantization_bias_seconds",
                    "observed_matches_edge_quantization",
                    "observed_matches_edge_plus_post_admission_node_service_quantization")));
            writer.newLine();
            long taskId = 1L;
            for (Integer startValue : nodes) {
                for (Integer goalValue : nodes) {
                    int start = startValue.intValue();
                    int goal = goalValue.intValue();
                    if (start == goal) {
                        continue;
                    }
                    FengDhPolicy.Path path = policy.shortestPath(start, goal);
                    if (path == null) {
                        continue;
                    }
                    FengDhPolicy.Decision origin = policy.choose(
                            start, goal, lattice.snapshot());
                    double edgeQuantized = 0.0d;
                    for (Integer edgeId : path.edgeIds) {
                        edgeQuantized += lattice.edge(edgeId.intValue()).cellCount
                                * FengDhEdgeLattice.TICK_SECONDS;
                    }
                    double pathNodeService = 0.0d;
                    double postAdmissionNodeService = 0.0d;
                    for (int nodeIndex = 0; nodeIndex < path.nodeIds.size(); nodeIndex++) {
                        Integer nodeId = path.nodeIds.get(nodeIndex);
                        double service;
                        if (nodeIndex == 0) {
                            service = FengDhSimulator.RECONSTRUCTED_TRANSFER_DURATION_SECONDS;
                        } else if (nodeIndex == path.nodeIds.size() - 1) {
                            service = 0.0d;
                        } else {
                            service = quantizedNodeServiceSeconds(
                                    lattice.nodes().get(nodeId).throughTimeSeconds
                                            + FengDhSimulator.RECONSTRUCTED_TRANSFER_DURATION_SECONDS);
                        }
                        pathNodeService += service;
                        if (nodeIndex > 0) {
                            // The bridge observes completion minus first edge
                            // admission as an explicitly diagnostic view;
                            // source service belongs to the pre-admission view.
                            postAdmissionNodeService += service;
                        }
                    }
                    double physicalQuantized = edgeQuantized + postAdmissionNodeService;
                    FengDhBagState bag = new FengDhBagState(
                            taskId, taskId, 0, 1, 0.0d, 0.0d, 0L,
                            100_000.0d, start, goal, false,
                            taskId + " 0 100000 " + start + " " + goal + " BRIDGE BRIDGE");
                    FengDhSimulator simulator = new FengDhSimulator(
                            lattice, policy, Collections.singletonList(bag));
                    FengDhSimulator.RunResult result = simulator.run(
                            FengDhSimulator.RunConfig.untilComplete(0));
                    if (!"COMPLETE".equals(result.status) || !bag.isCompleted()) {
                        throw new IllegalStateException(
                                "single-bag static bridge did not complete for "
                                        + start + "->" + goal);
                    }
                    double observed = ticksToSeconds(
                            bag.getCompletionTick() - bag.getFirstAdmissionTick());
                    boolean edgeOnlyMatch = Math.abs(observed - edgeQuantized) <= 1.0e-9d;
                    boolean physicalMatch = Math.abs(observed - physicalQuantized) <= 1.0e-9d;
                    writer.write(csvRow(values(
                            start,
                            goal,
                            join(path.nodeIds),
                            join(path.edgeIds),
                            path.edgeIds.size(),
                            origin == null ? 0 : origin.equalScoreCandidateCount,
                            path.freeFlowSeconds,
                            edgeQuantized,
                            pathNodeService,
                            postAdmissionNodeService,
                            physicalQuantized,
                            observed,
                            observed - physicalQuantized,
                            edgeOnlyMatch,
                            physicalMatch)));
                    writer.newLine();
                    reachable++;
                    taskId++;
                }
            }
        } finally {
            writer.close();
        }
        System.out.println("method=STATIC_FREE_FLOW_FENG_EXECUTOR"
                + " reachable_od=" + reachable
                + " output=" + outputPath.getAbsolutePath());
    }

    private static void runFormal(HashMap<String, String> options) throws Exception {
        File mapPath = new File(required(options, "--map"));
        File inputPath = new File(required(options, "--input"));
        File outputDirectory = new File(required(options, "--output"));
        File schedulePath = options.containsKey("--schedule")
                ? new File(options.get("--schedule")) : null;
        int limit = integerOption(options, "--limit", 0);
        double workloadScale = doubleOption(options, "--workload-scale", 1.0d);
        long seed = longOption(options, "--seed", 0L);
        double horizonSeconds = doubleOption(options, "--horizon-seconds", 0.0d);
        int traceSampleModulo = integerOption(options, "--trace-sample-modulo", 0);
        int storageInGoal = integerOption(
                options, "--storage-in-goal", DEFAULT_STORAGE_IN_GOAL);
        int storageOutStart = integerOption(
                options, "--storage-out-start", DEFAULT_STORAGE_OUT_START);
        boolean formalTimingRequested = booleanOption(
                options, "--formal-timing-eligible", true);
        if (limit < 0 || workloadScale <= 0.0d || horizonSeconds < 0.0d
                || traceSampleModulo < 0 || storageInGoal < 0 || storageOutStart < 0) {
            throw new IllegalArgumentException(
                    "limit/horizon/trace/storage nodes must be nonnegative and scale positive");
        }
        if (!outputDirectory.exists() && !outputDirectory.mkdirs()) {
            throw new IOException("cannot create output directory " + outputDirectory);
        }
        FengDhEdgeLattice lattice = FengDhEdgeLattice.readLegacyMap(mapPath);
        double alpha = doubleOption(options, "--alpha", lattice.headwaySeconds());
        double beta = doubleOption(options, "--beta", 2.0d * alpha);
        FengDhPolicy policy = new FengDhPolicy(lattice, alpha, beta);
        List<RawInput> rawInputs = readRawInputs(inputPath, limit);
        List<RawInput> scaledInputs = scaleInputs(rawInputs, workloadScale, seed);
        ScheduleData schedule = schedulePath == null ? null : readSchedule(schedulePath);
        List<FengDhBagState> segments = expandSegments(
                scaledInputs, schedule, storageInGoal, storageOutStart);
        FengDhSimulator simulator = new FengDhSimulator(lattice, policy, segments);
        long horizonTick = horizonSeconds <= 0.0d
                ? Long.MAX_VALUE : secondsToReleaseTick(horizonSeconds);
        long wallStart = System.nanoTime();
        FengDhSimulator.RunResult result = simulator.run(
                new FengDhSimulator.RunConfig(horizonTick, traceSampleModulo, 50_000L));
        double wallSeconds = (System.nanoTime() - wallStart) / 1.0e9d;
        List<RawResult> rawResults = buildRawResults(segments);
        writeSegments(new File(outputDirectory, "segments.csv"), segments);
        writeRawBags(new File(outputDirectory, "bags.csv"), rawResults);
        writeTrace(new File(outputDirectory, "trace.csv"), segments);
        writeEventSummary(new File(outputDirectory, "event_summary.csv"), result);
        writeSummary(
                new File(outputDirectory, "summary.csv"),
                mapPath,
                inputPath,
                schedule,
                lattice,
                policy,
                result,
                rawResults,
                segments,
                workloadScale,
                seed,
                limit,
                horizonSeconds,
                storageInGoal,
                storageOutStart,
                formalTimingRequested,
                wallSeconds);
        String executedMethod = isStaticControl(policy)
                ? "STATIC_FREE_FLOW_FENG_EXECUTOR" : METHOD;
        System.out.println("method=" + executedMethod
                + " status=" + result.status
                + " raw_bags=" + result.completedRawBags + "/" + result.rawBagPopulation
                + " segments=" + result.completedSegments + "/" + result.segmentPopulation
                + " output=" + outputDirectory.getAbsolutePath());
    }

    private static List<RawInput> readRawInputs(File path, int limit) throws IOException {
        BufferedReader reader = new BufferedReader(new FileReader(path));
        try {
            String header = reader.readLine();
            if (header == null || !header.contains("EntryTime")) {
                throw new IOException("legacy input header is missing EntryTime: " + path);
            }
            ArrayList<RawInput> rows = new ArrayList<RawInput>();
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty()) {
                    continue;
                }
                String[] fields = line.trim().split("\\s+");
                if (fields.length < 7) {
                    throw new IOException("legacy task row has fewer than seven fields: " + line);
                }
                rows.add(new RawInput(
                        Long.parseLong(fields[0]),
                        Double.parseDouble(fields[1]),
                        Double.parseDouble(fields[2]),
                        Integer.parseInt(fields[3]),
                        Integer.parseInt(fields[4]),
                        fields[5],
                        fields[6],
                        line.trim()));
                if (limit > 0 && rows.size() >= limit) {
                    break;
                }
            }
            return rows;
        } finally {
            reader.close();
        }
    }

    private static ScheduleData readSchedule(File path) throws IOException {
        if (!path.isFile()) {
            throw new IOException("schedule is not a regular file: " + path);
        }
        BufferedReader reader = Files.newBufferedReader(path.toPath(), StandardCharsets.UTF_8);
        try {
            String header = reader.readLine();
            if (header != null && header.startsWith("\ufeff")) {
                header = header.substring(1);
            }
            String expected = "raw_bag_id,segment_id,start,goal,scheduled_release_seconds";
            if (!expected.equals(header)) {
                throw new IOException("schedule header must be exactly " + expected);
            }
            LinkedHashMap<String, ScheduleRow> rows =
                    new LinkedHashMap<String, ScheduleRow>();
            String line;
            int lineNumber = 1;
            while ((line = reader.readLine()) != null) {
                lineNumber++;
                if (line.trim().isEmpty()) {
                    throw new IOException("blank schedule row at line " + lineNumber);
                }
                String[] fields = line.split(",", -1);
                if (fields.length != 5) {
                    throw new IOException(
                            "schedule row must have five columns at line " + lineNumber);
                }
                try {
                    long rawBagId = Long.parseLong(fields[0].trim());
                    int segmentId = Integer.parseInt(fields[1].trim());
                    int start = Integer.parseInt(fields[2].trim());
                    int goal = Integer.parseInt(fields[3].trim());
                    double release = Double.parseDouble(fields[4].trim());
                    if (segmentId < 0 || !Double.isFinite(release)) {
                        throw new IOException("invalid segment/release at schedule line "
                                + lineNumber);
                    }
                    ScheduleRow row = new ScheduleRow(
                            rawBagId, segmentId, start, goal, release);
                    String key = segmentKey(rawBagId, segmentId);
                    if (rows.put(key, row) != null) {
                        throw new IOException("duplicate schedule key " + key);
                    }
                } catch (NumberFormatException error) {
                    throw new IOException(
                            "invalid numeric schedule field at line " + lineNumber, error);
                }
            }
            if (rows.isEmpty()) {
                throw new IOException("schedule contains no data rows: " + path);
            }
            return new ScheduleData(path.getAbsoluteFile(), rows);
        } finally {
            reader.close();
        }
    }

    private static List<RawInput> scaleInputs(
            List<RawInput> source, double workloadScale, long seed) {
        if (source.isEmpty()) {
            return Collections.emptyList();
        }
        int target = Math.max(1, (int) Math.round(source.size() * workloadScale));
        ArrayList<RawInput> result = new ArrayList<RawInput>(target);
        int fullCopies = target / source.size();
        int remainder = target % source.size();
        for (int copy = 0; copy < fullCopies; copy++) {
            result.addAll(source);
        }
        if (remainder > 0) {
            ArrayList<Integer> order = new ArrayList<Integer>();
            for (int index = 0; index < source.size(); index++) {
                order.add(Integer.valueOf(index));
            }
            Collections.shuffle(order, new Random(seed));
            ArrayList<Integer> selected = new ArrayList<Integer>(order.subList(0, remainder));
            Collections.sort(selected);
            for (Integer index : selected) {
                result.add(source.get(index.intValue()));
            }
        }
        return result;
    }

    private static List<FengDhBagState> expandSegments(
            List<RawInput> raws,
            ScheduleData schedule,
            int storageInGoal,
            int storageOutStart) {
        ArrayList<FengDhBagState> segments = new ArrayList<FengDhBagState>();
        HashSet<String> usedScheduleRows = new HashSet<String>();
        HashSet<Long> sourceIds = new HashSet<Long>();
        boolean sourceIdsUnique = true;
        for (RawInput raw : raws) {
            sourceIdsUnique = sourceIds.add(Long.valueOf(raw.sourceRawId)) && sourceIdsUnique;
        }
        for (int ordinal = 0; ordinal < raws.size(); ordinal++) {
            RawInput raw = raws.get(ordinal);
            long rawId = sourceIdsUnique ? raw.sourceRawId : ordinal;
            boolean early = raw.deadlineSeconds - raw.entrySeconds
                    >= EARLY_BAG_THRESHOLD_SECONDS;
            int segmentCount = early ? 2 : 1;
            ScheduleRow firstSchedule = scheduleRow(
                    schedule,
                    rawId,
                    0,
                    raw.start,
                    early ? storageInGoal : raw.goal,
                    usedScheduleRows);
            double firstRelease = firstSchedule == null
                    ? raw.entrySeconds : firstSchedule.scheduledReleaseSeconds;
            segments.add(new FengDhBagState(
                    rawId * 2L,
                    rawId,
                    0,
                    segmentCount,
                    raw.entrySeconds,
                    firstRelease,
                    secondsToReleaseTick(firstRelease),
                    raw.deadlineSeconds,
                    raw.start,
                    early ? storageInGoal : raw.goal,
                    early,
                    raw.sourceRow));
            if (early) {
                ScheduleRow secondSchedule = scheduleRow(
                        schedule,
                        rawId,
                        1,
                        storageOutStart,
                        raw.goal,
                        usedScheduleRows);
                double release = secondSchedule == null
                        ? raw.deadlineSeconds - EBS_RELEASE_LEAD_SECONDS
                        : secondSchedule.scheduledReleaseSeconds;
                segments.add(new FengDhBagState(
                        rawId * 2L + 1L,
                        rawId,
                        1,
                        2,
                        raw.entrySeconds,
                        release,
                        secondsToReleaseTick(release),
                        raw.deadlineSeconds,
                        storageOutStart,
                        raw.goal,
                        true,
                raw.sourceRow));
            }
        }
        if (schedule != null && usedScheduleRows.size() != schedule.rows.size()) {
            ArrayList<String> extra = new ArrayList<String>();
            for (String key : schedule.rows.keySet()) {
                if (!usedScheduleRows.contains(key)) {
                    extra.add(key);
                }
            }
            throw new IllegalArgumentException(
                    "schedule has extra rows not present in workload segments: " + extra);
        }
        return segments;
    }

    private static ScheduleRow scheduleRow(
            ScheduleData schedule,
            long rawBagId,
            int segmentId,
            int expectedStart,
            int expectedGoal,
            HashSet<String> usedRows) {
        if (schedule == null) {
            return null;
        }
        String key = segmentKey(rawBagId, segmentId);
        ScheduleRow row = schedule.rows.get(key);
        if (row == null) {
            throw new IllegalArgumentException("schedule is missing workload segment " + key);
        }
        if (row.start != expectedStart || row.goal != expectedGoal) {
            throw new IllegalArgumentException(
                    "schedule OD mismatch for " + key + ": expected "
                            + expectedStart + "->" + expectedGoal + " but found "
                            + row.start + "->" + row.goal);
        }
        if (!usedRows.add(key)) {
            throw new IllegalArgumentException("workload reused schedule segment " + key);
        }
        return row;
    }

    private static String segmentKey(long rawBagId, int segmentId) {
        return rawBagId + ":" + segmentId;
    }

    private static List<RawResult> buildRawResults(List<FengDhBagState> segments) {
        LinkedHashMap<Long, ArrayList<FengDhBagState>> grouped =
                new LinkedHashMap<Long, ArrayList<FengDhBagState>>();
        for (FengDhBagState bag : segments) {
            ArrayList<FengDhBagState> values = grouped.get(Long.valueOf(bag.rawBagId));
            if (values == null) {
                values = new ArrayList<FengDhBagState>();
                grouped.put(Long.valueOf(bag.rawBagId), values);
            }
            values.add(bag);
        }
        ArrayList<RawResult> results = new ArrayList<RawResult>();
        for (java.util.Map.Entry<Long, ArrayList<FengDhBagState>> entry : grouped.entrySet()) {
            ArrayList<FengDhBagState> values = entry.getValue();
            Collections.sort(values, new Comparator<FengDhBagState>() {
                @Override
                public int compare(FengDhBagState left, FengDhBagState right) {
                    return Integer.compare(left.segmentId, right.segmentId);
                }
            });
            FengDhBagState first = values.get(0);
            boolean complete = values.size() == first.segmentCount;
            double finalCompletion = Double.NaN;
            double table53ScheduledInterval = 0.0d;
            double diagnosticFirstAdmissionInterval = 0.0d;
            for (FengDhBagState bag : values) {
                complete = complete && bag.isCompleted();
                if (bag.isCompleted()) {
                    double completion = ticksToSeconds(bag.getCompletionTick());
                    finalCompletion = Math.max(
                            finalCompletionOrNegative(finalCompletion), completion);
                    table53ScheduledInterval += completion - bag.releaseSeconds;
                    if (bag.getFirstAdmissionTick() >= 0L) {
                        diagnosticFirstAdmissionInterval += ticksToSeconds(
                                bag.getCompletionTick() - bag.getFirstAdmissionTick());
                    } else {
                        complete = false;
                    }
                }
            }
            if (!complete) {
                finalCompletion = Double.NaN;
                table53ScheduledInterval = Double.NaN;
                diagnosticFirstAdmissionInterval = Double.NaN;
            }
            results.add(new RawResult(
                    first.rawBagId,
                    sourceRawId(first.sourceRow),
                    first.segmentCount,
                    complete,
                    first.rawEntrySeconds,
                    first.deadlineSeconds,
                    finalCompletion,
                    complete ? finalCompletion - first.rawEntrySeconds : Double.NaN,
                    table53ScheduledInterval,
                    diagnosticFirstAdmissionInterval));
        }
        return results;
    }

    private static void writeSummary(
            File path,
            File mapPath,
            File inputPath,
            ScheduleData schedule,
            FengDhEdgeLattice lattice,
            FengDhPolicy policy,
            FengDhSimulator.RunResult result,
            List<RawResult> rawResults,
            List<FengDhBagState> segments,
            double workloadScale,
            long seed,
            int limit,
            double horizonSeconds,
            int storageInGoal,
            int storageOutStart,
            boolean formalTimingRequested,
            double wallSeconds) throws IOException, NoSuchAlgorithmException {
        ArrayList<Double> table53Scheduled = new ArrayList<Double>();
        ArrayList<Double> diagnosticFirstAdmission = new ArrayList<Double>();
        ArrayList<Double> rawWall = new ArrayList<Double>();
        ArrayList<Double> segmentRelease = new ArrayList<Double>();
        ArrayList<Double> segmentFirstAdmission = new ArrayList<Double>();
        ArrayList<Double> segmentSourceWait = new ArrayList<Double>();
        int onTime = 0;
        for (RawResult raw : rawResults) {
            if (raw.complete) {
                table53Scheduled.add(Double.valueOf(raw.table53ScheduledIntervalSeconds));
                diagnosticFirstAdmission.add(Double.valueOf(
                        raw.diagnosticFirstAdmissionToCompletionSeconds));
                rawWall.add(Double.valueOf(raw.rawEntryToFinalSeconds));
                if (raw.finalCompletionSeconds <= raw.deadlineSeconds + 1.0e-9d) {
                    onTime++;
                }
            }
        }
        for (FengDhBagState segment : segments) {
            if (!segment.isCompleted()) {
                continue;
            }
            double completion = ticksToSeconds(segment.getCompletionTick());
            double admission = ticksToSeconds(segment.getFirstAdmissionTick());
            segmentRelease.add(Double.valueOf(completion - segment.releaseSeconds));
            segmentFirstAdmission.add(Double.valueOf(completion - admission));
            segmentSourceWait.add(Double.valueOf(admission - segment.releaseSeconds));
        }
        SummaryStats table53Stats = new SummaryStats(table53Scheduled);
        SummaryStats diagnosticFirstAdmissionStats =
                new SummaryStats(diagnosticFirstAdmission);
        SummaryStats rawStats = new SummaryStats(rawWall);
        SummaryStats segmentReleaseStats = new SummaryStats(segmentRelease);
        SummaryStats segmentFirstAdmissionStats = new SummaryStats(segmentFirstAdmission);
        SummaryStats segmentSourceWaitStats = new SummaryStats(segmentSourceWait);
        SummaryStats unavailableStats = new SummaryStats(Collections.<Double>emptyList());
        ArrayList<String> header = new ArrayList<String>();
        ArrayList<String> values = new ArrayList<String>();
        boolean staticControl = isStaticControl(policy);
        add(header, values, "method",
                staticControl ? "STATIC_FREE_FLOW_FENG_EXECUTOR" : METHOD);
        add(header, values, "status", result.status);
        add(header, values, "reproduction_level",
                staticControl ? "EXECUTOR_BRIDGE_STATIC_CONTROL" : REPRODUCTION_LEVEL);
        add(header, values, "coefficient_disclosure_status",
                staticControl ? "NOT_APPLICABLE_STATIC_CONTROL"
                        : "UNDISCLOSED_SENSITIVITY_REQUIRED");
        add(header, values, "map_path", mapPath.getAbsolutePath());
        add(header, values, "map_sha256", sha256(mapPath));
        add(header, values, "input_path", inputPath.getAbsolutePath());
        add(header, values, "input_sha256", sha256(inputPath));
        add(header, values, "schedule_path",
                schedule == null ? "" : schedule.path.getAbsolutePath());
        add(header, values, "schedule_sha256",
                schedule == null ? "" : sha256(schedule.path));
        add(header, values, "schedule_row_count",
                schedule == null ? 0 : schedule.rows.size());
        add(header, values, "table53_start_semantics",
                schedule == null
                        ? "DERIVED_RELEASE_COMPATIBILITY_ONLY_NOT_TABLE53"
                        : "FROZEN_SHARED_SCHEDULE_D");
        add(header, values, "raw_bag_count", result.rawBagPopulation);
        add(header, values, "completed_raw_bags", result.completedRawBags);
        add(header, values, "on_time_raw_bags", onTime);
        add(header, values, "segment_count", result.segmentPopulation);
        add(header, values, "completed_segments", result.completedSegments);
        boolean fullPopulationComplete = result.completedRawBags == result.rawBagPopulation;
        boolean formalTimingEligible = formalTimingRequested && fullPopulationComplete;
        boolean table53TimingEligible = formalTimingEligible && schedule != null;
        add(header, values, "formal_timing_requested", formalTimingRequested);
        add(header, values, "full_population_timing_eligible", formalTimingEligible);
        add(header, values, "table53_timing_eligible", table53TimingEligible);
        add(header, values, "table53_scheduled_interval_count",
                table53TimingEligible ? table53Stats.count : 0);
        addStats(header, values, "table53_scheduled_interval",
                table53TimingEligible ? table53Stats : unavailableStats);
        addStats(header, values, "raw_entry_to_final",
                formalTimingEligible ? rawStats : unavailableStats);
        addStats(header, values, "segment_release_to_completion",
                formalTimingEligible ? segmentReleaseStats : unavailableStats);
        addStats(header, values, "diagnostic_first_admission_to_completion",
                formalTimingEligible ? diagnosticFirstAdmissionStats : unavailableStats);
        addStats(header, values, "diagnostic_segment_first_admission_to_completion",
                formalTimingEligible ? segmentFirstAdmissionStats : unavailableStats);
        addStats(header, values, "segment_source_wait",
                formalTimingEligible ? segmentSourceWaitStats : unavailableStats);
        SummaryStats diagnosticRawStats = formalTimingEligible
                ? rawStats : unavailableStats;
        SummaryStats diagnosticSegmentReleaseStats = formalTimingEligible
                ? segmentReleaseStats : unavailableStats;
        SummaryStats diagnosticSegmentFirstAdmissionStats = formalTimingEligible
                ? segmentFirstAdmissionStats : unavailableStats;
        SummaryStats diagnosticSegmentSourceWaitStats = formalTimingEligible
                ? segmentSourceWaitStats : unavailableStats;
        add(header, values, "diagnostic_survivor_raw_bag_count",
                formalTimingEligible ? table53Stats.count : 0);
        addStats(header, values, "diagnostic_survivor_raw_entry_to_final",
                diagnosticRawStats);
        addStats(header, values, "diagnostic_survivor_segment_release_to_completion",
                diagnosticSegmentReleaseStats);
        addStats(header, values,
                "diagnostic_survivor_segment_first_admission_to_completion",
                diagnosticSegmentFirstAdmissionStats);
        addStats(header, values, "diagnostic_survivor_segment_source_wait",
                diagnosticSegmentSourceWaitStats);
        add(header, values, "alpha_move_seconds", policy.getAlphaMoveSeconds());
        add(header, values, "beta_stop_seconds", policy.getBetaStopSeconds());
        add(header, values, "agv_length_meters", lattice.getAgvLengthMeters());
        add(header, values, "safe_length_meters", lattice.getSafeLengthMeters());
        add(header, values, "footprint_cells", lattice.getFootprintCells());
        add(header, values, "tick_seconds", FengDhEdgeLattice.TICK_SECONDS);
        add(header, values, "cell_meters", FengDhEdgeLattice.CELL_METERS);
        add(header, values, "speed_meters_per_second",
                FengDhEdgeLattice.DEFAULT_SPEED_METERS_PER_SECOND);
        add(header, values, "workload_scale", workloadScale);
        add(header, values, "workload_scale_semantics",
                workloadScale == 1.0d ? "ORIGINAL_ROWS" : "DETERMINISTIC_ROW_REPLICATION_NON_FORMAL");
        add(header, values, "seed", seed);
        add(header, values, "limit", limit);
        add(header, values, "horizon_seconds", horizonSeconds);
        add(header, values, "storage_in_goal", storageInGoal);
        add(header, values, "storage_out_start", storageOutStart);
        add(header, values, "start_tick", result.startTick);
        add(header, values, "end_tick", result.endTick);
        add(header, values, "simulation_end_seconds", ticksToSeconds(result.endTick));
        add(header, values, "wall_seconds", wallSeconds);
        add(header, values, "route_decisions", result.decisions);
        add(header, values, "tied_route_decisions", result.tiedDecisions);
        add(header, values, "unreachable_route_decisions", result.unreachableDecisions);
        add(header, values, "released_segments", result.releasedSegments);
        add(header, values, "entered_segments", result.enteredSegments);
        add(header, values, "move_commits", result.moveCommits);
        add(header, values, "stopped_ticks", result.stoppedTicks);
        add(header, values, "hold_count", result.holds);
        add(header, values, "entry_stopped_holds", result.entryStoppedHolds);
        add(header, values, "entry_moving_holds", result.entryMovingHolds);
        add(header, values, "local_fifo_conflict_holds", result.mergeConflictHolds);
        add(header, values, "following_footprint_holds", result.followingHolds);
        add(header, values, "junction_through_busy_holds", result.junctionThroughBusyHolds);
        add(header, values, "no_path_holds", result.noPathHolds);
        add(header, values, "peak_active_segments", result.peakActiveSegments);
        add(header, values, "peak_edge_occupancy", result.peakEdgeOccupancy);
        BufferedWriter writer = new BufferedWriter(new FileWriter(path));
        try {
            writer.write(csvRow(header));
            writer.newLine();
            writer.write(csvRow(values));
            writer.newLine();
        } finally {
            writer.close();
        }
    }

    private static void writeSegments(File path, List<FengDhBagState> segments) throws IOException {
        BufferedWriter writer = new BufferedWriter(new FileWriter(path));
        try {
            writer.write("task_id,raw_bag_id,source_raw_bag_id,segment_id,segment_count,start,goal,"
                    + "raw_entry_seconds,release_seconds,release_tick,admission_time_seconds,"
                    + "completion_time_seconds,table53_scheduled_interval_seconds,"
                    + "diagnostic_first_admission_to_completion_seconds,status,moving_ticks,"
                    + "stopped_ticks,hold_count,"
                    + "last_hold_reason");
            writer.newLine();
            for (FengDhBagState bag : segments) {
                double admission = bag.getFirstAdmissionTick() < 0L
                        ? Double.NaN : ticksToSeconds(bag.getFirstAdmissionTick());
                double completion = bag.getCompletionTick() < 0L
                        ? Double.NaN : ticksToSeconds(bag.getCompletionTick());
                double releaseDuration = bag.isCompleted()
                        ? completion - bag.releaseSeconds : Double.NaN;
                double admissionDiagnostic = bag.isCompleted()
                        && bag.getFirstAdmissionTick() >= 0L
                        ? ticksToSeconds(bag.getCompletionTick() - bag.getFirstAdmissionTick())
                        : Double.NaN;
                writer.write(csvRow(values(
                        bag.taskId,
                        bag.rawBagId,
                        sourceRawId(bag.sourceRow),
                        bag.segmentId,
                        bag.segmentCount,
                        bag.startNode,
                        bag.goalNode,
                        bag.rawEntrySeconds,
                        bag.releaseSeconds,
                        bag.releaseTick,
                        admission,
                        completion,
                        releaseDuration,
                        admissionDiagnostic,
                        bag.getStatus().name(),
                        bag.getMovingTicks(),
                        bag.getStoppedTicks(),
                        bag.getHoldCount(),
                        bag.getLastHoldReason())));
                writer.newLine();
            }
        } finally {
            writer.close();
        }
    }

    private static void writeRawBags(File path, List<RawResult> rows) throws IOException {
        BufferedWriter writer = new BufferedWriter(new FileWriter(path));
        try {
            writer.write("task_id,raw_bag_id,source_raw_bag_id,segment_count,complete,"
                    + "raw_entry_seconds,deadline_seconds,final_completion_seconds,"
                    + "raw_entry_to_final_seconds,table53_scheduled_interval_seconds,"
                    + "diagnostic_first_admission_to_completion_seconds,on_time");
            writer.newLine();
            for (RawResult row : rows) {
                writer.write(csvRow(values(
                        row.rawBagId,
                        row.rawBagId,
                        row.sourceRawBagId,
                        row.segmentCount,
                        row.complete,
                        row.rawEntrySeconds,
                        row.deadlineSeconds,
                        row.finalCompletionSeconds,
                        row.rawEntryToFinalSeconds,
                        row.table53ScheduledIntervalSeconds,
                        row.diagnosticFirstAdmissionToCompletionSeconds,
                        row.complete && row.finalCompletionSeconds <= row.deadlineSeconds + 1.0e-9d)));
                writer.newLine();
            }
        } finally {
            writer.close();
        }
    }

    private static void writeTrace(File path, List<FengDhBagState> segments) throws IOException {
        BufferedWriter writer = new BufferedWriter(new FileWriter(path));
        try {
            writer.write("task_id,raw_bag_id,segment_id,tick,time_seconds,event,node,edge_id,"
                    + "position_cell,detail");
            writer.newLine();
            for (FengDhBagState bag : segments) {
                for (FengDhBagState.TraceEvent event : bag.getTrace()) {
                    writer.write(csvRow(values(
                            bag.taskId,
                            bag.rawBagId,
                            bag.segmentId,
                            event.tick,
                            ticksToSeconds(event.tick),
                            event.event,
                            event.node,
                            event.edgeId,
                            event.positionCell,
                            event.detail)));
                    writer.newLine();
                }
            }
        } finally {
            writer.close();
        }
    }

    private static void writeEventSummary(File path, FengDhSimulator.RunResult result)
            throws IOException {
        BufferedWriter writer = new BufferedWriter(new FileWriter(path));
        try {
            writer.write("event,count");
            writer.newLine();
            writeEvent(writer, "released_segments", result.releasedSegments);
            writeEvent(writer, "entered_segments", result.enteredSegments);
            writeEvent(writer, "move_commits", result.moveCommits);
            writeEvent(writer, "stopped_ticks", result.stoppedTicks);
            writeEvent(writer, "holds", result.holds);
            writeEvent(writer, "entry_stopped_holds", result.entryStoppedHolds);
            writeEvent(writer, "entry_moving_holds", result.entryMovingHolds);
            writeEvent(writer, "local_fifo_conflict_holds", result.mergeConflictHolds);
            writeEvent(writer, "following_footprint_holds", result.followingHolds);
            writeEvent(writer, "junction_through_busy_holds", result.junctionThroughBusyHolds);
            writeEvent(writer, "no_path_holds", result.noPathHolds);
            writeEvent(writer, "route_decisions", result.decisions);
            writeEvent(writer, "tied_route_decisions", result.tiedDecisions);
        } finally {
            writer.close();
        }
    }

    private static void writeEvent(BufferedWriter writer, String name, long count)
            throws IOException {
        writer.write(name + "," + count);
        writer.newLine();
    }

    private static int runMicrotests(HashMap<String, String> options) throws Exception {
        String path = options.containsKey("--json-out")
                ? options.get("--json-out") : "feng_cie_dh_microtests.jsonl";
        ArrayList<MicroResult> results = new ArrayList<MicroResult>();
        results.add(testFreeFlow());
        results.add(testMovingLeader());
        results.add(testStoppedLeader());
        results.add(testCongestedFork());
        results.add(testEntryHold());
        results.add(testSameTickMerge());
        results.add(testSynchronousConvoy());
        results.add(testEqualPaths());
        results.add(testPathScope());
        results.add(testCompletionMetrics());
        File output = new File(path);
        File parent = output.getAbsoluteFile().getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new IOException("cannot create microtest output parent " + parent);
        }
        BufferedWriter writer = Files.newBufferedWriter(
                output.toPath(), StandardCharsets.UTF_8);
        int failures = 0;
        try {
            for (MicroResult result : results) {
                writer.write(result.toJsonLine());
                writer.newLine();
                if (!result.passed) {
                    failures++;
                }
            }
        } finally {
            writer.close();
        }
        System.out.println("MICROTESTS passed=" + (results.size() - failures)
                + " failed=" + failures + " json=" + output.getAbsolutePath());
        return failures;
    }

    private static MicroResult testFreeFlow() {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .physicalDimensions(1.0d, 0.0d)
                .addNode(0, 1).addNode(1, 0, 1.0d, 0, 0)
                .addNode(2, 0).addNode(3, 2)
                .addEdge(0, 1, 2.5d).addEdge(1, 3, 2.5d)
                .addEdge(0, 2, 3.0d).addEdge(2, 3, 3.0d).build();
        FengDhBagState bag = bag(1, 1, 0, 1, 0.0d, 0, 3);
        FengDhSimulator simulator = simulator(lattice, list(bag), 0.4d, 0.8d);
        FengDhSimulator.RunResult result = simulator.run(FengDhSimulator.RunConfig.untilComplete(1));
        double actual = ticksToSeconds(bag.getCompletionTick()) - bag.releaseSeconds;
        String tickTrace = trace(bag);
        boolean sourceTransfer = bag.getFirstAdmissionTick() == 10L;
        boolean intermediateLayer = tickTrace.contains(
                "15:NODE_SERVICE_START@0/4[arrival_tick=14;ready_tick=20;"
                        + "MAP_JUNCTION_THROUGH_EXCLUSIVE;map_through_seconds=1.0;")
                && tickTrace.contains(
                        "20:NODE_SERVICE_START@-1/-1[arrival_tick=14;ready_tick=30;"
                                + "INTERMEDIATE_FIXED_TRANSFER_DELAY;"
                                + "reconstructed_transfer_seconds=2.0;");
        boolean noGoalTransfer = countTraceEvents(bag, "NODE_SERVICE_START") == 3
                && bag.getCompletionTick() == 35L;
        boolean pass = "COMPLETE".equals(result.status)
                && bag.isCompleted() && selectedEdge(bag) == 0
                && Math.abs(actual - 7.0d) <= 1.0e-9d
                && sourceTransfer && intermediateLayer && noGoalTransfer;
        return micro("T1", "{\"short_path_m\":5.0,\"long_path_m\":6.0,\"bags\":1,"
                        + "\"source_transfer_s\":2.0,\"fixed_transfer_s\":2.0,"
                        + "\"intermediate_map_through_s\":1.0}",
                "{\"selected_first_node\":1,\"release_to_completion_s\":7.0,"
                        + "\"first_admission_tick\":10,\"intermediate_ready_tick\":30,"
                        + "\"goal_transfer_s\":0.0}",
                "{\"selected_first_node\":"
                        + lattice.edge(selectedEdge(bag)).to
                        + ",\"completion_s\":" + f(actual)
                        + ",\"first_admission_tick\":" + bag.getFirstAdmissionTick()
                        + ",\"intermediate_layer\":" + intermediateLayer
                        + ",\"goal_transfer_absent\":" + noGoalTransfer + "}",
                "source_fixed2;edge1;upstream_retained_exclusive_map1;fixed_transfer2;"
                        + "edge2;goal_complete_without_transfer",
                tickTrace, pass);
    }

    private static MicroResult testMovingLeader() {
        FengDhEdgeLattice lattice = lineLattice(5.0d);
        FengDhBagState leader = bag(1, 1, 0, 1, 0.0d, 0, 1);
        leader.release(0, true);
        leader.enterEdge(0, 0, true, "seed", true);
        lattice.enter(0, leader);
        lattice.move(0, leader, 1);
        leader.moveOnEdge(0, 1, true);
        FengDhBagState follower = bag(2, 2, 0, 1, 0.0d, 0, 1);
        seedSourceReady(follower, 0L);
        FengDhPolicy policy = new FengDhPolicy(lattice, 0.4d, 0.8d);
        FengDhPolicy.Decision decision = policy.choose(0, 1, lattice.snapshot());
        FengDhSimulator simulator = new FengDhSimulator(
                lattice, new FengDhPolicy(lattice, 0.4d, 0.8d), list(leader, follower));
        simulator.step(1);
        boolean pass = decision != null && decision.movingBags == 1
                && decision.stoppedBags == 0 && leader.getPositionCell() == 2
                && follower.getCurrentEdgeId() == 0 && follower.getPositionCell() == 0;
        return micro("T2", "{\"leader_state\":\"MOVING_ON_EDGE\",\"leader_cell\":1}",
                "{\"moving_count\":1,\"stopped_count\":0,\"same_tick_entry\":true}",
                "{\"moving_count\":" + decision.movingBags
                        + ",\"stopped_count\":" + decision.stoppedBags
                        + ",\"leader_commit_cell\":" + leader.getPositionCell()
                        + ",\"follower_commit_cell\":" + follower.getPositionCell()
                        + ",\"same_tick_entry\":" + (follower.getCurrentEdgeId() == 0) + "}",
                "moving_leader_advances@1;safe_follower_enters@1",
                trace(leader) + "|" + trace(follower), pass);
    }

    private static MicroResult testStoppedLeader() {
        FengDhEdgeLattice lattice = lineLattice(5.0d);
        FengDhBagState leader = bag(1, 1, 0, 1, 0.0d, 0, 1);
        leader.release(0, true);
        leader.enterEdge(0, 0, true, "seed", true);
        lattice.enter(0, leader);
        leader.stopOnEdge(0, "seed_block", 0, -1, null, true);
        FengDhBagState follower = bag(2, 2, 0, 1, 0.0d, 0, 1);
        seedSourceReady(follower, 0L);
        FengDhPolicy policy = new FengDhPolicy(lattice, 0.4d, 0.8d);
        FengDhPolicy.Decision decision = policy.choose(0, 1, lattice.snapshot());
        FengDhEdgeLattice.EntryBlocker blocker = lattice.entryBlocker(0);
        boolean blockerWasStopped = blocker != null
                && blocker.bag.getStatus() == FengDhBagState.Status.STOPPED_ON_EDGE;
        FengDhSimulator simulator = new FengDhSimulator(
                lattice, new FengDhPolicy(lattice, 0.4d, 0.8d), list(leader, follower));
        simulator.step(1);
        boolean pass = decision != null && decision.stoppedBags == 1
                && decision.movingBags == 0 && blocker != null
                && blockerWasStopped
                && policy.getBetaStopSeconds() > policy.getAlphaMoveSeconds()
                && follower.getStatus() == FengDhBagState.Status.AT_LOADING_OR_JUNCTION
                && "ENTRY_STOPPED_OCCUPANT".equals(follower.getLastHoldReason());
        return micro("T3", "{\"leader_state\":\"STOPPED_ON_EDGE\",\"leader_cell\":0}",
                "{\"moving_count\":0,\"stopped_count\":1,\"entry_blocked\":true,"
                        + "\"beta_gt_alpha\":true}",
                "{\"moving_count\":" + decision.movingBags
                        + ",\"stopped_count\":" + decision.stoppedBags
                        + ",\"entry_blocked\":" + (blocker != null)
                        + ",\"beta_gt_alpha\":"
                        + (policy.getBetaStopSeconds() > policy.getAlphaMoveSeconds())
                        + ",\"follower_hold_reason\":\"" + follower.getLastHoldReason() + "\"}",
                "stopped_snapshot_counted;entry_hold@1;no_overlap",
                trace(leader) + "|" + trace(follower), pass);
    }

    private static MicroResult testCongestedFork() {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .physicalDimensions(1.0d, 0.0d)
                .addNode(0, 4).addNode(1, 0).addNode(2, 0).addNode(3, 2)
                .addEdge(0, 1, 5.0d).addEdge(1, 3, 5.0d)
                .addEdge(0, 2, 6.0d).addEdge(2, 3, 6.0d).build();
        FengDhBagState stopped = bag(10, 10, 0, 1, 0.0d, 0, 3);
        stopped.release(0, true);
        stopped.enterEdge(1, 0, true, "seed", true);
        lattice.enter(0, stopped);
        stopped.stopOnEdge(2, "seed", 0, -1, null, true);
        FengDhPolicy policy = new FengDhPolicy(lattice, 0.2d, 1.0d);
        FengDhPolicy.Decision decision = policy.choose(0, 3, lattice.snapshot());
        boolean pass = decision != null && lattice.edge(decision.selectedEdgeId).to == 2;
        return micro("T4", "{\"short_branch_m\":10.0,\"long_branch_m\":12.0,"
                        + "\"short_branch_stopped\":1}",
                "{\"selected_first_node\":2}",
                "{\"selected_first_node\":" + lattice.edge(decision.selectedEdgeId).to
                        + ",\"eta_s\":" + f(decision.etaSeconds) + "}",
                "stopped_short_branch_penalized;select_long_branch",
                trace(stopped), pass);
    }

    private static MicroResult testEntryHold() {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .physicalDimensions(1.0d, 0.0d)
                .addNode(0, 1).addNode(1, 2)
                .addEdge(0, 1, 1.0d).build();
        FengDhBagState blocker = bag(1, 1, 0, 1, 0.0d, 0, 1);
        blocker.release(0, true);
        blocker.enterEdge(0, 0, true, "seed", true);
        blocker.stopOnEdge(0, "seed_no_path", -1, -1, null, true);
        lattice.enter(0, blocker);
        FengDhBagState waiting = bag(2, 2, 0, 1, 0.0d, 0, 1);
        seedSourceReady(waiting, 0L);
        FengDhSimulator simulator = simulator(lattice, list(blocker, waiting), 0.4d, 0.8d);
        simulator.step(1);
        boolean held = waiting.getStatus() == FengDhBagState.Status.AT_LOADING_OR_JUNCTION
                && "ENTRY_STOPPED_OCCUPANT".equals(waiting.getLastHoldReason());
        long firstRetryTick = waiting.getRetryTick();
        simulator.step(1);
        boolean pass = held && firstRetryTick == 2L && blocker.isCompleted()
                && waiting.getStatus() == FengDhBagState.Status.MOVING_ON_EDGE
                && waiting.getCurrentEdgeId() == 0 && waiting.getPositionCell() == 0;
        return micro("T5", "{\"entry_occupant_state\":\"STOPPED_ON_EDGE\"}",
                "{\"waiting_state\":\"AT_LOADING_OR_JUNCTION\","
                        + "\"hold_reason\":\"ENTRY_STOPPED_OCCUPANT\",\"retry_tick\":2,"
                        + "\"next_tick_entry\":true}",
                "{\"first_hold\":" + held
                        + ",\"retry_tick\":" + firstRetryTick
                        + ",\"blocker_completed\":" + blocker.isCompleted()
                        + ",\"next_tick_entry\":"
                        + (waiting.getCurrentEdgeId() == 0) + "}",
                "hold_for_stopped_snapshot@1;blocker_complete_and_waiting_enter@2",
                trace(waiting), pass);
    }

    private static MicroResult testSameTickMerge() {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .physicalDimensions(1.0d, 0.0d)
                .addNode(0, 1).addNode(3, 2)
                .addEdge(0, 3, 2.0d).build();
        FengDhBagState lowId = bag(10, 10, 0, 1, 0.0d, 0, 3);
        FengDhBagState highId = bag(20, 20, 0, 1, 0.0d, 0, 3);
        seedSourceReady(lowId, 0L);
        seedSourceReady(highId, 0L);
        FengDhSimulator simulator = simulator(lattice, list(lowId, highId), 0.4d, 0.8d);
        simulator.step(1);
        boolean edgeEntryPass = lowId.getCurrentEdgeId() == 0
                && highId.getCurrentEdgeId() == -1
                && "LOCAL_FIFO_ENTRY_CONFLICT".equals(highId.getLastHoldReason());

        FengDhEdgeLattice serviceLattice = FengDhEdgeLattice.builder()
                .physicalDimensions(1.0d, 0.0d)
                .addNode(0, 1).addNode(1, 1).addNode(2, 5, 1.0d, 0, 0)
                .addNode(3, 2)
                // Reverse source/edge insertion: the later arrival is visited
                // first by the lattice container and must still lose FIFO.
                .addEdge(1, 2, 1.5d).addEdge(0, 2, 0.5d)
                .addEdge(2, 3, 0.5d).build();
        FengDhBagState serviceLater = bag(10, 10, 0, 1, 0.0d, 1, 3);
        FengDhBagState serviceEarlier = bag(20, 20, 0, 1, 0.0d, 0, 3);
        FengDhBagState serviceFollower = bag(30, 30, 0, 1, 0.0d, 1, 3);
        seedAtEdgeEnd(serviceLattice, serviceLater, 0, 0L);
        seedAtEdgeEnd(serviceLattice, serviceEarlier, 1, -1L);
        seedAtPosition(serviceLattice, serviceFollower, 0, 0, 0L);
        FengDhSimulator serviceSimulator = simulator(
                serviceLattice,
                list(serviceLater, serviceEarlier, serviceFollower), 0.4d, 0.8d);
        serviceSimulator.step(1);
        boolean endogenousSpillback = serviceEarlier.getStatus()
                        == FengDhBagState.Status.STOPPED_ON_EDGE
                && serviceEarlier.getNodeServiceStartTick() == 1L
                && serviceEarlier.getNodeServiceReadyTick() == 6L
                && serviceLater.getStatus() == FengDhBagState.Status.STOPPED_ON_EDGE
                && "JUNCTION_THROUGH_BUSY".equals(serviceLater.getLastHoldReason())
                && serviceLater.getStoppedTicks() == 1L
                && serviceFollower.getStatus() == FengDhBagState.Status.STOPPED_ON_EDGE
                && "FOLLOWING_FOOTPRINT_BLOCKED".equals(
                        serviceFollower.getLastHoldReason());
        for (int index = 0; index < 5; index++) {
            serviceSimulator.step(1);
        }
        boolean throughRetainsUpstream = serviceEarlier.getCurrentEdgeId() == -1
                && serviceEarlier.getNodeServiceStartTick() == 6L
                && serviceEarlier.getNodeServiceReadyTick() == 16L
                && serviceLater.getCurrentEdgeId() == 0
                && serviceLater.getNodeServiceStartTick() == 6L
                && serviceLater.getNodeServiceReadyTick() == 11L
                && serviceFollower.getStatus() == FengDhBagState.Status.STOPPED_ON_EDGE;
        for (int index = 0; index < 5; index++) {
            serviceSimulator.step(1);
        }
        boolean halfOpenThroughBoundary = serviceEarlier.getCurrentEdgeId() == -1
                && serviceLater.getCurrentEdgeId() == -1
                && serviceEarlier.getNodeServiceStartTick() == 6L
                && serviceEarlier.getNodeServiceReadyTick() == 16L
                && serviceLater.getNodeServiceStartTick() == 11L
                && serviceLater.getNodeServiceReadyTick() == 21L;
        boolean pass = edgeEntryPass && endogenousSpillback
                && throughRetainsUpstream && halfOpenThroughBoundary;
        return micro("T6", "{\"entry_arrival_tick\":0,\"task_ids\":[10,20],"
                        + "\"reverse_edge_insertion\":[\"1>2\",\"0>2\"],"
                        + "\"node_service_arrival_ticks\":{\"10\":0,\"20\":-1}}",
                "{\"entry_winner_task_id\":10,\"junction_winner_task_id\":20,"
                        + "\"junction_busy_task_id\":10,\"rear_follower_stops\":true,"
                        + "\"through_retains_upstream_footprint\":true,"
                        + "\"through_boundary_half_open\":true,"
                        + "\"fixed_transfer_timers_overlap\":true}",
                "{\"winner_task_id\":" + (lowId.getCurrentEdgeId() == 0 ? 10 : 20)
                        + ",\"loser_reason\":\"" + highId.getLastHoldReason()
                        + "\",\"endogenous_spillback\":" + endogenousSpillback
                        + ",\"through_retains_upstream\":" + throughRetainsUpstream
                        + ",\"through_boundary_half_open\":" + halfOpenThroughBoundary
                        + "}",
                "same_target_entry:equal_arrival_task10_wins;"
                        + "task20_arrival-1_wins_exclusive_map1;task10_and_rear_stop;"
                        + "map1_keeps_upstream_footprint;half_open_release;"
                        + "fixed_transfer2_timers_overlap_without_node_capacity",
                trace(lowId) + "|" + trace(highId) + "||"
                        + trace(serviceLater) + "|" + trace(serviceEarlier) + "|"
                        + trace(serviceFollower), pass);
    }

    private static MicroResult testSynchronousConvoy() {
        FengDhEdgeLattice lattice = lineLattice(5.0d);
        FengDhBagState leader = bag(10, 10, 0, 1, 0.0d, 0, 1);
        FengDhBagState follower = bag(20, 20, 0, 1, 0.0d, 0, 1);
        seedAtPosition(lattice, leader, 0, 2, 0L);
        seedAtPosition(lattice, follower, 0, 0, 0L);
        FengDhSimulator simulator = simulator(lattice, list(leader, follower), 0.4d, 0.8d);
        simulator.step(1);
        boolean safe = leader.getPositionCell() - follower.getPositionCell()
                >= lattice.getFootprintCells();
        boolean internalPass = leader.getPositionCell() == 3
                && follower.getPositionCell() == 1 && safe;

        FengDhEdgeLattice boundary = FengDhEdgeLattice.builder()
                .physicalDimensions(1.0d, 0.0d)
                .addNode(0, 1).addNode(1, 5, 1.0d, 0, 0).addNode(2, 2)
                .addEdge(0, 1, 2.0d).addEdge(1, 2, 1.0d).build();
        FengDhBagState boundaryLeader = bag(30, 30, 0, 1, 0.0d, 0, 2);
        FengDhBagState boundaryFollower = bag(40, 40, 0, 1, 0.0d, 0, 2);
        seedAtEdgeEnd(boundary, boundaryLeader, 0, 0L);
        seedAtPosition(boundary, boundaryFollower, 0, 1, 0L);
        FengDhSimulator boundarySimulator = simulator(
                boundary, list(boundaryLeader, boundaryFollower), 0.4d, 0.8d);
        boundarySimulator.step(1);
        boolean boundaryPass = boundaryLeader.getStatus()
                        == FengDhBagState.Status.STOPPED_ON_EDGE
                && boundaryLeader.getCurrentNode() == 1
                && boundaryLeader.getNodeServiceReadyTick() == 6L
                && boundaryFollower.getCurrentEdgeId() == 0
                && boundaryFollower.getPositionCell() == 1;
        boolean pass = internalPass && boundaryPass;
        return micro("T7", "{\"snapshot_cells\":[2,0],\"footprint_cells\":2,"
                        + "\"boundary_snapshot_cells\":[3,1],"
                        + "\"map_through_s\":1.0,\"transfer_s\":2.0}",
                "{\"commit_cells\":[3,1],\"safe\":true,"
                        + "\"boundary_commit\":[\"leader_stopped_at_edge_end\",1]}",
                "{\"commit_cells\":[" + leader.getPositionCell() + ","
                        + follower.getPositionCell() + "],\"safe\":" + safe
                        + ",\"boundary_leader_state\":\""
                        + boundaryLeader.getStatus().name()
                        + "\",\"boundary_follower_cell\":"
                        + boundaryFollower.getPositionCell() + "}",
                "internal:[2,0]->[3,1];boundary_handoff:[3,1]retained;"
                        + "leader_stops_at_terminal_and_follower_propagates_stop",
                trace(leader) + "|" + trace(follower) + "||"
                        + trace(boundaryLeader) + "|" + trace(boundaryFollower), pass);
    }

    private static MicroResult testEqualPaths() {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 4).addNode(1, 0).addNode(2, 0).addNode(3, 2)
                .addEdge(0, 1, 5.0d).addEdge(1, 3, 5.0d)
                .addEdge(0, 2, 5.0d).addEdge(2, 3, 5.0d).build();
        FengDhPolicy first = new FengDhPolicy(lattice, 0.4d, 0.8d);
        FengDhPolicy second = new FengDhPolicy(lattice, 0.4d, 0.8d);
        FengDhPolicy.Decision left = first.choose(0, 3, lattice.snapshot());
        FengDhPolicy.Decision right = second.choose(0, 3, lattice.snapshot());
        int selected = lattice.edge(left.selectedEdgeId).to;
        boolean pass = selected == 1 && left.selectedEdgeId == right.selectedEdgeId
                && left.equalScoreCandidateCount == 2;
        return micro("T8", "{\"equal_paths\":[\"0>1>3\",\"0>2>3\"]}",
                "{\"selected_path\":\"0>1>3\",\"repeat_equal\":true}",
                "{\"selected_path\":\"" + join(left.continuation.nodeIds)
                        + "\",\"repeat_equal\":"
                        + (left.selectedEdgeId == right.selectedEdgeId) + "}",
                "equal_score_count=2;lex_path=0>1>3;repeat_equal",
                left.traceDetail(), pass);
    }

    private static MicroResult testPathScope() {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 4).addNode(1, 0).addNode(2, 2).addNode(4, 0).addNode(5, 2)
                .addEdge(0, 1, 5.0d).addEdge(1, 2, 5.0d).addEdge(4, 5, 5.0d).build();
        FengDhBagState onPath = bag(1, 1, 0, 1, 0.0d, 0, 2);
        seedAtPosition(lattice, onPath, 0, 2, 0L);
        FengDhBagState elsewhere = bag(2, 2, 0, 1, 0.0d, 4, 5);
        seedAtPosition(lattice, elsewhere, 2, 0, 0L);
        elsewhere.stopOnEdge(1, "seed", -1, -1, null, true);
        FengDhPolicy policy = new FengDhPolicy(lattice, 0.4d, 0.8d);
        FengDhPolicy.Decision decision = policy.choose(0, 2, lattice.snapshot());
        boolean pass = decision.movingBags == 1 && decision.stoppedBags == 0;
        return micro("T9", "{\"on_path_moving\":1,\"off_path_stopped\":1,"
                        + "\"future_planned\":0}",
                "{\"moving_count\":1,\"stopped_count\":0}",
                "{\"moving_count\":" + decision.movingBags
                        + ",\"stopped_count\":" + decision.stoppedBags + "}",
                "count_on_path_moving_only;ignore_off_path_stopped_and_future_flow",
                decision.traceDetail(), pass);
    }

    private static MicroResult testCompletionMetrics() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1)
                .addNode(2, 5, 1.0d, 0, 0).addNode(3, 2)
                .addNode(47, 2).addNode(52, 1)
                .addEdge(0, 2, 2.5d).addEdge(2, 3, 2.5d)
                .addEdge(1, 47, 15.0d).addEdge(52, 3, 2.5d).build();
        File scheduleFixture = File.createTempFile("feng_table53_schedule_", ".csv");
        List<FengDhBagState> segments;
        ScheduleData schedule;
        try {
            BufferedWriter fixtureWriter = Files.newBufferedWriter(
                    scheduleFixture.toPath(), StandardCharsets.UTF_8);
            try {
                fixtureWriter.write(
                        "raw_bag_id,segment_id,start,goal,scheduled_release_seconds\n");
                fixtureWriter.write("0,0,0,3,0.0\n");
                fixtureWriter.write("1,0,1,47,0.0\n");
                fixtureWriter.write("1,1,52,3,5.0\n");
            } finally {
                fixtureWriter.close();
            }
            schedule = readSchedule(scheduleFixture);
            ArrayList<RawInput> fixtureInputs = new ArrayList<RawInput>();
            fixtureInputs.add(new RawInput(
                    0L, 0.0d, 20.0d, 0, 3, "X", "X", "0 0 20 0 3 X X"));
            fixtureInputs.add(new RawInput(
                    1L, 0.0d, 5_000.0d, 1, 3, "X", "X",
                    "1 0 5000 1 3 X X"));
            segments = expandSegments(
                    fixtureInputs,
                    schedule,
                    DEFAULT_STORAGE_IN_GOAL,
                    DEFAULT_STORAGE_OUT_START);
        } finally {
            Files.deleteIfExists(scheduleFixture.toPath());
        }
        FengDhBagState direct = segments.get(0);
        FengDhBagState early0 = segments.get(1);
        FengDhBagState early1 = segments.get(2);
        FengDhSimulator simulator = simulator(lattice, segments, 0.4d, 0.8d);
        FengDhSimulator.RunResult result = simulator.run(FengDhSimulator.RunConfig.untilComplete(1));
        List<RawResult> raws = buildRawResults(segments);
        RawResult directResult = raws.get(0);
        RawResult earlyResult = raws.get(1);
        double earlyAdmissionSum = ticksToSeconds(
                early0.getCompletionTick() - early0.getFirstAdmissionTick())
                + ticksToSeconds(early1.getCompletionTick() - early1.getFirstAdmissionTick());
        double earlyScheduleSum = ticksToSeconds(early0.getCompletionTick())
                - early0.releaseSeconds
                + ticksToSeconds(early1.getCompletionTick()) - early1.releaseSeconds;
        double directTable53 = directResult.table53ScheduledIntervalSeconds;
        double directAdmissionDiagnostic =
                directResult.diagnosticFirstAdmissionToCompletionSeconds;
        String directTickTrace = trace(direct);
        boolean sourceTransferVerified = direct.getFirstAdmissionTick() == 10L;
        boolean serviceArrivalPreserved = directTickTrace.contains(
                "15:NODE_SERVICE_START@0/4[arrival_tick=14;ready_tick=20;"
                        + "MAP_JUNCTION_THROUGH_EXCLUSIVE;map_through_seconds=1.0;")
                && directTickTrace.contains(
                        "20:NODE_SERVICE_START@-1/-1[arrival_tick=14;ready_tick=30;"
                                + "INTERMEDIATE_FIXED_TRANSFER_DELAY;"
                                + "reconstructed_transfer_seconds=2.0;");
        boolean goalTransferAbsent = countTraceEvents(direct, "NODE_SERVICE_START") == 3
                && countTraceEvents(early0, "NODE_SERVICE_START") == 1;
        boolean independentTimedRelease = early1.getFirstAdmissionTick()
                < early0.getCompletionTick()
                && early1.getFirstAdmissionTick() == 35L
                && early0.getCompletionTick() == 40L;
        boolean pass = "COMPLETE".equals(result.status) && result.completedRawBags == 2
                && directResult.complete && earlyResult.complete
                && schedule.rows.size() == 3
                && Math.abs(directTable53 - 7.0d) < 1.0e-9d
                && Math.abs(directAdmissionDiagnostic - 5.0d) < 1.0e-9d
                && Math.abs(directTable53 - directAdmissionDiagnostic - 2.0d) < 1.0e-9d
                && sourceTransferVerified && serviceArrivalPreserved && goalTransferAbsent
                && Math.abs(earlyResult.table53ScheduledIntervalSeconds
                        - earlyScheduleSum) < 1.0e-9d
                && Math.abs(earlyResult.diagnosticFirstAdmissionToCompletionSeconds
                        - earlyAdmissionSum) < 1.0e-9d
                && Math.abs(earlyScheduleSum - earlyAdmissionSum - 4.0d) < 1.0e-9d
                && independentTimedRelease
                && Math.abs(earlyResult.rawEntryToFinalSeconds - 8.0d) < 1.0e-9d;
        return micro("T10", "{\"direct_bags\":1,\"intermediate_service_s\":1.0,"
                        + "\"fixed_transfer_s\":2.0,"
                        + "\"two_segment_bags\":1,\"inbound_edge_m\":15.0,"
                        + "\"schedule_fixture_rows\":3,\"outbound_release_tick\":25}",
                "{\"completed_raw_bags\":2,\"table53_is_segment_sum_E_minus_D\":true,"
                        + "\"direct_table53_s\":7.0,\"direct_admission_diagnostic_s\":5.0,"
                        + "\"early_table53_s\":11.0,\"early_admission_diagnostic_s\":7.0,"
                        + "\"source_transfer_s\":2.0,\"intermediate_total_s\":3.0,"
                        + "\"goal_transfer_s\":0.0,\"outbound_admission_tick\":35,"
                        + "\"inbound_completion_tick\":40,"
                        + "\"independent_timed_release\":true}",
                "{\"completed_raw_bags\":" + result.completedRawBags
                        + ",\"schedule_fixture_rows\":" + schedule.rows.size()
                        + ",\"direct_table53_s\":" + f(directTable53)
                        + ",\"direct_admission_diagnostic_s\":"
                        + f(directAdmissionDiagnostic)
                        + ",\"early_table53_s\":" + f(earlyScheduleSum)
                        + ",\"early_admission_diagnostic_s\":" + f(earlyAdmissionSum)
                        + ",\"raw_wall_s\":" + f(earlyResult.rawEntryToFinalSeconds)
                        + ",\"service_arrival_preserved\":"
                        + serviceArrivalPreserved
                        + ",\"source_transfer_verified\":"
                        + sourceTransferVerified
                        + ",\"goal_transfer_absent\":" + goalTransferAbsent
                        + ",\"outbound_admission_tick\":"
                        + early1.getFirstAdmissionTick()
                        + ",\"inbound_completion_tick\":"
                        + early0.getCompletionTick()
                        + ",\"independent_timed_release\":"
                        + independentTimedRelease + "}",
                "direct:source_ready10;arrival14-map_through15-20-transfer20-30;"
                        + "edge-map1-retained-transfer2-edge-goal_without_transfer;"
                        + "early_outbound_admit35_before_inbound_complete40;"
                        + "table53=sum(completion-D);admission_interval_is_diagnostic;"
                        + "physical_boundary_footprint_retained",
                directTickTrace + "|" + trace(early0) + "|" + trace(early1), pass);
    }

    private static FengDhSimulator simulator(
            FengDhEdgeLattice lattice,
            List<FengDhBagState> bags,
            double alpha,
            double beta) {
        return new FengDhSimulator(lattice, new FengDhPolicy(lattice, alpha, beta), bags);
    }

    private static FengDhEdgeLattice lineLattice(double length) {
        return FengDhEdgeLattice.builder().physicalDimensions(1.0d, 0.0d)
                .addNode(0, 1).addNode(1, 2).addEdge(0, 1, length).build();
    }

    private static FengDhBagState bag(
            long taskId, long rawId, int segmentId, int segmentCount,
            double release, int start, int goal) {
        return new FengDhBagState(taskId, rawId, segmentId, segmentCount,
                release, release, secondsToReleaseTick(release), release + 100.0d,
                start, goal, segmentCount > 1, Long.toString(rawId));
    }

    private static void seedAtEdgeEnd(
            FengDhEdgeLattice lattice, FengDhBagState bag, int edgeId, long tick) {
        seedAtPosition(lattice, bag, edgeId, lattice.edge(edgeId).cellCount - 1, tick);
        bag.markDownstreamArrival(tick, lattice.edge(edgeId).to);
    }

    private static void seedAtPosition(
            FengDhEdgeLattice lattice,
            FengDhBagState bag,
            int edgeId,
            int position,
            long tick) {
        bag.release(tick, true);
        bag.enterEdge(tick, edgeId, true, "seed", true);
        lattice.enter(edgeId, bag);
        if (position > 0) {
            lattice.move(edgeId, bag, position);
            bag.moveOnEdge(tick, position, true);
        }
    }

    /** Bypass production induction only in microtests focused on another mechanism. */
    private static void seedSourceReady(FengDhBagState bag, long tick) {
        bag.release(tick, true);
        bag.beginNodeService(tick, bag.startNode, tick,
                "MICROTEST_SOURCE_TRANSFER_ALREADY_COMPLETE", true);
    }

    @SafeVarargs
    private static <T> List<T> list(T... values) {
        ArrayList<T> result = new ArrayList<T>();
        for (T value : values) {
            result.add(value);
        }
        return result;
    }

    private static MicroResult micro(
            String caseId,
            String input,
            String expected,
            String actual,
            String expectedTrace,
            String actualTrace,
            boolean pass) {
        return new MicroResult(
                caseId, input, expected, actual, expectedTrace, actualTrace, pass);
    }

    private static int selectedEdge(FengDhBagState bag) {
        for (FengDhBagState.TraceEvent event : bag.getTrace()) {
            if ("SELECT".equals(event.event)) {
                return event.edgeId;
            }
        }
        return -1;
    }

    private static int countTraceEvents(FengDhBagState bag, String eventName) {
        int count = 0;
        for (FengDhBagState.TraceEvent event : bag.getTrace()) {
            if (eventName.equals(event.event)) {
                count++;
            }
        }
        return count;
    }

    private static String trace(FengDhBagState bag) {
        StringBuilder result = new StringBuilder();
        for (FengDhBagState.TraceEvent event : bag.getTrace()) {
            if (result.length() > 0) {
                result.append(';');
            }
            result.append(event.tick).append(':').append(event.event)
                    .append('@').append(event.edgeId).append('/').append(event.positionCell);
            if (!event.detail.isEmpty()) {
                result.append('[').append(event.detail).append(']');
            }
        }
        return result.toString();
    }

    private static String join(List<Integer> values) {
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < values.size(); index++) {
            if (index > 0) {
                result.append('>');
            }
            result.append(values.get(index).intValue());
        }
        return result.toString();
    }

    private static HashMap<String, String> parseOptions(String[] args, int offset) {
        HashMap<String, String> options = new HashMap<String, String>();
        for (int index = offset; index < args.length; index += 2) {
            if (!args[index].startsWith("--") || index + 1 >= args.length) {
                throw new IllegalArgumentException("expected --name value at argument " + index);
            }
            if (options.put(args[index], args[index + 1]) != null) {
                throw new IllegalArgumentException("duplicate option " + args[index]);
            }
        }
        return options;
    }

    private static String required(HashMap<String, String> options, String name) {
        String value = options.get(name);
        if (value == null || value.isEmpty()) {
            throw new IllegalArgumentException("missing required option " + name);
        }
        return value;
    }

    private static int integerOption(HashMap<String, String> options, String name, int fallback) {
        String value = options.get(name);
        return value == null ? fallback : Integer.parseInt(value);
    }

    private static long longOption(HashMap<String, String> options, String name, long fallback) {
        String value = options.get(name);
        return value == null ? fallback : Long.parseLong(value);
    }

    private static double doubleOption(
            HashMap<String, String> options, String name, double fallback) {
        String value = options.get(name);
        return value == null ? fallback : Double.parseDouble(value);
    }

    private static boolean booleanOption(
            HashMap<String, String> options, String name, boolean fallback) {
        String value = options.get(name);
        if (value == null) {
            return fallback;
        }
        if ("true".equalsIgnoreCase(value)) {
            return true;
        }
        if ("false".equalsIgnoreCase(value)) {
            return false;
        }
        throw new IllegalArgumentException(name + " must be true or false, got " + value);
    }

    private static boolean isStaticControl(FengDhPolicy policy) {
        return policy.getAlphaMoveSeconds() == 0.0d
                && policy.getBetaStopSeconds() == 0.0d;
    }

    private static long secondsToReleaseTick(double seconds) {
        return (long) Math.ceil(seconds / FengDhEdgeLattice.TICK_SECONDS - 1.0e-9d);
    }

    private static double ticksToSeconds(long tick) {
        return tick * FengDhEdgeLattice.TICK_SECONDS;
    }

    private static double quantizedNodeServiceSeconds(double seconds) {
        long ticks = (long) Math.ceil(
                seconds / FengDhEdgeLattice.TICK_SECONDS - 1.0e-12d);
        return ticksToSeconds(ticks);
    }

    private static double percentile(List<Double> sorted, double quantile) {
        if (sorted.size() == 1) {
            return sorted.get(0).doubleValue();
        }
        double position = quantile * (sorted.size() - 1);
        int lower = (int) Math.floor(position);
        int upper = (int) Math.ceil(position);
        double fraction = position - lower;
        return sorted.get(lower).doubleValue() * (1.0d - fraction)
                + sorted.get(upper).doubleValue() * fraction;
    }

    private static double finalCompletionOrNegative(double value) {
        return Double.isNaN(value) ? Double.NEGATIVE_INFINITY : value;
    }

    private static long sourceRawId(String sourceRow) {
        if (sourceRow == null || sourceRow.trim().isEmpty()) {
            return -1L;
        }
        String first = sourceRow.trim().split("\\s+", 2)[0];
        try {
            return Long.parseLong(first);
        } catch (NumberFormatException ignored) {
            return -1L;
        }
    }

    private static String sha256(File path) throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        InputStream stream = new FileInputStream(path);
        try {
            byte[] buffer = new byte[65_536];
            int count;
            while ((count = stream.read(buffer)) >= 0) {
                digest.update(buffer, 0, count);
            }
        } finally {
            stream.close();
        }
        StringBuilder result = new StringBuilder();
        for (byte value : digest.digest()) {
            result.append(String.format(Locale.ROOT, "%02x", value & 0xff));
        }
        return result.toString();
    }

    private static void add(
            List<String> header, List<String> values, String name, Object value) {
        header.add(name);
        values.add(format(value));
    }

    private static void addStats(
            List<String> header, List<String> values, String prefix, SummaryStats stats) {
        add(header, values, prefix + "_min_seconds", stats.minimum);
        add(header, values, prefix + "_mean_seconds", stats.mean);
        add(header, values, prefix + "_p95_seconds", stats.p95);
        add(header, values, prefix + "_p99_seconds", stats.p99);
        add(header, values, prefix + "_max_seconds", stats.maximum);
    }

    private static ArrayList<String> values(Object... source) {
        ArrayList<String> result = new ArrayList<String>();
        for (Object value : source) {
            result.add(format(value));
        }
        return result;
    }

    private static String format(Object value) {
        if (value == null) {
            return "";
        }
        if (value instanceof Double) {
            double number = ((Double) value).doubleValue();
            return Double.isNaN(number) || Double.isInfinite(number)
                    ? "N/A" : String.format(Locale.ROOT, "%.9f", number);
        }
        if (value instanceof Float) {
            float number = ((Float) value).floatValue();
            return Float.isNaN(number) || Float.isInfinite(number)
                    ? "N/A" : String.format(Locale.ROOT, "%.9f", number);
        }
        return String.valueOf(value);
    }

    private static String csvRow(List<String> values) {
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < values.size(); index++) {
            if (index > 0) {
                result.append(',');
            }
            String value = values.get(index);
            if (value.indexOf(',') >= 0 || value.indexOf('"') >= 0
                    || value.indexOf('\n') >= 0 || value.indexOf('\r') >= 0) {
                result.append('"').append(value.replace("\"", "\"\"")).append('"');
            } else {
                result.append(value);
            }
        }
        return result.toString();
    }

    private static String json(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\r", "\\r").replace("\n", "\\n")
                .replace("\t", "\\t");
    }

    private static String f(double value) {
        return String.format(Locale.ROOT, "%.9f", value);
    }

    private static void usage() {
        System.err.println("usage:");
        System.err.println("  App.FengDhBenchmark microtests [--json-out PATH]");
        System.err.println("  App.FengDhBenchmark run --map PATH --input PATH --output DIR"
                + " [--schedule CSV]"
                + " [--alpha SEC] [--beta SEC] [--limit N] [--workload-scale X]"
                + " [--seed N] [--horizon-seconds SEC] [--trace-sample-modulo N]"
                + " [--storage-in-goal NODE] [--storage-out-start NODE]"
                + " [--formal-timing-eligible true|false]");
        System.err.println("  App.FengDhBenchmark static-bridge --map PATH --csv-out PATH");
    }
}
