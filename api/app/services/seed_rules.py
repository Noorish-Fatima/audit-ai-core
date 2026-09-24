from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import SyncSessionLocal
from app.models.rule import Rule, RuleSeverity
from app.tier_config.tiers import TIER

def seed_default_rules():
    """Seeds the rules table with default examples if empty."""
    with SyncSessionLocal() as session:
        existing = session.execute(select(Rule)).scalars().all()
        if existing:
            return

        default_rules = [
            Rule(
                name="New vendor, high first invoice",
                description="Flagged if vendor is new and total amount > 5000",
                condition={
                    "and": [
                        {"field": "vendor.is_new", "operator": "equals", "value": True},
                        {"field": "invoice.total_amount", "operator": "gt", "value": 5000}
                    ]
                },
                severity=RuleSeverity.high,
                active=True
            ),
            Rule(
                name="Unapproved vendor",
                description="Flagged if vendor is not approved",
                condition={"field": "vendor.is_approved", "operator": "equals", "value": False},
                severity=RuleSeverity.critical,
                active=True
            ),
            Rule(
                name="Tax rate outside expected range",
                description="Flagged if tax rate < 0 or > 0.25",
                condition={
                    "or": [
                        {"field": "invoice.tax_rate", "operator": "lt", "value": 0},
                        {"field": "invoice.tax_rate", "operator": "gt", "value": 0.25}
                    ]
                },
                severity=RuleSeverity.medium,
                active=True
            ),
            Rule(
                name="three_way_match_tolerance",
                description="Tolerance threshold for three-way match (invoice vs PO vs receipt)",
                condition={"tolerance_percent": 2.0},
                severity=RuleSeverity.medium,
                active=True
            ),
            Rule(
                name="three_way_match_tolerance_exceeded",
                description="Three-way match tolerance exceeded: invoice amount differs from PO or receipt beyond allowed threshold",
                condition={
                    "and": [
                        {"field": "invoice.po_reference", "operator": "not_equals", "value": None},
                        {"field": "invoice.total_amount", "operator": "gt", "value": 0}
                    ]
                },
                severity=RuleSeverity.high,
                active=True
            )
        ]
        session.add_all(default_rules)
        session.commit()
        print("Default rules seeded successfully.")

if __name__ == "__main__":
    seed_default_rules()
