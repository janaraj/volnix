"""Condition evaluator for policy rules.

Uses Python's ``ast`` module for safe expression evaluation.
Supports: dot access (input.amount), comparisons (>, <, ==, !=),
logical operators (and, or, not), literals (strings, numbers, bools),
and containment (in, not in).

NO arbitrary code execution. NO imports. NO function calls.
"""

from __future__ import annotations

import ast
import logging
from typing import Any

logger = logging.getLogger(__name__)

# AST node types that are NEVER allowed in condition expressions.
_UNSAFE_NODES = (
    ast.Call,
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Delete,
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.If,
    ast.With,
    ast.AsyncWith,
    ast.Raise,
    ast.Try,
    ast.Global,
    ast.Nonlocal,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
    ast.FormattedValue,
    ast.JoinedStr,
    ast.Starred,
)


class ConditionEvaluator:
    """Evaluates policy condition expressions against a context dict.

    The evaluator parses condition strings into a Python AST, validates
    that only safe operations are present, and evaluates the expression
    recursively against a provided context dictionary.
    """

    def evaluate(self, condition: str, context: dict[str, Any]) -> bool:
        """Evaluate a condition string against the given context.

        Args:
            condition: A simple boolean expression string.
            context: Variable bindings available to the expression.

        Returns:
            ``True`` if the condition is satisfied, ``False`` otherwise.
            Empty/blank conditions return ``True`` (always match).
            Malformed or unsafe expressions return ``False`` (safe failure).
        """
        if not condition or not condition.strip():
            return True

        try:
            tree = ast.parse(condition, mode="eval")
            self._validate_ast(tree)
            return bool(self._eval_node(tree.body, context))
        except Exception:
            logger.debug("Condition evaluation failed for: %s", condition, exc_info=True)
            return False

    def _validate_ast(self, tree: ast.AST) -> None:
        """Reject unsafe AST nodes (calls, imports, assignments, etc.)."""
        for node in ast.walk(tree):
            if isinstance(node, _UNSAFE_NODES):
                raise ValueError(f"Unsafe expression node: {type(node).__name__}")

    def _eval_node(self, node: ast.AST, context: dict[str, Any]) -> Any:
        """Recursively evaluate an AST node against the context."""
        if isinstance(node, ast.Expression):
            return self._eval_node(node.body, context)

        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            return context.get(node.id)

        if isinstance(node, ast.Attribute):
            value = self._eval_node(node.value, context)
            if isinstance(value, dict):
                return value.get(node.attr)
            if value is not None:
                return getattr(value, node.attr, None)
            return None

        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, context)
                if not self._compare(op, left, right):
                    return False
                left = right
            return True

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(self._eval_node(v, context) for v in node.values)
            if isinstance(node.op, ast.Or):
                return any(self._eval_node(v, context) for v in node.values)

        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, context)
            if isinstance(node.op, ast.Not):
                return not operand
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand

        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, context)
            right = self._eval_node(node.right, context)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right

        if isinstance(node, ast.List):
            return [self._eval_node(e, context) for e in node.elts]

        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(e, context) for e in node.elts)

        if isinstance(node, ast.Subscript):
            value = self._eval_node(node.value, context)
            sl = self._eval_node(node.slice, context)
            if isinstance(value, (dict, list, tuple)):
                return value[sl]
            return None

        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    @staticmethod
    def _compare(op: ast.cmpop, left: Any, right: Any) -> bool:
        """Evaluate a single comparison operation."""
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.In):
            return left in right
        if isinstance(op, ast.NotIn):
            return left not in right
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right
        raise ValueError(f"Unsupported comparison operator: {type(op).__name__}")
