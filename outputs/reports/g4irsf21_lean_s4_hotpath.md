# G4IRSF21 rejected lean S4 hotpath experiment

Status: **NO_GO_KEEP_RICH_S4**

The controller remains `Source A0 + Route S4 + Merge J2 + E2`. The candidate
path skipped diagnostics that S4 does not consume, but it was removed after
the paired gate below failed. No lean runtime branch is retained.

## Full-flow semantic parity

- 1x: PASS
- 2x: PASS

## 4x bounded median (two order-balanced repeats)

- events/s: 75723.207289 -> 76721.558524 (1.318422%)
- completed segments: 25714.000000 -> 26069.500000 (1.382515%)
- events/completed: 177.130252 -> 177.230018 (0.056324% worse)

The required gain was at least 5% in events/s or completion with no regression
in the other bounded-work measures. The observed gain was below threshold and
events/completed regressed slightly, so this is negative evidence rather than
a retained optimization. Full 4x completion and v2-safe gap closure are not
claimed.
