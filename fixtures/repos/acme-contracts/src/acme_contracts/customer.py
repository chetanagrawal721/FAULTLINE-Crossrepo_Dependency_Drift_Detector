"""The customer request that orders-svc sends and billing-svc parses (scenario J)."""
from typing import Optional

from pydantic import BaseModel


class CustomerRequest(BaseModel):
    customer_id: int
    email: str
    middle_name: Optional[str]         # no default: optional in pydantic 1, required in pydantic 2


class LoyaltyNote(BaseModel):
    """Negative control: every field has a default, so both pydantic versions accept the same payloads."""
    note: Optional[str] = None
    points: int = 0
