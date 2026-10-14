# Clock interpretation: primary references read during Round8

Consulted 2026-10-10. This is interpretation evidence, not a change to frozen clocks or the experimental sample.

- [Python 3.11 time documentation](https://docs.python.org/3.11/library/time.html#time.process_time): process CPU combines system and user execution time and excludes sleep; nanosecond-returning APIs avoid floating-point representation loss. This does not imply nanosecond CPU accounting accuracy. `get_clock_info` records implementation and reported resolution. The same page states `perf_counter` is system-wide on Windows from Python 3.10, supporting the parent/child monotonic entry-boundary difference on this Python 3.11 host.
- [Microsoft GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes): kernel and user times sum execution across threads of the process; returned FILETIME counts are expressed in 100 ns units. We query after process exit, before closing its handle. Units are not proof of observed increment size or measurement accuracy. Complete OS lifetime CPU includes child startup/import/receipt/teardown and excludes the parent process, which is measured separately.

Our conclusion from actual saved query records is narrower than those API descriptions: short active intervals can measure zero CPU while having nonzero elapsed time. The final artifact census reports zero frequencies, minimum positive CPU and observed GCD separately for each arm, query role and timer. These are empirical quantization diagnostics, not an inferred error bound. Episode algorithm timing is still a sum of quantized sampled intervals; complete-process CPU and elapsed time remain separate measurement axes. No hard real-time or unloaded production latency claim follows.

The Python issue-tracker page returned an unavailable/internal error and is not used as evidence.
