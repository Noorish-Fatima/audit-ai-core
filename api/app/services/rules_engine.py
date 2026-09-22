from typing import Any, Dict, List, Optional, Union
from decimal import Decimal, InvalidOperation
import logging

logger = logging.getLogger(__name__)

class RuleEvaluator:
    """
    Deterministic rule evaluator for document and vendor data.
    Supports recursive condition trees with AND/OR logic.
    """

    @staticmethod
    def evaluate(condition: Dict[str, Any], data: Dict[str, Any], vendor: Any) -> bool:
        """
        Evaluate a rule condition against provided data and vendor record.

        :param condition: The rule condition tree (JSON).
        :param data: Flattened extracted fields (e.g., {"total_amount": "1200.00"}).
        :param vendor: The Vendor model instance.
        :return: True if the rule is violated, False otherwise.
        """
        # Handle AND conditions
        if "and" in condition:
            return all(RuleEvaluator.evaluate(c, data, vendor) for c in condition["and"])

        # Handle OR conditions
        if "or" in condition:
            return any(RuleEvaluator.evaluate(c, data, vendor) for c in condition["or"])

        # Base case: a single condition triplet (field, operator, value)
        field = condition.get("field")
        operator = condition.get("operator")
        expected_value = condition.get("value")

        if not field or not operator:
            logger.warning(f"Invalid condition encountered: {condition}")
            return False

        actual_value = RuleEvaluator._resolve_field(field, data, vendor)
        return RuleEvaluator._compare(actual_value, operator, expected_value)

    @staticmethod
    def _resolve_field(field: str, data: Dict[str, Any], vendor: Any) -> Any:
        """Resolves a field path like 'invoice.total_amount' or 'vendor.is_approved'."""
        if field.startswith("invoice."):
            field_name = field.replace("invoice.", "", 1)
            return data.get(field_name)

        if field.startswith("vendor."):
            attr_name = field.replace("vendor.", "", 1)
            return getattr(vendor, attr_name, None)

        return None

    @staticmethod
    def _compare(actual: Any, operator: str, expected: Any) -> bool:
        """Deterministic comparison logic."""
        # Handle Nulls
        if actual is None:
            return operator == "not_equals"

        # Try to treat as numeric if either side looks like a number
        # This is crucial for 'gt', 'lt', etc.
        try:
            if any(op in operator for op in ["gt", "lt", "gte", "lte"]):
                actual_num = Decimal(str(actual)) if not isinstance(actual, (int, float, Decimal)) else Decimal(str(actual))
                expected_num = Decimal(str(expected)) if not isinstance(expected, (int, float, Decimal)) else Decimal(str(expected))

                if operator == "gt": return actual_num > expected_num
                if operator == "gte": return actual_num >= expected_num
                if operator == "lt": return actual_num < expected_num
                if operator == "lte": return actual_num <= expected_num
        except (InvalidOperation, ValueError, TypeError):
            # If numeric conversion fails, fallback to string comparison or return False
            pass

        # String/General operators
        if operator == "equals":
            return str(actual).lower() == str(expected).lower() if isinstance(actual, str) else actual == expected
        if operator == "not_equals":
            return str(actual).lower() != str(expected).lower() if isinstance(actual, str) else actual != expected
        if operator == "contains":
            if isinstance(actual, (str, list, dict)):
                return str(expected).lower() in str(actual).lower() if isinstance(actual, str) else expected in actual
            return False

        return False
