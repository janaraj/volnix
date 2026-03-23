"""Helpers for architecture and contract guard tests."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_ROOT = REPO_ROOT / "terrarium"
TEST_ROOT = REPO_ROOT / "tests"


def iter_python_files(root: Path) -> list[Path]:
    """Return all Python source files beneath *root*."""
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def rel_repo_path(path: Path) -> str:
    """Return a repository-relative POSIX path."""
    return path.relative_to(REPO_ROOT).as_posix()


def parse_module(path: Path) -> ast.AST:
    """Parse a Python source file into an AST."""
    return ast.parse(path.read_text(), filename=str(path))


def dotted_name(node: ast.AST) -> str | None:
    """Return the dotted name represented by *node*, if any."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        if base is None:
            return None
        return f"{base}.{node.attr}"
    return None


def find_call_offenders(
    root: Path,
    targets: set[str],
    include: Iterable[str] | None = None,
) -> dict[str, list[int]]:
    """Return repo-relative call sites that invoke any dotted target name."""
    include_set = set(include or [])
    offenders: dict[str, list[int]] = {}

    for path in iter_python_files(root):
        rel_path = rel_repo_path(path)
        if include_set and rel_path not in include_set:
            continue
        lines: list[int] = []
        for node in ast.walk(parse_module(path)):
            if not isinstance(node, ast.Call):
                continue
            name = dotted_name(node.func)
            if name in targets:
                lines.append(node.lineno)
        if lines:
            offenders[rel_path] = lines
    return offenders


def imported_modules(path: Path) -> set[str]:
    """Return all imported module names in *path*."""
    modules: set[str] = set()
    for node in ast.walk(parse_module(path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def find_import_offenders(
    root: Path,
    predicate,
    include: Iterable[str] | None = None,
) -> dict[str, list[str]]:
    """Return repo-relative files whose imports satisfy *predicate*."""
    include_set = set(include or [])
    offenders: dict[str, list[str]] = {}

    for path in iter_python_files(root):
        rel_path = rel_repo_path(path)
        if include_set and rel_path not in include_set:
            continue
        matches = sorted(module for module in imported_modules(path) if predicate(module))
        if matches:
            offenders[rel_path] = matches
    return offenders


def find_attribute_call_offenders(paths: Iterable[Path], attrs: set[str]) -> dict[str, list[int]]:
    """Return repo-relative files that call attribute names in *attrs*."""
    offenders: dict[str, list[int]] = {}

    for path in paths:
        lines: list[int] = []
        for node in ast.walk(parse_module(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in attrs:
                    lines.append(node.lineno)
        if lines:
            offenders[rel_repo_path(path)] = lines
    return offenders


def find_placeholder_tests(root: Path) -> dict[str, list[str]]:
    """Return test functions whose body is only ``...`` or ``pass``."""
    offenders: dict[str, list[str]] = {}

    for path in iter_python_files(root):
        placeholders: list[str] = []
        for node in ast.walk(parse_module(path)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_") or len(node.body) != 1:
                continue
            stmt = node.body[0]
            if isinstance(stmt, ast.Pass):
                placeholders.append(node.name)
                continue
            if (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and stmt.value.value is Ellipsis
            ):
                placeholders.append(node.name)
        if placeholders:
            offenders[rel_repo_path(path)] = placeholders
    return offenders


def _method_object(obj: Any, method_name: str) -> Any:
    """Resolve an unbound method or function from a class-like object."""
    return inspect.getattr_static(obj, method_name)


def _normalized_signature(method: Any) -> tuple[bool, list[tuple[str, inspect._ParameterKind]]]:
    """Return coroutine-ness and simplified parameter metadata."""
    params = list(inspect.signature(method).parameters.values())
    if params and params[0].name == "self":
        params = params[1:]
    simplified = [
        (param.name, param.kind)
        for param in params
    ]
    return inspect.iscoroutinefunction(method), simplified


def assert_method_signature_matches_protocol(
    implementation: Any,
    protocol: Any,
    method_names: Iterable[str],
) -> None:
    """Assert that *implementation* methods match the protocol signatures."""
    for method_name in method_names:
        impl_method = _method_object(implementation, method_name)
        proto_method = _method_object(protocol, method_name)
        impl_signature = _normalized_signature(impl_method)
        proto_signature = _normalized_signature(proto_method)
        assert impl_signature == proto_signature, (
            f"{implementation.__name__}.{method_name} signature {impl_signature} "
            f"!= {protocol.__name__}.{method_name} signature {proto_signature}"
        )
