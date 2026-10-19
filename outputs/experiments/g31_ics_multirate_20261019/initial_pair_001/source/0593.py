"""Derive reviewable same-tray event rows from saved native receipts."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from .original_workload import digest, write_json


def summarize(folder: Path) -> dict:
    data = json.loads((folder / "input.json").read_text(encoding="utf-8"))
    jobs = {job["business_bag_id"]: job for job in data["jobs"]}
    result = {"schema": "g31.original_actual_event_table.v1", "source_hashes": {},
              "time_unit": "seconds on original source simulation clock",
              "scope": "same-source mechanism witness; full-flow negative is separate", "policies": {}}
    for policy in ("reactive", "predictive"):
        path = folder / f"{policy}_raw.json.gz"
        result["source_hashes"][path.name] = digest(path)
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            run = json.load(stream)
        events = run["result"]["receipts"]
        rows = []
        for load in (event for event in events if event["event"] == "LOAD_START"):
            bag, tray, start = load["business_bag_id"], load["tray_id"], load["time"]
            relevant = [event for event in events if event["business_bag_id"] == bag
                        and event["tray_id"] == tray]
            times = {name: next((event["time"] for event in relevant if event["event"] == name), None)
                     for name in ("STORAGE_ENTER", "STORAGE_RELEASE", "UNLOAD_COMPLETE", "HOLD_COMPLETE")}
            incoming = [event for event in events if event["event"] == "EMPTY_RECEIVED"
                        and event["tray_id"] == tray and event["time"] <= start + 1e-8]
            received = incoming[-1] if incoming else None
            exported = next((event for event in events if event["event"] == "EXPORT_GRANTED"
                             and received and event["reason"] == received["reason"]), None)
            rows.append({"sequence": len(rows) + 1, "business_bag_id": bag, "tray_id": tray,
                         "source_arrival": jobs[bag]["arrival"], "source_deadline": jobs[bag]["deadline"],
                         "origin": jobs[bag]["origin"], "destination": jobs[bag]["destination"],
                         "preceding_export_at": exported["time"] if exported else None,
                         "preceding_empty_received_at": received["time"] if received else None,
                         "preceding_return_transport_leg_id": received["transport_leg_id"] if received else None,
                         "load_at": start, **{name.lower() + "_at": value for name, value in times.items()},
                         "on_time": times["UNLOAD_COMPLETE"] is not None and
                                    times["UNLOAD_COMPLETE"] <= jobs[bag]["deadline"] + 1e-8})
        result["policies"][policy] = {"offered": len(jobs), "loaded": len(rows), "rows": rows,
            "completed": sum(row["unload_complete_at"] is not None for row in rows),
            "on_time": sum(row["on_time"] for row in rows),
            "empty_received": sum(event["event"] == "EMPTY_RECEIVED" for event in events)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    result = summarize(args.folder)
    write_json(args.folder / "actual_same_tray_event_table.json", result)
    text = ["# 原图同盘实际事件账", "", "时刻单位：原来源模拟时钟秒。全部数值由 native receipts 提取，完整业务身份和返程 leg ID 见同名 JSON。单盘独立机制组不能替代完整流负例。", ""]
    fmt = lambda value: "—" if value is None else f"{value:.3f}"
    for policy, summary in result["policies"].items():
        text += [f"## {policy}", "", f"{summary['completed']}/{summary['offered']} 完成，{summary['on_time']} 按时；真实返供 {summary['empty_received']} 次。托盘身份始终为 initial:26:0。", "",
                 "| 次序/源袋 | 前次导出 | 空盘实际接收 | 本次装载 | 入 Storage | 实际释放 | 实际卸载 | 截止 | 按时 |",
                 "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
        for row in summary["rows"]:
            values = [row[name] for name in ("preceding_export_at", "preceding_empty_received_at", "load_at", "storage_enter_at", "storage_release_at", "unload_complete_at", "source_deadline")]
            text.append(f"| {row['sequence']} / {row['business_bag_id']} | " + " | ".join(map(fmt, values)) + f" | {'是' if row['on_time'] else '否'} |")
        text.append("")
    (args.folder / "actual_same_tray_event_table.md").write_text("\n".join(text), encoding="utf-8")
    print(json.dumps({policy: {k: v for k, v in summary.items() if k != "rows"}
                      for policy, summary in result["policies"].items()}))


if __name__ == "__main__":
    main()
