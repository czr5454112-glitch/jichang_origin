# Early-bag storage: preserve the carrier contract

Read-only follow-up, 2026-10-10. No frozen controller, physical batch, business parameter or input graph changed. This note complements the repository task-source inventory; it does not assert which storage implementation the Nanning installation uses.

## Primary source and limited use

BEUMER Group's *The business case for ICS: Is it a BHS solution for your airport?*, printed pages 4, 8 and 22, describes a carrier-based flow in which a bag stays with its carrier through screening/sortation and can remain in its individual tray/bin during automated early-bag storage. The source therefore establishes that storage need not release the tray. It is a supplier description, not an independent performance study or a specification of this repository's installation. Its throughput, reliability and marketing comparisons are not imported into this experiment. [Supplier PDF](https://www.beumergroup.com/app/uploads/2023/03/NEW-AP-BP-Is-it-a-BHS-solution-for-your-airport__02.21.2023.pdf).

The source was read through PDF text at these pages. No airport storage capacity, carrier stock, release protocol, access permission, headway, travel speed or transit fault rate is inferred from it.

## Consequences for the next implementation (our model design)

The workload adapter must declare the storage contract explicitly. A first OD ending at EBS followed by a second OD starting there does not itself specify whether a bag remains on its tray, whether an unload/reload takes place, or whether the second movement has legitimately obtained a real tray. Those alternatives produce different finite-inventory and capacity constraints.

For **on-carrier storage**, the same bag and tray identities persist through ingress, storage occupancy, release and outbound transport. The storage interval consumes real carrier inventory as well as its declared storage resource. Reaching the intermediate storage waypoint must not mark the business bag complete or advertise its tray as empty supply. Release requires an actually available/published authorization; a future flight update in the hidden event tape cannot release it early. The final completion/deadline denominator remains the original bag.

For **off-carrier storage**, transfer has an explicit legal unload service, bag-storage occupancy and subsequent retrieval/load service. A release cannot invent a tray or bypass FIFO, module capacity or owner admission. The carrier becomes supply only when its declared transfer and hold obligations finish. A second leg must remain causally dependent on completion of the first and on legitimate release; its fixed scheduled timestamp is not proof that ingress actually succeeded.

The existing `Bag.destination` / route commitment / completion boundary needs an explicit stage interface before either representation can become a physical scenario. Merely renaming two independent transport jobs with one common bag ID is insufficient: the owner must reserve the relevant storage/module resources, retain entered legs and irrevocable commitments, and publish the stage transition atomically. Carry stage, release-message version and storage mode into checkpoint/cache/action contracts whenever they affect continuation.

Validation should report original bags and movement legs separately; all unadmitted, stored, unreleased, unfinished and in-transit bags stay in the business denominator. Measure actual loaded-storage dwell, tray reuse, storage/transfer backpressure, and release-to-final tail service. Preserve the original topology and show which declared interface is synthetic until its operational contract is confirmed. This is modeling work still to implement, not a newly proved service guarantee or a substitute for the two original routing/prebalancing requirements.

External browsing and note authoring were unmetered auxiliary work. No CPU or physical-simulation count is invented for them.
