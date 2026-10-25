"""Portable rebuild registration checks; no compiler or native simulation."""
import hashlib
import importlib.machinery
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from scripts.eval import rebuild_g31_research as rebuild


def test_mock_rebuild_creates_fresh_parent_and_preserves_frozen_contracts(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "ROOT", tmp_path)
    # Keep the synthetic tree below Windows MAX_PATH even under long CI temp roots.
    monkeypatch.setattr(rebuild, "CANDIDATE", Path("candidate011"))
    candidate = tmp_path / rebuild.CANDIDATE
    (candidate / "source").mkdir(parents=True)
    (candidate / "source/core.cpp").write_bytes(b"immutable test-only source")
    (candidate / "source/CMakeLists.txt").write_bytes(b"test-only cmake")
    templates = candidate / "registered_contracts_011"
    templates.mkdir()
    originals = {}
    for label, end in (("original_window", 98259), ("drain200000", 200000)):
        contract = dict(native_source=dict(path="old/core.cpp", sha256=rebuild.digest(candidate / "source/core.cpp")),
                        default_binary=dict(path="old/native.pyd", sha256="historical"),
                        end_time=end, candidate_id="frozen011", unchanged=dict(controls="same"))
        path = templates / ("physical_contract_" + label + ".json")
        path.write_text(json.dumps(contract), encoding="utf-8")
        originals[path] = path.read_bytes()
    monkeypatch.setitem(sys.modules, "pybind11", SimpleNamespace(get_cmake_dir=lambda: "toolchain/pybind11"))
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if "--build" in command:
            output = Path(command[command.index("--build") + 1]) / "python"
            output.mkdir()
            (output / ("g31_nowait" + importlib.machinery.EXTENSION_SUFFIXES[0])).write_bytes(b"test-only binary")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(rebuild.subprocess, "run", fake_run)
    assert not (tmp_path / "build").exists()
    receipt = rebuild.rebuild("portable_test", generator="Ninja")
    assert receipt["status"] == "complete" and len(commands) == 2
    assert commands[0][-2:] == ["-G", "Ninja"]
    assert not receipt["frozen_source_and_contracts_modified"]
    for path, original_bytes in originals.items():
        assert path.read_bytes() == original_bytes
        label = "drain200000" if "drain" in path.name else "original_window"
        new_path = tmp_path / receipt["registered_contracts"][label]["path"]
        new = json.loads(new_path.read_text(encoding="utf-8"))
        old = json.loads(original_bytes)
        assert {k:v for k,v in new.items() if k not in ("native_source", "default_binary")} == {
            k:v for k,v in old.items() if k not in ("native_source", "default_binary")}
        for key in ("native_source", "default_binary"):
            data = (tmp_path / new[key]["path"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == new[key]["sha256"]
