"""One new Python process per invocation; preserve actual extension identities."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-rejection", action="store_true")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("_identity_probe_host", args.source)
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    report = dict(schema="g31.native_identity_probe.v1", source=str(args.source.resolve()),
                  source_sha256=sha(args.source), requested=[], result="running")
    modules = []
    for requested in (args.first, args.second):
        if requested is None:
            continue
        requested = requested.resolve(strict=True)
        row = dict(requested=str(requested), requested_sha256=sha(requested))
        try:
            module = host.load_native(requested)
            actual = Path(module.__file__).resolve(strict=True)
            row.update(actual=str(actual), actual_sha256=sha(actual),
                       path_matches=actual == requested, content_matches=sha(actual) == sha(requested),
                       has_owner_notifications=hasattr(module.NativeSession, "owner_notifications"),
                       same_native_class_as_first=bool(modules and module.NativeSession is modules[0].NativeSession))
            modules.append(module)
            # Exercise real native physics and the known version-sensitive
            # forecast boundary, not merely a filename or module attribute.
            data = host.tiny_cycle()
            data["jobs"] = [data["jobs"][0]]
            data["jobs"][0]["load_seconds"] = 0.
            data["transfers"] = []
            data["node_records"] = [(n,k,2. if n==0 else t,x,y,e) for n,k,t,x,y,e in data["node_records"]]
            next(n for n in data["node_contracts"] if n["node"] == 1)["resource_owner"] = "B"
            data["owner_protocol"] = dict(enabled=True, timeout=5., ack_delay=.2)
            data = host.prepare_input(data)
            session = module.NativeSession(data)
            session.advance_to(0.)
            request = dict(request_id="live:1:A:identity", owner_id="A", kind="service_forecast", target_owner="B",
                           tray_id="T0", next=1, message_delay=2., publication_delay=.5)
            session.submit_protocol_command(request)
            session.advance_to(2.8)
            ack = session.protocol_command("A", request["request_id"])["last_delivered_ack"]
            message = next(m for m in session.observe_protocol("B")["delivered_messages"] if m["message_id"] == ack["result_id"])
            row["real_forecast_entry_estimate"] = message["entry_estimate"]
            row["raw"] = dict(input=data, request=request, ack=ack, delivered_message=message, result=session.result_at(4.))
        except Exception as exc:
            row.update(exception_type=type(exc).__name__, exception=str(exc))
        report["requested"].append(row)
    second = report["requested"][-1]
    if args.expect_rejection:
        passed = bool(second.get("exception")) and len(report["requested"]) == 2 and "exception" not in report["requested"][0]
    else:
        passed = all(row.get("path_matches") and row.get("content_matches") for row in report["requested"])
    report["result"] = "passed" if passed else "failed"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({**{k:v for k,v in report.items() if k!="requested"}, "requested":[{k:v for k,v in r.items() if k!="raw"} for r in report["requested"]]}))
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
