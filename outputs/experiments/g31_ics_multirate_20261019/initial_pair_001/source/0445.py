"""Separate executable quiescent-cap experiment; original campaign is immutable."""
from __future__ import annotations
import argparse
import ast
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from . import research_original_low_wip_repeat as reference
from . import repeat_quiescent_cap as candidate

SCHEMA='g31.original_low_wip_quiescent.v1'
MODULE='scripts.experiments.g31_ics_circulation.research_original_low_wip_quiescent'
REFERENCE=reference.OUT/'original_low_wip_repeat_prepare_001'
READY_SHA='822cc0e73d71a2c44efcc36618fcc11941c350b54c9621fda3081a6d8a8f4ca4'
REFERENCE_SHA='7756dbfc24e756bfb7f1cf12d1a9574e1a3c5bfdef37a47d973ed0b77749d9e8'
_original={key:getattr(reference,key) for key in ('RepeatOwner','SCHEMA','MODULE','contract','source_paths','verify_campaign')}
_active=False
_require_terminal=False


def source_paths():
    pending=[Path(__file__),Path(__file__).with_name('launch_original_low_wip_quiescent.py'),
        Path(__file__).with_name('verify_original_low_wip_quiescent.py'),
        reference.ROOT/'tests/test_g31_circulation_low_wip_quiescent.py',
        reference.ROOT/'tests/test_g31_circulation_repeat_quiescent_cap.py',
        reference.ROOT/'tests/test_g31_circulation_low_wip_repeat_review.py']
    pending.extend(_original['source_paths']())
    found=set()
    def enqueue(target):
        for path in (target.with_suffix('.py'),target/'__init__.py'):
            if path.is_file() and path.resolve().is_relative_to(reference.ROOT):
                pending.append(path)
                for parent in path.parents:
                    if parent==reference.ROOT: break
                    if (parent/'__init__.py').is_file(): pending.append(parent/'__init__.py')
    while pending:
        path=pending.pop().resolve()
        if path in found: continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node,ast.ImportFrom):
                for root in ([path.parent] if node.level else [reference.ROOT,reference.ROOT/'src']):
                    for _ in range(max(0,node.level-1)): root=root.parent
                    if node.module: root=root.joinpath(*node.module.split('.')); enqueue(root)
                    for alias in node.names:
                        if alias.name!='*': enqueue(root/alias.name)
            elif isinstance(node,ast.Import):
                for alias in node.names:
                    for root in (reference.ROOT,reference.ROOT/'src'): enqueue(root.joinpath(*alias.name.split('.')))
    return sorted(found)


def contract():
    result=deepcopy(_original['contract']())
    result['quiescent_cap']=candidate.comparison_contract()
    result['comparison_reference']={'path':str(REFERENCE),'ready_sha256':READY_SHA,'source_sha256':REFERENCE_SHA}
    return result


def verify_campaign(output):
    result=_original['verify_campaign'](output)
    reference.require(reference.base.sha(reference.__file__)==REFERENCE_SHA
        and reference.base.sha(REFERENCE/'ready.json')==READY_SHA,'quiescent_reference_changed')
    candidate.prove_only_cap_check_moved()
    if _require_terminal:
        from .review_original_low_wip_repeat_saved import terminal_inventory
        terminal_inventory(REFERENCE)  # evidence-read gate; never a reason to drop an incomplete arm
    return result


@contextmanager
def installed(*,require_terminal=False):
    global _active,_require_terminal
    reference.require(not _active,'quiescent_context_overlap')
    prior={key:getattr(reference,key) for key in _original}
    _active=True;_require_terminal=require_terminal
    values={'RepeatOwner':candidate.RepeatOwner,'SCHEMA':SCHEMA,'MODULE':MODULE,
        'contract':contract,'source_paths':source_paths,'verify_campaign':verify_campaign}
    try:
        for key,value in values.items(): setattr(reference,key,value)
        yield
    finally:
        for key,value in prior.items(): setattr(reference,key,value)
        _active=False;_require_terminal=False


def prepare(output):
    with installed(): return reference.prepare(output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--worker',choices=tuple(reference.CAPS));parser.add_argument('--verify',choices=tuple(reference.CAPS))
    parser.add_argument('--compare',action='store_true');parser.add_argument('--campaign',action='store_true');parser.add_argument('--admission')
    args=parser.parse_args();output=args.output.resolve()
    reference.require(sum((args.prepare,bool(args.worker),bool(args.verify),args.compare,args.campaign))==1,'quiescent_mode')
    if args.prepare: prepare(output);return
    if args.campaign:
        with installed(require_terminal=True): raise SystemExit(reference.campaign_worker(output,args.admission))
    if args.worker:
        with installed(require_terminal=True),reference.installed(): reference.base.worker(output/args.worker)
        return
    from . import verify_original_low_wip_quiescent as verifier
    result=verifier.verify_case(output/args.verify) if args.verify else verifier.compare(output)
    path=output/args.verify/'independent_verification.json' if args.verify else output/'comparison.json'
    reference.require(not path.exists(),'quiescent_verification_exists');reference.base.write(path,result)


if __name__=='__main__': main()
