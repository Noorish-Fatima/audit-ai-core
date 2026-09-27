from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.dependencies.auth import get_current_user
from app.tier_config.tiers import verify_feature
from app.services import query_tools

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/health", include_in_schema=False)
async def reporting_health():
    return {"status": "ok", "service": "reporting"}


@router.get("/summary", dependencies=[Depends(verify_feature("reporting"))])
async def get_reporting_summary(
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
    days: int = Query(90, ge=1, le=365, description="Lookback window in days"),
    top_vendors_limit: int = Query(10, ge=1, le=25),
):
    """Reports dashboard data: aging summary + top vendors by spend.

    Reuses the shared query_tools functions (same code path as NL query).
    """
    today = date.today()
    date_from = today - timedelta(days=days)

    aging = await query_tools.get_aging_summary(db)
    top_vendors = await query_tools.get_top_vendors_by_spend(
        db, date_from, today, limit=top_vendors_limit
    )

    return {
        "window_days": days,
        "aging": aging,
        "top_vendors": [
            {"vendor": v["vendor"], "total_spend": v["total_spend"]}
            for v in top_vendors
        ],
    }


@router.get("/{report_id}", dependencies=[Depends(verify_feature("reporting"))])
async def get_report(report_id: str, current_user=Depends(get_current_user)):
    return {"message": "Get report endpoint - not implemented yet", "report_id": report_id}


@router.get("", dependencies=[Depends(verify_feature("reporting"))])
async def list_reports(current_user=Depends(get_current_user)):
    return {"message": "List reports endpoint - not implemented yet"}