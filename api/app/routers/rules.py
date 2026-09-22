from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.dependencies.auth import get_current_user, require_role
from app.models.user import User, UserRole
from app.models.rule import Rule, RuleSeverity
from app.tier_config.tiers import verify_feature

router = APIRouter(prefix="/rules", tags=["rules"])

# --- Schemas ---

class RuleCondition(BaseModel):
    field: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[Any] = None
    and_: Optional[List["RuleCondition"]] = Field(None, alias="and")
    or_: Optional[List["RuleCondition"]] = Field(None, alias="or")

    class Config:
        populate_by_name = True

class RuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    condition: RuleCondition
    severity: RuleSeverity = RuleSeverity.medium

class RuleUpdate(BaseModel):
    description: Optional[str] = None
    condition: Optional[RuleCondition] = None
    severity: Optional[RuleSeverity] = None
    active: Optional[bool] = None

# --- Endpoints ---

@router.get("/health", include_in_schema=False)
async def rules_health():
    return {"status": "ok", "service": "rules"}

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(verify_feature("rules_engine")),
        Depends(require_role(UserRole.admin, UserRole.approver))
    ]
)
async def create_rule(
    rule_in: RuleCreate,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user)
):
    # Check for duplicate name
    existing = await db.execute(select(Rule).where(Rule.name == rule_in.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Rule with this name already exists")

    new_rule = Rule(
        name=rule_in.name,
        description=rule_in.description,
        condition=rule_in.condition.model_dump(by_alias=True, exclude_none=True),
        severity=rule_in.severity,
        created_by=current_user.id,
        active=True
    )
    db.add(new_rule)
    await db.commit()
    await db.refresh(new_rule)
    return new_rule

@router.get(
    "",
    dependencies=[
        Depends(verify_feature("rules_engine")),
        Depends(require_role(UserRole.admin, UserRole.approver))
    ]
)
async def list_rules(
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user)
):
    result = await db.execute(select(Rule).where(Rule.active == True))
    return result.scalars().all()

@router.get(
    "/{rule_id}",
    dependencies=[
        Depends(verify_feature("rules_engine")),
        Depends(require_role(UserRole.admin, UserRole.approver))
    ]
)
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user)
):
    rule = await db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule

@router.patch(
    "/{rule_id}",
    dependencies=[
        Depends(verify_feature("rules_engine")),
        Depends(require_role(UserRole.admin, UserRole.approver))
    ]
)
async def update_rule(
    rule_id: str,
    rule_in: RuleUpdate,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user)
):
    rule = await db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    update_data = rule_in.model_dump(exclude_unset=True)
    if "condition" in update_data and update_data["condition"]:
        # Ensure we use alias for JSONB storage
        update_data["condition"] = rule_in.condition.model_dump(by_alias=True, exclude_none=True)

    for key, value in update_data.items():
        setattr(rule, key, value)

    await db.commit()
    await db.refresh(rule)
    return rule

@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(verify_feature("rules_engine")),
        Depends(require_role(UserRole.admin, UserRole.approver))
    ]
)
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user)
):
    rule = await db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Soft delete
    rule.active = False
    await db.commit()
    return None
