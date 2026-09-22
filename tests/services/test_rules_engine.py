from typing import Any, Dict
from decimal import Decimal
import pytest
from api.app.services.rules_engine import RuleEvaluator
from unittest.mock import MagicMock

class MockVendor:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

def test_evaluator_basic_equals():
    evaluator = RuleEvaluator()
    data = {"total_amount": "100.00", "invoice_number": "INV-1"}
    vendor = MockVendor(is_approved=True)

    # Invoice check
    cond1 = {"field": "invoice.total_amount", "operator": "equals", "value": "100.00"}
    assert RuleEvaluator.evaluate(cond1, data, vendor) is True

    # Vendor check
    cond2 = {"field": "vendor.is_approved", "operator": "equals", "value": True}
    assert RuleEvaluator.evaluate(cond2, data, vendor) is True

def test_evaluator_numeric_comparisons():
    data = {"total_amount": "6000.00"}
    vendor = MockVendor(is_new=True)

    # Greater than
    cond1 = {"field": "invoice.total_amount", "operator": "gt", "value": 5000}
    assert RuleEvaluator.evaluate(cond1, data, vendor) is True

    # Less than
    cond2 = {"field": "invoice.total_amount", "operator": "lt", "value": 5000}
    assert RuleEvaluator.evaluate(cond2, data, vendor) is False

def test_evaluator_nested_and():
    data = {"total_amount": "6000.00"}
    vendor = MockVendor(is_new=True)

    condition = {
        "and": [
            {"field": "vendor.is_new", "operator": "equals", "value": True},
            {"field": "invoice.total_amount", "operator": "gt", "value": 5000}
        ]
    }
    assert RuleEvaluator.evaluate(condition, data, vendor) is True

def test_evaluator_nested_or():
    data = {"tax_rate": "0.30"}
    vendor = MockVendor()

    condition = {
        "or": [
            {"field": "invoice.tax_rate", "operator": "lt", "value": 0},
            {"field": "invoice.tax_rate", "operator": "gt", "value": 0.25}
        ]
    }
    assert RuleEvaluator.evaluate(condition, data, vendor) is True

def test_evaluator_contains():
    data = {"notes": "This is a high priority invoice"}
    vendor = MockVendor()

    cond = {"field": "invoice.notes", "operator": "contains", "value": "priority"}
    assert RuleEvaluator.evaluate(cond, data, vendor) is True

def test_evaluator_not_equals():
    data = {"total_amount": "100.00"}
    vendor = MockVendor(is_approved=False)

    cond = {"field": "vendor.is_approved", "operator": "not_equals", "value": True}
    assert RuleEvaluator.evaluate(cond, data, vendor) is True
