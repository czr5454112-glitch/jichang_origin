# G4IRSF19 BOLT-P executor decision

The executable BOLT-P seam reuses the real native G15 in-memory
checkpoint/clone counterfactual runner. P=1 replayed the same shard twice with
strict semantic parity: 13 action-changing targets, 13 applied targets, zero
worker failures, zero stale rejections, and zero conflicts. Compute took
274.198 s; stable aggregation took 0.0015 s.

P=2/4/8 support is executable, but the native checkpoint lane was not launched
on this machine: prior worker peak memory was about 5.27 GiB, making P=8 exceed
the available 31.4 GiB physical-memory envelope. This is reported as an honest
resource boundary, not a parallel speedup result.

Independent complete rollout pairs do have measured process parallelism. On a
fixed 32,768 pair-segment-replica plan, the two clean repeats measured
P=2 at 1.863x/1.966x, P=4 at 3.289x/3.330x, and P=8 at 5.247x/5.325x. Every
output was semantically identical to P=1 with no retry or failure. Those
numbers prove experiment/data-generation parallelism only; they do not prove
shared-runtime parallel commit.
