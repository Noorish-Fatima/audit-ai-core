from fastapi import APIRouter, Depends
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/approval-routing", tags=["approval-routing"])


@router.get("/health", include_in_schema=False)
async def approval_routing_health():
    return {"status": "ok", "service": "approval-routing"}


@router.post("", status_code=201)
async def create_approval(current_user=Depends(get_current_user)):
    return {"message": "Approval routing endpoint - not implemented yet"}


@router.get("/{approval_id}")
async def get_approval(approval_id: str, current_user=Depends(get_current_user)):
    return {"message": "Get approval endpoint - not implemented yet", "approval_id": approval_id}


@router.get("")
async def list_approvals(current_user=Depends(get_current_user)):
    return {"message": "List approvals endpoint - not implemented yet"}