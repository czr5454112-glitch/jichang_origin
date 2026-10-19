"""Separate owned120 driver12 gate; accepted routing37 is not rerun.

Source collection never consults this gate's future receipt. The exact old
owned runner provides all-source entry/exit and one synthetic pytest child.
An external typed full Python launch-to-exit clock is independently required.
"""
from __future__ import annotations
import time
BOOT = time.perf_counter()
from types import FunctionType

from . import run_bridge_saved_c_digest_pure as old
from . import audit_bridge_saved_c_digest as driver

MODULE = driver.DRIVER_PURE_MODULE
TEST = driver.TEST
SCHEMA = driver.DRIVER_PURE_SCHEMA
EXPECTED_TESTS = 12
LIMIT = 120.


def sources():
    # driver.source_files is only static/manual source collection. It does not
    # call contract(), prepare(), check_driver_pure() or read actual fixtures.
    return driver.source_files()


def namespace():
    values = dict(vars(old))
    for name, function in vars(old).items():
        if isinstance(function, FunctionType) and function.__globals__ is vars(old):
            copied = FunctionType(function.__code__, values, function.__name__,
                                  function.__defaults__, function.__closure__)
            copied.__kwdefaults__ = function.__kwdefaults__
            copied.__annotations__ = dict(function.__annotations__)
            values[name] = copied
    values.update(BOOT=BOOT, MODULE=MODULE, TEST=TEST, SCHEMA=SCHEMA,
                  EXPECTED_TESTS=EXPECTED_TESTS, LIMIT=LIMIT, sources=sources)
    old.require(values['main'].__code__ is old.main.__code__
                and values['worker'].__code__ is old.worker.__code__
                and values['source_check'].__code__ is old.source_check.__code__
                and values['main'].__globals__ is values['worker'].__globals__ is values
                and values['source_check'].__globals__ is values,
                'driver_pure_full_namespace')
    return values


def main():
    return namespace()['main']()


if __name__ == '__main__':
    raise SystemExit(main())
