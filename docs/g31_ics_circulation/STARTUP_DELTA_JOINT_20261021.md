# Joint reposition stage: startup review

Reviewed against `f3567943e31bbbfa6ac40887547603d397ce25d6`; tracked tree was clean. The supplied plan is a proposal authorized for review and implementation, not evidence that its expected gains already exist.

The diagnosis is supported by code: the previous learned catalogue fixes the first eligible tray before ranking destinations; R0 stock return also sorts source IDs before selecting. Actual waiting-demand matching already compares ETA, so the missing mechanism is specifically proactive post-priority joint source/destination choice. The current B1 adapter uses feasible-domain v2 (including the 92-to-95 mass pushforward), not the older raw uniform loader directory.

Proceed with a separate, versioned post-priority selector; keep old defaults, native030, G31/R1, graph, FIFO, 22 trays, accepted obligations and hard source reserves. Catalogue construction remains current-only. A branch adds at most one real proposal, with quota charged before submission including rejection. New controller state identifies the selector and serializes policy state.

Clarifications before execution:

- The inventory proxy represents next availability and one use, not all future tray cycles. ETA is an estimate; unknown inventory remains missing. Primary supply is current facts plus identifiable accepted obligations; conditional releases are diagnostic.
- New train/dev/test parents have fresh identities and whole-parent splits, but share one historical template: zero new independent real airport days. Synthetic calendar availability is an explicit experiment coordinate, never real deployment evidence.
- The 160-start ceiling includes failed constructors, calibration, replay prefixes and timeouts. Register a new 48-hour active window; resumed work never resets accumulated time. Account calendar time and downtime separately. Use one native worker initially, 40 GiB new-evidence ceiling and 30 GiB free-space floor.
- Closed finite-horizon costs, same-owner actual next actions, frozen whole-joint-policy versions and real recollection are required for multi-step learning. Censored trajectories cannot receive zero terminal cost. No complete learned improvement is claimed from the previous stage.
- Test stays locked until data/support, model and development selection gates pass. Existing strict service promotion rules remain in force. Failure to improve is a valid result.

Local measurement: RTX 4070 Laptop 8 GiB, 32 GiB RAM, 22 logical CPUs, about 146 GiB free disk. The user subsequently selected local RTX 4070 only. All execution stays local; the current small NumPy learner uses CPU, so access to this GPU is not a claim that the learner has GPU acceleration.

Primary-source checks confirm the plan's PPL and DG-PG identities, but neither theorem automatically applies to this implementation. PPL requires behavior-policy overlap for useful actions; DG-PG is a specific gradient construction, not any proxy feature. Author-hosted hierarchical-repositioning metadata contains a DOI inconsistency; use the title/author record cautiously until publisher metadata is verified. These references motivate design only.

Sources: https://arxiv.org/abs/2212.09900v4 ; https://arxiv.org/abs/2602.20078v4 ; https://sirmatel.github.io/publications/beojone2024/

Implementation began in parallel: joint catalogue/controller; event-time inventory proxy and train-only mapping; continuous trajectory dataset and conservative SARSA. Root owns immutable registration, parent/calendar domain, runner, native gates and evidence integration. No prior experiment artifacts are overwritten.
