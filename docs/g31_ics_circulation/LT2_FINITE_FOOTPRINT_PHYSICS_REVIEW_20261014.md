# Finite footprint across adjacent segments: separate model question

The frozen original model remains authoritative: a0.6m edge with a2m tray and
the declared floor-capacity rule has capacity0. No route solver, larger search
budget or rounded-up capacity makes that edge executable under this contract.
The following is a literature-backed physical-extension question, not a patch,
permission change or explanation that invalidates the saved negative results.

## Primary evidence

Švancara and Barták, *Tackling Train Routing via Multi-agent Pathfinding and
Constraint-based Scheduling*, ICAART2022, pp306–313,
[publisher PDF](https://www.scitepress.org/PublishedPapers/2022/108697/108697.pdf),
DOI10.5220/0010869700003116, directly models a body's presence across adjoining
resources. Section3.2, pp309–310, defines traversal occupancy for the duration
that any part remains in a rail segment. Consecutive activities overlap by a
length/speed-dependent interval. Section3.1 explains why a fixed elapsed-time
clearance behind a point agent is insufficient when the body stops. Sections2.1
and3 distinguish rigid from bending agents and reject artificial shrinking at
stops or terminals. This supports the representation principle, not the claim
that a rigid baggage tray can traverse our specific short conveyor segment.

Atzmon, Diei and Rave, *Multi-Train Path Finding*, SoCS10(1),125–129(2019),
[publisher record](https://ojs.aaai.org/index.php/SOCS/article/view/18515),
DOI10.1609/socs.v10i1.18515, also treats agents as ordered sequences occupying
multiple locations. Its publisher date is2019-07-16. The2022 paper identifies
its start/goal expansion/shrinking abstraction, so it is not a direct full-body
physical specification for this project.

Johnstone, Creighton and Nahavandi, *Simulation-based baggage handling system
merge analysis*, Simulation Modelling Practice and Theory53(2015),45–59,
[institutional author record](https://dro.deakin.edu.au/articles/journal_contribution/Simulation-based_baggage_handling_system_merge_analysis/20912956),
DOI10.1016/j.simpat.2015.01.003, studies conveyor merge control together with
physical layout. Its reported dependence on merge layout supports requiring
actual geometry rather than importing a railway abstraction as validated tray
physics. The repository's2024 record revision is not the article's publication
year. This review used its primary abstract, not an unseen full-text result.

## Project-specific inference and required inputs

A segment shorter than a body need not be impassable in a different model that
allows the front to enter it while the rear remains on its predecessor. That
statement is conditional on physical support and allowed motion across the
boundary. A rigid tray, articulated train and point packet are different bodies.
The current map alone does not establish which boundary-crossing assumptions
are physically valid.

Before implementing an extension, establish:

* What each edge length measures: centerline travel distance, parking berth,
  conveyor module, sensor spacing or abstract connector. Supply geometry at
  nodes/merges, orientation, width, curvature and physical overlap boundaries.
* Tray length, width, rigidity, permitted rotation, support/bridgeability and
  minimum clearances; whether adjacent drives can support the same tray safely.
* Velocity/acceleration/braking and hold rules across drive boundaries, sensor
  uncertainty, headway reference points, and whether service uses front entry,
  center arrival, rear clearance or whole-body availability.
* Initial and terminal whole-body placement; unloading and Storage receiving
  requirements; switch/merge locking until the rear clears; capacity and FIFO
  semantics when one tray intersects several owner resources simultaneously.

As an illustrative derivation for a straight one-dimensional path, if the front
is at coordinate s and the rigid body has length L, its footprint is[s−L,s].
Every intersected resource remains occupied. At constant speed v without a stop,
a segment of length d is intersected for(d+L)/v. This equation is not a permission
rule for turns, changing drive speeds, unsupported gaps or stop-and-go motion.
A stop retains the rear footprint; it must not disappear after a timer.

An implementation would need an explicit new versioned physical/action contract
and native body-occupancy audit. It must retain predecessor occupancy until rear
clearance, preserve FIFO, and obtain legitimate owner authority for each occupied
resource. Reserving a whole segment for one body can be conservative and changes
effective capacity; using disjoint continuous intervals needs actual geometry and
separation rules. Neither approach is equivalent to setting the old capacity to1.
Compare both baseline and joint method under the same new inputs and contract,
while retaining all original-model evidence separately. No implementation or
physical-validation claim is made here.
