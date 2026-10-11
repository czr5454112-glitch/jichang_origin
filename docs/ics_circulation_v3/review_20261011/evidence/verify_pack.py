"""Verify the compact copies and full inventory without loading archives/pickle."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re


BASE = Path(__file__).resolve().parent


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            result.update(block)
    return result.hexdigest()


def main():
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    selected = {x["original_path"].removeprefix("outputs/experiments/ics_circulation_v3/"): x for x in manifest["selected"]}
    assert len(selected) == manifest["selected_file_count"]
    count, size, selected_count, selected_size = 0, 0, 0, 0
    seen = set()
    for item in manifest["inventory"]:
        path = BASE / item["path"]
        assert path.stat().st_size == item["bytes"]
        assert sha(path) == item["sha256"]
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                key = row["original_relative_path"]
                assert key not in seen, key
                seen.add(key)
                assert row["local_availability"] == "present_at_packaging"
                assert re.fullmatch("[0-9a-f]{64}", row["sha256"])
                count += 1
                size += int(row["bytes"])
                if row["publication_status"].startswith("selected_"):
                    item = selected[key]
                    assert item["bytes"] == int(row["bytes"])
                    assert item["sha256"] == row["sha256"]
                    assert item["reason"] == row["publication_status"]
                    copied = BASE / item["path"]
                    assert copied.stat().st_size == item["bytes"]
                    assert sha(copied) == item["sha256"]
                    selected_count += 1
                    selected_size += item["bytes"]
    assert count == manifest["file_count"]
    assert size == manifest["original_bytes"]
    assert selected_count == manifest["selected_file_count"]
    assert selected_size == manifest["selected_bytes"]
    assert count - selected_count == manifest["omitted_file_count"]
    assert size - selected_size == manifest["omitted_bytes"]
    actual_copies = {x.relative_to(BASE).as_posix() for x in (BASE / "receipts").rglob("*") if x.is_file()}
    assert actual_copies == {x["path"] for x in manifest["selected"]}
    assert not any(Path(x).suffix in {".pickle", ".pkl", ".pyc"} for x in actual_copies)
    links = re.findall(r"\]\(([^)]+)\)", (BASE / "README.md").read_text(encoding="utf-8"))
    local_links = [x for x in links if not x.startswith(("http:", "https:"))]
    missing = [x for x in local_links if not (BASE / x).exists()]
    assert not missing, missing
    print(json.dumps({"status": "passed", "inventory_files": count, "inventory_bytes": size,
                      "copied_files": selected_count, "copied_bytes": selected_size,
                      "readme_local_links": len(local_links), "missing_links": missing,
                      "pickle_loaded": False, "physical_runs": 0}, indent=2))


if __name__ == "__main__":
    main()
