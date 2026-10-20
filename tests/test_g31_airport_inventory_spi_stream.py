import gzip
import json

import pytest

from scripts.experiments.g31_ics_circulation.foundation_airport_inventory_spi_campaign import JsonArrayStream, write_gzip_json


def test_full_state_encoder_preserves_exact_json_bytes_without_whole_state_dumps(tmp_path, monkeypatch):
    value = {"history": [{"中文": (i, 1.25, None, True), "ack": {"stock": [0, 1]}} for i in range(20)]}
    expected = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    original = json.dumps
    def bounded_dumps(item, *args, **kwargs):
        assert item is not value
        return original(item, *args, **kwargs)
    monkeypatch.setattr(json, "dumps", bounded_dumps)
    path = tmp_path / "state.json.gz"
    write_gzip_json(path, value)
    assert gzip.decompress(path.read_bytes()) == expected
    with pytest.raises(FileExistsError):
        write_gzip_json(path, value)


def test_full_state_encoder_keeps_nonfinite_validation(tmp_path):
    with pytest.raises(ValueError):
        write_gzip_json(tmp_path / "invalid.json.gz", {"value": float("nan")})


def test_stream_keeps_a_valid_prefix_on_failed_record_without_retaining_history(tmp_path):
    path = tmp_path / "control.json.gz"
    writer = JsonArrayStream(path)
    writer.extend({"tick": i, "queue": ["bag"] * 1000} for i in range(3))
    with pytest.raises(ValueError):
        writer.extend([{"tick": 4, "invalid": float("nan")}])
    writer.close()
    writer.close()
    with gzip.open(path, "rt") as stream:
        rows = json.load(stream)
    assert [r["tick"] for r in rows] == [0, 1, 2]
    assert writer.count == 3
    assert not any(isinstance(value, (list, dict)) for value in vars(writer).values())
    with pytest.raises(ValueError, match="closed_evidence_stream"):
        writer.extend([])
