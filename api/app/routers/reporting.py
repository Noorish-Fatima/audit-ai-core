from fastapi import APIRouter, Depends
from app.dependencies.auth import get_current_user
from app.tier_config.tiers import verify_feature

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/health", include_in_schema=False)
async def reporting_health():
    return {"status": "ok", "service": "reporting"}


@router.post("", status_code=201, dependencies=[Depends(verify_feature("reporting"))])
async def create_report(current_user=Depends(get_current_user)):
    return {"message": "Create report endpoint - not implemented yet"}


@router.get("/{report_id}", dependencies=[Depends(verify_feature("reporting"))])
async def get_report(report_id: str, current_user=Depends(get_current_user)):
    return {"message": "Get report endpoint - not implemented yet", "report_id": report_id}


@router.get("", dependencies=[Depends(verify_feature("reporting"))])
async def list_reports(current_user=Depends(get_current_user)):
    return {"message": "List reports endpoint - not implemented yet"}