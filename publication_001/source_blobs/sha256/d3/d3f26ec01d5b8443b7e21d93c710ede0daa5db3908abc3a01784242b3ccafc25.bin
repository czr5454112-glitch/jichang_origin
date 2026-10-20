"""Ledger-only entry for one immutable read-only shadow artifact audit."""
from __future__ import annotations
import sys
if __name__=='__main__' and sys.stdin.readline().strip()!='g31_shadow_readonly_audit_v1':
    raise SystemExit('shadow_review:parent_job_admission_required')

import argparse
import hashlib
from pathlib import Path
import runpy

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--audit-sha256',required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[3]
    audit=args.audit.resolve()
    if not audit.is_relative_to(root/'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001'):
        raise ValueError('shadow_review:artifact_scope')
    if hashlib.sha256(audit.read_bytes()).hexdigest()!=args.audit_sha256:
        raise ValueError('shadow_review:immutable_audit_bytes')
    runpy.run_path(str(audit),run_name='__main__')

if __name__=='__main__':main()
