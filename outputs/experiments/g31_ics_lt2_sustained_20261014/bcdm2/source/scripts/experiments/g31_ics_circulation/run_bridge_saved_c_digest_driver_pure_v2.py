"""Draft owned120: original12 plus resolver15, with bounded stage evidence."""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace
import sys
from . import run_bridge_saved_c_digest_pure as original
from . import audit_bridge_saved_c_digest_v2 as driver

MODULE, TEST, SCHEMA = driver.DRIVER_PURE_MODULE, driver.TEST, driver.DRIVER_PURE_SCHEMA
EXPECTED_TESTS, LIMIT = driver.COUNT, 120.


class Journal:
    LIMIT = 64
    def __init__(self, path):
        self.path = Path(path); self.stream = self.path.open('x', encoding='utf8'); self.count = 0
    def append(self, phase, event):
        original.require(self.count < self.LIMIT, 'driver_pure_journal_limit')
        value = {'sequence': self.count, 'phase': phase, 'event': event, 'at_ns': time.perf_counter_ns()}
        raw = json.dumps(value, allow_nan=False) + '\n'
        original.require(self.stream.write(raw) == len(raw), 'driver_pure_journal_short_write')
        self.stream.flush(); self.count += 1
    def close(self): self.stream.close()


def traced(journal, label, function):
    def invoke(*args, **kwargs):
        journal.append(label, 'started')
        try: result = function(*args, **kwargs)
        except BaseException:
            try: journal.append(label, 'failed')
            except BaseException: pass  # Original call failure stays primary; no success is emitted.
            raise
        journal.append(label, 'completed')
        return result
    return invoke


def namespace(journal):
    values = dict(vars(original))
    for name, function in vars(original).items():
        if isinstance(function, FunctionType) and function.__globals__ is vars(original):
            values[name] = driver.r.original.clone(function, values)
    values.update(BOOT=BOOT, MODULE=MODULE, TEST=TEST, SCHEMA=SCHEMA,
                  EXPECTED_TESTS=EXPECTED_TESTS, LIMIT=LIMIT,
                  sources=traced(journal, 'source_union', driver.source_files))
    values['source_check'] = traced(journal, 'current_archive_loaded_check', values['source_check'])
    values['reference'] = SimpleNamespace(**{**vars(original.reference),
        'archive_sources': traced(journal, 'archive_sources', original.reference.archive_sources)})
    values['bounded_windows_job'] = SimpleNamespace(**{**vars(original.bounded_windows_job),
        'run': traced(journal, 'owned_child', original.bounded_windows_job.run)})
    writer = values['write']
    def write(path, value):
        return traced(journal, 'write_' + Path(path).name, writer)(path, value)
    values['write'] = write
    original.require(values['main'].__code__ is original.main.__code__
        and values['worker'].__code__ is original.worker.__code__, 'shared_pure_original_execution_code')
    return values


def main():
    # Inspect args only to select one parent/child journal. The original parser
    # and actual owned runner are retained. Parent output.mkdir still occurs in
    # original main, so the journal is lazily opened at its first source stage.
    parser = original.argparse.ArgumentParser(add_help=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    args, _ = parser.parse_known_args()
    holder = []
    class Lazy:
        def append(self, phase, event):
            if not holder:
                holder.append(Journal(args.output.resolve() /
                    ('worker_stages.jsonl' if args.worker else 'parent_stages.jsonl')))
            holder[0].append(phase, event)
    try: return namespace(Lazy())['main']()
    finally:
        if holder: holder[0].close()


if __name__ == '__main__': raise SystemExit(main())
