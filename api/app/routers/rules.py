from fastapi import APIRouter, Depends
from app.dependencies.auth import get_current_user
from app.tier_config.tiers import verify_feature

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("/health", include_in_schema=False)
async def rules_health():
    return {"status": "ok", "service": "rules"}


@router.post("", status_code=201, dependencies=[Depends(verify_feature("rules_engine"))])
async def create_rule(current_user=Depends(get_current_user)):
    return {"message": "Create rule endpoint - not implemented yet"}


@router.get("/{rule_id}", dependencies=[Depends(verify_feature("rules_engine"))])
async def get_rule(rule_id: str, current_user=Depends(get_current_user)):
    return {"message": "Get rule endpoint - not implemented yet", "rule_id": rule_id}


@router.get("", dependencies=[Depends(verify_feature("rules_engine"))])
async def list_rules(current_user=Depends(get_current_user)):
    return {"message": "List rules endpoint - not implemented yet"}