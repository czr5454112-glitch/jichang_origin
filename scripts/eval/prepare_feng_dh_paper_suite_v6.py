"""One-time derivation of the independently named V6 source from its V5 copy.

This script never writes the V5 directory. The small transforms are retained so
reviewers can reproduce and inspect the exact speed extension.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "benchmarks/java/feng_cie_dh_paper_suite_v6/App"


def change(text, old, new, count=1):
    assert text.count(old) == count, (old, text.count(old), count)
    return text.replace(old, new)


def main():
    path = SOURCE / "FengDhEdgeLattice.java"
    text = path.read_text(encoding="utf-8")
    text = change(text, "lengthMeters / CELL_METERS", "lengthMeters / (TICK_SECONDS * speedMetersPerSecond)")
    text = change(text, "    private final int footprintCells;", "    private final int footprintCells;\n    private final double speedMetersPerSecond;\n    private final double cellMeters;")
    text = change(text, "        this.footprintCells = Math.max(1,", "        this.speedMetersPerSecond = sourceEdges.isEmpty()\n                ? DEFAULT_SPEED_METERS_PER_SECOND : sourceEdges.get(0).speedMetersPerSecond;\n        for (EdgeData edge : sourceEdges) {\n            if (Math.abs(edge.speedMetersPerSecond - this.speedMetersPerSecond) > 1e-12d) {\n                throw new IllegalArgumentException(\"V6 requires uniform speed; heterogeneous physics is unsupported\");\n            }\n        }\n        this.cellMeters = TICK_SECONDS * this.speedMetersPerSecond;\n        this.footprintCells = Math.max(1,")
    text = change(text, "(agvLengthMeters + safeLengthMeters) / CELL_METERS", "(agvLengthMeters + safeLengthMeters) / cellMeters")
    text = change(text, "    public static FengDhEdgeLattice readLegacyMap(File path) throws IOException {", "    public static FengDhEdgeLattice readLegacyMap(File path) throws IOException {\n        return readLegacyMap(path, Double.NaN);\n    }\n\n    public static FengDhEdgeLattice readLegacyMap(File path, double uniformSpeed) throws IOException {\n        if (!Double.isNaN(uniformSpeed) && (!Double.isFinite(uniformSpeed) || uniformSpeed <= 0)) {\n            throw new IllegalArgumentException(\"speed must be positive and finite\");\n        }")
    text = change(text, "                        speed));", "                        Double.isNaN(uniformSpeed) ? speed : uniformSpeed));")
    text = change(text, "(agvLengthMeters + safeLengthMeters) / DEFAULT_SPEED_METERS_PER_SECOND", "(agvLengthMeters + safeLengthMeters) / speedMetersPerSecond")
    text = change(text, "    public Snapshot snapshot() {", "    public double getSpeedMetersPerSecond() { return speedMetersPerSecond; }\n\n    public double getCellMeters() { return cellMeters; }\n\n    public Snapshot snapshot() {")
    text = change(text, "the leading reference point on a 0.5 m lattice.", "the leading reference point on a v * 0.2 s lattice.")
    path.write_text(text, encoding="utf-8", newline="\n")

    path = SOURCE / "FengDhBenchmark.java"
    text = path.read_text(encoding="utf-8")
    text = text.replace("FENG_DH_BOUNDARY_CLEARANCE_V5", "FENG_DH_PAPER_SUITE_V6")
    text = text.replace("STATIC_FREE_FLOW_BOUNDARY_CLEARANCE_V5", "STATIC_FREE_FLOW_PAPER_SUITE_V6")
    text = change(text, "        FengDhEdgeLattice lattice = FengDhEdgeLattice.readLegacyMap(mapPath);", "        FengDhEdgeLattice lattice = FengDhEdgeLattice.readLegacyMap(\n                mapPath, doubleOption(options, \"--speed-mps\", 2.5d));", 2)
    text = change(text, '"cell_meters", FengDhEdgeLattice.CELL_METERS', '"cell_meters", lattice.getCellMeters()')
    text = change(text, "                FengDhEdgeLattice.DEFAULT_SPEED_METERS_PER_SECOND);", "                lattice.getSpeedMetersPerSecond());")
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
