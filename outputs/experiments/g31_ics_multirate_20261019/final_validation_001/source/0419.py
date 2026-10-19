"""Static hook census for frozen controllers, never a runtime lineage inference."""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
from pathlib import Path


EXPECTED_SUBMITS = {
    ("protocol_control.py", "_publish_services", "route"),
    ("protocol_control.py", "_publish_services", "service_forecast"),
    ("protocol_control.py", "_publish_services", "withdraw_service_forecast"),
    ("protocol_control.py", "run_protocol_control", "demand"),
    ("protocol_control.py", "run_protocol_control", "transfer"),
    ("protocol_control.py", "complete_protocol_route", "route"),
    ("event_protocol_control.py", "_publish_owner_demand", "demand"),
    ("event_protocol_control.py", "_activate_owner", "transfer"),
}
EXPECTED_SENDS = {
    ("protocol_control.py", "ProtocolClient.submit", False),
    ("protocol_control.py", "ProtocolClient.refresh", True),
}


def inspect_source(filename, source):
    """Collect calls under lexical function names without importing controllers."""
    calls = []
    class Visitor(ast.NodeVisitor):
        def __init__(self): self.stack = []
        def visit_ClassDef(self, node):
            self.stack.append(node.name); self.generic_visit(node); self.stack.pop()
        def visit_FunctionDef(self, node):
            self.stack.append(node.name); self.generic_visit(node); self.stack.pop()
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
                if name in {"submit", "_send", "submit_protocol_transfer", "submit_protocol_command"}:
                    detail = None
                    if name == "submit":
                        candidate = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "kind"), None)
                        detail = candidate.value if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str) else "unknown_dynamic_kind"
                    elif name == "_send":
                        candidate = next((k.value for k in node.keywords if k.arg == "retry"), None)
                        detail = candidate.value if isinstance(candidate, ast.Constant) and type(candidate.value) is bool else "unknown_retry_flag"
                    calls.append({"file": filename, "function": ".".join(self.stack), "line": node.lineno,
                        "call": name, "detail": detail})
            self.generic_visit(node)
    Visitor().visit(ast.parse(source, filename=filename))
    return calls


def audit_sources(sources):
    rows = [row for filename, source in sources.items() for row in inspect_source(filename, source)]
    submits = Counter((r["file"], r["function"], r["detail"]) for r in rows if r["call"] == "submit")
    sends = Counter((r["file"], r["function"], r["detail"]) for r in rows if r["call"] == "_send")
    native = Counter((r["file"], r["function"], r["call"]) for r in rows if r["call"].startswith("submit_protocol_"))
    expected_native = {("protocol_control.py", "ProtocolClient._send", name)
        for name in ("submit_protocol_transfer", "submit_protocol_command")}
    mismatches = []
    for label, actual, expected in (("submit", submits, EXPECTED_SUBMITS), ("send", sends, EXPECTED_SENDS),
                                    ("native", native, expected_native)):
        for key in set(actual) | expected:
            if actual[key] != int(key in expected):
                mismatches.append({"kind": label, "site": list(key), "actual_count": actual[key],
                    "expected_count": int(key in expected)})
    return {"schema": "g31.request_lineage_static_inventory.v1",
        "status": "known_syntactic_sites_only" if not mismatches else "unknown_unclassified_sites",
        "parsed_utf8_text_sha256": {name: hashlib.sha256(source.encode()).hexdigest() for name, source in sources.items()},
        "calls": rows, "mismatches": mismatches,
        "business_request_runtime_roots_available": False,
        "branch_contracts_implemented": False,
        "complete_lineage_certified": False,
        "scope": "Static call-site inventory only. Does not classify dynamic branches, task identities or request continuation."}


def current_inventory(directory=None):
    directory = Path(directory) if directory is not None else Path(__file__).parent
    names = ("protocol_control.py", "event_protocol_control.py")
    report = audit_sources({name: (directory/name).read_text(encoding="utf-8") for name in names})
    report["source_sha256"] = {name: hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in names}
    return report
