# Audit-AI

Document Intelligence Platform - A monorepo for processing, analyzing, and extracting insights from documents using AI.

## Folder Structure

```
audit-ai/
├── api/                    # FastAPI backend service
│   ├── app/
│   │   ├── main.py         # FastAPI application entry point
│   │   ├── config.py       # Pydantic settings configuration
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic request/response schemas
│   │   ├── routers/        # API route handlers
│   │   ├── services/       # Business logic services
│   │   ├── agents/         # LangGraph subgraphs for AI agents
│   │   └── db/             # Database session and initialization
│   ├── alembic/            # Database migrations
│   ├── tests/              # API tests
│   ├── Dockerfile          # API container definition
│   └── requirements.txt    # Python dependencies (pinned)
├── worker/                 # Celery worker service
│   ├── celery_app.py       # Celery application configuration
│   ├── tasks/              # Celery task definitions
│   └── Dockerfile          # Worker container definition
├── frontend/               # Next.js 14 frontend (Pages Router, TypeScript strict)
│   ├── pages/              # Next.js pages and API routes
│   ├── components/         # React components
│   ├── hooks/              # Custom React hooks
│   ├── lib/                # Utility libraries
│   └── Dockerfile          # Frontend container definition
├── scripts/                # Utility scripts
│   ├── generate_synthetic_invoices.py
│   └── verify_system.py
├── docker-compose.yml      # Multi-service orchestration
├── .env.example            # Environment variables template
└── README.md               # This file
```

## Quick Start

### Prerequisites

- Docker and Docker Compose (v2.0+)
- Git

### Running with Docker Compose

1. **Clone and navigate to the project:**
   ```bash
   cd audit-ai
   ```

2. **Copy environment template:**
   ```bash
   cp .env.example .env
   ```

3. **Start all services:**
   ```bash
   docker-compose up --build
   ```

4. **Verify services are running:**
   - API: http://localhost:8000/health
   - API Docs (Swagger): http://localhost:8000/docs
   - Frontend: http://localhost:3000
   - Frontend Health: http://localhost:3000/api/health

5. **Stop services:**
   ```bash
   docker-compose down
   ```

   To remove volumes (database data):
   ```bash
   docker-compose down -v
   ```

### Service Health Endpoints

All services expose health check endpoints that return `200 OK` with JSON status:

| Service | Endpoint | Expected Response |
|---------|----------|-------------------|
| API | `GET /health` | `{"status": "ok", "service": "api", "version": "0.1.0"}` |
| API | `GET /health/ready` | `{"status": "ready", "service": "api"}` |
| API | `GET /health/live` | `{"status": "alive", "service": "api"}` |
| Frontend | `GET /api/health` | `{"status": "ok", "service": "frontend", "timestamp": "..."}` |
| Worker | Celery ping | `pong` |

## Development

### API Development

The API service uses FastAPI with async SQLAlchemy. Code changes are hot-reloaded via volume mounts.

```bash
# View API logs
docker-compose logs -f api

# Run database migrations
docker-compose exec api alembic upgrade head

# Create a new migration
docker-compose exec api alembic revision --autogenerate -m "description"

# Run tests
docker-compose exec api pytest
```

### Worker Development

The worker shares the API codebase via volume mount.

```bash
# View worker logs
docker-compose logs -f worker
```

### Frontend Development

The frontend uses Next.js 14 with Pages Router and strict TypeScript.

```bash
# View frontend logs
docker-compose logs -f frontend

# For local development without Docker:
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
# API tests
docker-compose exec api pytest -v

# Frontend type checking
docker-compose exec frontend npm run type-check

# Frontend linting
docker-compose exec frontend npm run lint
```

## Technology Stack

### Backend (API)
- **Python 3.11**
- **FastAPI 0.115** - Modern, fast web framework
- **Pydantic v2** - Data validation and settings management
- **SQLAlchemy 2.0 (async)** - Async ORM
- **Alembic** - Database migrations
- **PostgreSQL 16** - Primary database
- **Redis 7** - Caching and Celery broker
- **Celery 5.4** - Distributed task queue
- **LangGraph 0.2** - AI agent workflows
- **uv/pip-tools** - Dependency pinning

### Frontend
- **Node 20**
- **Next.js 14** - React framework (Pages Router)
- **TypeScript 5.5** - Strict mode enabled
- **React 18** - UI library
- **SWR** - Data fetching
- **Axios** - HTTP client
- **ESLint** - Linting

### Infrastructure
- **Docker** - Containerization
- **Docker Compose** - Service orchestration
- **PostgreSQL** - Persistent storage
- **Redis** - Message broker and cache

## Environment Variables

See `.env.example` for all configurable options. Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@db:5432/audit_ai` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379/0` |
| `CELERY_BROKER_URL` | Celery broker URL | `redis://redis:6379/1` |
| `SECRET_KEY` | JWT secret key | **Change in production!** |
| `DEBUG` | Enable debug mode | `true` |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:3000,http://frontend:3000` |

## Scripts

### Generate Synthetic Invoices
```bash
docker-compose run --rm api python scripts/generate_synthetic_invoices.py
```

### Verify System
```bash
docker-compose run --rm api python scripts/verify_system.py
```

## API Endpoints (Placeholder)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/health/ready` | Readiness check |
| GET | `/health/live` | Liveness check |
| POST | `/api/v1/documents` | Create document (stub) |
| GET | `/api/v1/documents/{id}` | Get document (stub) |
| GET | `/api/v1/documents` | List documents (stub) |
| POST | `/api/v1/analysis/{id}/start` | Start analysis (stub) |
| GET | `/api/v1/analysis/{id}/status` | Analysis status (stub) |
| GET | `/api/v1/analysis/{id}/result` | Analysis result (stub) |
| POST | `/api/v1/webhooks/documents/{id}/callback` | Document webhook (stub) |
| POST | `/api/v1/webhooks/analysis/{id}/callback` | Analysis webhook (stub) |

## License

MIT License - See LICENSE file for details.