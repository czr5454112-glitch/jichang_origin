"""Read-only process memory evidence for bounded development experiments."""
from __future__ import annotations

import os
import platform


def memory_snapshot():
    """Report OS byte counters; peak covers this process's entire lifetime.

    Child processes must record their own measurements. Current RSS is never
    substituted for a missing peak counter, and peaks from parallel workers
    must not be described as a measured simultaneous aggregate peak.
    """
    result = {"pid": os.getpid(), "platform": platform.system(),
              "scope": "current process; peak includes imports and earlier stages, excludes child processes",
              "rss_bytes": None, "peak_working_set_bytes": None,
              "private_bytes": None, "peak_commit_bytes": None}
    try:
        import psutil
    except ImportError as error:
        result.update(provider=None, peak_available=False,
                      unavailable_reason=type(error).__name__)
        return result
    try:
        counters = psutil.Process().memory_info()._asdict()
        result.update(provider="psutil", provider_version=psutil.__version__,
                      rss_bytes=counters.get("rss"),
                      peak_working_set_bytes=counters.get("peak_wset"),
                      private_bytes=counters.get("private"),
                      peak_commit_bytes=counters.get("peak_pagefile"),
                      peak_available="peak_wset" in counters)
    except (psutil.Error, OSError) as error:
        result.update(provider=None, peak_available=False,
                      unavailable_reason=type(error).__name__)
    return result
