from fastapi import APIRouter, Depends
from app.dependencies.auth import get_current_user
from app.tier_config.tiers import verify_feature

router = APIRouter(prefix="/nl-query", tags=["nl-query"])


@router.get("/health", include_in_schema=False)
async def nl_query_health():
    return {"status": "ok", "service": "nl-query"}


@router.post("", status_code=201, dependencies=[Depends(verify_feature("nl_query"))])
async def create_nl_query(current_user=Depends(get_current_user)):
    return {"message": "Natural language query endpoint - not implemented yet"}


@router.get("/{query_id}", dependencies=[Depends(verify_feature("nl_query"))])
async def get_nl_query(query_id: str, current_user=Depends(get_current_user)):
    return {"message": "Get NL query endpoint - not implemented yet", "query_id": query_id}


@router.get("", dependencies=[Depends(verify_feature("nl_query"))])
async def list_nl_queries(current_user=Depends(get_current_user)):
    return {"message": "List NL queries endpoint - not implemented yet"}