# Finite-body short-link reference and manufacturer evidence

This is a separate research model, not a correction to the original physical contract. No native physics, map, workload, capacity, FIFO or controller source was changed for this investigation. It complements [the finite-footprint review](LT2_FINITE_FOOTPRINT_PHYSICS_REVIEW_20261014.md) and [the physical ledger](PHYSICAL_SEMANTICS_LEDGER.md).

There is a constructive physical interpretation worth testing: a short conveyor link can have zero capacity for a whole parked tray while a longer tray traverses it with its body supported by neighboring sections. Such traversal must reserve every overlapped section and clear resources only when the rear passes. The original numeric zero remains zero. Choosing this interpretation changes the model's admission/occupancy contract and must be explicit; it cannot be presented as successful execution under the current zero-as-closed runtime.

## Manufacturer precedent and its limits

Hytrol's own EZLogic4.0 manual, printed pages16–17, distinguishes fixed zones from dynamic zone allocation. Fixed-zone operation requires a zone longer than the product. Dynamic allocation assigns multiple base zones to a longer product and retains a base-zone gap. This supports the engineering plausibility of coordinated multi-zone occupancy; it does not establish that the airport's devices implement that function. The manual also describes coordinated upstream holding and separate loading/unloading functions, reinforcing that a local length change alone is insufficient. [Hytrol EZLogic4.0 Network Model User Manual](https://cdn.hytrol.com/H2-MN-NP-001.1.0_EZLogic4.0_Network_Model_User_Manual_EN-2.pdf).

The large-agent MAPF formulation explicitly models bodies occupying multiple locations, rather than treating agents as points. Continuous-time MAPF separately supports unequal action durations without an arbitrary global time step. These are useful modeling precedents; neither source certifies the rectangular-tray/conveyor/divert mechanics here or supplies a complete ready-made controller. [Li et al., Multi-Agent Path Finding for Large Agents](https://ojs.aaai.org/index.php/SOCS/article/view/18483), [Andreychuk et al., Multi-Agent Pathfinding with Continuous Time](https://www.ijcai.org/proceedings/2019/6).

## The actual local source contract

The unchanged processed profile has `97→98` length0.6m, speed2m/s, pallet count0. Both endpoints are type4 divert devices:97 is DD3/ICS103 and98 is DD4/ICS104, each with1.5s service. Relevant neighbors include `96→97` length116.6m and `98→99` length4.9m. These are directed lengths, not a surveyed straight layout. Both endpoint coordinates are0,0 with explicit `NOT_PROVIDED_ROUTING_ONLY_ZERO_PLACEHOLDER` status. The profile states that all227 pallet counts follow floor(length/2m), but this pattern does not establish actual tray dimensions; the legacy1m AGV header is itself marked provisional. [Original map profile](../../data/processed/maps/nanning_airport_profile.json), [saved workbook-cell audit](../../outputs/experiments/g31_ics_long_term_20261013/p2_zero_capacity_semantics_001.json).

Consequently, a credible variant must handle two closely spaced diverts as a potentially coupled body-occupancy region. It cannot independently release DD3 when the front reaches DD4, ignore tail occupancy, make the rigid body bend along a polyline, infer turns from placeholder coordinates, or omit either service operation. A particular straight-through movement may be feasible under an explicit support/drive/turn contract; other branches may remain blocked. Any actual hardware closure remains closed.

## Executable exact reference

[finite_body_reference.py](../../scripts/experiments/g31_ics_circulation/finite_body_reference.py) is a small offline validator for a declared contiguous straight supported guideway. Its required contract is `research.straight_supported_finite_body.v1`, with explicit `short_link_semantics=explicit_multisegment_body`. It accepts a fixed inventory and prescribed piecewise-linear forward front positions. It does not find routes, create motion, query native state or simulate an airport.

For body lengthL and front positionp(t), the occupied interval is[p(t)-L,p(t)]. Segment occupancy is positive-length intersection with that body. The reference computes exact rational times when front or rear crosses each boundary and includes every motion slope change. Collision clearance is linear between those times, so checking interval endpoints suffices; additional midpoint checks determine constant resource membership and speed constraints. Following order is fixed from initial physical order, never resorted to conceal an overtake. A body spanning a slower section must satisfy that section's speed bound. Whole-body storage counts remain an additional limit; the zero short-link count is never raised. A stationary or horizon-truncated body retains every segment it still overlaps.

The simplest successful witness is a2m tray starting in a2m source bay, crossing the0.6m section at2m/s, and coming fully into a2m receiver bay. These bays are declared synthetic support, not inferred airport geometry:

| Time | Front | Rear | Consequence |
|---|---:|---:|---|
|0s|0m|-2m|Body lies in source support.|
|0.3s|0.6m|-1.4m|Front exits the short link; source and short-link resources still belong to the same body.|
|1s|2m|0m|Rear clears the source; short link remains occupied.|
|1.3s|2.6m|0.6m|Rear clears the short link; body occupies the receiver.|

The front still traverses0.6m in0.3s. Its occupancy lasts1.3s, and the source remains reserved for1s. Thus the witness adds physical constraints instead of replacing zero with one or erasing the link. This is a motion-only reference; actual node services, stopping/acceleration, mechanical support, turns and multi-owner grants must be supplied before integration.

Fifteen pure cases pass in [pure_003.xml](../../outputs/experiments/g31_ics_lt2_sustained_20261014/finite_body_reference_001/pure_003.xml). They include the positive crossing, stopped straddling, partial-horizon live leases, finite following gap, a collision missed by looking only at start/end, occupied receiver, slower overlapped drive, hardware closure, unsupported rear, preserved positive storage limits, reverse motion, duplicate tray IDs, nonfinite values and undeclared/broken corridors. The earlier14-case pass and the subsequent fixture failure are preserved: after adding whole-body storage enforcement, the collision fixture first violated its unchanged one-body source capacity; assigning its explicitly enlarged synthetic5m source its declared two-body capacity allows the intended later-collision test. No field input was retuned.

## Smallest next integration experiment

Use a new synthetic domain with a2m source support,0.6m connector and2m receiver, fixed tray IDs, mandatory source/receiver services and strict FIFO. Predeclare successful empty-receiver passage, occupied-receiver rejection, stopped spanning, source-controller loss, receiver-controller loss, lost/duplicate/reordered grant and stale-tail-clearance cases. Add one merge only after the straight case passes; retain both device conflict regions until actual rear clearance. A front-edge-exit receipt must not authorize release of a body reservation.

The prospective native contract needs front progress, rigid-body length/width, committed path support behind the front, physical tail-clearance events, overlapping-resource identities, and coordinated downstream receiving grants. A failed or expired communication lease cannot delete an already entered physical body; resources remain occupied until actual clearance or explicit physical recovery. Source reserve and normal-service protection still count real trays once, despite a single tray occupying several resources. Old all-offered business objectives and strict per-job protection remain unchanged in the separately declared variant.

Do not run a whole original-map success campaign by assuming every short link is straight and supported. First validate the DD3→DD4 movement using an explicit surveyed or research geometry/drive contract and the two original1.5s service obligations. Preserve the original model's negative result alongside any alternative. A successful alternative would show feasibility under its changed physical interpretation, not invalidate the existing zero-as-closed blocking certificate or establish full-day/100ms performance.
