"""Owned120 fixed25 synthetic ABBA harness tests, no real predictions."""
from __future__ import annotations
import time
BOOT=time.monotonic()
import hashlib
from pathlib import Path
from types import FunctionType, SimpleNamespace
from . import run_scoped_public_inputs_v2_cost_pure as frozen

MODULE='scripts.experiments.g31_ics_circulation.run_owned_initial_bundle_cost_pure'
TEST='tests/test_g31_circulation_owned_initial_bundle_cost.py'
COUNT=25
HELPER_MODULE='tests.test_g31_circulation_initial_scoped_inputs_cost'
HELPER_PATH='tests/test_g31_circulation_initial_scoped_inputs_cost.py'
HELPER_SHA='cf273fd628f1b264c0538de22afe8a5c653982d007c45878ff33b31c731dfc59'
HELPER_ARCHIVE=frozen.ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/owned_initial_bundle_source_prepare_001/source'/HELPER_PATH


def _helper_pins():
    for path in (frozen.ROOT/HELPER_PATH, HELPER_ARCHIVE):
        frozen.require(hashlib.sha256(path.read_bytes()).hexdigest()==HELPER_SHA,'explicit_bare_helper_identity')


def _source_closure(root,entries):
    # The test's bare import is resolved by pytest's tests path, whereas the
    # repository closure resolver needs the explicit qualified module name.
    _helper_pins()
    frozen.require(Path(root).resolve()==frozen.ROOT,'explicit_helper_root')
    files=frozen.image.source_closure(root,(*entries,HELPER_MODULE))
    frozen.require(HELPER_PATH in files
        and hashlib.sha256(files[HELPER_PATH]).hexdigest()==HELPER_SHA,'explicit_helper_in_execution_closure')
    return files


def runner_function():
    image=SimpleNamespace(**{**vars(frozen.image),'source_closure':_source_closure})
    function=FunctionType(frozen.main.__code__,{**frozen.main.__globals__,
        'BOOT':BOOT,'MODULE':MODULE,'TEST':TEST,'COUNT':COUNT,'image':image},frozen.main.__name__,frozen.main.__defaults__,frozen.main.__closure__)
    function.__kwdefaults__=frozen.main.__kwdefaults__
    return function


def source_proof():
    _helper_pins(); function=runner_function(); original=frozen.main
    allowed={'BOOT','MODULE','TEST','COUNT','image'}
    frozen.require(function.__code__ is original.__code__
        and function.__defaults__ is original.__defaults__ and function.__closure__ is original.__closure__
        and function.__kwdefaults__ is original.__kwdefaults__
        and set(function.__globals__)==set(original.__globals__)
        and all(function.__globals__[key] is value for key,value in original.__globals__.items() if key not in allowed),
        'complete_pure_runner_namespace')
    image=function.__globals__['image']
    frozen.require(set(vars(image))==set(vars(frozen.image))
        and all(getattr(image,key) is value for key,value in vars(frozen.image).items() if key!='source_closure')
        and image.source_closure is _source_closure,'private_image_only_closure_entry')
    return {'original_owned_main_code_defaults_closure_retained':True,
        'explicit_bare_helper':HELPER_MODULE,'helper_sha256':HELPER_SHA,
        'current_and_prior_archive_checked':True,'closure_addition_before_worker_launch':True,
        'frozen_image_not_modified':True,'fixed_tests':COUNT}


def main():
    source_proof()
    return runner_function()()


if __name__=='__main__': raise SystemExit(main())
