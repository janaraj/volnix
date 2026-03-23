"""Tests for the ConditionEvaluator — safe expression evaluation."""
import pytest

from terrarium.engines.policy.evaluator import ConditionEvaluator


@pytest.fixture
def evaluator():
    return ConditionEvaluator()


class TestBasicEvaluation:
    """Test basic condition evaluation scenarios."""

    def test_empty_condition_returns_true(self, evaluator):
        assert evaluator.evaluate("", {}) is True

    def test_whitespace_condition_returns_true(self, evaluator):
        assert evaluator.evaluate("   ", {}) is True

    def test_none_condition_returns_true(self, evaluator):
        assert evaluator.evaluate(None, {}) is True

    def test_constant_true(self, evaluator):
        assert evaluator.evaluate("True", {}) is True

    def test_constant_false(self, evaluator):
        assert evaluator.evaluate("False", {}) is False

    def test_numeric_constant(self, evaluator):
        assert evaluator.evaluate("42", {}) is True
        assert evaluator.evaluate("0", {}) is False


class TestComparisons:
    """Test comparison operators."""

    def test_greater_than_true(self, evaluator):
        ctx = {"input": {"amount": 10000}}
        assert evaluator.evaluate("input.amount > 5000", ctx) is True

    def test_greater_than_false(self, evaluator):
        ctx = {"input": {"amount": 3000}}
        assert evaluator.evaluate("input.amount > 5000", ctx) is False

    def test_less_than(self, evaluator):
        ctx = {"input": {"amount": 100}}
        assert evaluator.evaluate("input.amount < 500", ctx) is True

    def test_greater_equal(self, evaluator):
        ctx = {"input": {"amount": 5000}}
        assert evaluator.evaluate("input.amount >= 5000", ctx) is True

    def test_less_equal(self, evaluator):
        ctx = {"input": {"amount": 5000}}
        assert evaluator.evaluate("input.amount <= 5000", ctx) is True

    def test_equal(self, evaluator):
        ctx = {"actor": {"role": "supervisor"}}
        assert evaluator.evaluate('actor.role == "supervisor"', ctx) is True

    def test_not_equal(self, evaluator):
        ctx = {"actor": {"role": "agent"}}
        assert evaluator.evaluate('actor.role != "supervisor"', ctx) is True

    def test_string_equality_false(self, evaluator):
        ctx = {"actor": {"role": "agent"}}
        assert evaluator.evaluate('actor.role == "supervisor"', ctx) is False

    def test_action_name_comparison(self, evaluator):
        ctx = {"action": "email_send"}
        assert evaluator.evaluate('action == "email_send"', ctx) is True

    def test_action_name_mismatch(self, evaluator):
        ctx = {"action": "email_send"}
        assert evaluator.evaluate('action == "payment_create"', ctx) is False

    def test_chained_comparison(self, evaluator):
        ctx = {"input": {"amount": 50}}
        assert evaluator.evaluate("10 < input.amount < 100", ctx) is True

    def test_chained_comparison_false(self, evaluator):
        ctx = {"input": {"amount": 200}}
        assert evaluator.evaluate("10 < input.amount < 100", ctx) is False


class TestLogicalOperators:
    """Test and, or, not operators."""

    def test_and_both_true(self, evaluator):
        ctx = {"input": {"amount": 10000}, "actor": {"role": "agent"}}
        assert evaluator.evaluate(
            'input.amount > 5000 and actor.role != "supervisor"', ctx
        ) is True

    def test_and_one_false(self, evaluator):
        ctx = {"input": {"amount": 10000}, "actor": {"role": "supervisor"}}
        assert evaluator.evaluate(
            'input.amount > 5000 and actor.role != "supervisor"', ctx
        ) is False

    def test_or_one_true(self, evaluator):
        ctx = {"input": {"amount": 100}, "actor": {"role": "supervisor"}}
        assert evaluator.evaluate(
            'input.amount > 5000 or actor.role == "supervisor"', ctx
        ) is True

    def test_or_both_false(self, evaluator):
        ctx = {"input": {"amount": 100}, "actor": {"role": "agent"}}
        assert evaluator.evaluate(
            'input.amount > 5000 or actor.role == "supervisor"', ctx
        ) is False

    def test_not(self, evaluator):
        ctx = {"input": {"amount": 100}}
        assert evaluator.evaluate("not input.amount > 5000", ctx) is True


class TestContainment:
    """Test in and not in operators."""

    def test_in_list(self, evaluator):
        ctx = {"actor": {"role": "admin"}}
        assert evaluator.evaluate('actor.role in ["admin", "supervisor"]', ctx) is True

    def test_not_in_list(self, evaluator):
        ctx = {"actor": {"role": "agent"}}
        assert evaluator.evaluate('actor.role not in ["admin", "supervisor"]', ctx) is True


class TestDotAccess:
    """Test nested dict access via dot notation."""

    def test_simple_dot_access(self, evaluator):
        ctx = {"input": {"amount": 42}}
        assert evaluator.evaluate("input.amount == 42", ctx) is True

    def test_missing_key_is_none(self, evaluator):
        ctx = {"input": {}}
        # input.amount resolves to None, None > 5000 raises TypeError → False
        assert evaluator.evaluate("input.amount > 5000", ctx) is False

    def test_missing_top_level_is_none(self, evaluator):
        ctx = {}
        assert evaluator.evaluate("input.amount > 5000", ctx) is False


class TestSafety:
    """Test that unsafe expressions are rejected."""

    def test_function_call_rejected(self, evaluator):
        assert evaluator.evaluate("print('hello')", {}) is False

    def test_import_rejected(self, evaluator):
        assert evaluator.evaluate("__import__('os')", {}) is False

    def test_lambda_rejected(self, evaluator):
        assert evaluator.evaluate("(lambda: 1)()", {}) is False

    def test_list_comprehension_rejected(self, evaluator):
        assert evaluator.evaluate("[x for x in range(10)]", {}) is False

    def test_malformed_expression(self, evaluator):
        assert evaluator.evaluate("if True:", {}) is False

    def test_syntax_error(self, evaluator):
        assert evaluator.evaluate(">>> hello", {}) is False

    def test_incomplete_expression(self, evaluator):
        assert evaluator.evaluate("input.amount >", {}) is False
