#!/usr/bin/env python3
"""
One-command end-to-end verification for a deployed Audit-AI stack.

Flow:
  1. Health checks (api, readiness with DB+Redis, liveness, frontend)
  2. Register a unique test user (or log in if it already exists)
  3. Render a synthetic invoice PNG and upload it
  4. Poll the document until a terminal status
     (verified | review | flagged | duplicate)
  5. Assert extracted fields were produced

Exit 0 = PASS, 1 = FAIL. Use after every client deploy:

    python3 scripts/verify_system.py [--api-url ...] [--timeout ...]
"""
import argparse
import sys
import time
import uuid
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("FAIL - the 'requests' package is required: pip install requests")
    sys.exit(2)

TERMINAL_STATUSES = {"verified", "review", "flagged", "duplicate"}

INVOICE_LINES = [
    "HomeStore",
    "6146 Honey Bluff Parkway",
    "Calder, Michigan 49628",
    "Invoice #INV-VERIFY-001",
    "Date: 2024-11-02",
    "Clamber Watch  1 x $100.00",
    "Jacket         1 x $77.00",
    "Subtotal: $177.00",
    "Tax: $26.06",
    "Grand Total: $203.06",
    "Thank you for your order!",
]


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}", flush=True)


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""), flush=True)
    return ok


def render_invoice_png(path: str) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (900, 700), "white")
    draw = ImageDraw.Draw(img)
    # NOTE: fill="black" is required — Pillow >= 10 renders draw.text()
    # with the default fill as invisible ink, which once produced a blank
    # 3KB PNG that OCR'd to nothing and failed the whole verify run.
    y = 40
    for i, line in enumerate(INVOICE_LINES):
        draw.text((60, y), line, fill="black")
        y += 44 if i in (0, 3) else 34
    img.save(path, format="PNG")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a deployed Audit-AI stack end to end")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--frontend-url", default="http://localhost:3000", help="Frontend base URL")
    parser.add_argument("--timeout", type=int, default=600, help="Max seconds to wait for terminal status")
    parser.add_argument("--poll-interval", type=int, default=10, help="Seconds between status polls")
    args = parser.parse_args()

    api = args.api_url.rstrip("/")
    ok = True

    # 1. Health checks
    log("Step 1/4: health checks")
    for name, url, want in [
        ("api", api + "/health", 200),
        ("readiness", api + "/health/ready", 200),
        ("liveness", api + "/health/live", 200),
        ("frontend", args.frontend_url.rstrip("/") + "/api/health", 200),
    ]:
        try:
            r = requests.get(url, timeout=10)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            ok &= check(f"GET {name}", r.status_code == want, f"HTTP {r.status_code} {body}")
        except Exception as e:
            ok &= check(f"GET {name}", False, f"{type(e).__name__}: {e}")
    if not ok:
        log("RESULT: FAIL (services unhealthy)")
        return 1

    # 2. Test user
    log("Step 2/4: test user")
    email = f"verify-{uuid.uuid4().hex[:8]}@example.com"
    password = "Verify123!"
    r = requests.post(f"{api}/api/v1/auth/register", json={"email": email, "password": password}, timeout=15)
    if r.status_code == 201:
        token = r.json()["access_token"]
        ok &= check("register user", True, email)
    else:
        log(f"register returned {r.status_code}, trying login")
        r = requests.post(f"{api}/api/v1/auth/login", json={"email": email, "password": password}, timeout=15)
        if r.status_code != 200:
            ok &= check("authenticate", False, f"HTTP {r.status_code}: {r.text[:200]}")
            log("RESULT: FAIL (cannot authenticate)")
            return 1
        token = r.json()["access_token"]
        ok &= check("login user", True, email)
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Upload synthetic invoice
    log("Step 3/4: upload synthetic invoice")
    img_path = "/tmp/verify_invoice.png"
    render_invoice_png(img_path)
    with open(img_path, "rb") as f:
        r = requests.post(
            f"{api}/api/v1/documents/upload",
            files={"file": ("verify_invoice.png", f, "image/png")},
            headers=headers,
            timeout=60,
        )
    if r.status_code != 202:
        ok &= check("upload", False, f"HTTP {r.status_code}: {r.text[:200]}")
        log("RESULT: FAIL (upload rejected)")
        return 1
    document_id = r.json()["document_id"]
    ok &= check("upload accepted", True, f"document_id={document_id}")

    # 4. Poll to terminal status
    log(f"Step 4/4: poll {document_id} until terminal {sorted(TERMINAL_STATUSES)}")
    deadline = time.time() + args.timeout
    final = None
    while time.time() < deadline:
        r = requests.get(f"{api}/api/v1/documents/{document_id}", headers=headers, timeout=15)
        if r.status_code != 200:
            log(f"  ... status poll HTTP {r.status_code}, retrying")
            time.sleep(args.poll_interval)
            continue
        doc = r.json()
        status = doc.get("status")
        log(f"  ... status={status}")
        if status in TERMINAL_STATUSES:
            final = doc
            break
        time.sleep(args.poll_interval)

    if final is None:
        ok &= check("terminal status", False, f"no terminal status within {args.timeout}s")
        log("RESULT: FAIL (pipeline stuck)")
        return 1
    ok &= check("terminal status", True, final["status"])
    n_fields = len(final.get("extracted_fields") or [])
    ok &= check("extracted fields produced", n_fields > 0, f"{n_fields} fields")

    log("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
