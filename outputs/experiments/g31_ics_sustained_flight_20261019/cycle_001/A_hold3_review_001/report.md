# Independent hold3 native pair audit

The baseline and guarded-prefer8 branch both closed native acceptance. Their input bytes match: six actual jobs, three trays. All archived source bytes in each run match their own prepared and accepted hashes. Completion values were independently bound to BAG_ARRIVAL and UNLOAD_COMPLETE receipts.

Actual per-job deltas: {'loaded': 0.0, 'receiver': 0.0, 'reuse1': 0.0, 'reuse2': -11.08900000000001, 'blocker': 0.0, 'reuse3': -9.789000000000005}. Every delta is nonpositive. The selected reuse2 and reuse3 route commands both have updated ACKs and actual first edges7→8. This is an executed fixed guarded preference mechanism; it is not learned-policy improvement.

The first command was issued at15.150999999999991 with expiry20.15099999999999, generation8, traversal9. The second choice was at21.86100000000001, generation11, traversal13. The old preference is expired and mismatches both identity versions. Native027 apply_circulation_route_preference checks all three conditions (event_driven_junction.hpp:14697). native_default issues no new command and does not clear a still-applicable hint; here the previous hint is already inapplicable.

The second mask has native_default and prefer8 enabled; prefer3 is correctly disabled by current capacity even though its conditional completion projection passes. Recorded model deltas distinguish waiting/default from bypass8. The second native_default physical result has not been executed by this pair. A separately closed protected-current comparison is still required for an early-choice witness; the original baseline alone does not satisfy that gate.
