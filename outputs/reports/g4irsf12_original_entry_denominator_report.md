# G4IRSF12 Original-Entry Denominator

Status: `FROZEN_FORMULAS_READY`.

For each raw `task_id`, every protected segment participates:

```text
original_entry_time_tth = sum(finish_time - original_entry_time)
java_release_time_tth   = sum(finish_time - pass_time)
scheduled_pre_release   = sum(pass_time - original_entry_time)
source_wait             = sum(admitted_time - pass_time)
network_time            = sum(finish_time - admitted_time)
total_system_time       = scheduled_pre_release + source_wait + network_time
```

`total_system_time` must equal `original_entry_time_tth`. The source file's
`original_entry_time` is the raw-task pass time; split storage rows retain that
same value, while `pass_time` is each Java segment release. A raw bag is
complete only if every selected segment completes. Survivor means are reported
only with an explicit survivor label and never participate in promotion.

Historical HCA* `3.967122711 min` is parsed
`processed_segment_attempt_time_tth`, not original-entry, and never participates
in the Phase-J original-entry gate. Matched original-entry gates use frozen
v2-safe `4.124305453 min` and corrected historical HCA `5.764936746 min`.
The stricter v2-safe target therefore controls promotion, while both comparisons
remain explicit.
