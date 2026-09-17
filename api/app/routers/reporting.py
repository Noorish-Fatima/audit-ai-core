from fastapi import APIRouter, Depends
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/health", include_in_schema=False)
async def reporting_health():
    return {"status": "ok", "service": "reporting"}


@router.post("", status_code=201)
async def create_report(current_user=Depends(get_current_user)):
    return {"message": "Create report endpoint - not implemented yet"}


@router.get("/{report_id}")
async def get_report(report_id: str, current_user=Depends(get_current_user)):
    return {"message": "Get report endpoint - not implemented yet", "report_id": report_id}


@router.get("")
async def list_reports(current_user=Depends(get_current_user)):
    return {"message": "List reports endpoint - not implemented yet"}