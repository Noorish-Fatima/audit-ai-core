#!/usr/bin/env python3
"""
Generate synthetic invoice data for testing and development.
This script creates sample invoice JSON files that can be used
to test the document processing pipeline.
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from faker import Faker

fake = Faker()


def generate_line_items(count: int = None) -> List[Dict[str, Any]]:
    """Generate random line items for an invoice."""
    if count is None:
        count = random.randint(1, 10)
    
    items = []
    for i in range(count):
        quantity = random.randint(1, 100)
        unit_price = round(random.uniform(10.0, 500.0), 2)
        items.append({
            "line_number": i + 1,
            "description": fake.catch_phrase(),
            "quantity": quantity,
            "unit_price": unit_price,
            "total_price": round(quantity * unit_price, 2),
            "sku": fake.bothify(text="SKU-####-???"),
        })
    return items


def generate_invoice(invoice_number: int) -> Dict[str, Any]:
    """Generate a single synthetic invoice."""
    vendor = fake.company()
    customer = fake.company()
    
    invoice_date = fake.date_between(start_date="-1y", end_date="today")
    due_date = invoice_date + timedelta(days=random.choice([15, 30, 45, 60, 90]))
    
    line_items = generate_line_items()
    subtotal = round(sum(item["total_price"] for item in line_items), 2)
    tax_rate = round(random.uniform(0.0, 0.2), 2)
    tax_amount = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax_amount, 2)
    
    return {
        "invoice_number": f"INV-{2024}-{invoice_number:06d}",
        "vendor": {
            "name": vendor,
            "address": fake.street_address(),
            "city": fake.city(),
            "state": fake.state_abbr(),
            "zip_code": fake.zipcode(),
            "country": "USA",
            "tax_id": fake.bothify(text="??-#######"),
            "email": fake.company_email(),
            "phone": fake.phone_number(),
        },
        "customer": {
            "name": customer,
            "address": fake.street_address(),
            "city": fake.city(),
            "state": fake.state_abbr(),
            "zip_code": fake.zipcode(),
            "country": "USA",
            "email": fake.company_email(),
        },
        "invoice_date": invoice_date.isoformat(),
        "due_date": due_date.isoformat(),
        "currency": "USD",
        "line_items": line_items,
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": total,
        "payment_terms": f"Net {random.choice([15, 30, 45, 60])}",
        "notes": fake.text(max_nb_chars=200) if random.random() > 0.5 else None,
        "metadata": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "generator_version": "1.0.0",
        }
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate synthetic invoices")
    parser.add_argument("-n", "--count", type=int, default=10, help="Number of invoices to generate")
    parser.add_argument("-o", "--output", type=str, default="synthetic_invoices", help="Output directory")
    parser.add_argument("--single-file", action="store_true", help="Write all invoices to a single JSON file")
    
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    invoices = [generate_invoice(i) for i in range(1, args.count + 1)]
    
    if args.single_file:
        output_file = output_dir / "invoices.json"
        with open(output_file, "w") as f:
            json.dump(invoices, f, indent=2)
        print(f"Generated {args.count} invoices to {output_file}")
    else:
        for invoice in invoices:
            filename = f"{invoice['invoice_number']}.json"
            output_file = output_dir / filename
            with open(output_file, "w") as f:
                json.dump(invoice, f, indent=2)
        print(f"Generated {args.count} invoices in {output_dir}/")
    
    # Print summary
    total_amount = sum(inv["total"] for inv in invoices)
    print(f"Total amount across all invoices: ${total_amount:,.2f}")


if __name__ == "__main__":
    main()