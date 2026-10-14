"""The customer request that one service sends and another parses."""
from typing import Optional

from pydantic import BaseModel


class CustomerRequest(BaseModel):
    customer_id: int
    email: str
    middle_name: Optional[str]         # no default: optional in pydantic 1, required in pydantic 2


class LoyaltyNote(BaseModel):
    """Every field has a default, so both pydantic versions accept the same payloads: it must never be reported."""
    note: Optional[str] = None
    points: int = 0
