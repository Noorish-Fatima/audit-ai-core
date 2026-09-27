from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db.session import get_session
from app.dependencies.auth import get_current_user
from app.tier_config.tiers import verify_feature
from app.agents.nl_query_graph import run_nl_query
from app.models.user import User

router = APIRouter(prefix="/nl-query", tags=["nl-query"])


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    # Tabular answers come back as a list of rows; scalar answers as a dict.
    structured_data: dict | list | None
    intent: str
    error: str | None


@router.get("/health", include_in_schema=False)
async def nl_query_health():
    return {"status": "ok", "service": "nl-query"}


@router.post(
    "/query",
    response_model=QueryResponse,
    dependencies=[Depends(verify_feature("nl_query"))]
)
async def query_nl(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Process a natural language question and return a structured answer.
    """
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    result = await run_nl_query(request.question.strip(), current_user.id)
    
    return QueryResponse(**result)


@router.get("/{query_id}", dependencies=[Depends(verify_feature("nl_query"))])
async def get_nl_query(
    query_id: str,
    db = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Re-view a past NL query (own history only)."""
    from sqlalchemy import select
    from app.models.query_log import NLQueryLog

    log = await db.get(NLQueryLog, query_id)
    if not log or (log.user_id and str(log.user_id) != str(current_user.id)):
        raise HTTPException(status_code=404, detail="Query not found")
    return {
        "id": str(log.id),
        "question": log.question_text,
        "answer": log.response_text,
        "intent": log.resolved_intent,
        "tool_called": log.tool_called,
        "tool_args": log.tool_args,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("", dependencies=[Depends(verify_feature("nl_query"))])
async def list_nl_queries(
    db = Depends(get_session),
    current_user=Depends(get_current_user),
    limit: int = 20,
):
    """List the current user's recent NL queries for the history sidebar."""
    from sqlalchemy import select, desc
    from app.models.query_log import NLQueryLog

    result = await db.execute(
        select(NLQueryLog)
        .where(NLQueryLog.user_id == current_user.id)
        .order_by(desc(NLQueryLog.created_at))
        .limit(min(limit, 50))
    )
    logs = result.scalars().all()
    return [
        {
            "id": str(log.id),
            "question": log.question_text,
            "answer": log.response_text,
            "intent": log.resolved_intent,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]