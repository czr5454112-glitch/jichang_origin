"""Lossless archive codec probe, independent of policy/native simulations."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.source.read_bytes()
    payload = gzip.decompress(source)
    digest = hashlib.sha256(payload).hexdigest()
    rows = []
    # Two opposite orders expose order/load effects without selecting a winner.
    for trial, level in enumerate((9, 1, 1, 9)):
        wall, cpu = time.perf_counter(), time.process_time()
        encoded = gzip.compress(payload, compresslevel=level, mtime=0)
        cpu, wall = time.process_time()-cpu, time.perf_counter()-wall
        restored = gzip.decompress(encoded)
        exact = restored == payload
        name = f"trial_{trial:02d}_level_{level}.json.gz"
        (args.output/name).write_bytes(encoded)
        rows.append({"trial": trial, "level": level, "wall_seconds": wall,
            "cpu_seconds": cpu, "encoded_bytes": len(encoded), "decoded_bytes_exact": exact,
            "file": name, "sha256": hashlib.sha256(encoded).hexdigest()})
    report = {"schema": "g31.lossless_shard_codec_probe.v1", "status": "passed" if all(r["decoded_bytes_exact"] for r in rows) else "failed",
        "source": str(args.source), "source_sha256": hashlib.sha256(source).hexdigest(),
        "decoded_sha256": digest, "decoded_bytes": len(payload), "rows": rows,
        "native_executed": False, "source_unchanged": args.source.read_bytes() == source,
        "scope": "Concurrent research codec comparison only. Byte-for-byte identical decompression; no physical/control/request timing changes or speed certificate inferred."}
    (args.output/"receipt.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report))
    return int(report["status"] != "passed" or not report["source_unchanged"])


if __name__ == "__main__":
    raise SystemExit(main())
