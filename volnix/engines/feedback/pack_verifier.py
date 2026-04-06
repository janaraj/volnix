"""Pack verifier -- validates a Tier 1 pack for correctness.

Runs structural and semantic checks against a pack directory to
determine whether it meets the requirements for a verified pack.
All checks use AST analysis — no runtime imports (avoids side effects).
"""
from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path

from volnix.engines.feedback.models import (
    VerificationCheck,
    VerificationResult,
)

logger = logging.getLogger(__name__)

_REQUIRED_FILES = ("pack.py", "schemas.py", "handlers.py", "state_machines.py")


def _get_all_assignments(tree: ast.Module) -> list[str]:
    """Extract top-level variable names from AST.

    M5 fix: Only checks module-level statements (``tree.body``),
    not nested assignments inside functions or classes.
    Handles both ``x = ...`` and ``x: type = ...``.
    """
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                names.append(node.target.id)
    return names


class PackVerifier:
    """Validates a Tier 1 pack directory for completeness."""

    async def verify(self, pack_dir: str | Path) -> VerificationResult:
        """Run all verification checks on *pack_dir*.

        H4 fix: file I/O wrapped with asyncio.to_thread().
        """
        return await asyncio.to_thread(self._verify_sync, pack_dir)

    def _verify_sync(self, pack_dir: str | Path) -> VerificationResult:
        """Sync implementation of all verification checks.

        Checks:
        1. Structure — required files exist
        2. Importable — pack.py has a class definition
        3. Tools — schemas.py defines TOOL_DEFINITIONS
        4. Entities — schemas.py defines entity schema constants
        5. Handlers — handlers.py has handle_* functions
        6. State machines — state_machines.py defines TRANSITIONS
        7. No stubs — handlers don't contain NotImplementedError (warning)
        """
        pack_path = Path(pack_dir)
        service_name = pack_path.name
        checks: list[VerificationCheck] = []
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Structure
        check = self._check_structure(pack_path)
        checks.append(check)
        if not check.passed:
            errors.append(check.message)
            return VerificationResult(
                service_name=service_name,
                passed=False,
                checks=checks,
                errors=errors,
                warnings=warnings,
            )

        # 2. Importable (AST check)
        check = self._check_importable(pack_path)
        checks.append(check)
        if not check.passed:
            errors.append(check.message)

        # 3. Tools (M4 fix: real AST check)
        check = self._check_tools(pack_path)
        checks.append(check)
        if not check.passed:
            errors.append(check.message)

        # 4. Entities (M4 fix: real AST check)
        check = self._check_entities(pack_path)
        checks.append(check)
        if not check.passed:
            errors.append(check.message)

        # 5. Handlers
        check = self._check_handlers(pack_path)
        checks.append(check)
        if not check.passed:
            errors.append(check.message)

        # 6. State machines (M4 fix: real AST check)
        check = self._check_state_machines(pack_path)
        checks.append(check)
        if not check.passed:
            errors.append(check.message)

        # 7. No stubs (M12 fix: AST-based detection)
        check = self._check_no_stubs(pack_path)
        checks.append(check)
        if not check.passed:
            warnings.append(check.message)

        passed = len(errors) == 0
        return VerificationResult(
            service_name=service_name,
            passed=passed,
            checks=checks,
            errors=errors,
            warnings=warnings,
        )

    # -- Individual checks -----------------------------------------------------

    @staticmethod
    def _check_structure(pack_path: Path) -> VerificationCheck:
        """Check that all required files exist."""
        missing = [
            f for f in _REQUIRED_FILES if not (pack_path / f).exists()
        ]
        if missing:
            return VerificationCheck(
                name="structure",
                passed=False,
                message=f"Missing files: {', '.join(missing)}",
            )
        return VerificationCheck(
            name="structure",
            passed=True,
            message="All required files present",
        )

    @staticmethod
    def _check_importable(pack_path: Path) -> VerificationCheck:
        """Check that pack.py defines a class (AST check)."""
        pack_py = pack_path / "pack.py"
        try:
            tree = ast.parse(pack_py.read_text())
            classes = [
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
            ]
            if not classes:
                return VerificationCheck(
                    name="importable",
                    passed=False,
                    message="No class found in pack.py",
                )
            return VerificationCheck(
                name="importable",
                passed=True,
                message=f"Found class(es): {', '.join(classes)}",
            )
        except SyntaxError as exc:
            return VerificationCheck(
                name="importable",
                passed=False,
                message=f"Syntax error in pack.py: {exc}",
            )

    @staticmethod
    def _check_tools(pack_path: Path) -> VerificationCheck:
        """Check that schemas.py defines tool definitions.

        Looks for any variable ending with ``TOOL_DEFINITIONS`` or
        ``_TOOLS`` (handles both generated and hand-written packs).
        """
        schemas_py = pack_path / "schemas.py"
        if not schemas_py.exists():
            return VerificationCheck(
                name="tools",
                passed=False,
                message="schemas.py not found",
            )
        try:
            tree = ast.parse(schemas_py.read_text())
            assignments = _get_all_assignments(tree)
            tool_vars = [
                a for a in assignments
                if "TOOL_DEFINITION" in a.upper()
            ]
            if not tool_vars:
                return VerificationCheck(
                    name="tools",
                    passed=False,
                    message="No tool definitions found in schemas.py",
                )
            return VerificationCheck(
                name="tools",
                passed=True,
                message=f"Tool definitions: {', '.join(tool_vars)}",
            )
        except SyntaxError as exc:
            return VerificationCheck(
                name="tools",
                passed=False,
                message=f"Syntax error in schemas.py: {exc}",
            )

    @staticmethod
    def _check_entities(pack_path: Path) -> VerificationCheck:
        """Check that schemas.py defines *_ENTITY_SCHEMA constants."""
        schemas_py = pack_path / "schemas.py"
        if not schemas_py.exists():
            return VerificationCheck(
                name="entities",
                passed=False,
                message="schemas.py not found",
            )
        try:
            tree = ast.parse(schemas_py.read_text())
            all_names = _get_all_assignments(tree)
            schema_vars = [
                a for a in all_names if a.endswith("_ENTITY_SCHEMA")
            ]
            if not schema_vars:
                return VerificationCheck(
                    name="entities",
                    passed=False,
                    message="No *_ENTITY_SCHEMA constants in schemas.py",
                )
            return VerificationCheck(
                name="entities",
                passed=True,
                message=(
                    f"{len(schema_vars)} entity schema(s): "
                    f"{', '.join(schema_vars[:5])}"
                ),
            )
        except SyntaxError as exc:
            return VerificationCheck(
                name="entities",
                passed=False,
                message=f"Syntax error in schemas.py: {exc}",
            )

    @staticmethod
    def _check_handlers(pack_path: Path) -> VerificationCheck:
        """Check that handlers.py defines async handler functions."""
        handlers_py = pack_path / "handlers.py"
        if not handlers_py.exists():
            return VerificationCheck(
                name="handlers",
                passed=False,
                message="handlers.py not found",
            )
        try:
            tree = ast.parse(handlers_py.read_text())
            handler_funcs = [
                node.name
                for node in ast.walk(tree)
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                )
                and node.name.startswith("handle_")
            ]
            if not handler_funcs:
                return VerificationCheck(
                    name="handlers",
                    passed=False,
                    message="No handle_* functions in handlers.py",
                )
            return VerificationCheck(
                name="handlers",
                passed=True,
                message=(
                    f"{len(handler_funcs)} handler(s): "
                    f"{', '.join(handler_funcs[:5])}"
                ),
            )
        except SyntaxError as exc:
            return VerificationCheck(
                name="handlers",
                passed=False,
                message=f"Syntax error in handlers.py: {exc}",
            )

    @staticmethod
    def _check_state_machines(pack_path: Path) -> VerificationCheck:
        """Check that state_machines.py defines transition mappings.

        Looks for any variable containing ``TRANSITION`` (handles
        both ``TRANSITIONS`` and ``EMAIL_TRANSITIONS`` etc.).
        """
        sm_py = pack_path / "state_machines.py"
        if not sm_py.exists():
            return VerificationCheck(
                name="state_machines",
                passed=False,
                message="state_machines.py not found",
            )
        try:
            tree = ast.parse(sm_py.read_text())
            all_names = _get_all_assignments(tree)
            sm_vars = [
                a for a in all_names if "TRANSITION" in a.upper()
            ]
            if not sm_vars:
                return VerificationCheck(
                    name="state_machines",
                    passed=False,
                    message="No transition definitions in state_machines.py",
                )
            return VerificationCheck(
                name="state_machines",
                passed=True,
                message=f"Transitions: {', '.join(sm_vars)}",
            )
        except SyntaxError as exc:
            return VerificationCheck(
                name="state_machines",
                passed=False,
                message=f"Syntax error in state_machines.py: {exc}",
            )

    @staticmethod
    def _check_no_stubs(pack_path: Path) -> VerificationCheck:
        """Check handlers don't contain NotImplementedError (AST-based).

        M12 fix: uses AST to detect ``raise NotImplementedError`` and
        ``Expr(Constant(Ellipsis))`` instead of string matching.
        """
        handlers_py = pack_path / "handlers.py"
        if not handlers_py.exists():
            return VerificationCheck(
                name="no_stubs",
                passed=True,
                message="No handlers to check",
            )

        try:
            tree = ast.parse(handlers_py.read_text())
        except SyntaxError:
            return VerificationCheck(
                name="no_stubs",
                passed=True,
                message="Cannot parse handlers.py",
            )

        not_impl_count = 0
        ellipsis_count = 0

        for node in ast.walk(tree):
            # raise NotImplementedError(...)
            if isinstance(node, ast.Raise) and node.exc is not None:
                if isinstance(node.exc, ast.Call):
                    func = node.exc.func
                    if (
                        isinstance(func, ast.Name)
                        and func.id == "NotImplementedError"
                    ):
                        not_impl_count += 1
            # Bare ellipsis (... as function body)
            if isinstance(node, ast.Expr) and isinstance(
                node.value, ast.Constant
            ):
                if node.value.value is ...:
                    ellipsis_count += 1

        if not_impl_count > 0 or ellipsis_count > 0:
            return VerificationCheck(
                name="no_stubs",
                passed=False,
                message=(
                    f"{not_impl_count} NotImplementedError + "
                    f"{ellipsis_count} ellipsis stubs"
                ),
            )
        return VerificationCheck(
            name="no_stubs",
            passed=True,
            message="No stubs found in handlers",
        )
