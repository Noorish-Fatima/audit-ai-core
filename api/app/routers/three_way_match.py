from fastapi import APIRouter, Depends
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/three-way-match", tags=["three-way-match"])


@router.get("/health", include_in_schema=False)
async def three_way_match_health():
    return {"status": "ok", "service": "three-way-match"}


@router.post("", status_code=201)
async def create_match(current_user=Depends(get_current_user)):
    return {"message": "Three-way match endpoint - not implemented yet"}


@router.get("/{match_id}")
async def get_match(match_id: str, current_user=Depends(get_current_user)):
    return {"message": "Get match endpoint - not implemented yet", "match_id": match_id}


@router.get("")
async def list_matches(current_user=Depends(get_current_user)):
    return {"message": "List matches endpoint - not implemented yet"}