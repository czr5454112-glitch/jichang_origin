# Literature boundaries for joint repositioning

| Source checked | Implemented or intended use | Claim excluded |
|---|---|---|
| [NRC: Dray-Q, Aghazadeh et al., 2024](https://nrc-publications.canada.ca/eng/view/object/?id=64e2b7f8-7370-435d-ad26-4dde08363754) | Motivate demand-dependent empty-resource repositioning under limited stock and delay costs. | This implementation is not a Rainbow-DQN or exact Dray-Q/CUP reproduction. |
| [Beojone et al. author record](https://sirmatel.github.io/publications/beojone2024/) | Separate demand prediction, individual resource assignment and physical control. | Its ride-hailing result is not airport evidence. The author page's displayed DOI conflicts with its article metadata; do not use that DOI as verified. |
| [Jin et al., PPL v4](https://arxiv.org/abs/2212.09900v4) | Record behavior selection probabilities; abstain outside measured support. | Empirical neighbourhood fallback is not the paper's LCB algorithm or theorem, nor evidence of zero-support guarantees. |
| [Yang and Liu, DG-PG v4](https://arxiv.org/abs/2602.20078v4) | Recognize shared-return noise; use interpretable proxy features and measured paired differences. | Adding proxy features to cost regression does not implement DG-PG or inherit its gradient guarantees. |
| [Sørensen et al., ISCSIC 2021, Aarhus record](https://pure.au.dk/portal/en/publications/baggage-routing-with-scheduled-departures-using-deep-reinforcemen/) | Establish prior airport work combining scheduled departures, empty totes and reinforcement learning. | No broad first-ever airport flight-aware empty-tote RL claim. Its centralized simulated result does not establish this distributed protocol's benefit. |

The supplied plan's MPC and asynchronous-control references are design context. This stage has not independently reproduced their models, conditions, stability claims or deployment performance. The technical review accepts the plan's experiment structure while keeping conclusions dependent on actual closed native evidence.
