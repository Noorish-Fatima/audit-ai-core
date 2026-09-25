from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.dependencies.auth import get_current_user
from app.tier_config.tiers import verify_feature
from app.agents.nl_query_graph import run_nl_query
from app.models.user import User

router = APIRouter(prefix="/nl-query", tags=["nl-query"])


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    structured_data: dict | None
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
async def get_nl_query(query_id: str, current_user=Depends(get_current_user)):
    return {"message": "Get NL query endpoint - not implemented yet", "query_id": query_id}


@router.get("", dependencies=[Depends(verify_feature("nl_query"))])
async def list_nl_queries(current_user=Depends(get_current_user)):
    return {"message": "List NL queries endpoint - not implemented yet"}