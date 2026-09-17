from fastapi import APIRouter, Depends
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/fraud", tags=["fraud"])


@router.get("/health", include_in_schema=False)
async def fraud_health():
    return {"status": "ok", "service": "fraud"}


@router.post("", status_code=201)
async def create_fraud_check(current_user=Depends(get_current_user)):
    return {"message": "Fraud detection endpoint - not implemented yet"}


@router.get("/{check_id}")
async def get_fraud_check(check_id: str, current_user=Depends(get_current_user)):
    return {"message": "Get fraud check endpoint - not implemented yet", "check_id": check_id}


@router.get("")
async def list_fraud_checks(current_user=Depends(get_current_user)):
    return {"message": "List fraud checks endpoint - not implemented yet"}