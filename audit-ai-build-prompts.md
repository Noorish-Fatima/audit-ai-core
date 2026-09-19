# Audit-AI — Full Build Prompt Sequence

**How to use this document:** Feed each prompt to your coding agent **in order**. Do not skip ahead — later prompts assume earlier ones are complete and working. After each prompt, verify the acceptance criteria before moving to the next. Each prompt is self-contained: paste it directly, it does not require you to add context.

Tier gating (`TIER=basic|standard|premium`) is built in from Prompt 4 onward. Everything after that respects it automatically.

---

## PROMPT 0 — Repo Scaffolding

```
Create a monorepo for a document intelligence platform called Audit-AI with this exact structure:

audit-ai/
├── api/                    # FastAPI backend
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── routers/
│   │   ├── services/
│   │   ├── agents/         # LangGraph subgraphs live here
│   │   └── db/
│   ├── alembic/
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── worker/                 # Celery worker (shares api/app code via volume mount)
│   ├── celery_app.py
│   ├── tasks/
│   └── Dockerfile
├── frontend/                # Next.js 14, Pages Router, TypeScript strict
│   ├── pages/
│   ├── components/
│   ├── hooks/
│   ├── lib/
│   └── Dockerfile
├── scripts/
│   ├── generate_synthetic_invoices.py
│   └── verify_system.py
├── docker-compose.yml
├── .env.example
└── README.md

Requirements:
- Python 3.11, FastAPI, Pydantic v2, async SQLAlchemy
- Node 20, Next.js 14, TypeScript strict mode
- Use `uv` or `pip-tools` for Python dependency pinning — no unpinned versions
- Include a root README.md explaining the folder structure and how to run `docker-compose up`
- Do NOT write any business logic yet — this prompt is scaffolding only

Acceptance criteria: `docker-compose up` starts all services with placeholder health-check endpoints returning 200, even with no real logic yet.
```

---

## PROMPT 1 — Docker Compose Infrastructure

```
Build docker-compose.yml for Audit-AI with these services:

1. postgres — Postgres 16, named volume for data persistence, healthcheck via pg_isready
2. redis — Redis 7, healthcheck via redis-cli ping
3. api — FastAPI app, depends_on postgres/redis with condition: service_healthy, exposes port 8000, mounts ./api for hot reload in dev
4. worker — Celery worker, same image as api (multi-stage build sharing app code), depends_on redis/postgres healthy
5. beat — Celery Beat scheduler, only needed for standard/premium tier scheduled tasks (approval-chase reminders, monthly reports) — still define it, task logic comes later
6. frontend — Next.js, port 3000, depends_on api
7. flower — Celery monitoring UI, port 5555, basic-auth protected via environment variables, NOT exposed to public network by default

Requirements:
- Use multi-stage Dockerfiles, non-root user in every container
- All services read config from a single .env file (create .env.example with every variable documented, no real secrets)
- Include healthcheck blocks for every service
- api and worker share the same base image to avoid duplicated dependency installs
- Add a TIER environment variable (default: basic) passed into api, worker, and beat

Environment variables to include in .env.example:
DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, JWT_ACCESS_EXPIRE_MINUTES, JWT_REFRESH_EXPIRE_DAYS,
GROQ_API_KEY, GEMINI_API_KEY, TIER, FLOWER_USER, FLOWER_PASSWORD, CORS_ORIGINS

Acceptance criteria: docker-compose up brings all 7 services to a healthy state with no application code beyond health endpoints.
```

---

## PROMPT 2 — Database Schema & Migrations

```
Using SQLAlchemy 2.0 (async) and Alembic, create the full database schema for Audit-AI.

Tables required:

1. users
   - id (UUID, PK), email (unique, indexed), hashed_password, role (enum: admin, approver, auditor),
     is_active (bool, default true), created_at, updated_at

2. refresh_tokens
   - id (UUID, PK), user_id (FK → users), token_hash, expires_at, revoked (bool, default false), created_at

3. documents
   - id (UUID, PK), original_filename, storage_path, mime_type, file_size, status (enum: pending, ocr_processing,
     extracting, validating, review, verified, flagged, duplicate), uploaded_by (FK → users), created_at, updated_at

4. document_sessions
   - id (UUID, PK), document_id (FK → documents), current_stage, progress_percent, stage_history (JSONB), updated_at

5. extracted_fields
   - id (UUID, PK), document_id (FK → documents), field_name, field_value, confidence_score (float),
     extraction_method (enum: text_model, vision_model, ocr_only), is_corrected (bool, default false),
     original_value (nullable — populated only if a human corrects it), corrected_by (FK → users, nullable), corrected_at

6. vendors
   - id (UUID, PK), canonical_name, aliases (JSONB array), tax_id, is_approved (bool), is_new (bool, default true),
     bank_account_last4, bank_account_hash, created_at, updated_at

7. vendor_bank_history
   - id (UUID, PK), vendor_id (FK → vendors), old_bank_account_hash, new_bank_account_hash, changed_at, flagged (bool)

8. rules
   - id (UUID, PK), name, description, condition (JSONB), severity (enum: low, medium, high, critical),
     active (bool, default true), created_by (FK → users), created_at

9. rule_violations
   - id (UUID, PK), document_id (FK → documents), rule_id (FK → rules), details (JSONB), created_at

10. duplicate_flags
    - id (UUID, PK), document_id (FK → documents), duplicate_of_document_id (FK → documents),
      match_type (enum: exact_key, fuzzy_match), confidence_score, created_at

11. fraud_flags
    - id (UUID, PK), document_id (FK → documents), flag_type (enum: bank_change, new_vendor_high_amount,
      round_number_threshold), severity, details (JSONB), created_at

12. purchase_orders / goods_receipts (premium tier — create tables now, logic comes later)
    - purchase_orders: id, po_number, vendor_id (FK), expected_amount, line_items (JSONB), created_at
    - goods_receipts: id, po_id (FK), received_amount, received_at

13. nl_query_log
    - id (UUID, PK), user_id (FK → users), question_text, resolved_intent, tool_called, tool_args (JSONB),
      response_text, created_at

14. audit_log
    - id (UUID, PK), document_id (FK → documents, nullable), user_id (FK → users, nullable), action,
      before_state (JSONB, nullable), after_state (JSONB, nullable), created_at
    - This table is APPEND-ONLY. No update or delete operations should ever be written against it anywhere in the codebase.

Requirements:
- All FKs properly indexed
- Use Alembic for every migration, one logical migration per table group, not one giant migration
- Add a composite index on documents(status, created_at) for review-queue query performance
- Add a unique constraint on (vendor_id, invoice_number) is NOT enforced at DB level for duplicate detection — that logic is fuzzy and lives in application code, not a DB constraint
- Write a seed script (scripts/seed_db.py) that creates one admin user for local dev

Acceptance criteria: `alembic upgrade head` runs clean on a fresh Postgres instance, all tables and FKs exist, seed script creates a working admin login.
```

---

## PROMPT 3 — Auth Module (JWT + RBAC)

```
Build the complete authentication system for Audit-AI in api/app/routers/auth.py, api/app/services/auth_service.py,
and api/app/dependencies/auth.py.

Requirements:

1. Password hashing via passlib[bcrypt] — never store or log plaintext passwords anywhere, including debug logs.

2. JWT via python-jose[cryptography]:
   - Access token: 30 min expiry, contains user_id, role, exp claims
   - Refresh token: 7 day expiry, opaque random token, hashed and stored in refresh_tokens table (never store raw refresh tokens)

3. Endpoints:
   - POST /auth/register — admin-only in production (add a role check), open in dev via ENV flag
   - POST /auth/login — verifies password, returns access + refresh token. On failure, return a GENERIC error
     ("invalid email or password") — never reveal whether the email exists.
   - POST /auth/refresh — validates refresh token against stored hash, checks not revoked/expired, issues new access token
   - POST /auth/logout — revokes the refresh token (sets revoked=true, does not delete — audit trail)
   - GET /auth/me — returns current user from valid access token

4. Rate limiting on /auth/login — use slowapi or a simple Redis-backed counter, max 5 attempts per email per 15 minutes,
   return 429 on excess.

5. FastAPI dependency `get_current_user` — validates the Bearer token, loads user, raises 401 if invalid/expired.
   FastAPI dependency `require_role(*roles)` — raises 403 if current_user.role not in allowed roles. Every
   protected router in later prompts must use this.

6. Refresh tokens delivered to frontend via httpOnly, Secure, SameSite=Strict cookie — NOT returned in JSON body,
   NOT stored in localStorage on the frontend.

7. JWT_SECRET_KEY loaded strictly from environment variable — raise a startup error if it's missing or is the
   placeholder value from .env.example.

Write pytest tests covering: successful login, wrong password (generic error), expired token rejection,
role-based access rejection, refresh token rotation, rate limit triggering.

Acceptance criteria: full auth flow works end to end via curl/httpie, all tests pass, no secrets in logs.
```

---

## PROMPT 4 — Tier Configuration System

```
Build the tier-gating system that controls which features are active per deployment, in api/app/config/tiers.py.

Requirements:

1. Read TIER from environment (basic | standard | premium), default "basic", raise startup error on invalid value.

2. Define a FEATURES dict:
   FEATURES = {
     "basic":    {"rules_engine": False, "nl_query": False, "fraud_detection": False, "three_way_match": False, "approval_routing": False, "reporting": False},
     "standard": {"rules_engine": True,  "nl_query": True,  "fraud_detection": True,  "three_way_match": False, "approval_routing": False, "reporting": True},
     "premium":  {"rules_engine": True,  "nl_query": True,  "fraud_detection": True,  "three_way_match": True,  "approval_routing": True,  "reporting": True},
   }

3. Expose a helper `feature_enabled(name: str) -> bool` used everywhere in the codebase — routers, Celery tasks,
   and a GET /system/tier endpoint the frontend calls on load to know what UI to render.

4. Router registration in main.py must be conditional: rules/fraud/nl-query/three-way-match/reporting routers
   only get included in the FastAPI app if their corresponding feature flag is True. A disabled feature's
   endpoint should not exist at all (404), not just be hidden in the UI — this matters for the security story
   (a Basic-tier client's deployment literally does not contain Premium code paths active).

5. GET /system/tier response shape: { "tier": "standard", "features": { ...FEATURES["standard"] } }

Acceptance criteria: changing TIER in .env and restarting the stack changes which endpoints exist (verify with
curl — a rules-engine endpoint returns 404 on TIER=basic, 200 on TIER=standard).
```

---

## PROMPT 5 — Ingestion & Document Session

```
Build the document upload and session-tracking system.

Requirements:

1. POST /documents/upload (protected, any authenticated role):
   - Accept multipart file upload
   - Validate MIME type whitelist (application/pdf, image/jpeg, image/png, image/tiff) — reject anything else with 415
   - Validate file size limit (configurable via env, default 20MB) — reject with 413
   - Sanitize filename, store with a generated UUID filename on disk (or object storage if configured), never
     trust the original filename for the storage path — prevent path traversal
   - Create a `documents` row (status=pending) and a `document_sessions` row (current_stage="uploaded", progress=0)
   - Enqueue the Celery processing chain (chain assembled in Prompt 12) with document_id
   - Return 202 Accepted with document_id immediately — do not block on processing

2. GET /documents/{id}/session — returns current_stage, progress_percent, stage_history for the live progress UI
   to poll. This must be a lightweight, fast query (no joins beyond the session row).

3. GET /documents/{id} — full document detail including all extracted_fields, once available

4. GET /documents — paginated list with filters: status, uploaded_by, date_range, sorted by created_at desc

5. File serving: GET /documents/{id}/file — serves the original file for viewing, protected, validates the
   requesting user has access, path-containment check (never allow the resolved path to escape the storage
   root directory).

Acceptance criteria: upload a real PDF via curl, poll the session endpoint, see progress fields populate as
Celery tasks run (even if downstream tasks are still stubs at this point).
```

---

## PROMPT 6 — OCR + Image Normalization

```
Build the OCR and normalization Celery task in worker/tasks/ocr_task.py.

Requirements:

1. Task `ocr_normalize(document_id)`:
   - Load the file, detect type: if PDF, rasterize each page via pypdfium2 to images; if already an image, use directly
   - Image normalization pipeline: convert to RGB, auto-orient (EXIF), deskew, adaptive crop to document
     boundaries, contrast normalization — this is the step responsible for OCR yield improvement on scans
   - Run Tesseract OCR on the normalized image(s), extract raw text
   - Store raw OCR text + normalized image path(s) on the document record (add a `raw_ocr_text` and
     `normalized_image_paths` field to the documents table via a new Alembic migration)
   - Update document_session: stage="ocr_complete", progress=25
   - Task must be idempotent — safe to retry without creating duplicate normalized files (use deterministic
     output filenames keyed by document_id)

2. On any failure in this task: catch the exception, update document status to "flagged" with a reason of
   "ocr_failed", write an audit_log entry, do NOT let the exception propagate and crash the worker silently —
   the document must always land in a terminal or review state, never stuck.

Acceptance criteria: upload a scanned/photographed test invoice, confirm raw OCR text is captured and the
normalized image is visibly cleaner (straighter, cropped, higher contrast) than the original.
```

---

## PROMPT 7 — Extraction Pipeline (LangGraph Subgraph)

```
Build the field extraction subgraph using LangGraph, in api/app/agents/extraction_graph.py, called from a
Celery task in worker/tasks/extraction_task.py.

Requirements:

1. Define a strict Pydantic schema for extracted invoice fields: invoice_number, vendor_name, invoice_date,
   due_date, currency (ISO code only, mapped from symbols — never inferred if absent), subtotal, tax_amount,
   tax_rate, total_amount, line_items (list), each field paired with a confidence_score (0.0–1.0).

2. LangGraph subgraph nodes:
   - text_model_node: calls Groq (llama-3.3-70b-versatile), passes raw OCR text, prompts for structured JSON
     matching the Pydantic schema, enforces schema via function-calling / tool-schema (not just "return JSON"
     in the prompt — use provider-native structured output if available)
   - confidence_check_node: if any critical field (invoice_number, vendor_name, total_amount) has
     confidence < 0.7, OR the text model returns null for a critical field, route to vision_model_node
   - vision_model_node: calls Gemini (gemini-2.0-flash) with the normalized image directly, same structured
     schema, used as the fallback path for scans/low-quality text extraction
   - merge_node: combines results, text model output takes precedence field-by-field unless vision model
     resolved a null the text model couldn't

3. No-inference policy for currency: if no explicit currency symbol/code is present in the document, the field
   must be returned null, never guessed or defaulted to USD.

4. Write extracted_fields rows for each field with its extraction_method and confidence_score.

5. Update document_session: stage="extraction_complete", progress=50.

6. Handle provider errors gracefully (rate limit, timeout) — retry with exponential backoff (max 3 attempts),
   then route to review queue with reason "extraction_failed" rather than crashing the task.

Write a test using at least 3 synthetic invoice variants (typed PDF, scanned image, unusual field labels like
"Ref#" instead of "Invoice #") confirming correct extraction and correct fallback triggering.

Acceptance criteria: a clean typed PDF extracts via text model only; a low-quality scan correctly falls back
to vision model; currency is never fabricated when absent from the source document.
```

---

## PROMPT 8 — Validation & Duplicate Detection

```
Build critical-field validation and duplicate detection in worker/tasks/validation_task.py.

Requirements:

1. Task `validate_critical_fields(document_id)`:
   - Critical fields: invoice_number, vendor_name, total_amount, invoice_date
   - If any critical field is null or confidence_score < 0.5, set document status to "review" immediately,
     skip remaining automated checks, write audit_log entry with reason
   - Vendor name matching: fuzzy-match extracted vendor_name against `vendors.canonical_name` and
     `vendors.aliases` (use rapidfuzz, threshold configurable, default 85% similarity) — link the document
     to the matched vendor_id, or create a new vendor record with is_new=true if no match found

2. Task `check_duplicates(document_id)`:
   - Exact-key match: same vendor_id + same invoice_number already exists on another document → flag as
     duplicate_flags row, match_type="exact_key", confidence_score=1.0
   - Fuzzy match: same vendor_id + invoice amount within 1% + invoice date within 3 days of an existing
     document → flag as duplicate_flags row, match_type="fuzzy_match", confidence_score based on how close
     the match is — this catches OCR-error near-duplicates that exact matching misses
   - A flagged duplicate always routes the document to status="duplicate", never silently auto-rejects —
     a human confirms it's a true duplicate in the review workbench

3. Update document_session: stage="validation_complete", progress=65

Write tests: exact duplicate correctly flagged, near-duplicate (off by $0.50 due to OCR misread) correctly
flagged via fuzzy match, legitimately different invoices from the same vendor NOT falsely flagged.

Acceptance criteria: uploading the same invoice twice flags the second as an exact duplicate; a deliberately
altered near-duplicate (slightly different OCR'd amount) is still caught.
```

---

## PROMPT 9 — Configurable Rules Engine (Standard+)

```
Build the deterministic, client-configurable rules engine — gated behind feature_enabled("rules_engine").

Requirements:

1. Rules are stored in the `rules` table as JSON condition trees. Support this condition schema:
   {
     "field": "invoice.total_amount" | "vendor.is_new" | "vendor.is_approved" | "invoice.tax_rate" | ...,
     "operator": "equals" | "not_equals" | "gt" | "lt" | "gte" | "lte" | "contains",
     "value": <any>,
     "and": [ <nested conditions> ],   // optional
     "or": [ <nested conditions> ]     // optional
   }

2. Build a pure-Python rule evaluator (api/app/services/rules_engine.py) that takes a document's full
   extracted data + linked vendor record and evaluates every active rule against it. This must be
   deterministic — no LLM involvement in rule evaluation itself, so every flag is explainable and auditable.

3. CRUD endpoints (admin/approver role only):
   - POST /rules — create a rule
   - GET /rules — list rules
   - PATCH /rules/{id} — update/activate/deactivate
   - DELETE /rules/{id} — soft delete (set active=false, never hard-delete — audit trail)

4. Celery task `evaluate_rules(document_id)`:
   - Skips entirely if feature_enabled("rules_engine") is False — return early, no-op
   - Runs every active rule against the document, writes rule_violations rows for each match
   - If any rule_violation has severity="critical", force document status to "review" regardless of
     confidence scores elsewhere in the pipeline
   - Update document_session: stage="rules_complete", progress=75

5. Ship 3 default example rules seeded on first run (client can edit/deactivate them):
   - "New vendor, high first invoice" (vendor.is_new = true AND invoice.total_amount > 5000)
   - "Unapproved vendor" (vendor.is_approved = false)
   - "Tax rate outside expected range" (invoice.tax_rate < 0 OR invoice.tax_rate > 0.25)

Write tests confirming rule evaluation correctness for AND/OR nested conditions, and confirming the task
no-ops cleanly when rules_engine feature is disabled.

Acceptance criteria: creating a new rule via the API and re-processing a document correctly triggers or
skips a violation based on the rule's condition, with zero code changes required.
```

---

## PROMPT 10 — Fraud Pattern Detection (Standard+)

```
Build fraud pattern detection — gated behind feature_enabled("fraud_detection").

Requirements: implement these three detectors as a Celery task `check_fraud_patterns(document_id)`,
each writing a `fraud_flags` row when triggered:

1. Bank detail change detection:
   - Compare the vendor's current bank_account_hash against vendor_bank_history
   - If a bank detail change occurred within 14 days before this invoice's date, flag as
     flag_type="bank_change", severity="critical" — this is the highest-value fraud catch (Business Email
     Compromise pattern), surface it prominently in the review UI

2. New vendor + high first invoice:
   - If vendor.is_new = true AND this is the vendor's first invoice AND total_amount exceeds a configurable
     threshold (default $5,000, override per rules table if client wants a custom number instead of hardcoded)
   - flag_type="new_vendor_high_amount", severity="high"

3. Round-number / threshold-avoidance pattern:
   - Query all of this vendor's invoices in the last 90 days
   - If 3+ invoices cluster within 5% below a known approval threshold (thresholds configurable, default
     $10,000 example), flag flag_type="round_number_threshold", severity="high" on the newest one, referencing
     the pattern in `details` JSONB (list the other invoice IDs forming the pattern)

Update document_session: stage="fraud_check_complete", progress=85. Task no-ops cleanly if fraud_detection
feature is off.

Any fraud_flags row with severity="critical" forces document status to "review" — never auto-finalized.

Write tests for each of the 3 detectors independently, including a true-negative test (legitimate repeat
vendor invoices should NOT trigger false positives).

Acceptance criteria: seed a vendor with a recent bank-detail change, upload a new invoice for them, confirm
it's flagged critical and routed to review.
```

---

## PROMPT 11 — Three-Way Match (Premium)

```
Build 3-way match (Invoice vs Purchase Order vs Goods Receipt) — gated behind feature_enabled("three_way_match").

Requirements:

1. Endpoints to ingest PO and receipt data (admin/approver role):
   - POST /purchase-orders — po_number, vendor_id, expected_amount, line_items
   - POST /goods-receipts — po_id, received_amount, received_at

2. Celery task `three_way_match(document_id)`:
   - Attempt to match the invoice to a PO via extracted PO reference field (add po_reference to
     extracted_fields schema in Prompt 7 — note: PO number extraction should already be part of the schema,
     verify it's there or add via migration)
   - If no PO reference found or no matching PO exists, skip — not every invoice is PO-backed, this is not
     an automatic flag on its own
   - If matched: compare invoice.total_amount against po.expected_amount AND goods_receipt.received_amount.
     Tolerance threshold configurable (default 2% variance allowed for shipping/rounding)
   - Mismatch beyond tolerance → rule_violations row (reuse existing table), severity="high",
     details includes the three amounts side by side for the reviewer

3. Update document_session: stage="three_way_match_complete", progress=90. No-ops if feature disabled.

Acceptance criteria: upload an invoice referencing a PO where the billed amount exceeds the PO by more than
tolerance, confirm it's flagged with all three amounts visible in the violation detail.
```

---

## PROMPT 12 — Pipeline Assembly, Routing Decision, Audit Log

```
Assemble the full Celery chain and finalize routing logic.

Requirements:

1. In worker/celery_app.py, build the chain triggered on document upload:
   ocr_normalize → extract_fields → validate_critical_fields → check_duplicates →
   evaluate_rules → check_fraud_patterns → three_way_match → route_decision → audit_log_commit

   Each task must be independently idempotent (safe to retry without side-effect duplication) — this was
   already required per-task in earlier prompts, this step verifies the FULL chain is retry-safe end to end.

2. Task `route_decision(document_id)`:
   - If status is already "review", "flagged", or "duplicate" from any earlier step, leave it — do not
     override an existing review-required state
   - Otherwise, if all confidence scores are high, no rule violations, no fraud flags, no duplicate flags,
     no match mismatches → status = "verified", finalize automatically
   - Otherwise → status = "review", document enters the human review queue
   - This is the ONLY place final status is set — no other task should set a terminal status directly except
     via the "leave existing review state" rule above

3. Task `audit_log_commit(document_id)`:
   - Writes a final audit_log entry summarizing the full pipeline run: every stage's outcome, every flag
     raised, final status
   - Update document_session: stage="complete", progress=100

4. GET /documents/review-queue (protected) — returns documents with status in (review, flagged, duplicate),
   sorted by a priority score (lower confidence + higher severity flags = higher priority), paginated

5. PATCH /documents/{id}/review (approver/admin role) — human correction endpoint:
   - Accepts corrected field values
   - Writes to extracted_fields.original_value (preserve what the AI said) before overwriting field_value
   - Sets extracted_fields.is_corrected=true, corrected_by=user_id, corrected_at=now
   - Writes audit_log entry: before_state and after_state of the correction
   - Allows setting final status: verified / flagged (with reason) / confirmed_duplicate
   - This endpoint must never allow bypassing the audit trail — every correction is recorded, none are
     silently overwritten

Write an integration test that uploads a document and asserts it reaches a terminal status (verified or
review) with zero exceptions, and that retrying any single task in the chain does not create duplicate
database rows anywhere.

Acceptance criteria: 100% of test uploads reach a terminal state — none stuck in an intermediate status.
```

---

## PROMPT 13 — Natural Language Query Agent (Standard+)

```
Build the constrained NL query agent — gated behind feature_enabled("nl_query"). Do NOT let the LLM generate
raw SQL under any circumstances — this is a hard security requirement, not a style preference.

Requirements:

1. Define a fixed whitelist of parameterized query functions in api/app/services/query_tools.py:
   - get_vendor_spend(vendor_name: str, date_from: date, date_to: date) -> dict
   - get_avg_tax_rate(vendor_name: str | None, date_from: date, date_to: date) -> dict
   - list_flagged_documents(severity: str | None, date_from: date, date_to: date) -> list
   - get_invoice_summary(document_id: str) -> dict
   - get_top_vendors_by_spend(date_from: date, date_to: date, limit: int = 10) -> list
   Each function runs a fixed, parameterized SQLAlchemy query — no string interpolation of user input into
   SQL, ever.

2. LangGraph agent graph (api/app/agents/nl_query_graph.py):
   - intent_classifier_node: classifies the incoming question into one of the whitelisted function categories,
     or "unsupported" if it doesn't match any
   - argument_extraction_node: extracts function arguments from the natural language question (vendor name,
     date range, severity) using structured output, validates against expected types before calling anything
   - tool_execution_node: calls the corresponding whitelisted function with validated arguments only
   - response_formatter_node: turns the structured result into a natural language answer
   - If intent_classifier_node returns "unsupported", respond honestly that the question is outside what the
     system can currently answer — never let the agent attempt a workaround via free-form data access

3. POST /query (protected, any authenticated role):
   - Accepts { "question": string }
   - Runs the graph, logs to nl_query_log (question, resolved_intent, tool_called, tool_args, response_text)
   - Returns the natural language answer + the underlying structured data (so frontend can render a table too)

Write tests for at least 5 example questions covering each tool, plus one deliberately ambiguous/unsupported
question confirming it's handled honestly rather than hallucinated.

Acceptance criteria: asking "how much have we paid Acme Corp this year" returns a correct, DB-verified answer
with zero raw SQL ever touching the LLM's output path.
```

---

## PROMPT 14 — Frontend: Upload + Review Workbench

```
Build the core frontend in Next.js 14 (Pages Router, TypeScript strict).

Requirements:

1. Auth pages: /login — calls POST /auth/login, stores access token in memory (React context/state, NOT
   localStorage), refresh token handled automatically via httpOnly cookie, silent refresh on 401 via an
   axios/fetch interceptor.

2. /upload page:
   - Drag-and-drop file upload component
   - On upload, immediately show the document in a "processing" state
   - Poll GET /documents/{id}/session every 1.5s, render a live progress bar with the current stage name
     ("Extracting fields...", "Checking for duplicates...", etc.) — never a blank/frozen screen
   - On completion, redirect to the document detail view

3. /review page (review queue):
   - Table of documents with status in (review, flagged, duplicate), sortable, filterable by severity/date
   - Click into a document → side-by-side view: original file (PDF/image viewer) next to extracted fields
   - Every field is inline-editable; saving calls PATCH /documents/{id}/review
   - Show all flags (rule violations, fraud flags, duplicate matches, three-way-match mismatches) clearly,
     each with its severity and explanation — this is the trust-building UI, do not bury flags in a tab
   - Approve / Flag / Confirm-Duplicate action buttons calling the review endpoint

4. /documents page — searchable/filterable list of all documents, any status

5. Conditionally render nav items (Rules, Ask AI, Reports) based on GET /system/tier response — features
   not in the current tier should not appear in navigation at all, not just be disabled/greyed out.

Use TanStack Query for all data fetching/caching/polling. Use Tailwind for styling. No inline styles.

Acceptance criteria: full upload → live progress → review → correct/approve flow works end to end against
the real backend, with zero console errors.
```

---

## PROMPT 15 — Frontend: Rules Config Panel + NL Query Chat

```
Build the Standard/Premium-only frontend panels — only render if feature_enabled from GET /system/tier.

Requirements:

1. /rules page (rules_engine feature):
   - List existing rules with active/inactive toggle
   - Rule builder UI: form-based condition builder (field dropdown, operator dropdown, value input, add
     AND/OR nested condition) — do NOT require the user to hand-write JSON, generate it from the form
   - Preview: show a plain-English rendering of the rule as it's built ("Flag if vendor is new AND invoice
     amount is greater than $5,000") so non-technical admin users can verify correctness before saving

2. /ask page (nl_query feature):
   - Simple chat interface, POST /query on submit
   - Render the natural language answer, plus a collapsible structured data table below it when the response
     includes tabular data
   - Show nl_query_log history in a sidebar (past questions asked, clickable to re-view)

3. /reports page (reporting feature, standard+):
   - Basic aging summary (documents by status, by age bucket) and top-vendor-spend chart, sourced from the
     same query_tools functions built in Prompt 13 — reuse, don't duplicate query logic

Acceptance criteria: on a TIER=basic deployment, these pages/nav items do not exist at all (404 on direct
navigation, not just hidden). On TIER=standard, all three work end to end against the real backend.
```

---

## PROMPT 16 — Testing, Health Checks, CI

```
Finalize production-readiness.

Requirements:

1. GET /health/live — returns 200 if the API process is running, no dependency checks
2. GET /health/ready — checks DB connection AND Redis connection, returns 200 only if both healthy, 503 otherwise
3. Structured JSON logging across api and worker (use structlog or similar) — every log line includes
   request_id/task_id for tracing a document through the full pipeline
4. scripts/verify_system.py — a standalone script that: creates a test user, uploads a synthetic test
   invoice, polls until terminal status, asserts the result, prints pass/fail — this is your one-command
   "is the deployed system actually working" check, use it after every client deploy
5. GitHub Actions CI (.github/workflows/ci.yml): on every push — lint (ruff for Python, eslint for frontend),
   run pytest, run a docker-compose build to confirm images build cleanly. Fail the pipeline on any step failure.
6. Write a top-level README section: "Deploying to a new client" — env vars to set, how to choose TIER,
   how to run verify_system.py post-deploy.

Acceptance criteria: CI pipeline passes on a clean clone, verify_system.py exits 0 against a fresh
docker-compose stack.
```

---

## PROMPT 17 — Synthetic Invoice Generator (Demo Data)

```
Build scripts/generate_synthetic_invoices.py — produces realistic fake invoice PDFs/images for demos and
testing, with zero real client data ever required.

Requirements:
- Use reportlab or similar to generate PDF invoices with randomized but realistic vendor names, invoice
  numbers, line items, tax rates, currencies
- Generate variety deliberately: some typed/clean PDFs, some rendered-then-rescanned-with-noise to simulate
  scanned documents, different field-label conventions ("Invoice #" vs "Ref#" vs "Bill No.")
- Include a --scenario flag supporting: "clean" (normal invoices), "duplicate" (generates a near-identical
  pair with a slightly altered OCR-plausible amount), "fraud_bank_change" (generates a vendor with a recent
  bank detail change followed by a high invoice), "missing_field" (invoice with a deliberately unreadable/
  missing critical field)
- Output to a local ./demo_invoices/ folder, ready to drag into the upload UI

Acceptance criteria: running `python generate_synthetic_invoices.py --scenario duplicate` produces two files
that correctly trigger the duplicate detector when both are uploaded through the real pipeline.
```

---

## PROMPT 18 — Client Handover Package

```
Prepare the deployment/handover documentation for delivering a finished instance to a paying client.

Requirements:
- docs/DEPLOY.md: step-by-step Railway deployment guide — create project, add Postgres/Redis plugins, set
  environment variables (list every required var and what it should be), set TIER to the purchased package,
  deploy api/worker/beat/frontend services, run initial migration + seed admin user, run verify_system.py
  against the live URL to confirm a healthy deploy
- docs/CLIENT_HANDOVER.md: plain-language doc for the client's own IT/ops person — how to rotate the JWT
  secret, how to add/remove users, how to update their own API keys (Groq/Gemini) if they hit rate limits
  or want to switch providers, how to read the audit_log if their auditor asks for it
- .env.example fully documented with inline comments explaining what each variable does and where to get it

Acceptance criteria: someone with no prior context on this project can follow DEPLOY.md alone and reach a
working, verified deployment.
```

---

## Build Order Summary

| Order | Prompt | Depends On |
|---|---|---|
| 0 | Scaffolding | — |
| 1 | Docker infra | 0 |
| 2 | DB schema | 1 |
| 3 | Auth | 2 |
| 4 | Tier config | 3 |
| 5 | Ingestion | 4 |
| 6 | OCR | 5 |
| 7 | Extraction (LangGraph) | 6 |
| 8 | Validation + duplicates | 7 |
| 9 | Rules engine | 8 |
| 10 | Fraud detection | 9 |
| 11 | Three-way match | 10 |
| 12 | Chain assembly + routing | 11 |
| 13 | NL query agent | 12 |
| 14 | Frontend core | 12 |
| 15 | Frontend tier panels | 13, 14 |
| 16 | Testing/CI | 15 |
| 17 | Synthetic data | 16 |
| 18 | Handover docs | 17 |

Run `scripts/verify_system.py` after Prompt 16 and again after your first real client deploy — it's your single source of truth that the system actually works, not just that it built.
