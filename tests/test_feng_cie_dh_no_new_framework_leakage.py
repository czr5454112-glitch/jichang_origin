from __future__ import annotations

import ast
from pathlib import Path
import re

from scripts.eval import run_feng_paper_env_cie_dh as runner


ROOT = Path(__file__).resolve().parents[1]
JAVA_ROOT = ROOT / "benchmarks" / "java" / "feng_cie_dh" / "App"


PROHIBITED_EXECUTABLE_IDENTIFIERS = (
    "czr005_cpp",
    "g4irsf31_map_adapter",
    "H_SA",
    "scheduled_incoming",
    "service_calendar",
    "J2",
    "M3",
    "R3",
    "E2",
    "P2",
    "surviving_graph",
)


def _strip_java_comments_and_literals(source: str) -> str:
    """Keep executable tokens while removing comments and literal payloads."""

    output: list[str] = []
    index = 0
    state = "code"
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char == "/" and following == "/":
                output.extend("  ")
                index += 2
                state = "line_comment"
            elif char == "/" and following == "*":
                output.extend("  ")
                index += 2
                state = "block_comment"
            elif char == '"':
                output.append(" ")
                index += 1
                state = "string"
            elif char == "'":
                output.append(" ")
                index += 1
                state = "character"
            else:
                output.append(char)
                index += 1
            continue
        if state == "line_comment":
            output.append("\n" if char == "\n" else " ")
            index += 1
            if char == "\n":
                state = "code"
            continue
        if state == "block_comment":
            if char == "*" and following == "/":
                output.extend("  ")
                index += 2
                state = "code"
            else:
                output.append("\n" if char == "\n" else " ")
                index += 1
            continue
        if char == "\\" and following:
            output.extend("  ")
            index += 2
        elif (state == "string" and char == '"') or (
            state == "character" and char == "'"
        ):
            output.append(" ")
            index += 1
            state = "code"
        else:
            output.append("\n" if char == "\n" else " ")
            index += 1
    return "".join(output)


def test_java_reconstruction_has_no_current_framework_dependency() -> None:
    sources = runner.java_sources(JAVA_ROOT)
    assert len(sources) >= 5
    for path in sources:
        code = _strip_java_comments_and_literals(path.read_text(encoding="utf-8"))
        for token in PROHIBITED_EXECUTABLE_IDENTIFIERS:
            assert re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", code) is None, (
                f"current-framework identifier {token!r} leaked into {path}"
            )
        imports = re.findall(r"(?m)^\s*import\s+([^;]+);", code)
        assert all(name.startswith("java.") for name in imports), (
            f"non-JDK import in independent Feng reconstruction {path}: {imports}"
        )


def test_python_runner_is_orchestration_only() -> None:
    source_path = ROOT / "scripts" / "eval" / "run_feng_paper_env_cie_dh.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert not any(name.startswith("czr005_cpp") for name in imports)
    assert not any("g4irsf31" in name for name in imports)


def test_compile_command_does_not_compile_or_mutate_legacy_sources(tmp_path: Path) -> None:
    command = runner.compile_command(javac="javac", classes_dir=tmp_path / "classes")
    java_arguments = [Path(value) for value in command if value.endswith(".java")]
    assert java_arguments
    assert all(JAVA_ROOT.resolve() in path.resolve().parents for path in java_arguments)
    assert all("legacy/jichang_origin_readonly" not in path.as_posix() for path in java_arguments)


def test_manifest_keeps_source_exact_and_reconstruction_status_separate() -> None:
    manifest = runner._load_manifest()
    identity = manifest["identity"]
    exact = identity["exact_source_reproduction"]
    reconstruction = identity["paper_environment_reconstruction"]
    assert exact["status"] == "SOURCE_NOT_RECOVERED"
    assert exact["may_stop_exact_source_track"] is True
    assert reconstruction["required"] is True
    assert reconstruction["missing_source_is_not_a_stop_condition"] is True
    assert reconstruction["completion_requires_executable_baseline"] is True
    assert manifest["paper_environment"]["legacy_mirror_mutation_allowed"] is False
