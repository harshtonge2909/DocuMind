# =============================================================================
# DocuMind — API Routes: Payments
# Razorpay integration for Pro/Enterprise plans
# =============================================================================

import structlog
import razorpay
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.rate_limiter import set_user_tier

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments (Razorpay)"])

try:
    razorpay_client = razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )
except Exception as e:
    logger.error("Failed to initialize Razorpay client", error=str(e))
    razorpay_client = None

class CreateOrderRequest(BaseModel):
    plan_name: str
    amount: int  # Amount in INR (e.g. 499)

class CreateOrderResponse(BaseModel):
    order_id: str
    currency: str = "INR"
    amount: int  # Amount in paise

class PaymentVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_name: str  # For updating tier

@router.post("/create-order", response_model=CreateOrderResponse)
async def create_order(
    request: CreateOrderRequest,
    x_user_id: str = Header("anonymous"),
):
    """Create a new Razorpay order for the specified plan."""
    if not razorpay_client:
        raise HTTPException(status_code=500, detail="Razorpay is not configured.")

    amount_in_paise = request.amount * 100
    
    data = {
        "amount": amount_in_paise,
        "currency": "INR",
        "receipt": f"receipt_{x_user_id}_{request.plan_name}",
        "notes": {
            "user_id": x_user_id,
            "plan_name": request.plan_name
        }
    }
    
    try:
        order = razorpay_client.order.create(data=data)
        logger.info("Razorpay order created", order_id=order["id"], user_id=x_user_id)
        
        return CreateOrderResponse(
            order_id=order["id"],
            amount=amount_in_paise
        )
    except Exception as e:
        logger.error("Failed to create Razorpay order", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to create order")

@router.post("/verify")
async def verify_payment(
    request: PaymentVerifyRequest,
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """Verify Razorpay payment signature and upgrade user tier."""
    if not razorpay_client:
        raise HTTPException(status_code=500, detail="Razorpay is not configured.")
        
    try:
        # Verify the payment signature
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': request.razorpay_order_id,
            'razorpay_payment_id': request.razorpay_payment_id,
            'razorpay_signature': request.razorpay_signature
        })
        
        logger.info("Payment verified successfully", user_id=x_user_id, plan=request.plan_name)
        
        # Upgrade the user's tier
        # Ensure we map plan names like "Pro" to backend expected "pro"
        normalized_tier = request.plan_name.lower()
        if normalized_tier not in ["pro", "enterprise"]:
            normalized_tier = "pro"
            
        await set_user_tier(x_user_id, normalized_tier, db)
        
        return {"status": "success", "message": f"Successfully upgraded to {request.plan_name}"}
        
    except razorpay.errors.SignatureVerificationError:
        logger.warning("Invalid payment signature detected", user_id=x_user_id)
        raise HTTPException(status_code=400, detail="Invalid payment signature")
    except Exception as e:
        logger.error("Error during payment verification", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error during verification")
