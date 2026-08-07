# G4IRSF19 model ablation decision

| Candidate | Executed evidence | Decision |
|---|---|---|
| S1 frozen learned legal-local scorer | native closed loop | baseline only |
| S2 learned scorer without absolute IDs | 0 route mutations; identical metrics | reject as ineffective |
| S3 shortest-potential standalone rule | 0 route mutations; identical metrics | no advantage |
| S4 queue/calendar-aware standalone rule | real mutations; 1x and 2x benefit | select for research mainline |
| new residual / tiny MLP / set scorer | not trained | intentionally stopped before model growth |

Residual, standalone learned, and set-based learners cannot be ranked honestly
because the prerequisite counterfactual support was absent: Source ordering had
zero action mutations, while the existing learned Route variants duplicated the
baseline. Training them merely to fill an experiment matrix would add complexity
without evidence.

The winning ablation is therefore the smallest existing controller, S4. It is
not described as learned. A future learner must first beat S4 on replayable
local-route counterfactuals and then preserve the 1x/2x safety and tail results.
