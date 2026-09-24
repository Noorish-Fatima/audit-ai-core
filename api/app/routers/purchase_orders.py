from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.dependencies.auth import get_current_user, require_role
from app.models.user import User, UserRole
from app.models.purchase_order import PurchaseOrder, GoodsReceipt
from app.models.vendor import Vendor
from app.tier_config.tiers import verify_feature

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


class LineItemCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    total: Optional[Decimal] = None


class PurchaseOrderCreate(BaseModel):
    po_number: str = Field(..., min_length=1, max_length=100)
    vendor_id: str
    expected_amount: Decimal = Field(..., gt=0)
    line_items: List[LineItemCreate] = Field(default_factory=list)


class PurchaseOrderResponse(BaseModel):
    id: str
    po_number: str
    vendor_id: str
    expected_amount: Decimal
    line_items: List[dict]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GoodsReceiptCreate(BaseModel):
    po_id: str
    received_amount: Decimal = Field(..., gt=0)
    received_at: datetime


class GoodsReceiptResponse(BaseModel):
    id: str
    po_id: str
    received_amount: Decimal
    received_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/health", include_in_schema=False)
async def purchase_orders_health():
    return {"status": "ok", "service": "purchase-orders"}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(verify_feature("three_way_match")),
        Depends(require_role(UserRole.admin, UserRole.approver))
    ],
    response_model=PurchaseOrderResponse
)
async def create_purchase_order(
    po_in: PurchaseOrderCreate,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user)
):
    vendor = await db.get(Vendor, po_in.vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    existing = await db.execute(
        select(PurchaseOrder).where(PurchaseOrder.po_number == po_in.po_number)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="PO with this number already exists")

    new_po = PurchaseOrder(
        po_number=po_in.po_number,
        vendor_id=po_in.vendor_id,
        expected_amount=po_in.expected_amount,
        line_items=[item.model_dump() for item in po_in.line_items]
    )
    db.add(new_po)
    await db.commit()
    await db.refresh(new_po)
    return new_po


@router.get(
    "",
    dependencies=[
        Depends(verify_feature("three_way_match")),
        Depends(require_role(UserRole.admin, UserRole.approver))
    ],
    response_model=List[PurchaseOrderResponse]
)
async def list_purchase_orders(
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user)
):
    result = await db.execute(
        select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
    )
    return result.scalars().all()


@router.get(
    "/{po_id}",
    dependencies=[
        Depends(verify_feature("three_way_match")),
        Depends(require_role(UserRole.admin, UserRole.approver))
    ],
    response_model=PurchaseOrderResponse
)
async def get_purchase_order(
    po_id: str,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user)
):
    po = await db.get(PurchaseOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return po


@router.post(
    "/goods-receipts",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(verify_feature("three_way_match")),
        Depends(require_role(UserRole.admin, UserRole.approver))
    ],
    response_model=GoodsReceiptResponse
)
async def create_goods_receipt(
    receipt_in: GoodsReceiptCreate,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user)
):
    po = await db.get(PurchaseOrder, receipt_in.po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    new_receipt = GoodsReceipt(
        po_id=receipt_in.po_id,
        received_amount=receipt_in.received_amount,
        received_at=receipt_in.received_at
    )
    db.add(new_receipt)
    await db.commit()
    await db.refresh(new_receipt)
    return new_receipt


@router.get(
    "/{po_id}/goods-receipts",
    dependencies=[
        Depends(verify_feature("three_way_match")),
        Depends(require_role(UserRole.admin, UserRole.approver))
    ],
    response_model=List[GoodsReceiptResponse]
)
async def list_goods_receipts(
    po_id: str,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user)
):
    po = await db.get(PurchaseOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    result = await db.execute(
        select(GoodsReceipt)
        .where(GoodsReceipt.po_id == po_id)
        .order_by(GoodsReceipt.received_at.desc())
    )
    return result.scalars().all()