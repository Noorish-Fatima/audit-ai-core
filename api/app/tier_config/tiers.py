from typing import Dict, Any
from fastapi import FastAPI, APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.config import settings

VALID_TIERS = {"basic", "standard", "premium"}

TIER = settings.TIER.lower()
if TIER not in VALID_TIERS:
    raise ValueError(
        f"Invalid TIER: '{TIER}'. Must be one of: {', '.join(sorted(VALID_TIERS))}"
    )

FEATURES: Dict[str, Dict[str, bool]] = {
    "basic": {
        "rules_engine": False,
        "nl_query": False,
        "fraud_detection": False,
        "three_way_match": False,
        "approval_routing": False,
        "reporting": False,
    },
    "standard": {
        "rules_engine": True,
        "nl_query": True,
        "fraud_detection": True,
        "three_way_match": False,
        "approval_routing": False,
        "reporting": True,
    },
    "premium": {
        "rules_engine": True,
        "nl_query": True,
        "fraud_detection": True,
        "three_way_match": True,
        "approval_routing": True,
        "reporting": True,
    },
}


def feature_enabled(name: str) -> bool:
    """Check if a feature is enabled for the current tier."""
    return FEATURES[TIER].get(name, False)


def verify_feature(feature_name: str):
    """
    FastAPI dependency to verify if a feature is enabled.
    Raises HTTPException if the feature is not available in the current tier.
    """
    def dependency():
        if not feature_enabled(feature_name):
            raise HTTPException(
                status_code=403,
                detail=f"Feature '{feature_name}' is not available in the current tier ({TIER}). Please upgrade your plan."
            )
    return dependency


def get_tier_info() -> Dict[str, Any]:
    """Get tier info for /system/tier endpoint."""
    return {"tier": TIER, "features": FEATURES[TIER]}


tier_router = APIRouter(prefix="/system", tags=["system"])


@tier_router.get("/tier")
async def get_tier():
    return get_tier_info()


def register_tier_routes(app: FastAPI) -> None:
    app.include_router(tier_router)